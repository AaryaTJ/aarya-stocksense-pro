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
    @media screen and (max-width:640px){
        [data-testid="column"]{min-width:100%!important;margin-bottom:8px}
        [data-testid="stDataFrame"]{max-width:calc(100vw - 2rem)!important;overflow-x:auto!important}
        [data-testid="stMetric"]{padding:8px 10px!important}
        h1{font-size:1.3rem!important}
        h2,h3{font-size:1.05rem!important}
        [data-baseweb="tab"]{font-size:11px!important;padding:6px 8px!important}
        [data-testid="stAppViewContainer"] > section:first-child{padding:0.5rem!important}
        .block-container{padding:0.5rem 0.75rem!important;max-width:100vw!important}
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
        cfg.update({"portfolio": portfolio, "risk_pct": risk_pct, "refresh": refresh})
        _save(cfg)
        if refresh > 0:
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
        card(f"<div style='font-size:10px;color:#1a2f4a;text-align:center;margin-top:8px;'>"
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

    # Signal cards
    for group, label in [(buy,"🟢 BUY TODAY"),(prep,"🟦 PREPARE TO BUY"),
                          (watch,"🟡 WATCH"),(avoid,"🔴 DO NOT BUY")]:
        if not group: continue
        st.markdown(f"### {label}")
        cols = st.columns(min(len(group), 2))
        for i, r in enumerate(group):
            with cols[i%2]:
                try:
                    st.markdown(signal_card(r, cfg), unsafe_allow_html=True)
                    with st.expander(f"📋 {r['ticker']} — Full Breakdown"):
                        # Fundamentals strip
                        fd = c_fund(r["ticker"]) or {"error": True}
                        if not fd.get("error"):
                            fa,fb,fc,fd4 = st.columns(4)
                            fa.metric("Revenue Growth",  fmt(fd.get("rev_growth"),suffix="%",decimals=1) if fd.get("rev_growth") is not None else "N/A")
                            fb.metric("Earnings Growth", fmt(fd.get("earn_growth"),suffix="%",decimals=1) if fd.get("earn_growth") is not None else "N/A")
                            fc.metric("Analyst Rating",  fd.get("rec","N/A"))
                            fd4.metric("Inst. Holding",  fmt(fd.get("inst_pct"),suffix="%",decimals=1) if fd.get("inst_pct") is not None else "N/A")
                            st.caption(f"Sector: {fd.get('sector','—')}  ·  P/E: {fd.get('pe','—')}  ·  PEG: {fd.get('peg','—')}  ·  Target: {cur}{fd.get('target','—')}")
                        # News
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
                        # Chart
                        if r.get("_df") is not None:
                            try:
                                st.plotly_chart(candlestick(r["_df"], r, r["ticker"]),
                                                use_container_width=True)
                            except Exception:
                                st.caption("Chart unavailable.")
                except Exception as _card_err:
                    st.warning(f"{r.get('ticker','?')}: display error — {_card_err}")


# ══════════════════════════════════════════════════════════════════════
#  TAB 2 — AI COPILOT
# ══════════════════════════════════════════════════════════════════════
def tab_copilot(cfg, market):
    st.subheader("🤖 Aarya AI Copilot — 7 Analyst Personas")
    st.caption("All 7 analyst roles summarised below. Select a role to dive deeper.")

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
    t_cat, t_sim = st.tabs(["🗂️ Fund Catalogue", "🔢 Compounding Simulator"])

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
                if st.button("📥 Load into Simulator"):
                    st.session_state["mf_sym"]  = sym
                    st.session_state["mf_cagr"] = fund[4]
                    st.session_state["mf_name"] = fund[1]
                    st.success(f"Loaded {fund[1]} — switch to Simulator tab.")
            else:
                st.info("Not in catalogue. Enter ticker manually in the Simulator tab.")

    with t_sim:
        name = st.session_state.get("mf_name","Custom Fund / ETF")
        preset = float(st.session_state.get("mf_cagr", 12.0))
        st.markdown(f"**Simulating:** {name}")
        c1,c2,c3,c4 = st.columns(4)
        with c1: lump = st.number_input(f"Lump Sum ({cur})", 0.0, value=1000.0, step=100.0, format="%.0f")
        with c2: sip  = st.number_input(f"Monthly SIP ({cur})", 0.0, value=100.0, step=10.0, format="%.0f")
        with c3: cagr = st.slider("CAGR %", 4.0, 30.0, preset, 0.5)
        with c4: infl = st.slider("Inflation %", 0.0, 12.0, 5.0, 0.5)

        sim = eng.compound(lump, sip, cagr, infl, 30)

        # Milestone table
        df_m = pd.DataFrame(sim["milestones"])
        df_m.columns = ["Year","Nominal","Real (Infl-Adj.)","Invested","Gain %"]
        for col in ["Nominal","Real (Infl-Adj.)","Invested"]:
            df_m[col] = df_m[col].apply(lambda x: f"{cur}{x:,.0f}")
        df_m["Gain %"] = df_m["Gain %"].apply(lambda x: f"+{x:.1f}%")
        st.markdown("##### Wealth Milestones")
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
        st.plotly_chart(fig, use_container_width=True)
        st.caption("🟢 Nominal growth · 🔵 Real purchasing power (after inflation) · 🟠 Total cash you put in. "
                   "The gap between green and orange is your actual profit. Plan targets using the blue (real) line.")


# ══════════════════════════════════════════════════════════════════════
#  TAB 4 — STOCK CHECKER
# ══════════════════════════════════════════════════════════════════════
def tab_checker(cfg, market):
    mc  = MARKET_CONFIGS[market]
    cur = mc["currency"]
    st.subheader("🔍 Stock Checker — Predictive Analytics on Any Asset")
    st.caption("Type any stock, crypto, ETF or index. Get trade verdict + profit probability + news + options.")

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
        # Full company description — expandable
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
                st.plotly_chart(candlestick(r["_df"], r, ticker), use_container_width=True)
        else:
            st.plotly_chart(candlestick(r["_df"], r, ticker), use_container_width=True)


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

        st.markdown("---")
        st.markdown("#### 🧪 Test Your Setup")
        tc1, tc2 = st.columns(2)
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
#  SETTINGS SAVE HELPER (routes to DB when logged in, file otherwise)
# ══════════════════════════════════════════════════════════════════════
def _save(cfg: dict):
    user = st.session_state.get("_aarya_auth")
    if user:
        db.save_user_settings(user["id"], cfg)
    else:
        _save(cfg)


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
        submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Enter your email and password.")
        else:
            with st.spinner("Signing in…"):
                user, err = auth.login(email, password)
            if err:
                st.error(err)
            else:
                st.rerun()

    st.markdown("<div style='text-align:center;margin-top:20px;color:#4A7FA5;font-size:12px;'>"
                "Access is by invitation only.<br>Contact the admin to request an account.</div>",
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════
def tab_admin(current_user: dict):
    st.subheader("🔐 Admin Panel")

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

    user = auth.get_current_user()
    if not user:
        show_login()
        return

    cfg = db.get_user_settings(user["id"])
    cfg, market = sidebar(cfg)

    tab_names = ["📈 Today's Picks", "🤖 AI Copilot", "📊 Funds",
                 "🔍 Stock Checker", "💼 Portfolio", "⚙️ Settings"]
    if user.get("is_admin"):
        tab_names.append("🔐 Admin")

    tabs = st.tabs(tab_names)
    with tabs[0]: tab_picks(cfg, market)
    with tabs[1]: tab_copilot(cfg, market)
    with tabs[2]: tab_funds(cfg, market)
    with tabs[3]: tab_checker(cfg, market)
    with tabs[4]: tab_portfolio(cfg, market)
    with tabs[5]: tab_settings(cfg, market)
    if user.get("is_admin") and len(tabs) > 6:
        with tabs[6]: tab_admin(user)


main()
