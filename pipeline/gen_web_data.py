#!/usr/bin/env python3
"""Pre-aggregate Opal fact table into a compact data.js for the static dashboard."""
import json, os
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "web")
os.makedirs(OUT, exist_ok=True)

df = pd.read_parquet(os.path.join(ROOT, "data", "processed", "opal_fact.parquet"))
d = df[(~df.is_other) & (df["mode"] != "UNKNOWN")].copy()
d["ym"] = d["date"].dt.to_period("M").astype(str)
wd = d[d.dow < 5]

COORDS = {
    "Sydney CBD": (-33.8688, 151.2093), "North Sydney": (-33.8389, 151.2072),
    "Chatswood": (-33.7969, 151.1830), "Macquarie Park": (-33.7772, 151.1243),
    "Parramatta": (-33.8150, 151.0011), "Strathfield": (-33.8712, 151.0938),
    "Newcastle and surrounds": (-32.9283, 151.7817),
    "Wollongong and surrounds": (-34.4278, 150.8931),
}
FLAGGED = {"Wollongong and surrounds": "structural break in bus reporting",
           "Newcastle and surrounds": "recovery indeterminate (52-58% masked)"}

def daily_mean(x):
    return x.groupby("region")["tap_ons_mid"].sum() / x.groupby("region")["date"].nunique()

base = daily_mean(wd[(wd.date >= "2020-02-01") & (wd.date <= "2020-02-28")])
cur = daily_mean(wd[wd.date >= "2026-01-01"])
rec = (cur / base * 100).round(0)

sat = d[d.dow == 5]
sat_rec = (daily_mean(sat[sat.date >= "2026-01-01"]) /
           daily_mean(sat[(sat.date >= "2020-02-01") & (sat.date <= "2020-02-28")]) * 100).round(0)

regions = []
for r in sorted(COORDS):
    regions.append({
        "name": r, "lat": COORDS[r][0], "lon": COORDS[r][1],
        "recovery": rec[r], "satRecovery": sat_rec[r],
        "volume": round(cur[r]), "flag": FLAGGED.get(r),
    })

# monthly weekday recovery lines
m = wd.groupby(["ym", "region"])["tap_ons_mid"].sum().reset_index()
days = wd.groupby(["ym", "region"])["date"].nunique().reset_index(name="n")
m = m.merge(days)
m["v"] = m["tap_ons_mid"] / m["n"]
months = sorted(m["ym"].unique())
monthly = {r: [round(float(m[(m.region == r) & (m.ym == mo)]["v"].iloc[0]) / base[r] * 100, 1)
               if len(m[(m.region == r) & (m.ym == mo)]) else None for mo in months]
           for r in sorted(COORDS)}

# dow pattern 2026 (rel to Tue-Thu)
p = wd[wd.date >= "2026-01-01"].groupby(["region", "dow"])["tap_ons_mid"].sum().unstack()
n = wd[wd.date >= "2026-01-01"].groupby(["region", "dow"])["date"].nunique().unstack()
p = p / n
dow_rel = (p.T / p[[1, 2, 3]].mean(axis=1)).T * 100
dowHeat = {r: [round(dow_rel.loc[r, c], 0) for c in range(5)] for r in dow_rel.index}

# CBD hourly profiles
cbd = d[d.region == "Sydney CBD"]
def prof(a, b):
    s = cbd[(cbd.date >= a) & (cbd.date <= b) & (cbd.dow < 5)]
    return [round(float(v)) for v in (s.groupby("hour")["tap_ons_mid"].sum() / s.date.nunique())]
hourly = {"h2020": prof("2020-02-01", "2020-02-28"), "h2026": prof("2026-01-01", "2026-06-30")}

# CBD evening by dow
ev = cbd[cbd.hour.between(18, 23)]
def evdow(a, b):
    s = ev[(ev.date >= a) & (ev.date <= b)]
    return [round(float(v)) for v in
            (s.groupby(s.date.dt.dayofweek)["tap_ons_mid"].sum() /
             s.groupby(s.date.dt.dayofweek)["date"].nunique())]
evening = {"e2020": evdow("2020-02-01", "2020-02-28"), "e2026": evdow("2026-01-01", "2026-06-30")}

# mode share by year
mix = d.groupby([d.date.dt.year, "mode"])["tap_ons_mid"].sum().unstack().fillna(0)
share = ((mix.T / mix.sum(axis=1)).T * 100).round(1)
modeShare = {"years": [int(y) for y in share.index],
             "modes": {mo: [float(v) for v in share[mo]] for mo in share.columns}}

# CBD quarterly weekend ratio
cq = d[d.region == "Sydney CBD"].copy()
cq["q"] = cq["date"].dt.to_period("Q").astype(str)
g = cq.groupby(["q", "is_weekend"])["tap_ons_mid"].sum().unstack()
gn = cq.groupby(["q", "is_weekend"])["date"].nunique().unstack()
ratio = ((g / gn)[True] / (g / gn)[False] * 100).round(0).dropna()
wkRatio = {"quarters": list(ratio.index), "ratio": [float(v) for v in ratio]}

# Wollongong structural break
w = d[d.region == "Wollongong and surrounds"]
wm = (w.groupby([w.date.dt.year, "mode"])["tap_ons_mid"].sum() / 1e6).round(2).unstack().fillna(0)
woll = {"years": [int(y) for y in wm.index],
        "bus": [float(v) for v in wm["Bus"]], "train": [float(v) for v in wm["Train"]]}

data = {"regions": regions, "months": months, "monthly": monthly, "dowHeat": dowHeat,
        "hourly": hourly, "evening": evening, "modeShare": modeShare,
        "wkRatio": wkRatio, "woll": woll}

with open(os.path.join(OUT, "data.js"), "w") as f:
    f.write("const DATA = " + json.dumps(data, ensure_ascii=False) + ";")
print("data.js written,", os.path.getsize(os.path.join(OUT, 'data.js')) // 1024, "KB")
print("sat vs wd:", {r["name"]: (r["recovery"], r["satRecovery"]) for r in regions})
