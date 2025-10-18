# -*- coding: utf-8 -*-
# Streamlit dashboard for real-time rides metrics (Postgres -> SQLAlchemy)
# Works with Streamlit >= 1.33 (uses st.query_params and st.rerun)

import os
import time
from datetime import timedelta

import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from sqlalchemy import create_engine, text

# ---------- Page setup ----------
st.set_page_config(
    page_title="Rides Realtime Dashboard",
    page_icon="🚕",
    layout="wide"
)

# Small, opinionated Altair defaults
alt.themes.enable("none")
alt.data_transformers.disable_max_rows()

# ---------- Environment / DB ----------
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "rtp")
PG_USER = os.getenv("POSTGRES_USER", "rtp")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "rtp_password")

ENGINE = create_engine(
    f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

# ---------- Helpers for query params ----------
def _qp_get_int(key: str, default: int) -> int:
    val = st.query_params.get(key)
    if val is None:
        return default
    # st.query_params returns a str (or list-like if key repeated); normalize
    if isinstance(val, (list, tuple)):
        val = val[0] if val else default
    try:
        return int(val)
    except Exception:
        return default

def _sync_query_params(**pairs):
    """Update URL query params only when changed (avoids rerun loops)."""
    current = {k: (v if isinstance(v, str) else str(v)) for k, v in dict(st.query_params).items()}
    target = {k: (v if isinstance(v, str) else str(v)) for k, v in pairs.items()}
    if current != target:
        st.query_params.clear()
        st.query_params.update(target)

# ---------- Sidebar controls ----------
st.sidebar.header("Controls")

default_lookback = _qp_get_int("lookback", 15)           # minutes
default_rolling = _qp_get_int("rolling", 5)              # minutes (smoothing window)
default_refresh = _qp_get_int("refresh", 0)              # seconds (0 = off)

lookback_min = st.sidebar.number_input(
    "Lookback (minutes)", min_value=1, max_value=240, value=default_lookback, step=1
)

rolling_min = st.sidebar.number_input(
    "Rolling window (minutes)", min_value=1, max_value=60, value=default_rolling, step=1,
    help="Smoothing for time-series lines"
)

auto_refresh_secs = st.sidebar.number_input(
    "Auto-refresh (seconds, 0=off)", min_value=0, max_value=120, value=default_refresh, step=1
)

st.sidebar.caption("Tip: use a small auto-refresh (e.g., 5s) during live demos.")

# optional city filter (populated after data load; placeholder for layout stability)
city_filter_placeholder = st.sidebar.empty()

# Keep URL in sync with current controls (new API)
_sync_query_params(lookback=lookback_min, rolling=rolling_min, refresh=auto_refresh_secs)

# Cache TTL follows refresh cadence; fallback to 10s if manual mode
cache_ttl = auto_refresh_secs if auto_refresh_secs > 0 else 10

# ---------- Data ----------
@st.cache_data(ttl=cache_ttl, show_spinner=False)
def load_metrics(last_minutes: int) -> pd.DataFrame:
    with ENGINE.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT
                    window_start,
                    window_end,
                    city,
                    events,
                    avg_fare,
                    p95_fare,
                    avg_duration_sec
                FROM public.rides_minute_metrics
                WHERE window_start >= NOW() AT TIME ZONE 'utc' - (INTERVAL '1 minute' * :mins)
                ORDER BY window_start ASC
                """
            ),
            conn,
            params={"mins": last_minutes},
        )
    if df.empty:
        return df
    # Types
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True).dt.tz_convert(None)
    df["window_end"] = pd.to_datetime(df["window_end"], utc=True).dt.tz_convert(None)
    return df

df = load_metrics(lookback_min)

st.title("🚕 Rides Realtime Dashboard")
st.caption(
    f"Last **{lookback_min}** minutes · Window size **1 min** · Watermark **30s** · "
    f"{'Auto-refresh **on** ('+str(auto_refresh_secs)+'s)' if auto_refresh_secs else 'Manual refresh'}"
)

if df.empty:
    st.info("No data yet. Is the streaming job running and producing into Postgres?")
    if auto_refresh_secs > 0:
        time.sleep(auto_refresh_secs)
        st.rerun()
    st.stop()

# ---------- Filters ----------
all_cities = sorted(df["city"].dropna().unique().tolist())
selected_cities = city_filter_placeholder.multiselect(
    "City filter", options=all_cities, default=all_cities, help="Select one or more cities to include"
)

if selected_cities:
    df = df[df["city"].isin(selected_cities)]

# Precompute aggregates
last_ts = df["window_start"].max()
latest_slice = df[df["window_start"] == last_ts]

# ---------- KPI cards ----------
kpi_cols = st.columns(5)
with kpi_cols[0]:
    st.metric("Total events (latest minute)", int(latest_slice["events"].sum()))
with kpi_cols[1]:
    st.metric("Cities (active)", int(latest_slice["city"].nunique()))
with kpi_cols[2]:
    st.metric("Avg fare (latest)", f"${latest_slice['avg_fare'].mean():.2f}")
with kpi_cols[3]:
    st.metric("p95 fare (latest)", f"${latest_slice['p95_fare'].mean():.2f}")
with kpi_cols[4]:
    st.metric("Avg duration (sec, latest)", f"{latest_slice['avg_duration_sec'].mean():.0f}")

st.divider()

# ---------- Time-series (events/min by city) with rolling smoothing ----------
ts = (
    df.groupby(["window_start", "city"], as_index=False)["events"]
    .sum()
    .sort_values("window_start")
)

def rolling_mean_per_city(frame: pd.DataFrame, col: str, win: int) -> pd.Series:
    return frame.groupby("city")[col].transform(lambda s: s.rolling(win, min_periods=1).mean())

ts["events_smoothed"] = rolling_mean_per_city(ts, "events", rolling_min)

base = alt.Chart(ts).properties(height=280)
line = (
    base
    .mark_line(point=False)
    .encode(
        x=alt.X("window_start:T", title="Time"),
        y=alt.Y("events_smoothed:Q", title=f"Events / min (rolling {rolling_min}m)"),
        color=alt.Color("city:N", title="City"),
        tooltip=[
            alt.Tooltip("window_start:T", title="Time"),
            alt.Tooltip("city:N", title="City"),
            alt.Tooltip("events:Q", title="Events"),
            alt.Tooltip("events_smoothed:Q", title="Rolling events"),
        ],
    )
    .interactive()
)

st.subheader("Event rate over time")
st.altair_chart(line, use_container_width=True)

# ---------- City comparison: latest minute ----------
st.subheader("Latest minute: city comparison")
c1, c2 = st.columns(2)

with c1:
    top_events = (
        latest_slice.groupby("city", as_index=False)["events"].sum().sort_values("events", ascending=False)
    )
    chart_events = (
        alt.Chart(top_events)
        .mark_bar()
        .encode(
            x=alt.X("events:Q", title="Events (latest minute)"),
            y=alt.Y("city:N", sort="-x", title=None),
            tooltip=[alt.Tooltip("city:N"), alt.Tooltip("events:Q")],
        )
        .properties(height=max(140, 24 * len(top_events)))
    )
    st.altair_chart(chart_events, use_container_width=True)

with c2:
    latest_stats = latest_slice.groupby("city", as_index=False).agg(
        avg_fare=("avg_fare", "mean"),
        p95_fare=("p95_fare", "mean"),
        avg_duration_sec=("avg_duration_sec", "mean"),
    )
    # Scatter: Avg vs p95 fare
    scatter = (
        alt.Chart(latest_stats)
        .mark_circle(size=120)
        .encode(
            x=alt.X("avg_fare:Q", title="Avg fare (latest)"),
            y=alt.Y("p95_fare:Q", title="p95 fare (latest)"),
            color=alt.Color("city:N", title="City"),
            tooltip=[
                alt.Tooltip("city:N"),
                alt.Tooltip("avg_fare:Q", title="Avg fare", format="$.2f"),
                alt.Tooltip("p95_fare:Q", title="p95 fare", format="$.2f"),
                alt.Tooltip("avg_duration_sec:Q", title="Avg duration (s)", format=".0f"),
            ],
        )
    )
    st.altair_chart(scatter, use_container_width=True)

# ---------- Duration by city (lookback) ----------
st.subheader(f"Avg duration by city (last {lookback_min} min)")
dur_by_city = df.groupby("city", as_index=False)["avg_duration_sec"].mean().sort_values("avg_duration_sec", ascending=True)
chart_dur = (
    alt.Chart(dur_by_city)
    .mark_bar()
    .encode(
        x=alt.X("avg_duration_sec:Q", title="Avg duration (sec)"),
        y=alt.Y("city:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("city:N"), alt.Tooltip("avg_duration_sec:Q", title="Avg duration (s)", format=".0f")],
    )
    .properties(height=max(140, 24 * len(dur_by_city)))
)
st.altair_chart(chart_dur, use_container_width=True)

# ---------- Heatmap: events by minute x city ----------
st.subheader("Heatmap: events per minute × city")
heat = (
    ts.assign(minute=ts["window_start"].dt.strftime("%H:%M"))
    .groupby(["minute", "city"], as_index=False)["events"]
    .sum()
)
heatmap = (
    alt.Chart(heat)
    .mark_rect()
    .encode(
        x=alt.X("minute:O", title="Minute"),
        y=alt.Y("city:N", title="City"),
        color=alt.Color("events:Q", title="Events", scale=alt.Scale(type="linear")),
        tooltip=[alt.Tooltip("minute:O"), alt.Tooltip("city:N"), alt.Tooltip("events:Q")],
    )
    .properties(height=max(160, 24 * len(all_cities)))
)
st.altair_chart(heatmap, use_container_width=True)

# ---------- Data table (latest N rows) ----------
st.subheader("Recent aggregated rows")
st.dataframe(
    df.sort_values(["window_start", "city"], ascending=[False, True]).tail(500),
    use_container_width=True,
    hide_index=True,
)

st.caption(
    "Data source: `public.rides_minute_metrics`. "
    "Controls are synced to the URL via `st.query_params`. "
    "Auto-refresh uses `st.rerun()`."
)

# ---------- Auto-refresh loop ----------
if auto_refresh_secs > 0:
    time.sleep(auto_refresh_secs)
    st.rerun()
