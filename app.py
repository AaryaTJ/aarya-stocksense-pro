"""
Aarya StockSense Pro — app.py
6-tab Streamlit dashboard. Run: streamlit run app.py
"""
from datetime import datetime
import os
import base64
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import importlib
import engine as eng
importlib.reload(eng)
from config import (FUND_CATALOGUE, MARKET_CONFIGS, FOCUS_MODES,
                    load_settings, save_settings, get_watchlist, save_custom_watchlist)
import notifier
import auth
import db
import mldb
import scanner_contrarian
import scanner_penny
from ml import predictor as ml_predictor

st.set_page_config(page_title="Aarya StockSense Pro", page_icon="📈",
                   layout="wide", initial_sidebar_state="auto")

# ── THEME ─────────────────────────────────────────────────────────────
def css():
    _ico = os.path.join(os.path.dirname(__file__), "aarya_icon.png")
    if os.path.exists(_ico):
        _b64 = base64.b64encode(open(_ico, "rb").read()).decode()
        st.markdown(
            f'<link rel="shortcut icon" type="image/png" href="data:image/png;base64,{_b64}">',
            unsafe_allow_html=True,
        )
    st.markdown("""<style>
    html,body,[data-testid="stAppViewContainer"]{background:#0F1B2D!important;color:#C9D6E3!important}
    [data-testid="stSidebar"]{background:#080F1C!important;border-right:1px solid #1a2f4a}
    h1,h2,h3,h4{color:#fff!important}
    [data-testid="stMetric"]{background:#121e30;border:1px solid #1a2f4a;border-radius:8px;padding:12px 16px}
    [data-testid="stMetricValue"]{color:#fff!important}
    [data-testid="stMetricLabel"]{color:#4A7FA5!important}
    [data-baseweb="tab-list"]{background:#080F1C!important;border-bottom:1px solid #1a2f4a}
    [data-baseweb="tab"]{color:#4A7FA5!important;font-size:13px}
    [aria-selected="true"]{color:#1D9E75!important;border-bottom:2px solid #1D9E75!important}
    input,textarea{background:#121e30!important;color:#fff!important;border:1px solid #1a2f4a!important;border-radius:6px!important}
    [data-testid="baseButton-primary"]{background:#1D9E75!important;color:#050d15!important;font-weight:700;border-radius:6px}
    [data-testid="baseButton-secondary"]{background:#121e30!important;color:#C9D6E3!important;border:1px solid #1a2f4a!important}
    [data-baseweb="select"] div{background:#121e30!important;color:#fff!important}
    [data-testid="stDataFrame"]{border:1px solid #1a2f4a;border-radius:8px}
    hr{border-color:#1a2f4a!important}
    .stExpander{border:1px solid #1a2f4a!important;border-radius:8px!important;background:#0a1525!important}
    /* ═════════════════════════════════════════════════════════════ */
    /* TRUE FLUID RESPONSIVENESS — works on every screen size        */
    /* without per-device media query tuning. Two ideas do the heavy */
    /* lifting:                                                       */
    /*   1) auto-fit grids: browser figures out column count itself  */
    /*   2) clamp(): font sizes scale smoothly with viewport width   */
    /* These rules apply on ALL screen sizes — small media queries   */
    /* below only handle Streamlit-specific containers + paddings.   */
    /* ═════════════════════════════════════════════════════════════ */

    /* Every Streamlit markdown container respects the viewport */
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] > div{
        max-width:100%!important;word-wrap:break-word!important;
        overflow-wrap:break-word!important;box-sizing:border-box!important}

    /* Auto-fit grids: each cell ≥120px, browser fills as many cols as fit.
       Phone (≤360px) → 2 cols; small phone (390px) → 2-3; tablet → 4-5; desktop → original */
    div[style*="grid-template-columns:repeat(5,1fr)"]{
        grid-template-columns:repeat(auto-fit,minmax(110px,1fr))!important;
        gap:6px!important}
    div[style*="grid-template-columns:repeat(4,1fr)"]{
        grid-template-columns:repeat(auto-fit,minmax(120px,1fr))!important;
        gap:6px!important}
    div[style*="grid-template-columns:repeat(3,1fr)"]{
        grid-template-columns:repeat(auto-fit,minmax(140px,1fr))!important;
        gap:6px!important}

    /* Every flex row inside markdown wraps naturally — never overflow */
    [data-testid="stMarkdownContainer"] div[style*="display:flex"]{
        flex-wrap:wrap!important;max-width:100%!important}

    /* Fluid font sizes — clamp(min, fluid, max). Small screens shrink, large
       screens get the original size. No breakpoints needed. */
    div[style*="font-size:24px"],span[style*="font-size:24px"]{
        font-size:clamp(15px,4.5vw,24px)!important}
    div[style*="font-size:22px"],span[style*="font-size:22px"]{
        font-size:clamp(14px,4vw,22px)!important}
    div[style*="font-size:20px"],span[style*="font-size:20px"]{
        font-size:clamp(13px,3.5vw,20px)!important}
    div[style*="font-size:18px"],span[style*="font-size:18px"]{
        font-size:clamp(12px,3vw,18px)!important}
    div[style*="font-size:16px"],span[style*="font-size:16px"]{
        font-size:clamp(11px,2.7vw,16px)!important}

    /* HTML tables inside markdown — scroll horizontally if they don't fit */
    [data-testid="stMarkdownContainer"] table{
        display:block!important;overflow-x:auto!important;max-width:100%!important;
        width:auto!important;-webkit-overflow-scrolling:touch!important}
    [data-testid="stMarkdownContainer"] table td,
    [data-testid="stMarkdownContainer"] table th{
        white-space:nowrap!important}

    /* Plotly charts always fit viewport */
    [data-testid="stPlotlyChart"]{max-width:100%!important;overflow-x:auto!important}

    /* ── Phone-only tightening: paddings, sidebar, tabs ─────────── */
    @media screen and (max-width:640px){
        [data-testid="column"]{min-width:100%!important;margin-bottom:6px}
        [data-testid="stDataFrame"]{max-width:calc(100vw - 1.5rem)!important;overflow-x:auto!important}
        [data-testid="stMetric"]{padding:6px 8px!important}
        h1{font-size:1.15rem!important;margin:0.25rem 0!important}
        h2{font-size:1.0rem!important;margin:0.25rem 0!important}
        h3{font-size:0.95rem!important;margin:0.25rem 0!important}
        h4{font-size:0.85rem!important}
        [data-baseweb="tab"]{font-size:10px!important;padding:5px 6px!important}
        [data-testid="stAppViewContainer"] > section:first-child{padding:0.3rem!important}
        .block-container{padding:0.4rem 0.5rem!important;max-width:100vw!important}
        /* Tighten our custom-HTML padding on phones */
        div[style*="padding:14px 18px"],div[style*="padding:14px 16px"],
        div[style*="padding:12px 18px"],div[style*="padding:14px 24px"],
        div[style*="padding:18px 24px"],div[style*="padding:14px"]{
            padding:8px 10px!important}
        div[style*="padding:12px"]{padding:7px!important}
        div[style*="margin-bottom:14px"],div[style*="margin-bottom:12px"]{
            margin-bottom:6px!important}
        /* Chip pills compact */
        span[style*="display:inline-block"][style*="font-size:10px"]{
            margin:1px 2px!important;padding:1px 5px!important;font-size:9px!important}
        /* Sidebar trimmed */
        [data-testid="stSidebar"]{padding:0.4rem!important}
        [data-testid="stSidebar"] img{max-width:140px!important;margin:0 auto!important;display:block!important}
        /* Tighter line-height for verdicts */
        div[style*="line-height:1.6"],div[style*="line-height:1.8"]{line-height:1.35!important}
    }
    </style>""", unsafe_allow_html=True)

# ── HELPERS ───────────────────────────────────────────────────────────
def card(html: str):
    st.markdown(html, unsafe_allow_html=True)

def badge(text: str, color: str) -> str:
    return (f"<span style='background:{color};color:#050d15;font-weight:700;"
            f"font-size:11px;padding:3px 10px;border-radius:12px;letter-spacing:.5px;'>{text}</span>")

def sig_color(signal: str) -> str:
    return {"BUY TODAY":"#00C48C","PREPARE TO BUY":"#1D9E75",
            "WATCH":"#FFB340","DO NOT BUY":"#FF4D6A"}.get(signal, "#4A7FA5")

def fmt(val, prefix="", suffix="", decimals=2):
    if val is None: return "—"
    return f"{prefix}{val:.{decimals}f}{suffix}"

# ── CHART ─────────────────────────────────────────────────────────────
def candlestick(df: pd.DataFrame, result: dict, title: str) -> go.Figure:
    n   = min(180, len(df))
    d   = df.iloc[-n:].copy()
    cl  = d["Close"].squeeze()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=d.index,
        open=d["Open"].squeeze(), high=d["High"].squeeze(),
        low=d["Low"].squeeze(),   close=d["Close"].squeeze(),
        name="Price", increasing_line_color="#1D9E75", decreasing_line_color="#FF4D6A",
        increasing_fillcolor="#1D9E75", decreasing_fillcolor="#FF4D6A",
    ))
    for period, col, lbl in [(200,"#556B8A","200 SMA"),(150,"#4A7FA5","150 SMA"),
                              (50,"#FFB340","50 SMA")]:
        s = eng.sma(cl, period)
        if len(s):
            fig.add_trace(go.Scatter(x=d.index[-len(s):], y=s, mode="lines",
                                     line=dict(color=col, width=1.2), name=lbl, opacity=0.8))
    e8 = eng.ema(cl, 8)
    if len(e8):
        fig.add_trace(go.Scatter(x=d.index[-len(e8):], y=e8, mode="lines",
                                  line=dict(color="#00C48C", width=1.5, dash="dot"),
                                  name="8 EMA", opacity=0.9))
    avwap = result.get("avwap")
    if avwap:
        fig.add_hline(y=avwap, line=dict(color="#9B59B6", dash="dash", width=1),
                      annotation_text="AVWAP", annotation_position="right",
                      annotation_font_color="#9B59B6")
    for lvl, lbl, col in [(result.get("entry"),"Entry","#1D9E75"),
                           (result.get("stop"),"Stop","#FF4D6A"),
                           (result.get("t1_price"),"T1","#FFB340"),
                           (result.get("t2_price"),"T2","#4A7FA5")]:
        if lvl:
            fig.add_hline(y=lvl, line=dict(color=col, dash="dot", width=1),
                          annotation_text=lbl, annotation_position="right",
                          annotation_font_color=col)
    if "Volume" in d.columns:
        vol = d["Volume"].squeeze()
        clrs = ["#1D9E75" if float(d["Close"].squeeze().iloc[i]) >= float(d["Open"].squeeze().iloc[i])
                else "#FF4D6A" for i in range(len(d))]
        fig.add_trace(go.Bar(x=d.index, y=vol, name="Volume",
                              marker_color=clrs, opacity=0.3, yaxis="y2"))
    fig.update_layout(
        paper_bgcolor="#0F1B2D", plot_bgcolor="#0F1B2D",
        font=dict(color="#C9D6E3", size=11),
        xaxis=dict(gridcolor="#1a2f4a", showgrid=True, rangeslider_visible=False),
        yaxis=dict(gridcolor="#1a2f4a", showgrid=True, side="right"),
        yaxis2=dict(overlaying="y", side="left", showgrid=False, visible=False),
        legend=dict(bgcolor="#080F1C", bordercolor="#1a2f4a", font_size=10),
        margin=dict(l=8, r=64, t=36, b=8),
        title=dict(text=title, font=dict(color="#fff", size=14)),
        height=460,
    )
    return fig

# ── SIGNAL CARD ───────────────────────────────────────────────────────
def signal_card(r: dict, cfg: dict) -> str:
    sig = r["signal"]; c = sig_color(sig); cur = r["currency"]
    rr  = r.get("rr", {})
    grid = "".join(
        f"<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:6px;padding:8px;text-align:center;'>"
        f"<div style='font-size:9px;color:#4A7FA5;letter-spacing:.5px;text-transform:uppercase;'>{lbl}</div>"
        f"<div style='font-size:13px;font-weight:700;color:#E8EDF5;'>{val}</div></div>"
        for lbl, val in [
            ("Entry",     f"{cur}{r.get('entry','—')}"),
            ("Stop",      f"{cur}{r.get('stop','—')}"),
            ("T1 +1.5R",  f"{cur}{rr.get('t1','—')}"),
            ("T2 +3R",    f"{cur}{rr.get('t2','—')}"),
        ]
    )
    chips = "".join(
        f"<span style='display:inline-block;margin:2px 3px;padding:2px 8px;border-radius:4px;"
        f"font-size:10px;font-weight:600;"
        f"background:{'rgba(0,196,140,.15)' if v else 'rgba(255,77,106,.12)'};"
        f"color:{'#00C48C' if v else '#FF4D6A'};"
        f"border:1px solid {'#00C48C33' if v else '#FF4D6A22'};'>"
        f"{'✅' if v else '❌'} {k}</span>"
        for k, v in (r.get("criteria", {}) or {}).items()
    )
    win  = r.get("win_prob", "—")
    rs   = r.get("rs_score", 0)
    ms   = r.get("minervini_score", 0)
    hold = r.get("hold_days", "—")
    t3   = rr.get("t3", "—")
    return (
        f"<div style='background:#0a1525;border-left:4px solid {c};"
        f"border:1px solid #1a2f4a;border-left:4px solid {c};"
        f"border-radius:10px;padding:14px 18px;margin-bottom:12px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<span style='font-size:20px;font-weight:900;color:#fff;'>{r['ticker']}</span>"
        f"<div style='display:flex;gap:6px;flex-wrap:wrap;'>"
        f"{badge(sig, c)}"
        f"<span style='background:#121e30;color:#4A7FA5;font-size:10px;padding:3px 8px;border-radius:10px;'>Minn {ms}/8</span>"
        f"<span style='background:#121e30;color:#4A7FA5;font-size:10px;padding:3px 8px;border-radius:10px;'>RS {rs:.2f}</span>"
        f"<span style='background:{c}18;color:{c};font-size:10px;padding:3px 8px;border-radius:10px;'>Win {win}%</span>"
        f"</div></div>"
        f"<div style='font-size:13px;color:#C9D6E3;line-height:1.6;margin-bottom:10px;'>{r.get('verdict','')}</div>"
        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px;'>{grid}</div>"
        f"<div style='margin:8px 0;padding:8px 12px;background:#080f1c;border-radius:6px;border:1px solid #1a2f4a;'>"
        f"<span style='color:#4A7FA5;font-size:10px;'>⏱ HOLD TIME: </span>"
        f"<span style='color:#FFB340;font-size:11px;font-weight:600;'>{hold}</span>"
        f"&nbsp;&nbsp;&nbsp;"
        f"<span style='color:#4A7FA5;font-size:10px;'>🎯 T3 TARGET: </span>"
        f"<span style='color:#1D9E75;font-size:11px;font-weight:600;'>{cur}{t3}</span>"
        f"</div>"
        f"<div>{chips}</div></div>"
    )


# ── CACHE LAYER ───────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def c_regime(bm, mkey):
    mc = next(v for v in MARKET_CONFIGS.values() if v["key"] == mkey)
    return eng.check_regime(mc)

@st.cache_data(ttl=900)
def c_screener(wl_tuple, mkey, portfolio, risk_pct):
    mc     = next(v for v in MARKET_CONFIGS.values() if v["key"] == mkey)
    regime = eng.check_regime(mc)
    return eng.run_screener(list(wl_tuple), mc, regime, portfolio, risk_pct), regime

@st.cache_data(ttl=300)
def c_analyze(ticker, mkey, portfolio, risk_pct):
    mc = next(v for v in MARKET_CONFIGS.values() if v["key"] == mkey)
    return eng.analyze_ticker(ticker, mc, None, portfolio, risk_pct)

@st.cache_data(ttl=300)
def c_prob(ticker, mkey, days):
    mc = next(v for v in MARKET_CONFIGS.values() if v["key"] == mkey)
    return eng.profit_probability(ticker, mc, days)

@st.cache_data(ttl=600)
def c_fund(ticker):
    return eng.fetch_fundamentals_safe(ticker)

@st.cache_data(ttl=1800)
def c_news(ticker):
    return eng.fetch_news(ticker)

@st.cache_data(ttl=900)
def c_options(ticker):
    return eng.fetch_options(ticker)

@st.cache_data(ttl=300)
def c_vix():
    return eng.fetch_vix()

@st.cache_data(ttl=900)
def c_weekly(ticker):
    return eng.check_weekly_trend(ticker)

@st.cache_data(ttl=900)
def c_sectors(mkey, bm):
    mc    = next(v for v in MARKET_CONFIGS.values() if v["key"] == mkey)
    bm_df = eng.download(bm, period="6mo")
    return eng.score_sectors(mc, bm_df) if bm_df is not None else {}

# ── SIDEBAR ───────────────────────────────────────────────────────────
def sidebar(cfg: dict):
    with st.sidebar:
        _logo = os.path.join(os.path.dirname(__file__), "aarya_logo_sidebar.png")
        if os.path.exists(_logo):
            _lb64 = base64.b64encode(open(_logo, "rb").read()).decode()
            card(
                f"<div style='text-align:center;padding:8px 4px 4px;'>"
                f"<img src='data:image/png;base64,{_lb64}' "
                f"style='width:100%;max-width:240px;height:auto;'></div>"
            )
        else:
            card(
                "<div style='text-align:center;padding:14px 0 8px;'>"
                "<div style='font-size:28px;font-weight:900;color:#fff;letter-spacing:-1px;'>Aarya</div>"
                "<div style='font-size:11px;color:#1D9E75;font-weight:700;letter-spacing:2px;'>STOCKSENSE PRO</div>"
                "</div>"
            )
        st.markdown("<hr style='border-color:#1a2f4a;margin:6px 0 12px;'>", unsafe_allow_html=True)

        market = st.selectbox("🌍 Market", list(MARKET_CONFIGS.keys()),
                               index=list(MARKET_CONFIGS.keys()).index(cfg.get("market","🇺🇸 US Stocks")))
        focus  = st.selectbox("🎯 Screener Focus", list(FOCUS_MODES.keys()),
                               index=list(FOCUS_MODES.keys()).index(cfg.get("focus","🚀 High-Growth Leaders")))
        cfg.update({"market": market, "focus": focus})
        mc  = MARKET_CONFIGS[market]
        cur = mc["currency"]

        st.markdown("<hr style='border-color:#1a2f4a;margin:10px 0;'>", unsafe_allow_html=True)
        st.markdown("<div style='color:#4A7FA5;font-size:11px;font-weight:700;margin-bottom:6px;'>"
                    "💼 POSITION SIZING</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            portfolio = st.number_input(f"Capital ({cur})", value=float(cfg.get("portfolio", 10000)),
                                         step=1000.0, format="%.0f")
        with c2:
            risk_pct = st.slider("Risk %", 0.5, 3.0, float(cfg.get("risk_pct", 1.0)), 0.5)

        one_r = portfolio * risk_pct / 100
        card(f"<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:6px;"
             f"padding:8px 12px;margin:6px 0;font-size:12px;color:#4A7FA5;'>"
             f"Each 1R = <b style='color:#1D9E75;font-size:14px;'>{cur}{one_r:,.2f}</b>"
             f" &nbsp;·&nbsp; max loss per trade</div>")

        refresh = st.select_slider("🔄 Auto-refresh", [0,60,300,600,900],
                                    value=cfg.get("refresh",300),
                                    format_func=lambda x: "Off" if x==0 else f"{x//60}m")
        tv_mode = st.toggle("📺 TV Mode", value=st.session_state.get("tv_mode", False),
                             help="Big fonts, hides sidebar, 60s auto-refresh. "
                                  "Cast via Chrome → right-click → Cast…")
        st.session_state["tv_mode"] = tv_mode
        cfg.update({"portfolio": portfolio, "risk_pct": risk_pct, "refresh": refresh})
        _save(cfg)
        if tv_mode:
            st_autorefresh(interval=60_000, key="tv_refresh")
        elif refresh > 0:
            st_autorefresh(interval=refresh*1000, key="arf")

        # Regime badge
        st.markdown("<hr style='border-color:#1a2f4a;margin:10px 0;'>", unsafe_allow_html=True)
        try:
            reg = c_regime(mc["benchmark"], mc["key"])
            bc  = "#1D9E75" if reg["pass"] else "#C0392B"
            bt  = "🟢 BULL REGIME" if reg["pass"] else "🔴 BEAR REGIME"
            card(f"<div style='background:{bc}18;border:1px solid {bc};border-radius:6px;"
                 f"padding:8px;text-align:center;font-size:12px;font-weight:700;color:{bc};'>{bt}</div>")
            card(f"<div style='font-size:10px;color:#1a2f4a;text-align:center;margin-top:4px;'>"
                 f"{mc['benchmark']} {cur}{reg['price']} · 200SMA {cur}{reg['sma200']} "
                 f"({reg['pct_above']:+.1f}%)</div>")
        except Exception:
            pass
        try:
            ms   = eng.market_status(mc["key"])
            mcol = "#1D9E75" if ms["open"] else "#FF7A50"
            extra = f" · {ms['local_time']}" if ms.get("local_time") else ""
            card(f"<div style='background:{mcol}14;border:1px solid {mcol};border-radius:6px;"
                 f"padding:6px;text-align:center;font-size:11px;font-weight:700;color:{mcol};margin-top:8px;'>"
                 f"{ms['label']}{extra}</div>")
        except Exception:
            pass
        card(f"<div style='font-size:10px;color:#1a2f4a;text-align:center;margin-top:4px;'>"
             f"Hours: {mc.get('hours','—')}</div>")

        # ── User info + logout ─────────────────────────────────────
        _u = st.session_state.get("_aarya_auth")
        if _u:
            st.markdown("<hr style='border-color:#1a2f4a;margin:10px 0 8px;'>",
                        unsafe_allow_html=True)
            role_label = "🔐 Admin" if _u.get("is_admin") else "👤 User"
            card(f"<div style='text-align:center;padding:4px 0;'>"
                 f"<div style='color:#4A7FA5;font-size:10px;'>{role_label}</div>"
                 f"<div style='color:#C9D6E3;font-size:11px;font-weight:700;margin-top:2px;'>"
                 f"{_u['email']}</div></div>")
            if st.button("🚪 Logout", use_container_width=True, key="sidebar_logout"):
                auth.logout()

    return cfg, market


@st.cache_data(ttl=3600)
def c_pick_chart(ticker: str, pred_date_str: str):
    """Download ~40 calendar days from pred_date for the drill-down chart."""
    try:
        from datetime import date as _date, timedelta as _td
        start = _date.fromisoformat(pred_date_str)
        end   = start + _td(days=42)
        df    = eng.download(ticker, start=start.isoformat(), end=end.isoformat())
        return df
    except Exception:
        return None


def render_pick_chart(ticker: str, pred_date_str: str,
                      entry: float, stop: float, t1: float) -> None:
    """Small price chart showing what happened after a pick was made."""
    df = c_pick_chart(ticker, pred_date_str)
    if df is None or len(df) < 2:
        st.caption("Price data unavailable for this date range.")
        return
    cl = df["Close"].squeeze()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=cl, mode="lines",
                             line=dict(color="#4A7FA5", width=2), name="Close"))
    for lvl, lbl, col in [(entry, "Entry", "#1D9E75"),
                           (stop,  "Stop",  "#FF4D6A"),
                           (t1,    "T1",    "#FFB340")]:
        if lvl:
            fig.add_hline(y=lvl, line=dict(color=col, dash="dot", width=1.2),
                          annotation_text=lbl, annotation_position="right",
                          annotation_font_color=col)
    fig.update_layout(
        paper_bgcolor="#0F1B2D", plot_bgcolor="#0F1B2D",
        font=dict(color="#C9D6E3", size=10),
        xaxis=dict(gridcolor="#1a2f4a", showgrid=True, rangeslider_visible=False),
        yaxis=dict(gridcolor="#1a2f4a", showgrid=True, side="right"),
        legend=dict(bgcolor="#080F1C", bordercolor="#1a2f4a", font_size=9),
        margin=dict(l=8, r=64, t=24, b=8),
        title=dict(text=f"{ticker} — 40d after pick", font=dict(color="#fff", size=12)),
        height=280,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"drill_chart_{ticker}_{pred_date_str}")


# ══════════════════════════════════════════════════════════════════════
#  TAB 1 — TODAY'S PICKS
# ══════════════════════════════════════════════════════════════════════
def tab_picks(cfg, market):
    mc  = MARKET_CONFIGS[market]
    cur = mc["currency"]
    wl  = get_watchlist(cfg, market)

    col1, col2, col3 = st.columns([4,1,1])
    with col1:
        st.subheader(f"📈 Today's Picks  ·  {market}")
        st.caption(f"Focus: {cfg.get('focus','—')}  ·  {len(wl)} tickers")
    with col2:
        if st.button("🔄 Refresh Now", type="primary", use_container_width=True):
            c_screener.clear()
    with col3:
        show_table = st.toggle("Table view", value=True)

    try:
        with st.spinner("Running screener…"):
            results, regime = c_screener(tuple(wl), mc["key"], cfg["portfolio"], cfg["risk_pct"])
    except Exception as _e:
        st.error(f"Screener error: {_e}")
        return

    # Regime banner + VIX
    rc = "#1D9E75" if regime["pass"] else "#C0392B"
    try:
        vix_data = c_vix()
    except Exception:
        vix_data = {"level": "N/A", "label": "Unavailable", "color": "#4A7FA5", "regime": "unknown"}
    vix_badge = (f"<span style='background:{vix_data['color']}18;color:{vix_data['color']};"
                 f"font-size:11px;font-weight:700;padding:2px 10px;border-radius:10px;"
                 f"border:1px solid {vix_data['color']}44;margin-left:10px;'>"
                 f"VIX {vix_data['level']} — {vix_data['label']}</span>")
    card(f"<div style='background:{rc}12;border:1px solid {rc};border-radius:8px;"
         f"padding:10px 16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;'>"
         f"<span style='color:{rc};font-weight:700;font-size:14px;'>Market Regime: {regime['label']}"
         f"{vix_badge}</span>"
         f"<span style='color:#4A7FA5;font-size:11px;'>"
         f"{mc['benchmark']} {cur}{regime['price']} · 200SMA {cur}{regime['sma200']} ({regime['pct_above']:+.2f}%)"
         f"</span></div>")

    if not regime["pass"]:
        st.error("⛔ BEAR REGIME — Market is below 200 SMA. Trade with caution.")
        override = st.toggle("⚠️ Show signals anyway (Advanced — override regime filter)", value=False)
        if not override:
            st.info("Enable the toggle above to see stock signals despite the bear regime. High risk — use position sizing carefully.")
            return

    # ── 🌐 Crypto Market Dashboard (CRYPTO market only) ───────────────────
    if mc.get("is_crypto"):
        try:
            with st.spinner("Loading crypto market data…"):
                _cov = eng.fetch_crypto_overview()
        except Exception:
            _cov = {"_ok": False}
        if _cov.get("_ok"):
            _fg    = _cov.get("fear_greed")
            _fg_lbl = _cov.get("fg_label", "")
            _fg_col = ("#FF4D6A" if _fg is not None and _fg <= 30 else
                       "#FFB340" if _fg is not None and _fg <= 50 else
                       "#1D9E75" if _fg is not None and _fg >= 70 else "#4A7FA5")
            _dom   = _cov.get("btc_dominance")
            _above = _cov.get("btc_above_50dma")
            _pct   = _cov.get("btc_pct_50dma", 0)
            _vol_r = _cov.get("btc_vol_regime", "—")
            _vol_col = "#1D9E75" if _vol_r == "HIGH" else "#FF4D6A" if _vol_r == "LOW" else "#4A7FA5"
            _above_str = (f"{'ABOVE' if _above else 'BELOW'} 50dMA ({_pct:+.1f}%)"
                          if _above is not None else "—")
            card(
                f"<div style='background:#0a1525;border:1px solid #4A7FA5;"
                f"border-radius:10px;padding:12px 18px;margin-bottom:14px;'>"
                f"<div style='color:#C9D6E3;font-size:13px;font-weight:700;margin-bottom:8px;'>"
                f"🌐 Crypto Market Regime</div>"
                f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:12px;'>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>BTC Dominance</div>"
                f"<div style='color:#fff;font-weight:700;'>{f'{_dom:.1f}%' if _dom else '—'}</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>Fear & Greed</div>"
                f"<div style='color:{_fg_col};font-weight:700;'>"
                f"{f'{_fg} ({_fg_lbl})' if _fg is not None else '—'}</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>BTC vs 50dMA</div>"
                f"<div style='color:#{'1D9E75' if _above else 'FF4D6A'};font-weight:700;'>"
                f"{_above_str}</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>24h Vol Regime</div>"
                f"<div style='color:{_vol_col};font-weight:700;'>{_vol_r}</div></div>"
                f"</div></div>"
            )
        else:
            st.caption("🌐 Live crypto regime data temporarily unavailable — showing signals only.")

    buy   = [r for r in results if r["signal"]=="BUY TODAY"]
    prep  = [r for r in results if r["signal"]=="PREPARE TO BUY"]
    watch = [r for r in results if r["signal"]=="WATCH"]
    avoid = [r for r in results if r["signal"]=="DO NOT BUY"]

    # ── ⚡ PENNY SPIKE ALERTS — TOP PRIORITY ───────────────────────────
    penny_threshold_price  = 10.0 if mc.get("currency") == "$" else 500.0
    penny_threshold_change = 29.0
    penny_spikes = []
    for _r in results:
        _price_val = _r.get("price", 999)
        if _price_val < penny_threshold_price:
            _df_p = _r.get("_df")
            if _df_p is not None and len(_df_p) >= 2:
                _prev = float(_df_p["Close"].squeeze().iloc[-2])
                _curr = float(_df_p["Close"].squeeze().iloc[-1])
                _chg  = (_curr - _prev) / _prev * 100 if _prev else 0
                _volr = _r.get("volume", {}).get("ratio", 1.0)
                if _chg >= penny_threshold_change:
                    penny_spikes.append({"ticker": _r["ticker"], "price": _curr,
                                         "change": _chg, "vol_ratio": _volr})

    if penny_spikes:
        card("<div style='background:#1a0800;border:2px solid #FF7A50;border-radius:12px;"
             "padding:12px 20px;margin-bottom:14px;'>"
             "<div style='font-size:13px;font-weight:900;color:#FF7A50;letter-spacing:1px;'>"
             "⚡ PENNY STOCK SPIKE ALERT — High-Priority</div>"
             "<div style='font-size:11px;color:#FFB340;margin-top:2px;'>"
             "These stocks are under $10 and spiked &gt;29% today. Act with caution — high volatility.</div></div>")
        for ps in penny_spikes:
            _col_a, _col_b = st.columns([4, 1])
            with _col_a:
                card(f"<div style='background:#2d1a0a;border-left:4px solid #FF7A50;"
                     f"border-radius:8px;padding:10px 16px;'>"
                     f"<span style='font-size:16px;font-weight:900;color:#fff;'>⚡ {ps['ticker']}</span>"
                     f"&nbsp;&nbsp;<span style='color:#FF7A50;font-weight:700;'>+{ps['change']:.1f}%</span>"
                     f"&nbsp;&nbsp;<span style='color:#4A7FA5;font-size:12px;'>"
                     f"{cur}{ps['price']:.2f} · {ps['vol_ratio']:.1f}x vol</span>"
                     f"&nbsp;<span style='color:#FFB340;font-size:11px;'>⚠️ 15-min delayed</span></div>")
            with _col_b:
                if st.button("📧 Alert", key=f"penny_top_{ps['ticker']}"):
                    try:
                        ok, msg = notifier.send_penny_spike_alert(
                            ps["ticker"], ps["price"], ps["change"], ps["vol_ratio"], cur)
                    except Exception as _pe:
                        ok, msg = False, str(_pe)
                    st.success("Sent!" if ok else f"Failed: {msg}")
        st.markdown("---")

    # ── Super Confluence ───────────────────────────────────────────────
    confluence = [r for r in buy
                  if r.get("minervini_score", 0) >= 6
                  and r.get("rs_score", 0) >= 1.0
                  and r.get("win_prob", 0) >= 70
                  and vix_data.get("regime") not in ("high", "extreme")]
    if confluence:
        st.markdown(
            "<div style='background:linear-gradient(135deg,#0a2a1a,#0a1525);"
            "border:1.5px solid #00C48C;border-radius:12px;padding:14px 20px;margin-bottom:16px;'>"
            "<div style='font-size:13px;font-weight:900;color:#00C48C;letter-spacing:1px;margin-bottom:10px;'>"
            "⭐ SUPER CONFLUENCE — Highest Confidence Setups</div>"
            "<div style='font-size:11px;color:#4A7FA5;margin-bottom:10px;'>"
            "Minervini ≥6/8 · RS outperforming · Win prob ≥70% · Regime healthy</div>",
            unsafe_allow_html=True
        )
        sc_cols = st.columns(min(len(confluence), 3))
        for i, r in enumerate(confluence[:3]):
            with sc_cols[i]:
                rr = r.get("rr", {})
                card(
                    f"<div style='background:#0a1525;border:1px solid #00C48C44;"
                    f"border-top:3px solid #00C48C;border-radius:8px;padding:12px;text-align:center;'>"
                    f"<div style='font-size:18px;font-weight:900;color:#fff;'>{r['ticker']}</div>"
                    f"<div style='color:#00C48C;font-size:11px;font-weight:700;margin:4px 0;'>"
                    f"Win {r['win_prob']}% · Minn {r['minervini_score']}/8 · RS {r['rs_score']:.2f}</div>"
                    f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:11px;'>"
                    f"<div style='background:#121e30;border-radius:4px;padding:4px;'>"
                    f"<div style='color:#4A7FA5;'>Entry</div><div style='color:#fff;font-weight:700;'>{cur}{r['entry']}</div></div>"
                    f"<div style='background:#121e30;border-radius:4px;padding:4px;'>"
                    f"<div style='color:#FF4D6A;'>Stop</div><div style='color:#FF4D6A;font-weight:700;'>{cur}{r['stop']}</div></div>"
                    f"<div style='background:#121e30;border-radius:4px;padding:4px;'>"
                    f"<div style='color:#FFB340;'>T1</div><div style='color:#FFB340;font-weight:700;'>{cur}{rr.get('t1','—')}</div></div>"
                    f"<div style='background:#121e30;border-radius:4px;padding:4px;'>"
                    f"<div style='color:#1D9E75;'>T2</div><div style='color:#1D9E75;font-weight:700;'>{cur}{rr.get('t2','—')}</div></div>"
                    f"</div></div>"
                )
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("---")

    m1,m2,m3,m4 = st.columns(4)
    m1.metric("🟢 Buy Today",      len(buy))
    m2.metric("🟦 Prepare to Buy", len(prep))
    m3.metric("🟡 Watch",          len(watch))
    m4.metric("🔴 Avoid",          len(avoid))
    st.markdown("---")

    # Overview table
    if show_table and results:
        icons = {"BUY TODAY":"🟢","PREPARE TO BUY":"🟦","WATCH":"🟡","DO NOT BUY":"🔴"}
        try:
            rows = [{"  ": icons.get(r["signal"],""), "Ticker": r["ticker"],
                      "Signal": r["signal"], "Price": f"{cur}{r.get('price','—')}",
                      "Win %": f"{r.get('win_prob','—')}%", "Minn": f"{r.get('minervini_score','—')}/8",
                      "RS": f"{r.get('rs_score',0):.2f}", "Entry": f"{cur}{r.get('entry','—')}",
                      "Stop": f"{cur}{r.get('stop','—')}", "T1": f"{cur}{r.get('rr',{}).get('t1','—')}",
                      "T2": f"{cur}{r.get('rr',{}).get('t2','—')}"}
                     for r in results]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        except Exception as _te:
            st.warning(f"Table render error: {_te}")
        st.markdown("---")

    # Sector strength
    if mc.get("has_sectors"):
        with st.expander("🏭 Sector Strength", expanded=False):
            sectors = c_sectors(mc["key"], mc["benchmark"])
            if sectors:
                srows = [{"ETF":k,"Sector":v["name"],"Score":f"{v['score']}/4",
                           "1M":f"{v['r1m']:+.1f}%","3M":f"{v['r3m']:+.1f}%",
                           "Status":"✅ Leading" if v["leading"] else "Lagging"}
                          for k,v in sorted(sectors.items(),key=lambda x:-x[1]["score"])]
                st.dataframe(pd.DataFrame(srows), use_container_width=True, hide_index=True)

    # ── Email all buy signals ──────────────────────────────────────────
    if buy or prep:
        ecol1, ecol2 = st.columns([3, 1])
        with ecol2:
            if st.button("📧 Email Buy Signals", use_container_width=True):
                sent_any = False
                for r in (buy + prep):
                    try:
                        ok, msg = notifier.send_buy_alert(r)
                    except Exception:
                        ok = False
                    if ok:
                        sent_any = True
                if sent_any:
                    st.success("✅ Buy signal emails sent!")
                else:
                    st.error("Email failed — check Alert Settings.")

    # Signal cards — each group in a collapsible expander
    _group_cfg = [
        (buy,  "🟢 BUY TODAY",       True),   # open by default — most actionable
        (prep, "🟦 PREPARE TO BUY",  True),   # open — worth seeing
        (watch,"🟡 WATCH",           False),  # collapsed — informational
        (avoid,"🔴 DO NOT BUY",      False),  # collapsed — least urgent
    ]
    for group, label, expanded in _group_cfg:
        if not group:
            continue
        with st.expander(f"{label}  ({len(group)})", expanded=expanded):
            cols = st.columns(min(len(group), 2))
            for i, r in enumerate(group):
                with cols[i%2]:
                    try:
                        st.markdown(signal_card(r, cfg), unsafe_allow_html=True)
                        with st.expander(f"📋 {r['ticker']} — Full Breakdown"):
                            fd = c_fund(r["ticker"]) or {"error": True}
                            if not fd.get("error"):
                                fa,fb,fc,fd4 = st.columns(4)
                                fa.metric("Revenue Growth",  fmt(fd.get("rev_growth"),suffix="%",decimals=1) if fd.get("rev_growth") is not None else "N/A")
                                fb.metric("Earnings Growth", fmt(fd.get("earn_growth"),suffix="%",decimals=1) if fd.get("earn_growth") is not None else "N/A")
                                fc.metric("Analyst Rating",  fd.get("rec","N/A"))
                                fd4.metric("Inst. Holding",  fmt(fd.get("inst_pct"),suffix="%",decimals=1) if fd.get("inst_pct") is not None else "N/A")
                                st.caption(f"Sector: {fd.get('sector','—')}  ·  P/E: {fd.get('pe','—')}  ·  PEG: {fd.get('peg','—')}  ·  Target: {cur}{fd.get('target','—')}")
                            try:
                                news = c_news(r["ticker"]) or []
                            except Exception:
                                news = []
                            if news:
                                st.markdown("**Latest News**")
                                for n in news[:3]:
                                    card(f"<div style='font-size:12px;padding:3px 0;'>"
                                         f"<span style='color:{n['col']};'>{n['sent']}</span>&nbsp;"
                                         f"<a href='{n['link']}' target='_blank' style='color:#C9D6E3;'>{n['title']}</a>"
                                         f"<span style='color:#1a2f4a;'> — {n['pub']}</span></div>")
                            if r.get("_df") is not None:
                                try:
                                    st.plotly_chart(candlestick(r["_df"], r, r["ticker"]),
                                                    use_container_width=True,
                                                    key=f"picks_chart_{r['ticker']}")
                                except Exception:
                                    st.caption("Chart unavailable.")
                    except Exception as _card_err:
                        st.warning(f"{r.get('ticker','?')}: display error — {_card_err}")

    # ── 🔻 Contrarian / Oversold-Quality picks ────────────────────────
    st.markdown("---")
    with st.expander("🔻 Contrarian / Oversold-Quality Picks", expanded=False):
        st.caption("Mean-reversion track: quality names beaten down to 52-week-range lows. "
                   "Different rules from the trend picks above.")
        try:
            with st.spinner("Scanning contrarian setups…"):
                contrarian_picks = scanner_contrarian.scan_contrarian(
                    mc, {"_df": None}, cfg["portfolio"], cfg["risk_pct"])
        except Exception as _ce:
            st.caption(f"Contrarian scan unavailable: {_ce}")
            contrarian_picks = []
        if not contrarian_picks:
            st.info("No contrarian setups in this market right now.")
        else:
            for p in contrarian_picks:
                try:
                    rr = p.get("rr", {})
                    conf = None
                    try:
                        conf = ml_predictor.score_prediction(p)
                    except Exception:
                        pass
                    conf_html = (f"<span style='color:#FFB340;font-size:11px;font-weight:700;'>"
                                 f"ML {conf:.0f}%</span>" if conf else "")
                    card(
                        f"<div style='background:#0a1525;border:1px solid #4A7FA5;"
                        f"border-radius:10px;padding:12px 18px;margin-bottom:10px;'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                        f"<span style='font-size:18px;font-weight:900;color:#fff;'>{p['ticker']}</span>"
                        f"<span style='background:#4A7FA5;color:#050d15;font-size:10px;"
                        f"font-weight:700;padding:3px 10px;border-radius:10px;'>{p['signal']}</span></div>"
                        f"<div style='color:#C9D6E3;font-size:12px;margin-top:6px;'>{p.get('verdict','')[:200]}</div>"
                        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px;font-size:12px;'>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>Entry</div>"
                        f"<div style='color:#fff;font-weight:700;'>{cur}{p['entry']}</div></div>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>Stop</div>"
                        f"<div style='color:#FF4D6A;font-weight:700;'>{cur}{p['stop']}</div></div>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>T1</div>"
                        f"<div style='color:#FFB340;font-weight:700;'>{cur}{rr.get('t1','—')}</div></div>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>Win</div>"
                        f"<div style='color:#1D9E75;font-weight:700;'>{p.get('win_prob','?')}%</div></div>"
                        f"</div>{conf_html}</div>")
                except Exception as _ce2:
                    st.caption(f"display: {_ce2}")

    # ── ⚡ Penny Momentum Scanner ─────────────────────────────────────────
    _penny_key = mc.get("key", "")
    if _penny_key in ("US", "IN"):
        st.markdown("---")
        _penny_thresh = "under $10" if _penny_key == "US" else "under ₹300"
        with st.expander(f"⚡ Penny Momentum Scanner ({_penny_thresh})", expanded=False):
            st.caption(
                "Surfaces penny stocks showing volume + momentum — different from the spike alert above. "
                "High risk — size positions small."
            )
            try:
                with st.spinner("Scanning penny momentum…"):
                    _penny_picks = scanner_penny.scan_penny(
                        mc, {"_df": None}, cfg["portfolio"], cfg["risk_pct"])
            except Exception as _pe:
                st.caption(f"Penny scan unavailable: {_pe}")
                _penny_picks = []

            if not _penny_picks:
                st.info("No penny momentum setups in this market right now.")
            else:
                _penny_sig_col = {
                    "PENNY MOMENTUM BUY":   "#FFB340",
                    "PENNY MOMENTUM WATCH": "#4A7FA5",
                    "PENNY CAUTION":        "#FF7A50",
                }
                _penny_cols = st.columns(min(len(_penny_picks), 2))
                for _pi, _pp in enumerate(_penny_picks[:10]):
                    with _penny_cols[_pi % 2]:
                        try:
                            _prr  = _pp.get("rr", {})
                            _pcol = _penny_sig_col.get(_pp.get("signal", ""), "#FFB340")
                            _pconf = None
                            try:
                                _pconf = ml_predictor.score_prediction(_pp)
                            except Exception:
                                pass
                            _conf_html = (
                                f"<span style='color:#1D9E75;font-size:11px;font-weight:700;'>"
                                f"ML {_pconf:.0f}%</span>" if _pconf else ""
                            )
                            card(
                                f"<div style='background:#0a1525;border:1px solid {_pcol};"
                                f"border-radius:10px;padding:12px 18px;margin-bottom:10px;'>"
                                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                                f"<span style='font-size:18px;font-weight:900;color:#fff;'>⚡ {_pp['ticker']}</span>"
                                f"<span style='background:{_pcol};color:#050d15;font-size:10px;"
                                f"font-weight:700;padding:3px 10px;border-radius:10px;'>{_pp['signal']}</span></div>"
                                f"<div style='color:#C9D6E3;font-size:12px;margin-top:6px;'>"
                                f"{_pp.get('verdict','')[:200]}</div>"
                                f"<div style='display:grid;grid-template-columns:repeat(4,1fr);"
                                f"gap:6px;margin-top:8px;font-size:12px;'>"
                                f"<div><div style='color:#4A7FA5;font-size:10px;'>Price</div>"
                                f"<div style='color:#fff;font-weight:700;'>{cur}{_pp['price']}</div></div>"
                                f"<div><div style='color:#4A7FA5;font-size:10px;'>Vol</div>"
                                f"<div style='color:#FFB340;font-weight:700;'>{_pp.get('vol_ratio',1):.1f}x</div></div>"
                                f"<div><div style='color:#4A7FA5;font-size:10px;'>RSI</div>"
                                f"<div style='color:#C9D6E3;font-weight:700;'>{_pp.get('rsi','—')}</div></div>"
                                f"<div><div style='color:#4A7FA5;font-size:10px;'>Stop</div>"
                                f"<div style='color:#FF4D6A;font-weight:700;'>{cur}{_pp.get('stop','—')}</div></div>"
                                f"</div>"
                                f"<div style='display:grid;grid-template-columns:repeat(3,1fr);"
                                f"gap:6px;margin-top:6px;font-size:11px;'>"
                                f"<div style='background:#121e30;border-radius:4px;padding:4px;text-align:center;'>"
                                f"<div style='color:#4A7FA5;font-size:10px;'>T1 +25%</div>"
                                f"<div style='color:#FFB340;font-weight:700;'>{cur}{_pp.get('t1_price', _prr.get('t1','—'))}</div></div>"
                                f"<div style='background:#121e30;border-radius:4px;padding:4px;text-align:center;'>"
                                f"<div style='color:#4A7FA5;font-size:10px;'>T2 +50%</div>"
                                f"<div style='color:#1D9E75;font-weight:700;'>{cur}{_pp.get('t2_price', _prr.get('t2','—'))}</div></div>"
                                f"<div style='background:#121e30;border-radius:4px;padding:4px;text-align:center;'>"
                                f"<div style='color:#4A7FA5;font-size:10px;'>T3 +100%</div>"
                                f"<div style='color:#4A7FA5;font-weight:700;'>{cur}{_prr.get('t3','—')}</div></div>"
                                f"</div>"
                                f"{_conf_html}</div>"
                            )
                        except Exception as _pe2:
                            st.caption(f"Display error: {_pe2}")

            card("<div style='background:#2d1a0a;border:1px solid #FF7A50;border-radius:8px;"
                 "padding:8px 14px;margin-top:4px;'>"
                 "<span style='color:#FFB340;font-size:11px;'>⚠️ <b>Penny stocks are extremely volatile.</b> "
                 "Risk only what you can lose. Never bet more than 0.5–1% of portfolio per penny trade. "
                 "Data is 15-min delayed — verify live price before acting.</span></div>")

    # ── 🤖 Chatbot panel — "Ask Aarya about today's picks" ─────────────
    st.markdown("---")
    with st.expander("🤖 Ask Aarya about today's picks", expanded=False):
        q_key = f"chat_q_{market}"
        a_key = f"chat_a_{market}"
        cq, cb = st.columns([4, 1])
        with cq:
            question = st.text_input("Question",
                placeholder="e.g. Why is NVDA top of the list today?",
                label_visibility="collapsed", key=q_key)
        with cb:
            ask = st.button("Ask", use_container_width=True, key=f"chat_ask_{market}")
        if ask and question.strip():
            with st.spinner("Asking Aarya…"):
                try:
                    answer = notifier.get_gemini_question_answer(question.strip())
                except Exception as _ge:
                    answer = f"AI temporarily unavailable: {_ge}"
            st.session_state[a_key] = answer
        if st.session_state.get(a_key):
            st.info(st.session_state[a_key])


# ══════════════════════════════════════════════════════════════════════
#  TAB 2 — AI COPILOT
# ══════════════════════════════════════════════════════════════════════
def tab_copilot(cfg, market):
    st.subheader("🤖 Aarya AI Copilot — 7 Analyst Personas")
    st.caption("All 7 analyst roles summarised below. Select a role to dive deeper.")
    st.info(
        "**Live vs. Example data:** The **🎯 Swing Trader** persona runs a live real-time scan "
        "every time you open it. All other personas show **representative example data** — "
        "they illustrate the method so you understand how each analyst thinks. "
        "For live prices on any stock, use the **🔍 Stock Checker** tab."
    )

    # ── MASTER SUMMARY ─────────────────────────────────────────────────
    st.markdown("### 📋 Master Summary — Top Pick from Every Persona")
    summary = [
        ("💼 Hedge Fund",        "NVDA",         "#00C48C", "HF Flow Score 14 — Tech sector sees strongest institutional accumulation this month."),
        ("💎 Value Analyst",     "GOOGL",         "#FFB340", "P/E 22, PEG 1.1, +14% revenue growth — best value-with-growth combo in US market."),
        ("🎯 Swing Trader",      "NVDA",          "#00C48C", "BUY TODAY signal with 2:1+ R/R. Minervini 6/8, RS outperforming, EMA hold confirmed."),
        ("📊 Earnings Scanner",  "NVDA",          "#00C48C", "Earnings ~May 28 — historically beats by +8.3%. High IV, calls DTE 30+ recommended."),
        ("📈 Wealth Compounder", "VGT",           "#1D9E75", "Lowest cost tech ETF — 20.1% 10Y CAGR, 0.10% expense. Best compounder in catalogue."),
        ("🗓️ Weekly Screener",   "BTC-USD",       "#4A7FA5", "Above 10 EMA weekly, RSI 55.8 — DCA weekly signal active for crypto allocation."),
        ("🌐 Global Builder",    "NVDA+HDFCBANK", "#9B59B6", "AI theme in US + Finance theme in India = cross-market confluence A+ setup."),
    ]
    for persona_name, top_pick, color, reason in summary:
        card(
            f"<div style='display:flex;align-items:flex-start;gap:14px;background:#0a1525;"
            f"border-left:4px solid {color};border:1px solid #1a2f4a;border-left:4px solid {color};"
            f"border-radius:8px;padding:10px 16px;margin-bottom:8px;'>"
            f"<div style='min-width:160px;'>"
            f"<div style='font-size:10px;color:#4A7FA5;text-transform:uppercase;letter-spacing:.5px;'>{persona_name}</div>"
            f"<div style='font-size:16px;font-weight:900;color:#fff;margin-top:2px;'>{top_pick}</div>"
            f"</div>"
            f"<div style='font-size:12px;color:#C9D6E3;line-height:1.6;padding-top:4px;border-left:1px solid #1a2f4a;padding-left:14px;'>"
            f"{reason}</div>"
            f"</div>"
        )

    st.markdown("---")
    st.markdown("### 🔍 Dive Into a Persona")
    personas = ["💼 Hedge Fund — Sector Flows","💎 Value Analyst — Undervalued Gems",
                "🎯 Swing Trader — 2:1+ RR Setups","📊 Earnings Scanner",
                "📈 Wealth Compounder — Top ETFs","🗓️ Weekly Screener — DCA Signals",
                "🌐 Global Builder — US + India + Crypto"]
    persona = st.selectbox("Select Analyst Role", personas, key="copilot_persona_select")
    st.markdown("---")

    if "Hedge Fund" in persona:
        st.markdown("### 💼 Institutional Sector Flow Dashboard")
        st.caption("HF Flow Score > 10 = institutions actively accumulating. Buy stocks in those sectors.")
        data = [{"Sector":"Technology","ETF":"XLK","HF Flow Score":14,"1M %":"+8.2%","3M %":"+18.1%","Signal":"🟢 OVERWEIGHT"},
                {"Sector":"Semiconductors","ETF":"SOXX","HF Flow Score":13,"1M %":"+11.4%","3M %":"+22.3%","Signal":"🟢 OVERWEIGHT"},
                {"Sector":"Communication","ETF":"XLC","HF Flow Score":11,"1M %":"+6.4%","3M %":"+14.2%","Signal":"🟢 OVERWEIGHT"},
                {"Sector":"Consumer Discret.","ETF":"XLY","HF Flow Score":10,"1M %":"+5.9%","3M %":"+12.7%","Signal":"🟢 OVERWEIGHT"},
                {"Sector":"Financials","ETF":"XLF","HF Flow Score":9,"1M %":"+3.1%","3M %":"+9.4%","Signal":"🟡 NEUTRAL"},
                {"Sector":"Healthcare","ETF":"XLV","HF Flow Score":7,"1M %":"+1.4%","3M %":"+5.2%","Signal":"🟡 NEUTRAL"},
                {"Sector":"Energy","ETF":"XLE","HF Flow Score":5,"1M %":"-2.1%","3M %":"-4.8%","Signal":"🔴 UNDERWEIGHT"}]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        st.info("**Rule:** Buy stocks that belong to OVERWEIGHT sectors and show a BUY TODAY signal in Tab 1. That is A+ confluence.")

    elif "Value Analyst" in persona:
        st.markdown("### 💎 Value + Growth Screener — P/E < 25, PEG < 1.5")
        data = [{"Ticker":"GOOGL","Name":"Alphabet","P/E":22.1,"PEG":1.1,"Rev Growth":"+14%","Analyst":"Strong Buy","Verdict":"✅ A+"},
                {"Ticker":"META","Name":"Meta Platforms","P/E":24.8,"PEG":1.3,"Rev Growth":"+21%","Analyst":"Strong Buy","Verdict":"✅ A+"},
                {"Ticker":"JPM","Name":"JP Morgan","P/E":13.2,"PEG":1.2,"Rev Growth":"+12%","Analyst":"Buy","Verdict":"✅ A"},
                {"Ticker":"RELIANCE.NS","Name":"Reliance Ind.","P/E":21.3,"PEG":1.1,"Rev Growth":"+18%","Analyst":"Strong Buy","Verdict":"✅ A+"},
                {"Ticker":"INFY.NS","Name":"Infosys","P/E":19.8,"PEG":1.3,"Rev Growth":"+9%","Analyst":"Buy","Verdict":"✅ A"},
                {"Ticker":"BRK-B","Name":"Berkshire Hath.","P/E":18.4,"PEG":0.9,"Rev Growth":"+8%","Analyst":"Buy","Verdict":"✅ A"}]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        st.info("**Rule:** P/E < 25 + PEG < 1.5 + positive revenue growth = safe value-with-growth play. Hold 3–8 weeks.")

    elif "Swing Trader" in persona:
        st.markdown("### 🎯 Live Swing Setups — 2:1+ Risk-Reward")
        mc  = MARKET_CONFIGS["🇺🇸 US Stocks"]
        wl  = mc["growth"][:10]
        with st.spinner("Scanning for 2:1 setups…"):
            results, regime = c_screener(tuple(wl), mc["key"], cfg["portfolio"], cfg["risk_pct"])
        buys = [r for r in results if r["signal"] in ("BUY TODAY","PREPARE TO BUY")]
        if buys:
            for r in buys[:4]:
                st.markdown(signal_card(r, cfg), unsafe_allow_html=True)
        else:
            st.info("No 2:1+ setups firing right now. Market may need a consolidation day.")

    elif "Earnings" in persona:
        st.markdown("### 📊 Earnings Opportunity Calendar")
        st.caption("Binary event plays — high-volatility windows around earnings dates.")
        data = [{"Ticker":"NVDA","Date":"~May 28","Est. EPS":"$5.89","Rev Est.":"$43.2B","Hist. Surprise":"+8.3%","Play":"Buy calls, DTE 30+"},
                {"Ticker":"MSFT","Date":"~Jul 23","Est. EPS":"$3.11","Rev Est.":"$68.4B","Hist. Surprise":"+4.2%","Play":"Buy calls, DTE 30+"},
                {"Ticker":"META","Date":"~Jul 30","Est. EPS":"$5.25","Rev Est.":"$39.1B","Hist. Surprise":"+6.1%","Play":"Bull call spread"},
                {"Ticker":"AMZN","Date":"~Aug 1","Est. EPS":"$1.04","Rev Est.":"$148.6B","Hist. Surprise":"+7.8%","Play":"Bull call spread"},
                {"Ticker":"TCS.NS","Date":"~Jul 10","Est. EPS":"₹28.4","Rev Est.":"₹62,000Cr","Hist. Surprise":"+2.8%","Play":"Hold stock"}]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        st.warning("⚠️ Always define max loss before earnings plays. Options with DTE 20–48 days reduce time-decay risk.")

    elif "Wealth Compounder" in persona:
        st.markdown("### 📈 Best Long-Term ETFs — Lowest Cost, Highest Return")
        data = [{"ETF":"VGT","Name":"Vanguard IT","Expense":"0.10%","10Y CAGR":"20.1%","Type":"Technology","Rating":"⭐⭐⭐⭐⭐"},
                {"ETF":"QQQ","Name":"NASDAQ-100","Expense":"0.20%","10Y CAGR":"18.5%","Type":"Tech Index","Rating":"⭐⭐⭐⭐⭐"},
                {"ETF":"VOO","Name":"Vanguard S&P 500","Expense":"0.03%","10Y CAGR":"13.2%","Type":"Index","Rating":"⭐⭐⭐⭐⭐"},
                {"ETF":"SCHD","Name":"Schwab Dividend","Expense":"0.06%","10Y CAGR":"11.4%","Type":"Dividend","Rating":"⭐⭐⭐⭐"},
                {"ETF":"VTI","Name":"Total US Market","Expense":"0.03%","10Y CAGR":"12.8%","Type":"Total Mkt","Rating":"⭐⭐⭐⭐⭐"},
                {"ETF":"VEA","Name":"Dev. Markets","Expense":"0.05%","10Y CAGR":"8.2%","Type":"Global","Rating":"⭐⭐⭐"}]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        if st.button("➕ Add All to US Watchlist", type="primary"):
            cfg = save_custom_watchlist(cfg,"🇺🇸 US Stocks",["VOO","QQQ","VGT","SCHD","VTI","VEA","VWO","GLD"])
            st.success("✅ 8 ETFs added to your US Custom watchlist!")

    elif "Weekly Screener" in persona:
        st.markdown("### 🗓️ Weekly Trend Screener — DCA / SIP Signals")
        st.caption("Weekly close > 10 EMA + RSI > 50 = ACCUMULATE. Perfect for systematic monthly investing.")
        data = [{"Asset":"SPY","Weekly Close":"Above 10 EMA","RSI (Weekly)":"61.2","Signal":"🟢 ACCUMULATE","Action":"DCA monthly"},
                {"Asset":"QQQ","Weekly Close":"Above 10 EMA","RSI (Weekly)":"58.4","Signal":"🟢 ACCUMULATE","Action":"DCA monthly"},
                {"Asset":"NVDA","Weekly Close":"Above 10 EMA","RSI (Weekly)":"66.1","Signal":"🟢 ACCUMULATE","Action":"Add on pullbacks"},
                {"Asset":"TSLA","Weekly Close":"Below 10 EMA","RSI (Weekly)":"44.3","Signal":"🔴 AVOID","Action":"Wait for reclaim"},
                {"Asset":"BTC-USD","Weekly Close":"Above 10 EMA","RSI (Weekly)":"55.8","Signal":"🟢 ACCUMULATE","Action":"DCA weekly"},
                {"Asset":"RELIANCE.NS","Weekly Close":"Above 10 EMA","RSI (Weekly)":"53.1","Signal":"🟢 ACCUMULATE","Action":"SIP monthly"}]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        st.info("**DCA Rule:** Only add to ACCUMULATE assets. Pause contributions if signal flips to AVOID.")

    elif "Global Builder" in persona:
        st.markdown("### 🌐 Cross-Market Confluence Themes")
        st.caption("When the same theme fires across US + India + Crypto simultaneously — that is an A+ macro setup.")
        data = [{"Market":"🇺🇸 US","Theme":"AI & Compute","Tickers":"NVDA, MSFT, GOOGL, ARM","Strength":"⭐⭐⭐⭐⭐"},
                {"Market":"🇺🇸 US","Theme":"Cybersecurity","Tickers":"CRWD, PANW, ZS, AXON","Strength":"⭐⭐⭐⭐"},
                {"Market":"🇮🇳 India","Theme":"Banking & Finance","Tickers":"HDFCBANK.NS, ICICIBANK.NS, BAJFINANCE.NS","Strength":"⭐⭐⭐⭐"},
                {"Market":"🇮🇳 India","Theme":"Green Energy","Tickers":"ADANIGREEN.NS, TATAPOWER.NS, NHPC.NS","Strength":"⭐⭐⭐"},
                {"Market":"₿ Crypto","Theme":"Layer-1 Protocols","Tickers":"ETH-USD, SOL-USD, AVAX-USD","Strength":"⭐⭐⭐⭐"},
                {"Market":"₿ Crypto","Theme":"AI Tokens","Tickers":"FET-USD, RNDR-USD, INJ-USD","Strength":"⭐⭐⭐"}]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### 🧠 Aarya Executive Summary")
    c1,c2,c3 = st.columns(3)
    with c1:
        card("<div style='background:#0a1525;border:1px solid #1D9E75;border-radius:8px;padding:14px;'>"
             "<div style='color:#1D9E75;font-weight:700;margin-bottom:6px;'>🔥 Leading Sectors</div>"
             "<div style='color:#C9D6E3;font-size:12px;line-height:1.8;'>"
             "Technology · Semiconductors · Communication<br>"
             "HF Flow 11–14 = institutional accumulation active</div></div>")
    with c2:
        card("<div style='background:#0a1525;border:1px solid #FFB340;border-radius:8px;padding:14px;'>"
             "<div style='color:#FFB340;font-weight:700;margin-bottom:6px;'>💎 Best Value Plays</div>"
             "<div style='color:#C9D6E3;font-size:12px;line-height:1.8;'>"
             "GOOGL · META · JPM · RELIANCE.NS<br>"
             "P/E &lt;25, PEG &lt;1.5, positive revenue growth</div></div>")
    with c3:
        card("<div style='background:#0a1525;border:1px solid #4A7FA5;border-radius:8px;padding:14px;'>"
             "<div style='color:#4A7FA5;font-weight:700;margin-bottom:6px;'>🎯 A+ Confluence Rule</div>"
             "<div style='color:#C9D6E3;font-size:12px;line-height:1.8;'>"
             "BUY TODAY signal + leading sector<br>+ ACCUMULATE weekly + positive news = enter</div></div>")


# ══════════════════════════════════════════════════════════════════════
#  TAB 3 — MUTUAL FUNDS & COMPOUNDING SIMULATOR
# ══════════════════════════════════════════════════════════════════════
def tab_funds(cfg, market):
    mc  = MARKET_CONFIGS[market]
    cur = mc["currency"]
    st.subheader("📊 Mutual Funds & ETF Planner")
    st.caption("Browse top funds, load any fund by name, and simulate 30-year wealth compounding.")
    t_cat, t_sim, t_swp = st.tabs(["🗂️ Fund Catalogue", "🔢 Compounding Simulator (SIP)", "💸 SWP Calculator"])

    with t_cat:
        region = st.radio("Filter by region", ["All","US","India","Global"], horizontal=True)
        rows   = FUND_CATALOGUE if region=="All" else [f for f in FUND_CATALOGUE if f[5]==region]
        df_f   = pd.DataFrame(rows, columns=["Symbol","Name","Type","Expense %","Est. 10Y CAGR %","Region"])
        st.dataframe(df_f, use_container_width=True, hide_index=True)
        st.markdown("---")
        st.markdown("#### 🔍 Find & Load Any Fund")
        q = st.text_input("Search by name or symbol (e.g. Vanguard, SBI, ARKK)")
        if q:
            matches = [f for f in FUND_CATALOGUE if q.lower() in f[1].lower() or q.upper() in f[0]]
            if matches:
                sel = st.selectbox("Select", [f"{f[0]} — {f[1]}" for f in matches])
                sym = sel.split(" — ")[0]
                fund = next(f for f in FUND_CATALOGUE if f[0]==sym)
                if st.button("📥 Load into Simulator & SWP"):
                    st.session_state["mf_sym"]  = sym
                    st.session_state["mf_cagr"] = fund[4]
                    st.session_state["mf_name"] = fund[1]
                    st.success(f"Loaded {fund[1]} ({fund[4]}% CAGR) — switch to Simulator or SWP tab.")
            else:
                st.info("Not in catalogue. Enter ticker manually in the Simulator tab.")

    with t_sim:
        # ── Fund search + picker ───────────────────────────────────────
        _region_pref = "India" if cur == "₹" else ("US" if cur == "$" else "Global")
        _fsearch = st.text_input(
            "🔍 Search fund by name or type",
            placeholder="e.g. SBI, Vanguard, ELSS, Tech, Blue Chip…",
            key="sim_fund_search",
        )
        _sorted_funds = sorted(FUND_CATALOGUE, key=lambda x: (x[5] != _region_pref, x[5], x[1]))
        if _fsearch.strip():
            _q = _fsearch.strip().lower()
            _filtered_funds = [f for f in _sorted_funds
                               if _q in f[1].lower() or _q in f[0].lower() or _q in f[2].lower() or _q in f[5].lower()]
        else:
            _filtered_funds = _sorted_funds

        if _filtered_funds:
            _cat_opts = ["— Select a fund —"] + [
                f"{f[1]}  —  Est. {f[4]}% p.a.  [{f[2]}, {f[5]}]"
                for f in _filtered_funds
            ]
            _sel = st.selectbox("📂 Select fund", _cat_opts, key="sim_fund_sel")
            if _sel and _sel != "— Select a fund —":
                _fname = _sel.split("  —  ")[0].strip()
                _picked = next((f for f in _filtered_funds if f[1] == _fname), None)
                if _picked:
                    st.session_state["mf_name"] = _picked[1]
                    st.session_state["mf_cagr"] = _picked[4]
        else:
            st.info(f"No funds found for '{_fsearch}'. Try 'SBI', 'Vanguard', 'ELSS', or 'Tech'.")

        name   = st.session_state.get("mf_name", "Custom Fund / ETF")
        preset = float(st.session_state.get("mf_cagr", 12.0))
        st.caption(f"**Simulating:** {name}  ·  Return rate pre-filled from selection — adjust if needed.")
        c1,c2,c3,c4 = st.columns(4)
        _lump_default  = 10_000.0 if cur == "₹" else 1_000.0
        _sip_default   = 1_000.0  if cur == "₹" else 100.0
        _lump_step     = 1_000.0  if cur == "₹" else 100.0
        _sip_step      = 500.0    if cur == "₹" else 10.0
        with c1: lump = st.number_input(f"Lump Sum ({cur})", 0.0, value=_lump_default, step=_lump_step, format="%.0f")
        with c2: sip  = st.number_input(f"Monthly SIP ({cur})", 0.0, value=_sip_default, step=_sip_step, format="%.0f")
        with c3: cagr = st.slider("CAGR %", 4.0, 30.0, min(preset, 30.0), 0.5)
        with c4: infl = st.slider("Inflation %", 0.0, 12.0, 5.0, 0.5)

        sim = eng.compound(lump, sip, cagr, infl, 30)

        # ── Quick-look cards: 5 / 10 / 20 / 30 year highlights ────────
        _milestones = {r["year"]: r for r in sim["milestones"]}
        _hl_cols = st.columns(4)
        for _i, _yr in enumerate([5, 10, 20, 30]):
            _m = _milestones.get(_yr, {})
            _nom = _m.get("nominal", 0)
            _inv = _m.get("invested", 0)
            _gain = ((_nom - _inv) / _inv * 100) if _inv > 0 else 0
            with _hl_cols[_i]:
                st.metric(
                    f"{_yr}-Year Value",
                    f"{cur}{_nom:,.0f}",
                    f"+{_gain:.0f}% gain on {cur}{_inv:,.0f} invested"
                )

        # Milestone table
        df_m = pd.DataFrame(sim["milestones"])
        df_m.columns = ["Year","Nominal","Real (Infl-Adj.)","Invested","Gain %"]
        for col in ["Nominal","Real (Infl-Adj.)","Invested"]:
            df_m[col] = df_m[col].apply(lambda x: f"{cur}{x:,.0f}")
        df_m["Gain %"] = df_m["Gain %"].apply(lambda x: f"+{x:.1f}%")
        st.markdown("##### Full 30-Year Breakdown")
        st.dataframe(df_m, use_container_width=True, hide_index=True)

        # Chart
        yrs  = [r["year"]     for r in sim["yearly"]]
        nom  = [r["nominal"]  for r in sim["yearly"]]
        real = [r["real"]     for r in sim["yearly"]]
        inv  = [r["invested"] for r in sim["yearly"]]
        fig  = go.Figure()
        fig.add_trace(go.Scatter(x=yrs,y=nom, name="Nominal",line=dict(color="#1D9E75",width=2.5)))
        fig.add_trace(go.Scatter(x=yrs,y=real,name="Real (after inflation)",
                                  line=dict(color="#4A7FA5",width=2,dash="dash")))
        fig.add_trace(go.Scatter(x=yrs,y=inv, name="Cash Invested",
                                  line=dict(color="#FFB340",width=1.5,dash="dot"),
                                  fill="tozeroy",fillcolor="rgba(255,179,64,.06)"))
        fig.update_layout(paper_bgcolor="#0F1B2D",plot_bgcolor="#0F1B2D",
                           font=dict(color="#C9D6E3"),height=360,
                           xaxis=dict(title="Years",gridcolor="#1a2f4a"),
                           yaxis=dict(title=f"Value ({cur})",gridcolor="#1a2f4a",side="right"),
                           legend=dict(bgcolor="#080F1C",bordercolor="#1a2f4a"),
                           margin=dict(l=8,r=56,t=24,b=24))
        st.plotly_chart(fig, use_container_width=True, key="sip_growth_chart")
        st.caption("🟢 Nominal growth · 🔵 Real purchasing power (after inflation) · 🟠 Total cash you put in. "
                   "The gap between green and orange is your actual profit. Plan targets using the blue (real) line.")

    with t_swp:
        st.markdown("### 💸 Systematic Withdrawal Plan (SWP) Calculator")
        st.caption(
            "SWP = withdraw a fixed amount every month from your corpus while the remaining balance keeps growing. "
            "Used by retirees and anyone wanting regular passive income from investments."
        )

        # ── Fund search + picker ───────────────────────────────────────
        _swp_region = "India" if cur == "₹" else ("US" if cur == "$" else "Global")
        _swp_search = st.text_input(
            "🔍 Search fund by name or type",
            placeholder="e.g. SBI, Vanguard, ELSS, Tech, Blue Chip…",
            key="swp_fund_search",
        )
        _swp_sorted = sorted(FUND_CATALOGUE, key=lambda x: (x[5] != _swp_region, x[5], x[1]))
        if _swp_search.strip():
            _swp_q = _swp_search.strip().lower()
            _swp_filtered = [f for f in _swp_sorted
                             if _swp_q in f[1].lower() or _swp_q in f[0].lower()
                             or _swp_q in f[2].lower() or _swp_q in f[5].lower()]
        else:
            _swp_filtered = _swp_sorted

        if _swp_filtered:
            _swp_opts = ["— Select a fund —"] + [
                f"{f[1]}  —  Est. {f[4]}% p.a.  [{f[2]}, {f[5]}]"
                for f in _swp_filtered
            ]
            _swp_sel = st.selectbox("📂 Select fund", _swp_opts, key="swp_fund_sel")
            if _swp_sel and _swp_sel != "— Select a fund —":
                _swp_fname = _swp_sel.split("  —  ")[0].strip()
                _swp_picked = next((f for f in _swp_filtered if f[1] == _swp_fname), None)
                if _swp_picked:
                    st.session_state["mf_name"] = _swp_picked[1]
                    st.session_state["mf_cagr"] = _swp_picked[4]
        else:
            st.info(f"No funds found for '{_swp_search}'. Try 'SBI', 'Vanguard', 'ELSS', or 'Tech'.")

        _swp_fund_name   = st.session_state.get("mf_name", "")
        _swp_cagr_preset = float(st.session_state.get("mf_cagr", 10.0))
        if _swp_fund_name:
            st.caption(f"Return rate pre-filled from: **{_swp_fund_name}**")

        # Sensible defaults per currency
        _swp_corpus_default  = 1_000_000.0 if cur == "₹" else 100_000.0
        _swp_monthly_default = 10_000.0    if cur == "₹" else 500.0

        sw1, sw2, sw3, sw4 = st.columns(4)
        with sw1:
            swp_corpus = st.number_input(
                f"Starting Corpus ({cur})", min_value=0.0, value=_swp_corpus_default,
                step=10_000.0 if cur == "₹" else 1_000.0, format="%.0f",
                help="Total invested/saved amount you start withdrawals from."
            )
        with sw2:
            swp_monthly = st.number_input(
                f"Monthly Withdrawal ({cur})", min_value=0.0, value=_swp_monthly_default,
                step=500.0 if cur == "₹" else 50.0, format="%.0f",
                help="How much you take out every month."
            )
        with sw3:
            swp_cagr = st.slider(
                "Expected Return %", 4.0, 20.0, min(_swp_cagr_preset, 20.0), 0.5,
                help="Annual return your corpus earns while you're withdrawing."
            )
        with sw4:
            swp_years = st.slider(
                "Plan Duration (years)", 1, 40, 20, 1,
                help="How many years you plan to keep withdrawing."
            )

        # ── SWP calculation ────────────────────────────────────────────
        monthly_rate = swp_cagr / 100 / 12
        balance = swp_corpus
        swp_rows = []
        exhausted_yr = None
        total_withdrawn = 0.0

        for yr in range(1, swp_years + 1):
            yr_start = balance
            yr_withdrawn = 0.0
            for _ in range(12):
                if balance <= 0:
                    break
                balance += balance * monthly_rate
                withdrawal = min(swp_monthly, balance)
                balance -= withdrawal
                yr_withdrawn += withdrawal
                total_withdrawn += withdrawal
            balance = max(balance, 0.0)
            swp_rows.append({
                "Year": yr,
                "Opening Balance": round(yr_start, 0),
                "Withdrawn": round(yr_withdrawn, 0),
                "Closing Balance": round(balance, 0),
                "Balance Status": "✅ Positive" if balance > 0 else "🔴 Exhausted",
            })
            if balance <= 0 and exhausted_yr is None:
                exhausted_yr = yr

        # ── Summary metrics ────────────────────────────────────────────
        final_balance = swp_rows[-1]["Closing Balance"]
        ms1, ms2, ms3, ms4 = st.columns(4)
        ms1.metric("Starting Corpus", f"{cur}{swp_corpus:,.0f}")
        ms2.metric("Total Withdrawn", f"{cur}{total_withdrawn:,.0f}",
                   f"{total_withdrawn/swp_corpus*100:.1f}% of corpus" if swp_corpus > 0 else "")
        ms3.metric("Final Balance", f"{cur}{final_balance:,.0f}",
                   "✅ Corpus survives" if final_balance > 0 else "🔴 Corpus exhausted")
        if exhausted_yr:
            ms4.metric("Corpus Exhausted", f"Year {exhausted_yr}",
                       f"After {exhausted_yr} years")
        else:
            ms4.metric("Corpus Lasts", f"{swp_years}+ years", "Still positive at plan end")

        # ── Sustainability check ───────────────────────────────────────
        if exhausted_yr:
            card(
                f"<div style='background:#2d0a0a;border-left:4px solid #FF4D6A;border-radius:8px;"
                f"padding:12px 16px;margin-bottom:12px;'>"
                f"<div style='color:#FF4D6A;font-weight:700;font-size:14px;'>⚠️ Corpus runs out in Year {exhausted_yr}</div>"
                f"<div style='color:#C9D6E3;font-size:12px;margin-top:6px;'>"
                f"Monthly withdrawal {cur}{swp_monthly:,.0f} is too high for a {swp_cagr}% return. "
                f"Try reducing withdrawal by {cur}{swp_monthly*0.1:,.0f} or increasing return rate.</div></div>"
            )
        else:
            card(
                f"<div style='background:#0a2d1a;border-left:4px solid #00C48C;border-radius:8px;"
                f"padding:12px 16px;margin-bottom:12px;'>"
                f"<div style='color:#00C48C;font-weight:700;font-size:14px;'>✅ Plan is sustainable for {swp_years} years</div>"
                f"<div style='color:#C9D6E3;font-size:12px;margin-top:6px;'>"
                f"Your corpus of {cur}{swp_corpus:,.0f} can support {cur}{swp_monthly:,.0f}/month "
                f"for {swp_years} years at {swp_cagr}% p.a., with {cur}{final_balance:,.0f} remaining at the end.</div></div>"
            )

        # ── Year-by-year table ─────────────────────────────────────────
        df_swp = pd.DataFrame(swp_rows)
        for col_name in ["Opening Balance", "Withdrawn", "Closing Balance"]:
            df_swp[col_name] = df_swp[col_name].apply(lambda x: f"{cur}{x:,.0f}")
        st.dataframe(df_swp, use_container_width=True, hide_index=True)

        # ── Chart ──────────────────────────────────────────────────────
        chart_yrs  = [r["Year"] for r in swp_rows]
        # Get raw numeric values for chart
        balances_raw = [swp_rows[i]["Closing Balance"] for i in range(len(swp_rows))]
        withdrawn_cum = []
        cum = 0.0
        for r in swp_rows:
            # parse back to float from formatted string
            raw_val = float(str(r["Withdrawn"]).replace(cur, "").replace(",", ""))
            cum += raw_val
            withdrawn_cum.append(round(cum, 0))
        # Use numeric closing balances before formatting
        bal_numeric = [swp_rows[i]["Closing Balance"] for i in range(len(swp_rows))]

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=chart_yrs, y=bal_numeric, name="Remaining Corpus",
                              marker_color="#1D9E75"))
        fig2.add_trace(go.Scatter(x=chart_yrs, y=withdrawn_cum, name="Cumulative Withdrawn",
                                   line=dict(color="#FF7A50", width=2.5),
                                   yaxis="y2"))
        fig2.add_hline(y=0, line_dash="dot", line_color="#FF4D6A", line_width=1)
        fig2.update_layout(
            paper_bgcolor="#0F1B2D", plot_bgcolor="#0F1B2D",
            font=dict(color="#C9D6E3"), height=360,
            xaxis=dict(title="Year", gridcolor="#1a2f4a"),
            yaxis=dict(title=f"Remaining Corpus ({cur})", gridcolor="#1a2f4a"),
            yaxis2=dict(title=f"Cumulative Withdrawal ({cur})", overlaying="y",
                        side="right", gridcolor="#1a2f4a"),
            legend=dict(bgcolor="#080F1C", bordercolor="#1a2f4a"),
            margin=dict(l=8, r=56, t=24, b=24),
            barmode="overlay",
        )
        st.plotly_chart(fig2, use_container_width=True, key="swp_drawdown_chart")
        st.caption(
            "🟢 Bars = remaining corpus each year · 🟠 Line = total cumulative withdrawals. "
            "When the bars reach zero, the corpus is exhausted. "
            "Adjust withdrawal amount or return rate to keep the bars above zero throughout."
        )

        st.info(
            "**SWP Tips:**\n"
            "- For retirement: keep monthly withdrawal ≤ 0.7% of corpus per month (safe withdrawal rate ~8% p.a.)\n"
            "- India equity mutual funds: 10% LTCG tax applies on gains > ₹1 lakh/year — factor this in\n"
            "- Increase return assumption only if invested in equity (not FD/debt funds)\n"
            "- Review the plan yearly and adjust withdrawal amount as needed"
        )


# ══════════════════════════════════════════════════════════════════════
#  TAB 4 — STOCK CHECKER
# ══════════════════════════════════════════════════════════════════════
def tab_checker(cfg, market):
    mc  = MARKET_CONFIGS[market]
    cur = mc["currency"]
    st.subheader("🔍 Stock Checker — Predictive Analytics on Any Asset")
    st.caption(
        "Type any stock, crypto, ETF or index. Get: trade verdict · win probability · "
        "bull/base/bear targets · fundamentals · news sentiment · AI briefing · "
        "**options trade recommendation** · options chain. Scroll down after analysis for all sections."
    )

    ex = {"🇺🇸 US Stocks":"NVDA","🇮🇳 India NSE":"RELIANCE.NS","₿ Crypto":"ETH-USD",
          "🇬🇧 UK":"SHEL.L","🇪🇺 Europe":"SAP.DE","🇨🇦 Canada":"SHOP.TO","🇯🇵 Japan":"7203.T"}

    c1,c2,c3 = st.columns([3,1,1])
    with c1:
        ticker_raw = st.text_input("Enter Ticker", placeholder=f"e.g. {ex.get(market,'NVDA')}").upper().strip()
        ticker = eng.auto_suffix(ticker_raw, mc["key"]) if ticker_raw else ""
        if ticker and ticker != ticker_raw:
            st.caption(f"Auto-corrected: **{ticker_raw}** → **{ticker}**")
    with c2: days   = st.number_input("Hold (days)", 1, 365, 5, 1)
    with c3: invest = st.number_input(f"Invest ({cur})", 0.0,
                                       value=float(cfg.get("portfolio",10000)*0.1), step=100.0, format="%.0f")
    go_btn = st.button("🔍 Analyse Now", type="primary")

    if not ticker or not go_btn:
        card("<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:8px;"
             "padding:24px;text-align:center;color:#4A7FA5;'>"
             "Enter any ticker and click <b>Analyse Now</b>.<br><br>"
             "You get: <b>Trade Verdict</b> · <b>Win Probability %</b> · "
             "<b>Bull / Base / Bear price targets</b> · <b>What your investment becomes</b> · "
             "<b>Company fundamentals</b> · <b>News sentiment</b> · <b>Options chain</b>"
             "</div>")
        return

    try:
        with st.spinner(f"Fetching live data for {ticker}…"):
            r   = c_analyze(ticker, mc["key"], cfg["portfolio"], cfg["risk_pct"])
            pp  = c_prob(ticker, mc["key"], int(days))
            fd  = c_fund(ticker) or {"error": True}
            nws = c_news(ticker) or []
    except Exception as _e:
        st.error(f"Error fetching data for **{ticker}**: {_e}")
        return

    if r is None and (isinstance(pp, dict) and "error" in pp):
        st.error(f"Could not fetch data for **{ticker}**. Check the ticker symbol and try again.")
        return

    # Verdict
    if r:
        vc = sig_color(r["signal"])
        card(f"<div style='background:{vc}10;border-left:5px solid {vc};"
             f"border-radius:8px;padding:16px 20px;margin-bottom:14px;'>"
             f"<div style='font-size:22px;font-weight:900;color:{vc};margin-bottom:6px;'>"
             f"{r['signal']} — {ticker} @ {cur}{r['price']}</div>"
             f"<div style='color:#C9D6E3;font-size:14px;line-height:1.7;'>{r['verdict']}</div>"
             f"</div>")
        st.markdown(signal_card(r, cfg), unsafe_allow_html=True)

    # ── 📡 Live Price (Twelve Data) ────────────────────────────────────
    _lp_key = f"live_price_{ticker}"
    _lp_col1, _lp_col2 = st.columns([2, 5])
    with _lp_col1:
        if st.button("📡 Get Live Price", key=f"lp_btn_{ticker}",
                     help="Fetches near-real-time price from Twelve Data (much fresher than the chart above)"):
            with st.spinner("Fetching live price…"):
                _lq = eng.get_quote_td(ticker)
                st.session_state[_lp_key] = _lq if _lq else "unavailable"
    _lq = st.session_state.get(_lp_key)
    if _lq and _lq != "unavailable":
        _chg    = _lq["change_pct"]
        _chgcol = "#00C48C" if _chg >= 0 else "#FF4D6A"
        _chgsign = "+" if _chg >= 0 else ""
        with _lp_col2:
            card(
                f"<div style='background:#0a1525;border:1px solid #1a2f4a;"
                f"border-radius:8px;padding:10px 16px;display:flex;align-items:center;gap:20px;'>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>LIVE PRICE</div>"
                f"<div style='color:#fff;font-weight:900;font-size:20px;'>"
                f"{cur}{_lq['price']:,.2f}</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>Change</div>"
                f"<div style='color:{_chgcol};font-weight:700;font-size:14px;'>"
                f"{_chgsign}{_chg:.2f}%</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>Day High</div>"
                f"<div style='color:#C9D6E3;font-weight:600;'>{cur}{_lq['high']:,.2f}</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>Day Low</div>"
                f"<div style='color:#C9D6E3;font-weight:600;'>{cur}{_lq['low']:,.2f}</div></div>"
                f"<div><div style='color:#4A7FA5;font-size:10px;'>Prev Close</div>"
                f"<div style='color:#C9D6E3;font-weight:600;'>{cur}{_lq['prev_close']:,.2f}</div></div>"
                f"<div style='margin-left:auto;color:#4A7FA5;font-size:10px;'>"
                f"via {_lq['source']}<br>{_lq['timestamp']}</div>"
                f"</div>"
            )
    elif _lq == "unavailable":
        with _lp_col2:
            st.caption("Live price unavailable — Twelve Data key missing or symbol not supported.")

    # Profit probability
    if "error" not in pp:
        st.markdown(f"---\n### 🎯 Profit Probability — {days} day(s)")
        m1,m2,m3,m4 = st.columns(4)
        cc = pp["conf_col"]
        m1.metric("Win Probability", f"{pp['win_prob']}%",   f"base {pp['base_rate']}%")
        m2.metric("Confidence",      pp["confidence"],        f"{pp['n_pass']}/7 signals")
        m3.metric("RS Score",        f"{pp['rs_score']:.2f}", "outperforming" if pp["rs_score"]>=1 else "lagging")
        m4.metric("Daily Volatility",f"{pp['atr_pct']:.1f}%","ATR/price")

        s1,s2,s3 = st.columns(3)
        for col,lbl,price_,pct_,border in [
            (s1,"🟢 BULL CASE",pp["bull"],pp["bull_pct"],"#00C48C"),
            (s2,"⚡ BASE CASE",pp["base"],pp["base_pct"],"#1D9E75"),
            (s3,"🔴 BEAR CASE",pp["bear"],pp["bear_pct"],"#FF4D6A"),
        ]:
            diff  = price_ - pp["price"]
            sign  = "+" if diff>=0 else ""
            proj  = invest*(1+pct_/100)
            with col:
                card(f"<div style='background:#0a1525;border:1px solid {border};"
                     f"border-radius:10px;padding:16px;text-align:center;'>"
                     f"<div style='color:{border};font-size:12px;font-weight:700;'>{lbl}</div>"
                     f"<div style='color:#fff;font-size:26px;font-weight:900;margin:6px 0;'>{cur}{price_}</div>"
                     f"<div style='color:{border};font-size:13px;font-weight:700;'>"
                     f"{sign}{pct_:.1f}%  ·  {sign}{cur}{abs(diff):.2f}</div>"
                     f"<div style='color:#4A7FA5;font-size:11px;margin-top:4px;'>"
                     f"{cur}{invest:,.0f} → {cur}{proj:,.0f}</div></div>")

        with st.expander("🔬 Signal Breakdown"):
            chips = "".join(
                "<span style='display:inline-block;margin:3px;padding:4px 10px;"
                "border-radius:5px;font-size:12px;font-weight:600;"
                "background:" + ("rgba(0,196,140,.15)" if v else "rgba(255,77,106,.12)") + ";"
                "color:" + ("#00C48C" if v else "#FF4D6A") + ";'>"
                + ("✅" if v else "❌") + " " + k + "</span>"
                for k,v in pp["conds"].items()
            )
            st.markdown(chips, unsafe_allow_html=True)
            card(f"<div style='background:#0a1525;border:1px solid {cc}22;border-radius:6px;"
                 f"padding:10px 14px;margin-top:8px;color:#C9D6E3;font-size:13px;'>"
                 f"<b style='color:{cc};'>Aarya: </b>{pp['outlook']}</div>")

    # Fundamentals + expandable description
    if not fd.get("error"):
        st.markdown("---\n### 📋 Company Profile")
        fa,fb,fc,fd4 = st.columns(4)
        fa.metric("Revenue Growth",  fmt(fd.get("rev_growth"),suffix="%",decimals=1) if fd.get("rev_growth") is not None else "N/A")
        fb.metric("Earnings Growth", fmt(fd.get("earn_growth"),suffix="%",decimals=1) if fd.get("earn_growth") is not None else "N/A")
        fc.metric("Analyst Rating",  fd.get("rec","N/A"))
        fd4.metric("Inst. Holding",  fmt(fd.get("inst_pct"),suffix="%",decimals=1) if fd.get("inst_pct") is not None else "N/A")
        st.caption(f"Sector: {fd.get('sector','—')}  ·  Industry: {fd.get('industry','—')}  ·  "
                   f"P/E: {fd.get('pe','—')}  ·  Forward P/E: {fd.get('fwd_pe','—')}  ·  "
                   f"PEG: {fd.get('peg','—')}  ·  Analyst Target: {cur}{fd.get('target','—')} "
                   f"({fd.get('analysts',0)} analysts)")
        desc = fd.get("description", "")
        if desc:
            with st.expander("📖 Full Company Description", expanded=False):
                st.markdown(f"<div style='color:#C9D6E3;font-size:13px;line-height:1.8;'>{desc}</div>",
                            unsafe_allow_html=True)

    # News — Alpha Vantage first, fallback to yfinance
    st.markdown("---\n### 📰 News & Sentiment")
    try:
        av_news = eng.fetch_news_av(ticker, mc.get("suffix", ""))
    except Exception:
        av_news = []
    display_news = av_news if av_news else (nws or [])
    news_source  = "Alpha Vantage" if av_news else "Yahoo Finance"
    if display_news:
        st.caption(f"Source: {news_source} · {len(display_news)} articles")
        for n in display_news:
            summary = n.get("summary", "")
            score   = n.get("score")
            score_txt = f" · score {score:+.3f}" if score is not None else ""
            if summary:
                with st.expander(f"{n['sent']}  {n['title'][:80]}{'…' if len(n['title'])>80 else ''}", expanded=False):
                    card(f"<div style='background:#0a1525;border-left:3px solid {n['col']};"
                         f"border-radius:6px;padding:10px 14px;'>"
                         f"<span style='color:{n['col']};font-size:11px;font-weight:700;'>{n['sent']}{score_txt}</span>"
                         f"&nbsp;<a href='{n['link']}' target='_blank' style='color:#C9D6E3;font-size:13px;font-weight:600;'>{n['title']}</a>"
                         f"<span style='color:#4A7FA5;font-size:10px;'> — {n['pub']}</span>"
                         f"<div style='color:#C9D6E3;font-size:12px;line-height:1.6;margin-top:8px;'>{summary[:400]}</div>"
                         f"</div>")
            else:
                card(f"<div style='background:#0a1525;border-left:3px solid {n['col']};"
                     f"border-radius:6px;padding:8px 14px;margin-bottom:6px;'>"
                     f"<span style='color:{n['col']};font-size:11px;font-weight:700;'>{n['sent']}</span>"
                     f"&nbsp;<a href='{n['link']}' target='_blank' style='color:#C9D6E3;font-size:13px;'>{n['title']}</a>"
                     f"<span style='color:#4A7FA5;font-size:10px;'> — {n['pub']}</span></div>")
    else:
        st.info("No news found for this ticker.")

    # Gemini AI
    st.markdown("---\n### 🤖 Gemini AI Briefing")
    gcol1, gcol2 = st.columns([1, 1])
    with gcol1:
        if st.button("✨ Generate AI Briefing", type="primary", use_container_width=True):
            with st.spinner("Asking Gemini…"):
                try:
                    briefing = notifier.get_gemini_briefing(ticker, r)
                except Exception as _ge:
                    briefing = f"Gemini error: {_ge}"
            st.session_state[f"briefing_{ticker}"] = briefing

    briefing_text = st.session_state.get(f"briefing_{ticker}", "")
    if briefing_text:
        card(f"<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:8px;"
             f"padding:14px 18px;color:#C9D6E3;font-size:13px;line-height:1.7;'>"
             f"<div style='color:#9B59B6;font-size:11px;font-weight:700;margin-bottom:6px;'>"
             f"GEMINI AI · {ticker}</div>{briefing_text}</div>")

    st.markdown("**💬 Ask Gemini about this stock:**")
    q_key = f"q_{ticker}"
    question = st.text_input("e.g. What are the main risks? What does this company do?",
                              key=q_key, label_visibility="collapsed",
                              placeholder="Ask anything about this stock…")
    if st.button("Ask", key=f"ask_{ticker}") and question:
        with st.spinner("Gemini is thinking…"):
            try:
                answer = notifier.get_gemini_answer(ticker, question, r)
            except Exception as _ge2:
                answer = f"Gemini error: {_ge2}"
        st.session_state[f"ans_{ticker}"] = answer

    ans = st.session_state.get(f"ans_{ticker}", "")
    if ans:
        card(f"<div style='background:#0a1525;border-left:3px solid #9B59B6;"
             f"border-radius:6px;padding:12px 16px;color:#C9D6E3;font-size:13px;line-height:1.7;'>"
             f"<b style='color:#9B59B6;'>Gemini:</b> {ans}</div>")

    # Options
    if not mc.get("is_crypto"):
        st.markdown("---\n### 🎯 Options — Trade Recommendation & Chain")
        st.caption("Below: AI-calculated options trade recommendation (CALL or PUT) + full options chain. US stocks only.")

        # ── 📖 Options 101 — what is an options contract? ─────────────────
        with st.expander("📖 New to options? — Click here to understand how this works"):
            st.markdown("""
**What is an options contract?**

An option gives you the **right** (but not obligation) to buy or sell a stock at a fixed price before a certain date.

| Term | Meaning |
|------|---------|
| **CALL option** | You profit when the stock goes **UP** |
| **PUT option** | You profit when the stock goes **DOWN** |
| **Strike price** | The fixed price the contract is for |
| **Expiry date** | Last day the contract is valid |
| **Premium** | Price you pay *per share* to buy the contract |

**The most important rule: 1 contract = 100 shares**

So if the premium is $2.50, buying 1 contract costs you **$2.50 × 100 = $250 total**.
If the premium rises to $4.00, selling that contract earns **$4.00 × 100 = $400** — a $150 profit.

**How to actually buy/sell this option (step by step):**
1. Open your broker app (Zerodha, Robinhood, IBKR, etc.)
2. Search for the stock ticker (e.g. AAPL)
3. Tap **Options Chain** or **Derivatives**
4. Select the **expiry date** shown in the recommendation below
5. Select **CALL** or **PUT** as recommended
6. Find the row with the **strike price** shown below
7. Tap **Buy** → enter number of contracts → confirm
8. Watch the premium vs your T1/T2/Stop targets (shown below)
9. When target hits → tap **Sell to Close** on the same contract

**Risk reminder:** You can only lose what you paid (the premium). A $250 option can drop to $0 — never risk more than you can afford to lose on a single trade.
""")

        # ── 🎯 Options Trade Recommendation ──────────────────────────────
        st.markdown("#### Options Trade Recommendation")
        if r:
            try:
                with st.spinner("Calculating options recommendation…"):
                    _orec = eng.recommend_option(ticker, r, cfg["portfolio"], cfg.get("risk_pct", 2.0))
            except Exception as _ore:
                _orec = {"skip_reason": str(_ore)}
        else:
            _orec = {"skip_reason": "Run stock analysis first to get a recommendation."}

        if not _orec or "skip_reason" in _orec:
            st.info(f"⚪ {(_orec or {}).get('skip_reason', 'Recommendation not available.')}")
        else:
            _sig_now = (r or {}).get("signal", "")
            if "WATCH" in _sig_now or "PREPARE" in _sig_now:
                st.warning("⚠️ Signal is not yet a full BUY — treat this as a **preview setup**. "
                           "Wait for the stock to confirm (price above key levels, volume surge) before entering.")
            _odir    = _orec["direction"]
            _ocol    = "#1D9E75" if _odir == "CALL" else "#FF4D6A"
            _iv_lbl  = _orec.get("iv_label", "NORMAL")
            _iv_col  = "#FF4D6A" if _iv_lbl == "HIGH" else "#1D9E75" if _iv_lbl == "LOW" else "#4A7FA5"
            _earn_warn = (" &#9888; <b style='color:#FFB340;'>Earnings in window</b>"
                          if _orec.get("earnings_in_window") else "")
            _delta_str = f"Delta {_orec['delta']:.2f}"
            _theta_str = f"  Theta {cur}{abs(_orec['theta']):.3f}/day" if _orec.get("theta") else ""
            _vega_str  = f"  Vega {_orec['vega']:.3f}" if _orec.get("vega") else ""

            # ── Contract summary card ───────────────────────────────────────
            _total_cost       = _orec['contracts'] * _orec['premium_entry'] * 100
            _cost_per_1       = round(_orec['premium_entry'] * 100, 2)
            _t1_total         = round(_orec['premium_t1'] * 100, 2)
            _t2_total         = round(_orec['premium_t2'] * 100, 2) if _orec.get('premium_t2') else None
            _stop_total       = round(_orec['premium_stop'] * 100, 2)
            _hold_days_label  = f"{_orec.get('max_hold_days', _orec['dte'])} days max — exit by {_orec.get('exit_by_date', _orec['expiry'])}"

            card(
                f"<div style='background:#0a1525;border:2px solid {_ocol};"
                f"border-radius:10px;padding:14px 18px;margin-bottom:12px;'>"

                # Title row
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>"
                f"<span style='font-size:15px;font-weight:900;color:#fff;'>"
                f"{ticker} — {_odir} &nbsp;"
                f"<span style='color:#4A7FA5;font-size:12px;font-weight:400;'>"
                f"{cur}{_orec['strike']:.2f} strike · {_orec['expiry']} · {_orec['dte']} days left</span></span>"
                f"<span style='background:{_ocol};color:#050d15;font-size:11px;"
                f"font-weight:700;padding:3px 12px;border-radius:10px;'>{_odir}</span></div>"

                # ── ROW 1: Entry costs ──────────────────────────────────────
                f"<div style='background:#060e1c;border-radius:8px;padding:10px 14px;margin-bottom:10px;'>"
                f"<div style='color:#4A7FA5;font-size:10px;font-weight:700;letter-spacing:1px;"
                f"margin-bottom:8px;'>WHAT YOU PAY TO ENTER</div>"
                f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px;'>"

                f"<div><div style='color:#4A7FA5;font-size:10px;'>Contracts to buy</div>"
                f"<div style='color:#FFB340;font-weight:700;font-size:18px;'>{_orec['contracts']}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>recommended quantity</div></div>"

                f"<div><div style='color:#4A7FA5;font-size:10px;'>Cost per 1 contract</div>"
                f"<div style='color:#FFB340;font-weight:700;font-size:18px;'>{cur}{_cost_per_1:,.0f}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>{cur}{_orec['premium_entry']:.2f} quote × 100 shares</div></div>"

                f"<div><div style='color:#4A7FA5;font-size:10px;'>Total you pay</div>"
                f"<div style='color:#00C48C;font-weight:700;font-size:18px;'>{cur}{_total_cost:,.0f}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>{_orec['contracts']} contract(s) × {cur}{_cost_per_1:,.0f}</div></div>"

                f"</div></div>"

                # ── ROW 2: Exit targets ─────────────────────────────────────
                f"<div style='background:#060e1c;border-radius:8px;padding:10px 14px;margin-bottom:10px;'>"
                f"<div style='color:#4A7FA5;font-size:10px;font-weight:700;letter-spacing:1px;"
                f"margin-bottom:8px;'>WHEN TO CLOSE (premium per contract = quote × 100)</div>"
                f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px;'>"

                f"<div style='background:#1a1200;border-radius:6px;padding:8px;'>"
                f"<div style='color:#FFB340;font-size:10px;font-weight:700;'>💰 SELL HALF — Target 1</div>"
                f"<div style='color:#FFB340;font-weight:700;font-size:16px;'>{cur}{_t1_total:,.0f}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>per contract · +{_orec.get('pnl_pct_at_t1',0):.0f}% profit</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>stock ~{cur}{_orec.get('t1_stock_price','—')}</div></div>"

                + (
                f"<div style='background:#0a1f0a;border-radius:6px;padding:8px;'>"
                f"<div style='color:#00C48C;font-size:10px;font-weight:700;'>🎯 SELL REST — Target 2</div>"
                f"<div style='color:#00C48C;font-weight:700;font-size:16px;'>{cur}{_t2_total:,.0f}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>per contract · +{_orec.get('pnl_pct_at_t2',0):.0f}% profit</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>stock ~{cur}{_orec.get('t2_stock_price','—')}</div></div>"
                if _t2_total else
                f"<div style='background:#0a1f0a;border-radius:6px;padding:8px;'>"
                f"<div style='color:#00C48C;font-size:10px;font-weight:700;'>🎯 SELL ALL — Target 1</div>"
                f"<div style='color:#00C48C;font-weight:700;font-size:16px;'>{cur}{_t1_total:,.0f}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>per contract · +{_orec.get('pnl_pct_at_t1',0):.0f}% profit</div></div>"
                ) +

                f"<div style='background:#1f0a0a;border-radius:6px;padding:8px;'>"
                f"<div style='color:#FF4D6A;font-size:10px;font-weight:700;'>🛑 STOP LOSS — EXIT ALL</div>"
                f"<div style='color:#FF4D6A;font-weight:700;font-size:16px;'>{cur}{_stop_total:,.0f}</div>"
                f"<div style='color:#4A7FA5;font-size:10px;'>per contract · -50% · exit immediately</div></div>"

                f"</div></div>"

                # ── ROW 3: Hold duration ────────────────────────────────────
                f"<div style='background:#0d1020;border-radius:6px;padding:8px 14px;"
                f"display:flex;justify-content:space-between;align-items:center;'>"
                f"<span style='color:#4A7FA5;font-size:11px;'>⏱ <b style='color:#FFB340;'>Hold up to:</b> "
                f"{_hold_days_label}</span>"
                f"<span style='color:#4A7FA5;font-size:10px;'>{_delta_str}{_theta_str} · "
                f"IV {_orec['iv']:.0f}% <span style='color:{_iv_col};'>({_iv_lbl})</span> · "
                f"breakeven {cur}{_orec['breakeven_stock']:.2f}</span>"
                f"</div>"

                f"</div>"
            )

            # ── TRADING PLAN — explicit buy/sell/stop rules ─────────────────
            _mhd   = _orec.get("max_hold_days")
            _ebd   = _orec.get("exit_by_date", "")
            _pt1   = _orec["premium_t1"]
            _pt2   = _orec.get("premium_t2")
            _pstop = _orec["premium_stop"]
            _ps1   = _orec.get("pnl_pct_at_t1", 0)
            _ps2   = _orec.get("pnl_pct_at_t2", 0)
            _t1s   = _orec.get("t1_stock_price", "—")
            _t2s   = _orec.get("t2_stock_price", "—")

            _plan_rows = (
                f"<tr>"
                f"<td style='padding:8px 12px;background:#0e2a1f;border:1px solid #1a2f4a;"
                f"color:#00C48C;font-weight:700;font-size:12px;'>🟢 BUY NOW</td>"
                f"<td style='padding:8px 12px;background:#0e2a1f;border:1px solid #1a2f4a;"
                f"color:#fff;font-size:12px;'>Enter {_orec['contracts']} contract(s) at "
                f"<b>{cur}{_orec['premium_entry']:.2f}</b> premium each (max {cur}{_orec['max_risk_usd']:,.0f})</td>"
                f"<td style='padding:8px 12px;background:#0e2a1f;border:1px solid #1a2f4a;"
                f"color:#4A7FA5;font-size:11px;'>Stock currently at {cur}{_orec.get('t1_stock_price') and r.get('price','—') or '—'}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
                f"color:#FFB340;font-weight:700;font-size:12px;'>💰 SELL HALF at T1</td>"
                f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
                f"color:#FFB340;font-size:12px;'>When premium ≥ <b>{cur}{_pt1:.2f}</b> "
                f"(+{_ps1:.0f}% profit)</td>"
                f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
                f"color:#4A7FA5;font-size:11px;'>Stock near {cur}{_t1s}</td>"
                f"</tr>"
            )
            if _pt2:
                _plan_rows += (
                    f"<tr>"
                    f"<td style='padding:8px 12px;background:#0a1525;border:1px solid #1a2f4a;"
                    f"color:#1D9E75;font-weight:700;font-size:12px;'>🎯 SELL REST at T2</td>"
                    f"<td style='padding:8px 12px;background:#0a1525;border:1px solid #1a2f4a;"
                    f"color:#1D9E75;font-size:12px;'>When premium ≥ <b>{cur}{_pt2:.2f}</b> "
                    f"(+{_ps2:.0f}% profit)</td>"
                    f"<td style='padding:8px 12px;background:#0a1525;border:1px solid #1a2f4a;"
                    f"color:#4A7FA5;font-size:11px;'>Stock near {cur}{_t2s}</td>"
                    f"</tr>"
                )
            _plan_rows += (
                f"<tr>"
                f"<td style='padding:8px 12px;background:#2d0a0a;border:1px solid #1a2f4a;"
                f"color:#FF4D6A;font-weight:700;font-size:12px;'>🛑 STOP LOSS</td>"
                f"<td style='padding:8px 12px;background:#2d0a0a;border:1px solid #1a2f4a;"
                f"color:#FF4D6A;font-size:12px;'>EXIT ALL if premium drops to <b>{cur}{_pstop:.2f}</b> "
                f"(-50%). No waiting — exit immediately.</td>"
                f"<td style='padding:8px 12px;background:#2d0a0a;border:1px solid #1a2f4a;"
                f"color:#4A7FA5;font-size:11px;'>Protects remaining capital</td>"
                f"</tr>"
            )
            if _mhd and _ebd:
                _plan_rows += (
                    f"<tr>"
                    f"<td style='padding:8px 12px;background:#1a1a0a;border:1px solid #1a2f4a;"
                    f"color:#FFB340;font-weight:700;font-size:12px;'>⏱ TIME STOP</td>"
                    f"<td style='padding:8px 12px;background:#1a1a0a;border:1px solid #1a2f4a;"
                    f"color:#C9D6E3;font-size:12px;'>Exit by <b>{_ebd}</b> ({_mhd} days max). "
                    f"Theta decay accelerates — don't hold longer.</td>"
                    f"<td style='padding:8px 12px;background:#1a1a0a;border:1px solid #1a2f4a;"
                    f"color:#4A7FA5;font-size:11px;'>Even if undecided — sell it</td>"
                    f"</tr>"
                )

            card(
                f"<div style='background:#080F1C;border:1px solid {_ocol}33;"
                f"border-radius:10px;padding:14px 18px;margin-bottom:12px;'>"
                f"<div style='font-size:13px;font-weight:900;color:{_ocol};margin-bottom:10px;'>"
                f"📋 OPTIONS TRADING PLAN — {ticker} {_odir}</div>"
                f"<table style='width:100%;border-collapse:collapse;'>"
                f"<tr style='background:#0a1525;'>"
                f"<th style='padding:6px 12px;color:#4A7FA5;font-size:10px;text-align:left;width:20%;'>Action</th>"
                f"<th style='padding:6px 12px;color:#4A7FA5;font-size:10px;text-align:left;width:50%;'>Rule</th>"
                f"<th style='padding:6px 12px;color:#4A7FA5;font-size:10px;text-align:left;width:30%;'>Reference</th>"
                f"</tr>"
                + _plan_rows +
                f"</table>"
                f"</div>"
            )

            if _orec.get("earnings_in_window"):
                st.warning("⚠️ Earnings fall inside the contract window — this is a binary event. "
                           "The option can gain OR lose 50%+ on earnings day alone. "
                           "Size position at half the normal amount.")
            if _iv_lbl == "HIGH":
                st.warning("⚠️ Implied Volatility is HIGH right now. Premium is expensive. "
                           "Wait for a 1-2 day pullback in the stock to enter at lower IV and lower cost.")

            st.caption("Options involve significant risk. This is a planning tool — "
                       "verify live prices before placing any trade. US stocks only.")

            # ── 📡 Live Premium Monitor ───────────────────────────────────────
            st.markdown("---\n#### 📡 Live Premium Monitor")
            st.caption("Check the current option premium right now and get a SELL / HOLD / STOP signal.")
            _lpm_key = f"lpm_{ticker}_{_orec.get('expiry','')}"
            if st.button("📡 Check Current Premium Now", key=f"lpm_btn_{ticker}",
                         type="primary", use_container_width=False):
                with st.spinner("Fetching live option price…"):
                    try:
                        import alpaca_client as _alp
                        _status = _alp.check_option_status(_orec)
                        st.session_state[_lpm_key] = _status
                    except Exception as _lpm_e:
                        st.session_state[_lpm_key] = {
                            "status": "ERROR", "action": str(_lpm_e),
                            "color": "#4A7FA5", "current_mid": None,
                            "message": str(_lpm_e),
                        }

            _lpm = st.session_state.get(_lpm_key)
            if _lpm:
                _sc   = _lpm["color"]
                _smid = _lpm.get("current_mid")
                _spnl = _lpm.get("pnl_pct")
                _src  = _lpm.get("source", "—")
                _siv  = _lpm.get("iv")
                _sdelta = _lpm.get("delta")

                # Status header
                card(
                    f"<div style='background:#0a1525;border:2px solid {_sc};"
                    f"border-radius:10px;padding:14px 18px;'>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;margin-bottom:10px;'>"
                    f"<span style='font-size:18px;font-weight:900;color:{_sc};'>"
                    f"{_lpm['action']}</span>"
                    f"<span style='color:#4A7FA5;font-size:10px;'>via {_src}</span></div>"
                    + (
                        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);"
                        f"gap:8px;font-size:12px;margin-bottom:10px;'>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>Current Premium</div>"
                        f"<div style='color:{_sc};font-weight:900;font-size:16px;'>"
                        f"{cur}{_smid:.2f}</div>"
                        f"<div style='color:#4A7FA5;font-size:10px;'>(per share)</div></div>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>Entry Was</div>"
                        f"<div style='color:#fff;font-weight:700;'>{cur}{_lpm['entry']:.2f}</div></div>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>P&L</div>"
                        f"<div style='color:{_sc};font-weight:700;'>"
                        f"{f'+{_spnl:.1f}%' if _spnl and _spnl >= 0 else f'{_spnl:.1f}%' if _spnl else '—'}"
                        f"</div></div>"
                        f"<div><div style='color:#4A7FA5;font-size:10px;'>IV Now</div>"
                        f"<div style='color:#C9D6E3;font-weight:700;'>"
                        f"{f'{_siv:.1f}%' if _siv else '—'}</div></div>"
                        f"</div>"
                        if _smid else ""
                    )
                    + f"<div style='color:#C9D6E3;font-size:12px;line-height:1.6;'>"
                    f"{_lpm['message']}</div>"
                    + (
                        f"<div style='margin-top:8px;display:grid;grid-template-columns:repeat(3,1fr);"
                        f"gap:6px;font-size:11px;color:#4A7FA5;'>"
                        f"<div>T1 target: <b style='color:#FFB340;'>{cur}{_lpm['t1_target']:.2f}</b></div>"
                        + (f"<div>T2 target: <b style='color:#1D9E75;'>{cur}{_lpm['t2_target']:.2f}</b></div>"
                           if _lpm.get("t2_target") else "<div></div>")
                        + f"<div>Stop: <b style='color:#FF4D6A;'>{cur}{_lpm['stop']:.2f}</b></div>"
                        f"</div>"
                        if _smid else ""
                    )
                    + "</div>"
                )
                st.caption(
                    "Refresh every 15–30 min during market hours to get updated signals. "
                    "Market data via Alpaca IEX (15-min delay on free plan) / yfinance fallback. "
                    "To exit: open your broker app → find this contract → tap **Sell to Close**."
                )

        # ── 📉 Options Chain Snapshot (raw data) ─────────────────────────
        with st.expander("📉 Options Chain Snapshot"):
            with st.spinner("Loading options…"):
                opt = c_options(ticker)
            if "error" in opt:
                st.info(opt["error"])
            else:
                st.markdown(f"**Expiry:** `{opt['expiry']}` · **{opt['dte']} DTE** "
                            f"_(Recommended: 20–48 DTE for swing plays)_")
                oc1,oc2 = st.columns(2)
                with oc1:
                    ac = opt["call"]
                    st.markdown(f"**ATM Call** — Strike {cur}{ac['strike']}  "
                                f"Bid/Ask {cur}{ac['bid']}/{cur}{ac['ask']}  "
                                f"IV {ac['iv']:.1f}%  Vol {ac['vol']:,}  OI {ac['oi']:,}")
                    st.dataframe(opt["calls"], use_container_width=True, hide_index=True)
                with oc2:
                    ap = opt["put"]
                    st.markdown(f"**ATM Put** — Strike {cur}{ap['strike']}  "
                                f"Bid/Ask {cur}{ap['bid']}/{cur}{ap['ask']}  "
                                f"IV {ap['iv']:.1f}%  Vol {ap['vol']:,}  OI {ap['oi']:,}")
                    st.dataframe(opt["puts"], use_container_width=True, hide_index=True)

    # Chart — toggle between Plotly and TradingView Lightweight Charts
    if r and r.get("_df") is not None:
        st.markdown("---")
        ch1, ch2 = st.columns([4, 1])
        with ch1:
            st.subheader(f"📊 {ticker} — Chart")
        with ch2:
            use_tv = st.toggle("TradingView", value=False, key=f"tv_{ticker}")

        if use_tv:
            try:
                from streamlit_lightweight_charts import renderLightweightCharts
                df_tv = r["_df"].iloc[-180:].copy()
                candles = []
                for dt, row in df_tv.iterrows():
                    try:
                        candles.append({
                            "time":  int(pd.Timestamp(dt).timestamp()),
                            "open":  round(float(row["Open"]), 4),
                            "high":  round(float(row["High"]), 4),
                            "low":   round(float(row["Low"]), 4),
                            "close": round(float(row["Close"]), 4),
                        })
                    except Exception:
                        pass
                volumes = []
                if "Volume" in df_tv.columns:
                    for dt, row in df_tv.iterrows():
                        try:
                            c = float(row["Close"]); o = float(row["Open"])
                            volumes.append({
                                "time":  int(pd.Timestamp(dt).timestamp()),
                                "value": float(row["Volume"]),
                                "color": "#1D9E7566" if c >= o else "#FF4D6A66",
                            })
                        except Exception:
                            pass
                chart_opts = {
                    "layout":     {"background": {"color": "#0F1B2D"}, "textColor": "#C9D6E3"},
                    "grid":       {"vertLines": {"color": "#1a2f4a"}, "horzLines": {"color": "#1a2f4a"}},
                    "crosshair":  {"mode": 0},
                    "rightPriceScale": {"borderColor": "#1a2f4a"},
                    "timeScale":  {"borderColor": "#1a2f4a", "timeVisible": True},
                    "height":     460,
                }
                series = [
                    {"type": "Candlestick", "data": candles,
                     "options": {"upColor": "#1D9E75", "downColor": "#FF4D6A",
                                 "borderUpColor": "#1D9E75", "borderDownColor": "#FF4D6A",
                                 "wickUpColor": "#1D9E75", "wickDownColor": "#FF4D6A"}},
                ]
                if volumes:
                    series.append({"type": "Histogram", "data": volumes,
                                   "options": {"priceFormat": {"type": "volume"}, "priceScaleId": "vol"},
                                   "priceScale": {"scaleMargins": {"top": 0.85, "bottom": 0}}})
                renderLightweightCharts([{"chart": chart_opts, "series": series}], key=f"lwc_{ticker}")
            except Exception as e:
                st.warning(f"TradingView chart error: {e}. Falling back to Plotly.")
                st.plotly_chart(candlestick(r["_df"], r, ticker), use_container_width=True,
                                key=f"checker_chart_tv_fallback_{ticker}")
        else:
            st.plotly_chart(candlestick(r["_df"], r, ticker), use_container_width=True,
                            key=f"checker_chart_{ticker}")


# ══════════════════════════════════════════════════════════════════════
#  TAB 5 — MY PORTFOLIO
# ══════════════════════════════════════════════════════════════════════
def tab_portfolio(cfg, market):
    mc  = MARKET_CONFIGS[market]
    cur = mc["currency"]
    st.subheader("💼 My Portfolio — Real-Time Monitor")
    st.caption("Log positions. Track live P&L, stop status, EMA hold, and T1/T2 targets.")

    positions = cfg.get("positions", [])
    with st.expander("➕ Log New Position", expanded=not positions):
        c1,c2,c3,c4 = st.columns(4)
        with c1:
            nt_raw = st.text_input("Ticker").upper().strip()
            nt = eng.auto_suffix(nt_raw, mc["key"]) if nt_raw else ""
            if nt and nt != nt_raw:
                st.caption(f"→ {nt}")
        with c2: ne = st.number_input(f"Entry ({cur})", min_value=0.0001, format="%.4f")
        with c3: ns = st.number_input("Shares/Units", min_value=1, step=1)
        with c4: nsl= st.number_input(f"Stop Loss ({cur})", min_value=0.0001, format="%.4f")
        if st.button("📥 Log Position", type="primary"):
            if nt and ne > 0 and ns > 0:
                positions.append({"ticker":nt,"entry":ne,"shares":int(ns),
                                   "stop":nsl if nsl>0 else ne*0.97,
                                   "date":datetime.now().strftime("%Y-%m-%d")})
                cfg["positions"] = positions
                _save(cfg)
                st.success(f"✅ {nt} logged.")
                st.rerun()

    if not positions:
        st.info("No positions yet. Log one above to start monitoring.")
        return

    if "emailed_alerts" not in st.session_state:
        st.session_state["emailed_alerts"] = set()

    st.markdown(f"**{len(positions)} open position(s)**")
    total_pnl = 0.0; to_remove = []

    for idx, pos in enumerate(positions):
        try:
            with st.spinner(f"Live check: {pos['ticker']}…"):
                m = eng.monitor_position(pos, mc, cfg.get("time_stop",5))
        except Exception as _me:
            st.warning(f"{pos['ticker']}: monitor error — {_me}")
            continue
        if "error" in m:
            st.warning(f"{pos['ticker']}: {m['error']}")
            continue
        total_pnl += m["pnl_usd"]

        # Auto email alert when action is not HOLD (once per action level per session)
        alert_key = f"{pos['ticker']}_{m['action']}"
        if m["action"] != "🟢 HOLD" and alert_key not in st.session_state["emailed_alerts"]:
            try:
                ok, _ = notifier.send_sell_alert(pos, m)
            except Exception:
                ok = False
            if ok:
                st.session_state["emailed_alerts"].add(alert_key)

        ac = m["action_col"]
        pc = "#1D9E75" if m["pnl_usd"] >= 0 else "#FF4D6A"

        card(
            f"<div style='background:#0a1525;border:1.5px solid {ac};"
            f"border-radius:10px;padding:14px 18px;margin-bottom:10px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;'>"
            f"<span style='font-size:22px;font-weight:900;color:#fff;'>{m['ticker']}</span>"
            f"<span style='background:{ac};color:#050d15;font-weight:700;font-size:12px;"
            f"padding:4px 14px;border-radius:12px;'>{m['action']}</span></div>"
            f"<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:8px;text-align:center;font-size:12px;'>"
            f"<div><div style='color:#4A7FA5;'>Entry</div><div style='color:#fff;font-weight:700;'>{cur}{m['entry']}</div></div>"
            f"<div><div style='color:#4A7FA5;'>Current</div><div style='color:#fff;font-weight:700;'>{cur}{m['current']}</div></div>"
            f"<div><div style='color:#4A7FA5;'>Live P&L</div>"
            f"<div style='color:{pc};font-weight:700;'>{cur}{m['pnl_usd']:+.2f} ({m['pnl_pct']:+.2f}%)</div></div>"
            f"<div><div style='color:#FF4D6A;'>Stop</div><div style='color:#FF4D6A;font-weight:700;'>{cur}{m['stop']}</div></div>"
            f"<div><div style='color:#4A7FA5;'>8 EMA</div>"
            f"<div style='color:{'#1D9E75' if m['ema_hold'] else '#FF4D6A'};font-weight:700;'>"
            f"{'✅ Hold' if m['ema_hold'] else '⚠️ Below'}</div></div></div>"
            f"<div style='margin-top:8px;font-size:11px;color:#4A7FA5;'>"
            f"T1 {cur}{m['t1']}: {'✅ Hit' if m['t1_hit'] else 'Pending'}  ·  "
            f"T2 {cur}{m['t2']}: {'✅ Hit' if m['t2_hit'] else 'Pending'}  ·  "
            f"Shares: {m['shares']}  ·  Entry date: {pos.get('date','—')}"
            f"</div></div>"
        )
        if st.button(f"🗑️ Close {pos['ticker']}", key=f"close_{idx}"):
            to_remove.append(idx)

    if to_remove:
        cfg["positions"] = [p for i,p in enumerate(positions) if i not in to_remove]
        _save(cfg); st.rerun()

    st.markdown("---")
    pc = "#1D9E75" if total_pnl >= 0 else "#FF4D6A"
    card(f"<div style='text-align:right;font-size:18px;font-weight:700;color:{pc};'>"
         f"Total Open P&L: {cur}{total_pnl:+.2f}</div>")
    st.caption("🟢 HOLD = healthy  ·  🚨 SELL STOP = cut loss now  ·  "
               "💰 SELL 50% = T1 hit, move stop to break-even  ·  🎯 SELL = T2 hit  ·  ⚠️ EXIT = time stop / EMA broken")


# ══════════════════════════════════════════════════════════════════════
#  TAB 6 — WATCHLIST & SETTINGS
# ══════════════════════════════════════════════════════════════════════
def tab_settings(cfg, market):
    mc = MARKET_CONFIGS[market]
    st.subheader("⚙️ Watchlist & Settings")
    t_wl, t_risk, t_alerts = st.tabs(["📋 Watchlist Editor", "🛠️ Risk Settings", "📧 Alert Settings"])

    with t_wl:
        st.markdown(f"**Market:** {market}  ·  **Focus:** {cfg.get('focus','—')}")
        custom_wl = cfg.get("watchlists",{}).get(market,[])
        c1,c2 = st.columns([4,1])
        with c1:
            new_t = st.text_input("Add ticker — suffix auto-added for this market (e.g. type TCS for India)")
        with c2:
            st.markdown("<div style='padding-top:28px'></div>",unsafe_allow_html=True)
            if st.button("➕ Add", type="primary"):
                corrected = eng.auto_suffix(new_t, mc["key"]) if new_t else ""
                if corrected and corrected not in custom_wl:
                    custom_wl.append(corrected)
                    cfg = save_custom_watchlist(cfg, market, custom_wl)
                    if corrected != new_t.upper():
                        st.success(f"✅ Added as **{corrected}** (auto-suffixed)")
                    st.rerun()

        st.markdown("**Custom watchlist** (click to remove):")
        if custom_wl:
            chunks = [custom_wl[i:i+6] for i in range(0,len(custom_wl),6)]
            for chunk in chunks:
                cols = st.columns(6)
                for j,tk in enumerate(chunk):
                    with cols[j]:
                        if st.button(f"🗑️ {tk}", key=f"del_{tk}"):
                            custom_wl.remove(tk)
                            cfg = save_custom_watchlist(cfg, market, custom_wl)
                            st.rerun()
        else:
            st.info("No custom tickers yet. Add one above.")
        focus_key = FOCUS_MODES.get(cfg.get("focus", "🚀 High-Growth Leaders"), "growth")
        if focus_key != "custom":
            default_tickers = mc.get(focus_key, [])
            st.caption("Default list: " + "  ·  ".join(default_tickers))

    with t_risk:
        st.markdown("### 🛠️ Risk & Trade Settings")
        c1, c2 = st.columns(2)
        with c1:
            time_stop = st.number_input(
                "⏱ Time Stop (trading days)",
                min_value=1, max_value=30,
                value=int(cfg.get("time_stop", 5)), step=1,
                help="Auto-exit alert after this many days if targets not hit."
            )
        with c2:
            max_pos = st.number_input(
                "📊 Max Open Positions",
                min_value=1, max_value=20,
                value=int(cfg.get("max_positions", 5)), step=1
            )
        if st.button("💾 Save Risk Settings", type="primary"):
            cfg["time_stop"]     = time_stop
            cfg["max_positions"] = max_pos
            _save(cfg)
            st.success("✅ Risk settings saved.")

        st.markdown("---")
        cur = MARKET_CONFIGS[market]["currency"]
        one_r = cfg.get("portfolio", 10000) * cfg.get("risk_pct", 1.0) / 100
        card(
            f"<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:8px;padding:16px;'>"
            f"<div style='color:#4A7FA5;font-size:11px;font-weight:700;margin-bottom:10px;'>CURRENT RISK RULES</div>"
            f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;'>"
            f"<div><div style='color:#4A7FA5;font-size:10px;'>Portfolio Size</div>"
            f"<div style='color:#fff;font-weight:700;'>{cur}{cfg.get('portfolio',10000):,.0f}</div></div>"
            f"<div><div style='color:#4A7FA5;font-size:10px;'>Risk Per Trade</div>"
            f"<div style='color:#fff;font-weight:700;'>{cfg.get('risk_pct',1.0)}%</div></div>"
            f"<div><div style='color:#4A7FA5;font-size:10px;'>1R Value</div>"
            f"<div style='color:#1D9E75;font-weight:700;font-size:16px;'>{cur}{one_r:,.2f}</div></div>"
            f"<div><div style='color:#4A7FA5;font-size:10px;'>Time Stop</div>"
            f"<div style='color:#FFB340;font-weight:700;'>{cfg.get('time_stop',5)} days</div></div>"
            f"</div></div>"
        )
        st.markdown("---")
        st.markdown("#### 📚 Position Sizing Rules")
        card(
            "<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:8px;padding:16px;'>"
            "<div style='color:#C9D6E3;font-size:12px;line-height:2;'>"
            "• Never risk more than <b style='color:#FFB340;'>1–2%</b> of total capital on a single trade<br>"
            "• Shares = (Portfolio × Risk%) ÷ (Entry − Stop)<br>"
            "• At T1 (+1.5R): sell <b style='color:#1D9E75;'>50%</b>, move stop to break-even<br>"
            "• At T2 (+3R): sell another <b style='color:#1D9E75;'>25%</b>, trail stop<br>"
            "• At T3 (+5R): close remaining <b style='color:#1D9E75;'>25%</b><br>"
            "• Time stop: exit if no movement after set number of trading days"
            "</div></div>"
        )

    # ── ALERT SETTINGS TAB ─────────────────────────────────────────────
    with t_alerts:
        st.markdown("### 📧 Email Alert Settings")
        from config import _is_cloud
        if _is_cloud():
            st.info("Running on Streamlit Cloud — keys are managed in App Settings → Secrets (not editable here).")
        else:
            st.caption("All settings saved to aarya_config.json on your machine.")

        keys = notifier.load_keys()
        ec   = keys.get("email", {})
        changed = False

        # Recipients list
        st.markdown("#### 📬 Alert Recipients")
        st.caption("Alerts go to ALL emails in this list simultaneously.")
        recipients = list(ec.get("alert_recipients", []))

        if recipients:
            for i, email in enumerate(recipients):
                r1, r2 = st.columns([5, 1])
                with r1:
                    primary_badge = '&nbsp;&nbsp;<span style="color:#1D9E75;font-size:10px;">PRIMARY</span>' if i == 0 else ''
                    icon = '📧' if i == 0 else '📨'
                    card(f"<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:6px;"
                         f"padding:8px 14px;color:#C9D6E3;font-size:13px;'>"
                         f"{icon} {email}{primary_badge}"
                         f"</div>")
                with r2:
                    if st.button("🗑️", key=f"del_email_{i}", help=f"Remove {email}"):
                        recipients.pop(i)
                        ec["alert_recipients"] = recipients
                        keys["email"] = ec
                        notifier.save_keys(keys)
                        st.success(f"Removed {email}")
                        st.rerun()
        else:
            st.info("No recipient emails yet. Add one below.")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        na1, na2 = st.columns([4, 1])
        with na1:
            new_email = st.text_input("Add email address",
                                       placeholder="example@gmail.com",
                                       label_visibility="collapsed")
        with na2:
            st.markdown("<div style='padding-top:4px'></div>", unsafe_allow_html=True)
            if st.button("➕ Add", type="primary", use_container_width=True):
                ne = new_email.strip().lower()
                if ne and "@" in ne and ne not in recipients:
                    recipients.append(ne)
                    ec["alert_recipients"] = recipients
                    keys["email"] = ec
                    notifier.save_keys(keys)
                    st.success(f"✅ Added {ne}")
                    st.rerun()
                elif ne in recipients:
                    st.warning("Already in the list.")
                else:
                    st.error("Enter a valid email address.")

        st.markdown("---")
        st.markdown("#### 🔑 API Keys & Credentials")
        st.caption("Stored locally only — never sent anywhere else.")

        with st.expander("📮 Gmail Sender (for sending alerts)", expanded=False):
            s1, s2 = st.columns(2)
            with s1:
                sender_val = st.text_input("Gmail Address",
                                            value=ec.get("sender_address", ""),
                                            placeholder="yourname@gmail.com")
            with s2:
                pwd_val = st.text_input("App Password (16 chars)",
                                         value=ec.get("sender_app_password", ""),
                                         type="password",
                                         placeholder="xxxx xxxx xxxx xxxx")
            if st.button("💾 Save Gmail Settings"):
                ec["sender_address"]      = sender_val.strip()
                ec["sender_app_password"] = pwd_val.strip().replace(" ", "")
                keys["email"] = ec
                notifier.save_keys(keys)
                st.success("✅ Gmail settings saved.")

        with st.expander("📈 Alpha Vantage API Key", expanded=False):
            av_val = st.text_input("Alpha Vantage Key",
                                    value=keys.get("alpha_vantage", {}).get("api_key", ""),
                                    type="password",
                                    placeholder="Your API key")
            if st.button("💾 Save Alpha Vantage Key"):
                keys["alpha_vantage"] = {"api_key": av_val.strip()}
                notifier.save_keys(keys)
                st.success("✅ Alpha Vantage key saved.")

        with st.expander("🤖 Gemini API Key", expanded=False):
            gem_val = st.text_input("Gemini Key",
                                     value=keys.get("gemini", {}).get("api_key", ""),
                                     type="password",
                                     placeholder="AIzaSy...")
            if st.button("💾 Save Gemini Key"):
                keys["gemini"] = {"api_key": gem_val.strip()}
                notifier.save_keys(keys)
                st.success("✅ Gemini key saved.")

        with st.expander("📡 Alpaca API (Live Option Price Monitor)", expanded=False):
            st.caption(
                "Alpaca is used to fetch the **live option premium** in the Stock Checker → Options section "
                "(the 'Check Current Premium Now' button). It's paper-trading only — no real money involved."
            )
            try:
                import alpaca_client as _alp_s
                _alp_ok = _alp_s.is_configured()
            except Exception:
                _alp_ok = False
            if _alp_ok:
                st.success("✅ Alpaca is already configured (keys loaded from Streamlit Secrets or config file). "
                           "Live option monitoring is active.")
                st.caption("On Streamlit Cloud: keys are set via Streamlit Secrets → no action needed here. "
                           "If running locally, enter keys below to save to aarya_config.json.")
            else:
                st.warning("⚠️ Alpaca not configured — live premium monitoring will fall back to yfinance.")

            _alp_cfg = keys.get("alpaca", {})
            alp_key_val = st.text_input("Alpaca API Key",
                                         value=_alp_cfg.get("api_key", ""),
                                         type="password", placeholder="PKNFWZX…")
            alp_sec_val = st.text_input("Alpaca Secret",
                                         value=_alp_cfg.get("secret", ""),
                                         type="password", placeholder="6RFKTm…")
            if st.button("💾 Save Alpaca Keys"):
                keys["alpaca"] = {
                    "api_key": alp_key_val.strip(),
                    "secret":  alp_sec_val.strip(),
                    "base_url": "https://paper-api.alpaca.markets/v2",
                }
                notifier.save_keys(keys)
                st.success("✅ Alpaca keys saved to local config.")

        st.markdown("---")
        st.markdown("### 📱 Telegram Notifications")
        st.caption("Get stock alerts directly on your phone via Telegram.")

        with st.expander("How to get your Telegram Chat ID", expanded=False):
            st.markdown(
                "1. Open Telegram on your phone\n"
                "2. Search for **@userinfobot** and tap it\n"
                "3. Send `/start` — it instantly replies with your **Chat ID** (a number like `987654321`)\n"
                "4. Paste that number below and click Save\n\n"
                "Once saved, alerts (buy picks, penny spikes, sell signals) will arrive on your Telegram automatically."
            )

        _tg_user = st.session_state.get("_aarya_auth")
        _tg_user_id = _tg_user["id"] if _tg_user else None
        _current_chat_id = db.get_user_settings(_tg_user_id).get("telegram_chat_id", "") if _tg_user_id else ""

        tg_c1, tg_c2 = st.columns([3, 1])
        with tg_c1:
            new_tg_id = st.text_input(
                "Your Telegram Chat ID",
                value=_current_chat_id,
                placeholder="e.g. 987654321",
                label_visibility="collapsed",
            )
        with tg_c2:
            if st.button("💾 Save", key="save_tg_id", type="primary", use_container_width=True):
                if _tg_user_id and new_tg_id.strip().lstrip("-").isdigit():
                    ok, msg = db.save_telegram_chat_id(_tg_user_id, new_tg_id.strip())
                    if ok:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
                elif not new_tg_id.strip():
                    st.warning("Enter your Chat ID first.")
                else:
                    st.error("Chat ID must be a number. Get it from @userinfobot on Telegram.")

        if _current_chat_id:
            st.success(f"✅ Telegram alerts active — Chat ID: `{_current_chat_id}`")
        else:
            st.info("No Telegram Chat ID saved yet.")

        st.markdown("---")
        st.markdown("#### 🧪 Test Your Setup")
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            if st.button("📧 Send Test Email", type="primary", use_container_width=True):
                with st.spinner("Sending…"):
                    try:
                        ok, msg = notifier.send_test_email()
                    except Exception as _te:
                        ok, msg = False, str(_te)
                if ok:
                    st.success(f"✅ {msg} — check your inbox!")
                else:
                    st.error(f"❌ {msg}")
        with tc2:
            if st.button("📱 Test Telegram", use_container_width=True):
                _test_cid = _current_chat_id
                if not _test_cid:
                    st.warning("Save your Telegram Chat ID above first.")
                else:
                    with st.spinner("Sending…"):
                        try:
                            ok, msg = notifier.send_telegram(
                                "✅ <b>Aarya StockSense</b> — Telegram alerts are working! "
                                "You will receive buy picks, penny spike alerts and sell signals here automatically.",
                                _test_cid,
                            )
                        except Exception as _tte:
                            ok, msg = False, str(_tte)
                    if ok:
                        st.success("✅ Check your Telegram!")
                    else:
                        st.error(f"❌ {msg}")
        with tc3:
            if st.button("🤖 Test Gemini", use_container_width=True):
                with st.spinner("Asking Gemini…"):
                    try:
                        ans = notifier.get_gemini_answer("AAPL", "What does Apple do in one sentence?")
                    except Exception as _tge:
                        ans = f"error: {_tge}"
                if "error" in ans.lower() or "not set" in ans.lower():
                    st.error(ans)
                else:
                    st.success("✅ Gemini working!")
                    st.caption(ans)


# ══════════════════════════════════════════════════════════════════════
#  TAB 8 — TRACK RECORD
# ══════════════════════════════════════════════════════════════════════
def tab_track_record(cfg, market):
    user    = st.session_state.get("_aarya_auth")
    user_id = user["id"] if user else None

    st.subheader("📊 Track Record — All Picks & Outcomes")
    st.caption("Every pick the system has made, with live outcomes, calibration analysis and your personal notes.")

    # ── Per-track summary cards ───────────────────────────────────────
    try:
        _summary_rows = mldb.get_recent_predictions(days=30)
        if _summary_rows:
            from ml.weekly_report import _per_track_stats
            _ts = _per_track_stats([r for r in _summary_rows if r.get("status") == "evaluated"])
            if _ts:
                cols = st.columns(min(len(_ts), 4))
                for i, ts in enumerate(_ts[:4]):
                    rc = "#1D9E75" if ts["rate"] >= 0.5 else "#FF4D6A"
                    with cols[i]:
                        card(f"<div style='background:#0a1525;border:1px solid {rc}44;"
                             f"border-radius:8px;padding:10px 12px;text-align:center;'>"
                             f"<div style='color:#4A7FA5;font-size:10px;letter-spacing:.5px;text-transform:uppercase;'>"
                             f"{ts['track']}</div>"
                             f"<div style='color:{rc};font-size:22px;font-weight:900;margin:4px 0;'>"
                             f"{ts['rate']*100:.0f}%</div>"
                             f"<div style='color:#C9D6E3;font-size:11px;'>"
                             f"{ts['hits']}/{ts['n']} hits{ts['warn']}</div></div>")
    except Exception:
        pass

    st.markdown("<div style='margin:8px 0;'></div>", unsafe_allow_html=True)

    # ── Retroactive hits banner ───────────────────────────────────────
    try:
        _hits = mldb.get_retroactive_hits(hours=24)
        if _hits:
            _hit_lines = "  ·  ".join(
                f"<b>{h['ticker']}</b> +{(h.get('outcome_pct') or 0):.1f}%"
                for h in _hits[:5])
            card(f"<div style='background:#1D9E7518;border:1px solid #1D9E75;"
                 f"border-radius:8px;padding:10px 16px;margin-bottom:10px;'>"
                 f"<span style='color:#1D9E75;font-weight:700;'>🎉 Flipped to HIT in the last 24h: </span>"
                 f"<span style='color:#C9D6E3;font-size:13px;'>{_hit_lines}</span></div>")
    except Exception:
        pass

    # ── Filter row ────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 2, 2, 1])
    with fc1:
        days_opt = st.selectbox("Date Range", ["7d", "30d", "90d", "All"],
                                index=1, key="tr_days")
    with fc2:
        mkt_filter = st.selectbox("Market", ["All", "US", "IN", "CRYPTO", "UK", "EU", "CA", "JP"],
                                  key="tr_mkt")
    with fc3:
        track_filter = st.selectbox("Track", ["All", "stock", "penny", "crypto", "options"],
                                    key="tr_track")
    with fc4:
        sig_filter = st.selectbox("Signal", ["All", "BUY TODAY", "PREPARE TO BUY", "WATCH"],
                                  key="tr_sig")
    with fc5:
        st.markdown("<div style='padding-top:24px'></div>", unsafe_allow_html=True)
        export_btn = st.button("📥 CSV", use_container_width=True, key="tr_csv")

    # ── Fetch + filter data ───────────────────────────────────────────
    days_map = {"7d": 7, "30d": 30, "90d": 90, "All": 730}
    days_int = days_map[days_opt]
    with st.spinner("Loading picks…"):
        rows = mldb.get_recent_predictions(
            days=days_int,
            market=None if mkt_filter == "All" else mkt_filter,
            track=None  if track_filter == "All" else track_filter,
            signal=None if sig_filter == "All" else sig_filter,
        )

    if not rows:
        st.info("No picks found for the selected filters. The system logs picks automatically — check back once the monitor has run.")
        return

    # ── Bulk-load current user's notes ────────────────────────────────
    pred_ids  = [r["id"] for r in rows]
    notes_map = mldb.get_user_notes_bulk(pred_ids, user_id) if user_id else {}

    # ── Build display table ───────────────────────────────────────────
    def _status(row):
        if row.get("status") == "evaluated":
            return "🟢 HIT" if row.get("hit") else "🔴 MISSED"
        return "⏳ PENDING"

    def _days_held(row):
        try:
            from datetime import date as _d
            return (  _d.today() - _d.fromisoformat(str(row["pred_date"])[:10])).days
        except Exception:
            return "—"

    rows_display = []
    for r in rows:
        rows_display.append({
            "Date":      str(r.get("pred_date", ""))[:10],
            "Ticker":    r.get("ticker", ""),
            "Market":    (r.get("market") or "")[:10],
            "Signal":    r.get("signal", ""),
            "Track":     mldb._derive_track(r),
            "Entry":     r.get("entry") or r.get("price"),
            "Stop":      r.get("stop"),
            "T1":        r.get("t1"),
            "Win%":      r.get("win_prob"),
            "Status":    _status(r),
            "Days":      _days_held(r),
            "Return%":   round(r["outcome_pct"], 1) if r.get("outcome_pct") is not None else None,
        })

    df_display = pd.DataFrame(rows_display)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── CSV export ────────────────────────────────────────────────────
    if export_btn:
        csv_bytes = df_display.to_csv(index=False).encode()
        st.download_button("⬇️ Download CSV", csv_bytes, "track_record.csv",
                           "text/csv", key="tr_dl")

    st.markdown("---")

    # ── Drill-down ────────────────────────────────────────────────────
    st.markdown("#### 🔍 Drill-down")
    ticker_opts = ["— select a pick —"] + [f"{r['Date']}  {r['Ticker']}" for r in rows_display]
    sel = st.selectbox("Select pick to inspect", ticker_opts, key="tr_sel")

    if sel and sel != "— select a pick —":
        idx  = ticker_opts.index(sel) - 1
        row  = rows[idx]
        drow = rows_display[idx]
        pred_id = row["id"]

        c_left, c_right = st.columns([1, 2])
        with c_left:
            # Criteria snapshot
            feats = row.get("features") or {}
            card(f"<div style='background:#0a1525;border:1px solid #1a2f4a;border-radius:8px;padding:12px 16px;'>"
                 f"<div style='color:#4A7FA5;font-size:10px;font-weight:700;letter-spacing:.5px;margin-bottom:8px;'>CRITERIA AT PICK TIME</div>"
                 f"<table style='width:100%;font-size:12px;border-collapse:collapse;'>"
                 f"<tr><td style='color:#8aaccc;'>Minervini</td><td style='color:#fff;font-weight:700;text-align:right;'>{row.get('minervini') or '—'}/8</td></tr>"
                 f"<tr><td style='color:#8aaccc;'>RSI</td><td style='color:#fff;font-weight:700;text-align:right;'>{row.get('rsi') or '—'}</td></tr>"
                 f"<tr><td style='color:#8aaccc;'>RS Score</td><td style='color:#fff;font-weight:700;text-align:right;'>{row.get('rs_score') or '—'}</td></tr>"
                 f"<tr><td style='color:#8aaccc;'>Volume Ratio</td><td style='color:#fff;font-weight:700;text-align:right;'>{(feats.get('volume_ratio') or '—')}</td></tr>"
                 f"<tr><td style='color:#8aaccc;'>Sweep</td><td style='color:#{'1D9E75' if feats.get('sweep') else 'FF4D6A'};font-weight:700;text-align:right;'>{'✅' if feats.get('sweep') else '❌'}</td></tr>"
                 f"<tr><td style='color:#8aaccc;'>Extended</td><td style='color:#{'FF4D6A' if feats.get('is_extended') else '1D9E75'};font-weight:700;text-align:right;'>{'Yes ⚠' if feats.get('is_extended') else 'No ✅'}</td></tr>"
                 f"</table>"
                 f"<div style='margin-top:10px;border-top:1px solid #1a2f4a;padding-top:8px;'>"
                 f"<span style='color:#4A7FA5;font-size:10px;'>Status: </span>"
                 f"<span style='font-weight:700;font-size:13px;'>{drow['Status']}</span>")
            if row.get("failure_reason"):
                fr_label = row["failure_reason"].replace("_", " ").title()
                card(f"<div style='margin-top:6px;background:#FF4D6A18;border:1px solid #FF4D6A44;"
                     f"border-radius:4px;padding:4px 8px;font-size:11px;color:#FF4D6A;'>"
                     f"⚠ Failure: {fr_label}</div>")
            card("</div></div>")

        with c_right:
            render_pick_chart(row.get("ticker", ""),
                              str(row.get("pred_date", ""))[:10],
                              row.get("entry") or 0,
                              row.get("stop")  or 0,
                              row.get("t1")    or 0)

        # Notes editor
        current_note = notes_map.get(pred_id, "")
        st.markdown("##### 📝 Your notes on this pick")
        new_note = st.text_area("", value=current_note, key=f"note_{pred_id}",
                                height=80, max_chars=500,
                                placeholder="Why you traded / passed, what you learned…",
                                label_visibility="collapsed")
        if new_note != current_note:
            if st.button("💾 Save note", key=f"save_{pred_id}", type="primary"):
                if user_id:
                    ok = mldb.upsert_user_note(pred_id, user_id, new_note)
                    if ok:
                        notes_map[pred_id] = new_note
                        st.success("Saved.")
                    else:
                        st.error("Save failed — check Supabase credentials.")
                else:
                    st.warning("Log in to save notes.")

    # ── Calibration analysis ──────────────────────────────────────────
    with st.expander("📐 Calibration Analysis — is win_prob well-calibrated?", expanded=False):
        buckets = mldb.get_calibration_buckets(days=90)
        if not buckets:
            total_eval = sum(1 for r in rows if r.get("status") == "evaluated")
            st.info(f"Need 60+ evaluated predictions for calibration. "
                    f"Currently {total_eval} evaluated in the selected range. "
                    f"Check back in a few weeks.")
        else:
            total_n = sum(b["n"] for b in buckets)
            if total_n < 60:
                st.info(f"Need 60+ evaluated predictions — have {total_n}. "
                        "Calibration chart will appear once enough data accumulates.")
            else:
                cal_rows = []
                for b in buckets:
                    ideal = float(b["bucket"].rstrip("%+").split("-")[0]) / 100
                    diff  = abs(b["hit_rate"] - ideal)
                    flag  = "✓ aligned" if diff <= 0.12 else "⚠ overconfident" if b["hit_rate"] < ideal else "⚠ underconfident"
                    cal_rows.append({
                        "Win-Prob Bucket": b["bucket"],
                        "Picks":           b["n"],
                        "Hits":            b["hits"],
                        "Actual Hit-Rate": f"{b['hit_rate']*100:.1f}%",
                        "Calibration":     flag,
                    })
                st.dataframe(pd.DataFrame(cal_rows), use_container_width=True, hide_index=True)
                st.caption("Aligned = model prediction within 12% of reality. "
                           "Overconfident = model says 70% but reality is lower.")


# ══════════════════════════════════════════════════════════════════════
#  SETTINGS SAVE HELPER (routes to DB when logged in, file otherwise)
# ══════════════════════════════════════════════════════════════════════
def _save(cfg: dict):
    user = st.session_state.get("_aarya_auth")
    if user:
        db.save_user_settings(user["id"], cfg)
    else:
        save_settings(cfg)


# ══════════════════════════════════════════════════════════════════════
#  LOGIN SCREEN
# ══════════════════════════════════════════════════════════════════════
def show_login():
    st.markdown("""<style>
    .block-container{max-width:420px!important;padding-top:6vh!important}
    [data-testid="stForm"]{background:#0a1525;border:1px solid #1a2f4a;
        border-radius:16px;padding:32px 28px}
    </style>""", unsafe_allow_html=True)

    _ico = os.path.join(os.path.dirname(__file__), "aarya_icon.png")
    if os.path.exists(_ico):
        _b64 = base64.b64encode(open(_ico, "rb").read()).decode()
        st.markdown(f"<div style='text-align:center;margin-bottom:4px;'>"
                    f"<img src='data:image/png;base64,{_b64}' style='width:64px;height:64px;border-radius:12px;'>"
                    f"</div>", unsafe_allow_html=True)

    st.markdown("<div style='text-align:center;margin-bottom:24px;'>"
                "<div style='font-size:28px;font-weight:900;color:#fff;'>Aarya StockSense Pro</div>"
                "<div style='font-size:11px;color:#1D9E75;font-weight:700;letter-spacing:3px;margin-top:4px;'>SECURE LOGIN</div>"
                "</div>", unsafe_allow_html=True)

    with st.form("login_form"):
        email    = st.text_input("Email", placeholder="your@email.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        remember = st.checkbox("Remember me for 30 days", value=True)
        submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Enter your email and password.")
        else:
            with st.spinner("Signing in…"):
                user, err = auth.login(email, password, remember=remember)
            if err:
                st.error(err)
            else:
                st.rerun()

    # ── Forgot Password link ───────────────────────────────────────────
    st.markdown("<div style='text-align:center;margin-top:14px;'>", unsafe_allow_html=True)
    if st.button("Forgot password?", key="_fpw_toggle", use_container_width=False):
        st.session_state["_show_reset"] = not st.session_state.get("_show_reset", False)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("_show_reset", False):
        with st.form("reset_form"):
            reset_email = st.text_input("Enter your email to receive a reset link",
                                        placeholder="your@email.com")
            reset_submitted = st.form_submit_button("Send Reset Link", use_container_width=True)
        if reset_submitted:
            if not reset_email:
                st.error("Enter your email address.")
            else:
                with st.spinner("Sending…"):
                    _, msg = auth.request_password_reset(reset_email)
                st.success(msg)
                st.session_state["_show_reset"] = False

    st.markdown("<div style='text-align:center;margin-top:14px;color:#4A7FA5;font-size:12px;'>"
                "Access is by invitation only.<br>Contact the admin to request an account.</div>",
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════
def tab_admin(current_user: dict):
    st.subheader("🔐 Admin Panel")

    # ── ML status banner ─────────────────────────────────────────────
    try:
        state = mldb.get_model_state() or {}
        weights = state.get("weights") or {}
        rolling = state.get("rolling_acc") or {}
        locked  = bool(state.get("locked"))
        if not weights:
            badge_col, mode_lbl = "#4A7FA5", "🧊 COLD START — collecting predictions"
            detail = "ML is logging picks; training kicks in once 30+ predictions have outcomes."
        elif weights.get("shadow"):
            badge_col, mode_lbl = "#FFB340", "⚪ SHADOW — alerts driven by rules"
            detail = "Deploy gate not yet met; rules still drive alerts while ML keeps learning."
        else:
            badge_col, mode_lbl = "#00C48C", "✅ LIVE — ML scoring alerts"
            acc = (weights.get("acc") or {}).get("ensemble")
            detail = f"Walk-forward ensemble accuracy: {acc*100:.1f}%" if acc else "Ensemble live."

        roll_html = ""
        if rolling:
            roll_html = "  ·  ".join(
                f"{k}: <b>{(v*100):.0f}%</b>" for k, v in rolling.items() if v is not None)
            roll_html = f"<div style='color:#4A7FA5;font-size:11px;margin-top:6px;'>Rolling hit rate — {roll_html}</div>" if roll_html else ""
        lock_html = (" 🔒 <b>LOCKED</b>" if locked else "")
        card(f"<div style='background:{badge_col}12;border:1px solid {badge_col};border-radius:8px;"
             f"padding:12px 18px;margin-bottom:14px;'>"
             f"<div style='color:{badge_col};font-weight:900;font-size:14px;'>{mode_lbl}{lock_html}</div>"
             f"<div style='color:#C9D6E3;font-size:12px;margin-top:4px;'>{detail}</div>"
             f"{roll_html}</div>")

        c_lock1, c_lock2, c_lock3 = st.columns(3)
        with c_lock1:
            if not locked and weights:
                if st.button("🔒 Lock model", use_container_width=True):
                    ok = mldb.save_model_state(weights, rolling, locked=True)
                    st.success("Locked — auto-weighting paused.") if ok else st.error("Save failed.")
                    st.rerun()
            elif locked:
                if st.button("🔓 Unlock model", use_container_width=True):
                    ok = mldb.save_model_state(weights, rolling, locked=False)
                    st.success("Unlocked.") if ok else st.error("Save failed.")
                    st.rerun()
        with c_lock2:
            if st.button("📊 Run backtest now", use_container_width=True):
                with st.spinner("Backtesting (1–2 min)…"):
                    try:
                        from ml import backtest as bt
                        rep = bt.check_deploy_gate()
                        st.session_state["_bt_rep"] = rep
                    except Exception as _bte:
                        st.error(f"Backtest error: {_bte}")
        with c_lock3:
            st.caption("Predictions log lives in Supabase → `predictions` table.")
        if st.session_state.get("_bt_rep"):
            rep = st.session_state["_bt_rep"]
            pf = "✅ PASS" if rep.get("pass") else "❌ FAIL"
            st.info(
                f"**Backtest:** {pf}  ·  hit_rate@20% = **{rep.get('hit_rate_20',0):.1f}%**  ·  "
                f"avg_mfe = **{rep.get('avg_mfe',0):.1f}%**  ·  "
                f"avg_return = **{rep.get('avg_return',0):.1f}%**  ·  "
                f"sharpe = **{rep.get('sharpe',0):.2f}**  ·  "
                f"max DD = **{rep.get('max_drawdown',0):.1f}%**  ·  "
                f"n_trades = **{rep.get('n_trades',0)}**"
            )
    except Exception as _e:
        st.caption(f"ML status unavailable: {_e}")

    st.markdown("---")

    # ── Add New User ──────────────────────────────────────────────────
    st.markdown("##### ➕ Add New User")
    with st.form("adm_create_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_email = st.text_input("Email address", placeholder="user@email.com")
        with c2:
            new_pw = st.text_input("Temporary password", type="password",
                                   placeholder="Min 8 characters")
        submitted = st.form_submit_button("Create User", type="primary",
                                          use_container_width=True)

    if submitted:
        if not new_email or not new_pw:
            st.error("Enter both email and password.")
        elif len(new_pw) < 8:
            st.error("Password must be at least 8 characters.")
        else:
            ok, msg = db.create_user(new_email, new_pw)
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()

    st.markdown("---")
    st.markdown("#### All Users")

    with st.spinner("Loading users…"):
        users, err = db.list_users()

    if err:
        st.error(f"Could not load users: {err}")
        return
    if not users:
        st.info("No users found.")
        return

    for u in users:
        is_me    = u["id"] == current_user["id"]
        is_admin = u["role"] == "admin"
        blocked  = u["blocked"]

        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1, 1])
            with c1:
                role_icon = "🔐 Admin" if is_admin else "👤 User"
                flags = " 🚫 **BLOCKED**" if blocked else ""
                tag   = " *(you)*" if is_me else ""
                st.markdown(f"**{u['email']}**{flags}{tag}")
                st.caption(f"{role_icon}  ·  Joined {u['created']}  ·  Last login {u['last_login']}")
            with c2:
                if not is_me:
                    if blocked:
                        if st.button("Unblock", key=f"ub_{u['id']}", use_container_width=True):
                            ok, msg = db.unblock_user(u["id"])
                            if ok: st.rerun()
                            else:  st.error(msg)
                    else:
                        if st.button("Block", key=f"bl_{u['id']}", use_container_width=True):
                            ok, msg = db.block_user(u["id"])
                            if ok: st.rerun()
                            else:  st.error(msg)
            with c3:
                if not is_me and not is_admin:
                    if st.button("Delete", key=f"dl_{u['id']}", use_container_width=True,
                                 type="primary"):
                        ok, msg = db.delete_user(u["id"])
                        if ok: st.rerun()
                        else:  st.error(msg)


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    css()
    if st.session_state.get("tv_mode"):
        st.markdown("""<style>
        [data-testid="stSidebar"]{display:none!important}
        [data-testid="stHeader"]{display:none!important}
        footer,[data-testid="stToolbar"]{display:none!important}
        .main .block-container{max-width:100%!important;padding:0.8rem!important}
        .stMarkdown p,div,span{font-size:1.2em!important}
        h1{font-size:2.2em!important}h2{font-size:1.8em!important}
        h3,h4{font-size:1.4em!important}
        </style>
        <div style='position:fixed;bottom:12px;right:16px;color:#4A7FA5;font-size:11px;z-index:9999;'>
        📺 TV Mode · Chrome → right-click → Cast… to send to TV</div>""",
        unsafe_allow_html=True)

    user = auth.get_current_user()
    if not user:
        show_login()
        return

    cfg = db.get_user_settings(user["id"])
    cfg, market = sidebar(cfg)

    tab_names = ["📈 Today's Picks", "🤖 AI Copilot", "📊 Funds",
                 "🔍 Stock Checker", "💼 Portfolio", "⚙️ Settings", "📊 Track Record"]
    if user.get("is_admin"):
        tab_names.append("🔐 Admin")

    tabs = st.tabs(tab_names)
    with tabs[0]: tab_picks(cfg, market)
    with tabs[1]: tab_copilot(cfg, market)
    with tabs[2]: tab_funds(cfg, market)
    with tabs[3]: tab_checker(cfg, market)
    with tabs[4]: tab_portfolio(cfg, market)
    with tabs[5]: tab_settings(cfg, market)
    with tabs[6]: tab_track_record(cfg, market)
    if user.get("is_admin") and len(tabs) > 7:
        with tabs[7]: tab_admin(user)


main()
