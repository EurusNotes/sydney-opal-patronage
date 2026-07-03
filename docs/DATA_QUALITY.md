# Opal Patronage — Data Quality & Processing Notes

**Source:** TfNSW Open Data Hub, Opal Patronage dataset (CC-BY).
**Coverage:** 2020-01-01 → 2026-07-01, 2,372 daily files, 1,610,884 raw rows.
**Grain:** one row = date × mode × region × hour, with tap-ons and tap-offs.

## Pipeline
1. Bulk download via S3 listing with required referrer header (`download_opal.py`), resumable with retry and content validation.
2. Schema check per file (all 2,372 files match the expected header; 0 files rejected).
3. Merge, type, flag and impute (`merge_opal.py`) → `processed/opal_fact.parquet` (fact rows, 1,371,675) and `processed/opal_daily_summary.csv`.

## Known issues and how they are handled

### 1. Privacy masking, with a mid-series threshold change
Small counts are suppressed at source. **The threshold changed on 2024-07-01: values below 50 are masked as `<50` up to 2024-06-30, and values below 100 as `<100` from 2024-07-01.** Overall 27.4% of hourly cells are masked, concentrated in off-peak hours and smaller regions (Newcastle 63%, Wollongong 39%, Sydney CBD only 9.5%; the residual UNKNOWN mode is 83% masked).

Handling: raw strings preserved (`tap_ons_raw`); boolean flags (`ons_masked`, `offs_masked`); `mask_threshold` column (50/100); numeric columns keep NaN for masked cells; convenience columns `tap_*_mid` impute the midpoint (threshold/2). Daily/regional aggregates are dominated by unmasked peak-hour values, so imputation choice moves daily totals by well under 1% for major regions; hourly analysis of small regions at night should not be attempted.

Implication of the threshold change: masked cells carry different information before and after 2024-07-01. Any metric sensitive to small values must not compare across that boundary without noting it.

### 2. Missing days
2021-06-03 and 2021-06-04 are header-only at source (confirmed server-side, not a download failure). All other 2,372 days present. No duplicate keys.

### 3. Aggregate and residual rows
`All - NSW` is a pre-aggregated total (excluded from the fact table). `Other` is a residual region (kept, flagged `is_other`). Cross-check: sum of regional values (midpoint-imputed) vs `All - NSW` has median ratio 1.003; the right tail (max 9.0) occurs in low-volume hours where imputation dominates — expected behaviour, not a data defect.

### 4. Structural break: Wollongong bus volumes (treat recovery figure with caution)
Wollongong's apparent 167% "recovery" survives an imputation sensitivity test (bounds
166–168% whether masked cells are set to 0, midpoint, or the threshold), **but the mode
split reveals a structural break: bus tap-ons roughly tripled between 2022 (1.16M) and
2025 (3.78M) while train volumes stayed flat (~1M/yr).** Organic demand does not grow
like this; a service-coverage or region-definition change is the likely cause, though no
confirming public announcement was found. Wollongong is therefore flagged as unreliable
for pre/post-COVID comparison until the cause is confirmed (check the dataset's
documentation PDF / TfNSW open data forum).

### 5. Masking sensitivity: Newcastle recovery is indeterminate
Newcastle's masked share is 52% (baseline) to 58% (2026). Its recovery estimate ranges
from **77% to 109%** depending on imputation assumption — too wide to report as a single
number. Dashboard figures for Newcastle should be read as "no reliable signal", unlike
Sydney CBD where the same bounds are 88%–88% (0.5 pt spread).

### 6. UNKNOWN mode
Appears from ~2022 onward, mostly in `Other`/`All - NSW` and 83% masked. Excluded from mode-level analysis.

## Initial findings (weekday tap-ons vs Feb 2020 baseline)
- Recovery is uneven: Macquarie Park 111%, Chatswood 103%, Sydney CBD 88%, Parramatta 88%, **North Sydney only 72%**. (Wollongong's nominal 167% reflects a structural break in bus reporting, and Newcastle's masking makes its figure indeterminate — see issues 4 and 5.)
- WFH signature persists in 2026: CBD Mondays run 15% and Fridays 9% below the Tue–Thu average.
- The CBD's weekend/weekday ratio rose from 45% (Feb 2020) to 66% (2026 H1): the city is becoming relatively more of a leisure destination.

## Files
- `raw/` — 2,372 daily pipe-delimited files as published
- `processed/opal_fact.parquet` — cleaned fact table (9 MB)
- `processed/opal_daily_summary.csv` — daily × mode × region rollup for BI tools
- `processed/dq_stats.json` — machine-readable QA stats
