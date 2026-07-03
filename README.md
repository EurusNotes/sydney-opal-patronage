# Sydney, After the Office

**Six and a half years of Opal tap data (1.6M hourly records, 2020–2026), turned into
decisions: where Sydney's foot traffic recovered, when people actually come to the
office, and how the CBD quietly became a destination.**

🔗 **[Live dashboard](https://chenxi-ten.vercel.app/opal)** · 📊 [Data quality notes](docs/DATA_QUALITY.md) · 🐍 [Streamlit explorer](dashboard/)

---

## Headline findings

Each finding is written for the person who can act on it — the full twelve are on the
[live dashboard](https://chenxi-ten.vercel.app/opal). A sample:

| # | Finding | Who should care |
|---|---------|-----------------|
| 1 | **North Sydney is two markets now**: weekday demand at 72% of 2020, Saturdays at 136% | Property investors screening repositioning candidates |
| 2 | **Saturday nights beat pre-COVID by 49%** in the CBD | Retail leasing: late-trading F&B justifies premium rents |
| 3 | **The effective office week is 4.8 days** (Monday −15%, Friday −9% vs midweek) | Office landlords' DCF assumptions |
| 4 | **The 5pm peak lost a quarter** while total demand lost 12% | Transport service planning |
| 5 | **Recovery is a crawl**: 83% → 86% → 90% (2024→2026); full recovery ≈ 2029 at this pace | Valuers & CFOs: no rebound left to underwrite |
| 6 | **The "167% Wollongong boom" is a reporting artifact**, caught by mode decomposition | Anyone who has ever trusted an exciting number |

## Why this project is built the way it is

**The interesting engineering isn't the charts — it's the data honesty.** Three examples:

1. **The masking threshold changed mid-series.** TfNSW suppresses small counts, but the
   threshold silently moved from `<50` to `<100` on 2024-07-01. Every masked cell carries
   a `mask_threshold` column so no analysis accidentally compares across the boundary.
2. **Imputation is bounded, not assumed.** Masked cells are midpoint-imputed, and every
   headline number was re-run with masked cells set to 0 and to the ceiling. Sydney CBD's
   recovery moves 88%→88% (safe); Newcastle's moves 77%→109% (reported as "no reliable
   signal" instead of a number).
3. **The most exciting number was interrogated first.** Wollongong's 167% "recovery"
   survived the imputation test but failed mode decomposition — bus taps tripled in three
   years while trains stayed flat, the signature of a coverage change, not demand. It is
   flagged and excluded from headlines. Full write-up: [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

## Architecture

```
TfNSW Open Data Hub (S3, 2,372 daily files)
        │  pipeline/download_opal.py     resumable bulk download, referrer auth
        ▼
data/raw/ (~70MB, gitignored, reproducible)
        │  pipeline/merge_opal.py        schema validation → typed fact table
        ▼                                masking flags, imputation, QA stats
data/processed/opal_fact.parquet (1.37M rows, 9MB)
        │
        ├── dashboard/app.py             Streamlit + Plotly interactive explorer
        └── pipeline/gen_web_data.py     pre-aggregation → 7KB data.js
                └── web/index.html       zero-framework ECharts + Leaflet static site
```

Two front-ends on purpose: the **static site** (`web/`) is the publishable data story —
loads instantly, no server, deploys anywhere; the **Streamlit app** (`dashboard/`) is the
analyst's tool — sliders, region deep-dives, and a per-slice data-confidence indicator
showing how much of what you're looking at was privacy-masked at source.

## Run it

```bash
# 1. rebuild raw data (~70MB, ~3 min)
python3 pipeline/download_opal.py

# 2. rebuild the fact table + QA stats
pip install pandas pyarrow
python3 pipeline/merge_opal.py

# 3a. static site
open web/index.html

# 3b. interactive explorer
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py

# (optional) regenerate the static site's data payload
python3 pipeline/gen_web_data.py
```

## Data

[Opal Patronage](https://opendata.transport.nsw.gov.au/data/dataset/opal-patronage),
Transport for NSW Open Data Hub, CC-BY. Hourly tap-ons/offs by mode and commercial
centre. Known issues and how they are handled: [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).



*Independent analysis; not affiliated with Transport for NSW.*
