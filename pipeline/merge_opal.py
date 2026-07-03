#!/usr/bin/env python3
"""Merge + clean Opal Patronage daily files into a fact table, with DQ stats."""
import glob, io, json, os, sys
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT, exist_ok=True)

EXPECTED_HEADER = "trip_origin_date|mode_name|ti_region|tap_hour|Tap_Ons|Tap_Offs"

files = sorted(glob.glob(os.path.join(RAW, "Opal_Patronage_*.txt")))
print(f"files: {len(files)}")

chunks, bad_schema, empty_files = [], [], []
for fp in files:
    with open(fp, "r", encoding="utf-8-sig") as f:
        text = f.read()
    lines = text.strip().split("\n")
    header = lines[0].strip()
    if header != EXPECTED_HEADER:
        bad_schema.append((os.path.basename(fp), header[:80]))
        continue
    if len(lines) < 2:
        empty_files.append(os.path.basename(fp))
        continue
    chunks.append("\n".join(lines[1:]))

df = pd.read_csv(
    io.StringIO("\n".join(chunks)), sep="|",
    names=["date", "mode", "region", "hour", "tap_ons_raw", "tap_offs_raw"],
    dtype={"date": str, "mode": str, "region": str, "hour": int,
           "tap_ons_raw": str, "tap_offs_raw": str},
)
print(f"rows: {len(df):,}")

df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")

def parse(col):
    s = df[col].str.strip()
    thr = s.map({"<50": 50, "<100": 100})   # NaN = not masked
    masked = thr.notna()
    num = pd.to_numeric(s.where(~masked), errors="coerce")
    return masked, num, thr

ons_masked, ons, ons_thr = parse("tap_ons_raw")
offs_masked, offs, offs_thr = parse("tap_offs_raw")
df["ons_masked"] = ons_masked
df["offs_masked"] = offs_masked
df["mask_threshold"] = ons_thr.fillna(offs_thr)  # 50 / 100 / NaN
df["tap_ons"] = ons        # NaN where masked
df["tap_offs"] = offs
# midpoint imputation: half the applicable masking threshold
df["tap_ons_mid"] = df["tap_ons"].fillna(ons_thr / 2)
df["tap_offs_mid"] = df["tap_offs"].fillna(offs_thr / 2)

df["is_aggregate"] = df["region"].isin(["All - NSW"])
df["is_other"] = df["region"] == "Other"
df["dow"] = df["date"].dt.dayofweek  # 0=Mon
df["day_name"] = df["date"].dt.day_name()
df["is_weekend"] = df["dow"] >= 5

# unparseable numeric check (values that are neither numbers nor <100)
bad_ons = df[~df["ons_masked"] & df["tap_ons"].isna()]
bad_offs = df[~df["offs_masked"] & df["tap_offs"].isna()]

# duplicates check
dups = df.duplicated(subset=["date", "mode", "region", "hour"]).sum()

# date coverage
all_days = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
present = set(df["date"].dt.normalize().unique())
missing_days = [d.strftime("%Y-%m-%d") for d in all_days if d not in present]

# masked share by region (fact rows only)
fact = df[~df["is_aggregate"]].copy()
masked_by_region = (fact.groupby("region")["ons_masked"].mean().sort_values(ascending=False) * 100).round(1)
masked_by_mode = (fact.groupby("mode")["ons_masked"].mean().sort_values(ascending=False) * 100).round(1)
masked_overall = fact["ons_masked"].mean() * 100

# internal consistency: does sum of regions (mid imputation) roughly match All - NSW?
agg = df[df["is_aggregate"]].groupby(["date", "mode", "hour"])["tap_ons_mid"].sum()
parts = fact.groupby(["date", "mode", "hour"])["tap_ons_mid"].sum()
cmp = pd.concat([agg.rename("all_nsw"), parts.rename("sum_regions")], axis=1).dropna()
cmp["ratio"] = cmp["sum_regions"] / cmp["all_nsw"].replace(0, pd.NA)
ratio_desc = cmp["ratio"].describe().round(3).to_dict()

# save fact table (exclude All - NSW rows; keep Other with flag)
fact_out = fact.drop(columns=["is_aggregate"])
fact_out.to_parquet(os.path.join(OUT, "opal_fact.parquet"), index=False)

# daily summary CSV for quick Power BI / sanity use
daily = (fact[~fact["is_other"]]
         .groupby(["date", "day_name", "is_weekend", "mode", "region"], observed=True)
         .agg(tap_ons_mid=("tap_ons_mid", "sum"),
              tap_offs_mid=("tap_offs_mid", "sum"),
              masked_hours=("ons_masked", "sum"),
              hours=("ons_masked", "size"))
         .reset_index())
daily.to_csv(os.path.join(OUT, "opal_daily_summary.csv"), index=False)

stats = {
    "files_read": len(files),
    "bad_schema_files": bad_schema,
    "empty_files": empty_files,
    "rows_total": int(len(df)),
    "rows_fact": int(len(fact)),
    "date_min": str(df['date'].min().date()),
    "date_max": str(df['date'].max().date()),
    "missing_days": missing_days,
    "duplicate_keys": int(dups),
    "unparseable_ons": int(len(bad_ons)),
    "unparseable_offs": int(len(bad_offs)),
    "masked_pct_overall": round(float(masked_overall), 1),
    "mask_threshold_periods": {
        "lt50": [str(df.loc[df['mask_threshold'] == 50, 'date'].min().date()),
                 str(df.loc[df['mask_threshold'] == 50, 'date'].max().date())],
        "lt100": [str(df.loc[df['mask_threshold'] == 100, 'date'].min().date()),
                  str(df.loc[df['mask_threshold'] == 100, 'date'].max().date())],
    },
    "masked_pct_by_region": masked_by_region.to_dict(),
    "masked_pct_by_mode": masked_by_mode.to_dict(),
    "sum_regions_vs_allnsw_ratio": ratio_desc,
    "modes": sorted(df['mode'].unique().tolist()),
    "regions": sorted(df['region'].unique().tolist()),
}
with open(os.path.join(OUT, "dq_stats.json"), "w") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)
print(json.dumps(stats, indent=2, ensure_ascii=False)[:3000])
