"""
Sydney After COVID — an Opal patronage dashboard.

Four views, each aimed at a real decision-maker:
  1. Recovery Overview         -> property investors / asset managers
  2. The Three-Day Office Week -> office landlords & CBD employers
  3. The Leisure Shift         -> government & retail strategy
  4. Region Deep-Dive          -> interactive exploration + data confidence

Data: TfNSW Opal Patronage (CC-BY), Jan 2020 - Jul 2026, cleaned by merge_opal.py.
Run:  streamlit run app.py
"""

import os

import pandas as pd
import plotly.express as px
import plotly.io as pio
import streamlit as st

st.set_page_config(page_title="Sydney Opal Patronage", page_icon="🚆", layout="wide")

# ------------------------------------------------------------------ style
ACCENT = "#0B7285"
PALETTE = ["#0B7285", "#E8590C", "#5F3DC4", "#2B8A3E", "#C2255C",
           "#1971C2", "#E67700", "#495057"]
pio.templates.default = "plotly_white"
px.defaults.color_discrete_sequence = PALETTE

st.markdown("""
<style>
  h1 { font-weight: 750; letter-spacing: -0.5px; }
  [data-testid="stMetric"] {
      background: #F4F7F8; border: 1px solid #E3EAEC;
      border-radius: 12px; padding: 14px 18px;
  }
  [data-testid="stMetricLabel"] { color: #5C6F78; }
  div[data-testid="stExpander"] { border-radius: 12px; }
  .insight {
      background: #EDF6F7; border-left: 4px solid #0B7285;
      border-radius: 0 10px 10px 0; padding: 12px 16px; margin: 6px 0 14px 0;
      font-size: 0.95rem;
  }
  .insight b { color: #0B7285; }
</style>
""", unsafe_allow_html=True)


def insight(text: str):
    st.markdown(f'<div class="insight">{text}</div>', unsafe_allow_html=True)


# st.plotly_chart sizing API changed across Streamlit versions; support both.
import inspect
_HAS_WIDTH = "width" in inspect.signature(st.plotly_chart).parameters


def plot(fig):
    if _HAS_WIDTH:
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------ data
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "processed", "opal_fact.parquet")

BASELINE = ("2020-02-01", "2020-02-28")  # pre-COVID reference month (weekdays)
LOCKDOWNS = [("2020-03-23", "Lockdown 1"), ("2021-06-26", "Delta lockdown")]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REGION_COORDS = {
    "Sydney CBD":               (-33.8688, 151.2093),
    "North Sydney":             (-33.8389, 151.2072),
    "Chatswood":                (-33.7969, 151.1830),
    "Macquarie Park":           (-33.7772, 151.1243),
    "Parramatta":               (-33.8150, 151.0011),
    "Strathfield":              (-33.8712, 151.0938),
    "Newcastle and surrounds":  (-32.9283, 151.7817),
    "Wollongong and surrounds": (-34.4278, 150.8931),
}


@st.cache_data(show_spinner="Loading Opal data...")
def load():
    df = pd.read_parquet(DATA)
    df = df[(~df["is_other"]) & (df["mode"] != "UNKNOWN")].copy()
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["quarter"] = df["date"].dt.to_period("Q").dt.to_timestamp()
    daily = (df.groupby(["date", "region", "dow", "is_weekend", "month", "quarter"],
                        observed=True)
               .agg(tap_ons=("tap_ons_mid", "sum"),
                    masked_hours=("ons_masked", "sum"),
                    hours=("ons_masked", "size"))
               .reset_index())
    return df, daily


def weekday_baseline(daily):
    m = daily[(daily["date"] >= BASELINE[0]) & (daily["date"] <= BASELINE[1])
              & (~daily["is_weekend"])]
    return m.groupby("region")["tap_ons"].mean()


def recovery_for(daily, base, a, b):
    cur = daily[(daily["date"] >= a) & (daily["date"] <= b) & (~daily["is_weekend"])]
    return cur.groupby("region")["tap_ons"].mean() / base * 100


def add_lockdowns(fig):
    for d, label in LOCKDOWNS:
        fig.add_vline(x=d, line_dash="dot", line_color="grey")
        fig.add_annotation(x=d, y=1.02, yref="paper", text=label,
                           showarrow=False, font=dict(size=10, color="grey"))
    return fig


df, daily = load()
base = weekday_baseline(daily)
regions = sorted(daily["region"].unique())

st.sidebar.title("🚆 Sydney Opal Patronage")
page = st.sidebar.radio("View", [
    "1 · Recovery Overview",
    "2 · The Three-Day Office Week",
    "3 · The Leisure Shift",
    "4 · Region Deep-Dive",
])
st.sidebar.markdown("---")
st.sidebar.caption(
    "TfNSW Opal Patronage (CC-BY), 2020-01 → 2026-07. Masked cells (<50 pre-Jul-2024, "
    "<100 after) midpoint-imputed; see Data notes in view 4."
)

# ---------------------------------------------------------------- view 1
if page.startswith("1"):
    st.title("Where has foot traffic actually recovered?")
    st.caption("Average weekday tap-ons vs the February 2020 (pre-COVID) baseline.")

    # Regions whose cross-period comparison is unreliable (see DATA_QUALITY.md #4, #5):
    # Wollongong has a structural break in bus reporting; Newcastle is >50% masked.
    FLAGGED = ["Wollongong and surrounds", "Newcastle and surrounds"]

    rec = recovery_for(daily, base, "2026-01-01", "2026-06-30").sort_values()
    rec_prev = recovery_for(daily, base, "2025-01-01", "2025-06-30")
    reliable = rec.drop(index=FLAGGED)
    momentum = (reliable - rec_prev[reliable.index]).sort_values(ascending=False)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Network recovery (2026 H1)", f"{reliable.mean():.0f}%")
    c2.metric(f"Strongest: {reliable.idxmax()}", f"{reliable.max():.0f}%")
    c3.metric(f"Weakest: {reliable.idxmin()}", f"{reliable.min():.0f}%",
              delta=f"{reliable.min()-100:.0f} pts vs 2020", delta_color="inverse")
    c4.metric(f"Fastest riser: {momentum.idxmax()}", f"{reliable[momentum.idxmax()]:.0f}%",
              delta=f"+{momentum.max():.0f} pts YoY")

    insight(
        f"<b>Executive summary.</b> Six years on, Greater Sydney's centres sit at "
        f"{reliable.mean():.0f}% of pre-COVID weekday volume, but recovery is a story of "
        f"winners and losers: {reliable.idxmax()} ({reliable.max():.0f}%) and Chatswood "
        f"have outgrown 2020, while <b>{reliable.idxmin()} remains the clear laggard at "
        f"{reliable.min():.0f}%</b>. Momentum favours {momentum.idxmax()} "
        f"(+{momentum.max():.0f} pts YoY). Capital and leasing strategy set on 2019 "
        f"assumptions is mispriced. <i>Wollongong (nominal {rec['Wollongong and surrounds']:.0f}%) "
        f"and Newcastle are excluded from headline figures: the former shows a structural "
        f"break in bus reporting, the latter is >50% privacy-masked — see Data notes.</i>"
    )

    left, right = st.columns([1.1, 1])
    with left:
        vol = daily[(daily["date"] >= "2026-01-01") & (~daily["is_weekend"])] \
            .groupby("region")["tap_ons"].mean()
        geo = pd.DataFrame({
            "region": rec.index,
            "recovery": rec.values,
            "avg_daily_tap_ons": vol[rec.index].values,
            "lat": [REGION_COORDS[r][0] for r in rec.index],
            "lon": [REGION_COORDS[r][1] for r in rec.index],
        })
        fig_map = px.scatter_map(
            geo, lat="lat", lon="lon", size="avg_daily_tap_ons", color="recovery",
            color_continuous_scale="RdYlGn", range_color=(60, 140),
            size_max=42, zoom=7.2, center=dict(lat=-33.75, lon=151.15),
            hover_name="region",
            hover_data={"lat": False, "lon": False,
                        "recovery": ":.0f", "avg_daily_tap_ons": ":,.0f"},
            map_style="carto-positron",
            labels={"recovery": "Recovery %", "avg_daily_tap_ons": "Avg daily tap-ons"},
        )
        fig_map.update_layout(height=470, margin=dict(l=0, r=0, t=30, b=0),
                              title="Bubble = volume · Colour = recovery vs 2020")
        plot(fig_map)
    with right:
        fig = px.bar(rec, orientation="h",
                     text=rec.round(0).astype(int).astype(str) + "%",
                     color=rec.values, color_continuous_scale="RdYlGn",
                     range_color=(60, 140),
                     labels={"value": "Recovery vs Feb 2020 (%)", "region": ""})
        fig.add_vline(x=100, line_dash="dash", line_color="black")
        fig.update_layout(showlegend=False, coloraxis_showscale=False, height=470,
                          margin=dict(l=0, r=10, t=30, b=0), title="Ranked recovery")
        plot(fig)

    monthly = daily[~daily["is_weekend"]].groupby(["month", "region"])["tap_ons"].mean().reset_index()
    monthly["recovery"] = monthly.apply(lambda r: r["tap_ons"] / base[r["region"]] * 100, axis=1)
    fig2 = px.line(monthly, x="month", y="recovery", color="region",
                   labels={"recovery": "Recovery (%)", "month": ""})
    fig2.add_hline(y=100, line_dash="dash", line_color="black")
    add_lockdowns(fig2)
    fig2.update_layout(height=450, legend_title="")
    plot(fig2)

    insight("<b>So what?</b> North Sydney is the only centre still deep below its 2020 "
            "level; one hypothesis worth testing is Metro-driven mode shift after the "
            "Victoria Cross station opened in 2024. Macquarie Park and Chatswood now "
            "exceed pre-COVID volumes: the growth is no longer where it was in 2019. "
            "Wollongong's spectacular line is best read as a reporting-coverage change, "
            "not a demand story — a reminder that the most exciting number in a dataset "
            "is usually the one to interrogate first.")

# ---------------------------------------------------------------- view 2
elif page.startswith("2"):
    st.title("The three-day office week")
    st.caption("Hybrid work reshaped *when* people show up, not just how many.")

    yr = st.select_slider("Period", ["2020 (Jan-Feb)", "2022", "2023", "2024", "2025", "2026"],
                          value="2026")
    rng = {"2020 (Jan-Feb)": ("2020-01-01", "2020-02-28")}.get(yr, (f"{yr}-01-01", f"{yr}-12-31"))

    sel = daily[(daily["date"] >= rng[0]) & (daily["date"] <= rng[1]) & (~daily["is_weekend"])]
    pat = sel.groupby(["region", "dow"])["tap_ons"].mean().reset_index()
    pat["rel"] = pat.apply(
        lambda r: r["tap_ons"] / pat[(pat.region == r["region"]) & (pat.dow.isin([1, 2, 3]))]["tap_ons"].mean() * 100,
        axis=1)

    cbd = pat[pat.region == "Sydney CBD"].set_index("dow")["rel"]
    c1, c2, c3 = st.columns(3)
    c1.metric("CBD Monday vs midweek", f"{cbd[0]:.0f}%", delta=f"{cbd[0]-100:.0f} pts",
              delta_color="inverse")
    c2.metric("CBD Friday vs midweek", f"{cbd[4]:.0f}%", delta=f"{cbd[4]-100:.0f} pts",
              delta_color="inverse")
    c3.metric("Effective office week (CBD)", f"{cbd.sum()/100:.1f} days",
              help="Sum of each weekday's volume relative to the Tue-Thu average.")

    piv = pat.pivot(index="region", columns="dow", values="rel")
    piv.columns = DOW[:5]
    fig = px.imshow(piv.round(0), text_auto=True, color_continuous_scale="RdYlGn",
                    zmin=70, zmax=110, aspect="auto",
                    labels=dict(color="% of Tue-Thu avg"))
    fig.update_layout(height=380)
    plot(fig)

    insight(f"<b>So what?</b> In {yr}, a CBD 'week' is effectively "
            f"{cbd.sum()/100:.1f} days of pre-hybrid demand. Office services, transport "
            "supply and lunch retail are still sized for a five-day pattern that no "
            "longer exists; Monday is the day to rethink rosters and promotions.")

    st.subheader("The peak got shorter and later")
    reg = st.selectbox("Region", regions, index=regions.index("Sydney CBD"))
    hourly = df[(df["region"] == reg) & (~df["is_weekend"])]
    prof = []
    for label, a, b in [("Feb 2020", *BASELINE), ("2026 H1", "2026-01-01", "2026-06-30")]:
        h = (hourly[(hourly["date"] >= a) & (hourly["date"] <= b)]
             .groupby("hour")["tap_ons_mid"].sum())
        days = hourly[(hourly["date"] >= a) & (hourly["date"] <= b)]["date"].nunique()
        prof.append(pd.DataFrame({"hour": h.index, "tap_ons": h.values / days, "period": label}))
    fig2 = px.line(pd.concat(prof), x="hour", y="tap_ons", color="period",
                   labels={"tap_ons": "Avg weekday tap-ons", "hour": "Hour of day"})
    fig2.update_layout(height=420, legend_title="")
    plot(fig2)

# ---------------------------------------------------------------- view 3
elif page.startswith("3"):
    st.title("The leisure shift")
    st.caption("Weekends recovered faster than weekdays: the CBD is becoming a destination, "
               "not just a workplace.")

    reg = st.selectbox("Region", regions, index=regions.index("Sydney CBD"))
    q = daily[daily["region"] == reg].groupby(["quarter", "is_weekend"])["tap_ons"].mean().unstack()
    q["ratio"] = q[True] / q[False] * 100
    q = q[q["ratio"].notna()]  # drop incomplete quarters (e.g. a lone weekday at series end)
    then, now = q["ratio"].iloc[0], q["ratio"].iloc[-1]

    ev = df[(df["region"] == reg) & (df["hour"].between(18, 23))]
    ev_base = ev[(ev["date"] >= BASELINE[0]) & (ev["date"] <= BASELINE[1])]["tap_ons_mid"].sum() / 29
    ev_now = ev[ev["date"] >= "2026-01-01"]["tap_ons_mid"].sum() / \
        ev[ev["date"] >= "2026-01-01"]["date"].nunique()
    day_rec = recovery_for(daily, base, "2026-01-01", "2026-06-30")[reg]

    c1, c2, c3 = st.columns(3)
    c1.metric("Weekend / weekday ratio now", f"{now:.0f}%", delta=f"+{now-then:.0f} pts since 2020")
    c2.metric("Evening (6pm-12am) recovery", f"{ev_now/ev_base*100:.0f}%")
    c3.metric("Overall weekday recovery", f"{day_rec:.0f}%")

    fig = px.line(q.reset_index(), x="quarter", y="ratio",
                  labels={"ratio": "Weekend as % of weekday", "quarter": ""})
    add_lockdowns(fig)
    fig.update_layout(height=400)
    plot(fig)

    evd = ev.groupby(["month"])["tap_ons_mid"].sum().reset_index()
    fig2 = px.area(evd, x="month", y="tap_ons_mid",
                   labels={"tap_ons_mid": "Evening (6pm-midnight) tap-ons / month", "month": ""})
    add_lockdowns(fig2)
    fig2.update_layout(height=380)
    plot(fig2)

    insight(f"<b>So what?</b> {reg}'s weekend/weekday ratio climbed from {then:.0f}% to "
            f"{now:.0f}%, and evenings run at {ev_now/ev_base*100:.0f}% of 2020 versus "
            f"{day_rec:.0f}% for the commuter day. Precinct activation policy, late-night "
            "transport and retail leasing should follow the visitors, not the commuters.")

# ---------------------------------------------------------------- view 4
else:
    st.title("Region deep-dive")
    reg = st.selectbox("Region", regions, index=regions.index("North Sydney"))
    a, b = st.slider("Date range",
                     min_value=daily["date"].min().date(), max_value=daily["date"].max().date(),
                     value=(pd.Timestamp("2023-01-01").date(), daily["date"].max().date()))
    sel = daily[(daily["region"] == reg) & (daily["date"].dt.date >= a) & (daily["date"].dt.date <= b)]

    rec_all = recovery_for(daily, base, "2026-01-01", "2026-06-30")
    reg_rec = sel[~sel.is_weekend]["tap_ons"].mean() / base[reg] * 100
    masked_share = sel["masked_hours"].sum() / sel["hours"].sum() * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg daily tap-ons", f"{sel['tap_ons'].mean():,.0f}")
    c2.metric("vs Feb 2020 weekdays", f"{reg_rec:.0f}%")
    c3.metric("vs network median (2026)", f"{reg_rec - rec_all.median():+.0f} pts")
    c4.metric("Data confidence", f"{100 - masked_share:.0f}%",
              help="Share of hourly cells NOT privacy-masked at source. Masked cells "
                   "(<50 before Jul 2024, <100 after) are midpoint-imputed and matter "
                   "mostly in off-peak hours.")

    droll = sel.groupby("date")["tap_ons"].sum().rolling(7).mean().reset_index()
    fig = px.line(droll, x="date", y="tap_ons",
                  labels={"tap_ons": "Daily tap-ons (7-day avg)", "date": ""})
    fig.update_layout(height=380)
    plot(fig)

    hsel = df[(df["region"] == reg) & (df["date"].dt.date >= a) & (df["date"].dt.date <= b)]
    heat = hsel.groupby(["dow", "hour"])["tap_ons_mid"].mean().unstack()
    heat.index = DOW
    fig2 = px.imshow(heat, aspect="auto", color_continuous_scale="Viridis",
                     labels=dict(x="Hour of day", y="", color="Avg tap-ons"))
    fig2.update_layout(height=380)
    plot(fig2)

    gap = reg_rec - rec_all.median()
    insight(f"<b>Reading {reg}.</b> Over the selected window it averages "
            f"{sel['tap_ons'].mean():,.0f} tap-ons/day and sits {abs(gap):.0f} pts "
            f"{'above' if gap >= 0 else 'below'} the network median recovery. "
            f"{'Its off-peak cells are heavily masked, so treat hourly night-time detail with caution. ' if masked_share > 30 else ''}"
            "Use the heatmap to spot which daypart drives the gap before drawing conclusions.")

    with st.expander("Data notes & known limitations"):
        st.markdown(
            "- Source masks small counts: `<50` up to 2024-06-30, `<100` from 2024-07-01. "
            "Midpoint imputation used; do not compare masked-heavy slices across that boundary.\n"
            "- 2021-06-03 and 2021-06-04 are missing at source.\n"
            "- `Other` region and `UNKNOWN` mode excluded from all views.\n"
            "- Full pipeline and QA: see `opal_data/DATA_QUALITY.md`."
        )
