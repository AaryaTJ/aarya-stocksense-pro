"""
Aarya StockSense Pro — engine.py
Full strategy engine: indicators, Minervini, sweeps, RS, R/R,
fundamentals, news, options, compounding, profit probability.
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import json
import os
from datetime import datetime, time as _dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
import requests

from applog import get_logger

log = get_logger("aarya_engine")

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aarya_config.json")

def _av_key() -> str:
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE) as f:
                return json.load(f).get("alpha_vantage", {}).get("api_key", "")
        except Exception:
            pass
    try:
        import streamlit as st
        return str(st.secrets.get("ALPHA_VANTAGE_KEY", ""))
    except Exception:
        pass
    return os.environ.get("ALPHA_VANTAGE_KEY", "")


def _td_key() -> str:
    """Twelve Data API key."""
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE) as f:
                return json.load(f).get("twelve_data", {}).get("api_key", "")
        except Exception:
            pass
    try:
        import streamlit as st
        return str(st.secrets.get("TWELVE_DATA_KEY", ""))
    except Exception:
        pass
    return os.environ.get("TWELVE_DATA_KEY", "")


def get_rsi(ticker: str) -> float | None:
    """Fetch RSI 14 from Twelve Data (US stocks only). Returns None on any failure."""
    key = _td_key()
    if not key:
        return None
    td_symbol = ticker.split(".")[0].replace("-USD", "").replace("^", "").upper()
    try:
        r = requests.get(
            "https://api.twelvedata.com/rsi",
            params={"symbol": td_symbol, "interval": "1day",
                    "time_period": 14, "outputsize": 1, "apikey": key},
            timeout=8,
        )
        data = r.json()
        if data.get("status") == "ok" and data.get("values"):
            return round(float(data["values"][0]["rsi"]), 2)
    except Exception:
        pass
    return None


# ── Kraken public API for crypto (no key needed, global access) ───────

_KRAKEN_PAIRS = {
    "BTC-USD":  "XBTUSD",
    "ETH-USD":  "XETHZUSD",
    "SOL-USD":  "SOLUSD",
    "XRP-USD":  "XXRPZUSD",
    "ADA-USD":  "ADAUSD",
    "DOGE-USD": "XDGEZUSD",
    "DOT-USD":  "DOTUSD",
    "LTC-USD":  "XLTCZUSD",
    "LINK-USD": "LINKUSD",
    "AVAX-USD": "AVAXUSD",
    "MATIC-USD":"MATICUSD",
    "ATOM-USD": "ATOMUSD",
    "NEAR-USD": "NEARUSD",
    "UNI-USD":  "UNIUSD",
    "ALGO-USD": "ALGOUSD",
}

def _download_kraken(symbol: str, period: str = "1y") -> pd.DataFrame | None:
    pair = _KRAKEN_PAIRS.get(symbol.upper())
    if not pair:
        return None
    days = {"5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}.get(period, 365)
    since = int((pd.Timestamp.now() - pd.Timedelta(days=days)).timestamp())
    try:
        r = requests.get(
            "https://api.kraken.com/0/public/OHLC",
            params={"pair": pair, "interval": 1440, "since": since},
            timeout=15,
        )
        data = r.json()
        if data.get("error"):
            return None
        result = data.get("result", {})
        candles = next((v for k, v in result.items() if k != "last" and isinstance(v, list)), None)
        if not candles or len(candles) < 10:
            return None
        df = pd.DataFrame(candles, columns=["ts", "Open", "High", "Low", "Close", "vwap", "Volume", "count"])
        df.index = pd.to_datetime(df["ts"].astype(int), unit="s")
        df.index.name = "Date"
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        df = df.ffill().bfill().dropna(subset=["Close", "High", "Low", "Open"])
        return df if len(df) >= 10 else None
    except Exception:
        return None


# ── Crypto market regime overview (CoinGecko + alternative.me, no key) ─

def fetch_crypto_overview() -> dict:
    """BTC dominance, Fear & Greed Index, BTC volume regime. All free, no auth.
    Returns _ok=False on network failure so the UI degrades gracefully."""
    out = {"btc_dominance": None, "fear_greed": None, "fg_label": None,
           "btc_vol_regime": None, "btc_above_50dma": None, "btc_pct_50dma": None,
           "_ok": False}
    try:
        cg = requests.get("https://api.coingecko.com/api/v3/global", timeout=8)
        if cg.status_code == 200:
            data = cg.json().get("data", {})
            dom = data.get("market_cap_percentage", {}).get("btc")
            if dom is not None:
                out["btc_dominance"] = round(float(dom), 1)
    except Exception:
        pass
    try:
        fg = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if fg.status_code == 200:
            entry = fg.json().get("data", [{}])[0]
            val = int(entry.get("value", 0))
            out["fear_greed"] = val
            out["fg_label"]   = entry.get("value_classification", "")
    except Exception:
        pass
    try:
        df_btc = _download_kraken("BTC-USD", period="3mo")
        if df_btc is not None and len(df_btc) >= 50:
            close = df_btc["Close"].squeeze()
            vol   = df_btc["Volume"].squeeze()
            ma50  = float(close.rolling(50).mean().iloc[-1])
            price = float(close.iloc[-1])
            out["btc_above_50dma"] = price > ma50
            out["btc_pct_50dma"]   = round((price / ma50 - 1) * 100, 1)
            vol_avg20 = float(vol.iloc[-21:-1].mean()) if len(vol) > 21 else float(vol.mean())
            vol_today = float(vol.iloc[-1])
            ratio = vol_today / vol_avg20 if vol_avg20 > 0 else 1.0
            out["btc_vol_regime"] = "HIGH" if ratio >= 1.5 else "LOW" if ratio < 0.7 else "NORMAL"
    except Exception:
        pass
    out["_ok"] = any(v is not None for v in [out["btc_dominance"], out["fear_greed"]])
    return out


# ══════════════════════════════════════════════════════════════════════
#  LOW-LEVEL INDICATORS
# ══════════════════════════════════════════════════════════════════════

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean().dropna()

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi = df["High"].squeeze(); lo = df["Low"].squeeze(); cl = df["Close"].squeeze()
    tr = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ══════════════════════════════════════════════════════════════════════
#  DATA DOWNLOAD (safe, no crash on bad tickers)
# ══════════════════════════════════════════════════════════════════════

def download(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame | None:
    # Use Kraken for known crypto pairs — more reliable than yfinance for crypto
    if interval == "1d" and ticker.upper() in _KRAKEN_PAIRS:
        df = _download_kraken(ticker, period)
        if df is not None:
            return df
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False, threads=False)
        if df is None or len(df) < 10:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.ffill().bfill()
        df = df.dropna(subset=["Close", "High", "Low", "Open"])
        # Drop any rows with non-positive prices (bad/corrupt data)
        df = df[(df["Close"] > 0) & (df["Open"] > 0) & (df["High"] > 0) & (df["Low"] > 0)]
        if len(df) < 10:
            return None
        return df
    except Exception:
        return None


def data_quality(df: pd.DataFrame, ticker: str = "", max_stale_days: int = 6,
                 is_crypto: bool = False) -> tuple[bool, str]:
    """
    Validate a price frame BEFORE it is fed to any signal/prediction.
    Checks: not empty, no NaN in OHLC, all prices > 0, and freshness.
    Returns (ok, reason). reason is '' when ok.
    """
    if df is None or len(df) == 0:
        return False, "no data"
    ohlc = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
    if df[ohlc].isnull().any().any():
        return False, "contains NaN/null prices"
    if (df[ohlc] <= 0).any().any():
        return False, "contains non-positive prices"
    # Freshness — last bar should be recent. Daily bars skip weekends/holidays,
    # so allow a few days of slack. Crypto trades 24/7 → stricter.
    try:
        last = pd.Timestamp(df.index[-1])
        if last.tzinfo is not None:
            last = last.tz_localize(None)
        age_days = (pd.Timestamp.now() - last).days
        limit = 2 if is_crypto else max_stale_days
        if age_days > limit:
            return False, f"stale data — last bar {age_days}d old"
    except Exception:
        pass
    return True, ""


# ══════════════════════════════════════════════════════════════════════
#  MARKET REGIME  (C1)
# ══════════════════════════════════════════════════════════════════════

def check_regime(mc: dict) -> dict:
    bm  = mc["benchmark"]
    df  = download(bm, period="1y")
    if df is None:
        return {"pass": True, "label": "Unknown (data unavailable)",
                "price": "—", "sma200": "—", "pct_above": 0.0, "_df": None}
    cl       = df["Close"].squeeze()
    s200     = sma(cl, 200)
    price    = round(float(cl.iloc[-1]), 2)
    sma200_v = round(float(s200.iloc[-1]), 2) if len(s200) else price
    pct      = round((price - sma200_v) / sma200_v * 100, 2)
    passing  = price > sma200_v
    return {
        "pass":      passing,
        "label":     "BULL — Above 200 SMA" if passing else "BEAR — Below 200 SMA",
        "price":     price,
        "sma200":    sma200_v,
        "pct_above": pct,
        "_df":       df,
    }


# ══════════════════════════════════════════════════════════════════════
#  MARKET HOURS AWARENESS
# ══════════════════════════════════════════════════════════════════════

# key -> (IANA timezone, open HH:MM, close HH:MM)
_MARKET_HOURS = {
    "US":     ("America/New_York", (9, 30), (16, 0)),
    "IN":     ("Asia/Kolkata",     (9, 15), (15, 30)),
    "UK":     ("Europe/London",    (8, 0),  (16, 30)),
    "EU":     ("Europe/Berlin",    (9, 0),  (17, 30)),
    "CA":     ("America/Toronto",  (9, 30), (16, 0)),
    "JP":     ("Asia/Tokyo",       (9, 0),  (15, 30)),
}


def market_status(market_key: str) -> dict:
    """
    Whether a market is currently open. Crypto is always open.
    NOTE: does not account for public holidays (weekday + clock only).
    Returns {"open": bool, "label": str, "local_time": "HH:MM TZ"}.
    """
    if market_key == "CRYPTO":
        return {"open": True, "label": "🟢 Open (24/7)", "local_time": ""}
    info = _MARKET_HOURS.get(market_key)
    if not info:
        return {"open": True, "label": "Unknown", "local_time": ""}
    tz_name, (oh, om), (ch, cm) = info
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        return {"open": True, "label": "Unknown", "local_time": ""}
    local_str = now.strftime("%H:%M ") + tz_name.split("/")[-1]
    if now.weekday() >= 5:          # Sat/Sun
        return {"open": False, "label": "🔴 Closed (weekend)", "local_time": local_str}
    is_open = _dtime(oh, om) <= now.time() <= _dtime(ch, cm)
    return {
        "open":       is_open,
        "label":      "🟢 Open" if is_open else "🔴 Closed",
        "local_time": local_str,
    }


# ══════════════════════════════════════════════════════════════════════
#  MINERVINI 8-CRITERIA TREND TEMPLATE  (C2)
# ══════════════════════════════════════════════════════════════════════

def minervini(close: pd.Series) -> dict:
    if len(close) < 200:
        return {"score": 0, "criteria": {}, "pass": False}

    s50  = float(sma(close, 50).iloc[-1])
    s150 = float(sma(close, 150).iloc[-1])
    s200 = float(sma(close, 200).iloc[-1])
    s200_prev = float(sma(close, 200).iloc[-22]) if len(close) >= 222 else s200 - 1
    price    = float(close.iloc[-1])
    hi52     = float(close.rolling(252).max().iloc[-1])
    lo52     = float(close.rolling(252).min().iloc[-1])

    crit = {
        "Price > 200 SMA":      price > s200,
        "Price > 150 SMA":      price > s150,
        "Price > 50 SMA":       price > s50,
        "150 > 200 SMA":        s150 > s200,
        "50 > 150 SMA":         s50 > s150,
        "200 SMA trending up":  s200 > s200_prev,
        "Within 25% of 52W Hi": price >= hi52 * 0.75,
        "30%+ above 52W Lo":    price >= lo52 * 1.30,
    }
    score = sum(crit.values())
    return {"score": score, "criteria": crit, "pass": score >= 5}


# ══════════════════════════════════════════════════════════════════════
#  RELATIVE STRENGTH vs BENCHMARK  (C3)
# ══════════════════════════════════════════════════════════════════════

def calc_rs(stock_close: pd.Series, bm_close: pd.Series) -> tuple[float, bool]:
    def _safe_ret(s, n):
        if len(s) < n + 1:
            return 1.0
        return float(s.iloc[-1]) / float(s.iloc[-n]) if float(s.iloc[-n]) != 0 else 1.0

    r3m_s = _safe_ret(stock_close, 63)
    r3m_b = _safe_ret(bm_close,   63)
    r6m_s = _safe_ret(stock_close, 126)
    r6m_b = _safe_ret(bm_close,   126)

    rs3 = r3m_s / r3m_b if r3m_b != 0 else 1.0
    rs6 = r6m_s / r6m_b if r6m_b != 0 else 1.0
    rs  = round((rs3 + rs6) / 2, 3)
    return rs, rs > 1.0


# ══════════════════════════════════════════════════════════════════════
#  LIQUIDITY SWEEP DETECTION  (C4)
# ══════════════════════════════════════════════════════════════════════

def detect_sweep(df: pd.DataFrame, lookback: int = 10) -> dict:
    if len(df) < lookback + 2:
        return {"pass": False, "sweep_low": None, "close": None}
    lo_window = float(df["Low"].iloc[-(lookback+1):-1].min())
    today_lo  = float(df["Low"].iloc[-1])
    today_cl  = float(df["Close"].iloc[-1])
    swept = today_lo < lo_window and today_cl > lo_window
    return {"pass": swept, "sweep_low": round(lo_window, 4), "close": round(today_cl, 4)}


# ══════════════════════════════════════════════════════════════════════
#  VOLUME CONFIRMATION  (C5)
# ══════════════════════════════════════════════════════════════════════

def check_volume(df: pd.DataFrame, multiplier: float = 1.5) -> dict:
    if "Volume" not in df.columns or len(df) < 52:
        return {"pass": False, "ratio": 0.0}
    vol50  = float(df["Volume"].iloc[-51:-1].mean())
    vol_td = float(df["Volume"].iloc[-1])
    if vol50 == 0:
        return {"pass": False, "ratio": 0.0}
    ratio = round(vol_td / vol50, 2)
    return {"pass": ratio >= multiplier, "ratio": ratio}


# ══════════════════════════════════════════════════════════════════════
#  ANCHORED VWAP  (C6)
# ══════════════════════════════════════════════════════════════════════

def calc_avwap(df: pd.DataFrame, window: int = 60) -> float | None:
    if len(df) < 10 or "Volume" not in df.columns:
        return None
    sl = df["Low"].rolling(window).min()
    anchor_idx = sl.idxmin() if sl.notna().any() else None
    if anchor_idx is None:
        return None
    sub = df.loc[anchor_idx:]
    # AVWAP needs ≥2 bars; when the anchor lands on the last row sub is single-
    # row, .squeeze() collapses to a scalar, .cumsum() returns ndarray, and the
    # subsequent .iloc crashes. Skip — single-bar AVWAP is meaningless anyway.
    if len(sub) < 2:
        return None
    tp  = (sub["High"].squeeze() + sub["Low"].squeeze() + sub["Close"].squeeze()) / 3
    vol = sub["Volume"].squeeze()
    cum_vol = vol.cumsum()
    if float(cum_vol.iloc[-1]) == 0:
        return None
    return round(float((tp * vol).cumsum().iloc[-1] / cum_vol.iloc[-1]), 4)


# ══════════════════════════════════════════════════════════════════════
#  VCP — VOLATILITY CONTRACTION PATTERN
# ══════════════════════════════════════════════════════════════════════

def detect_vcp(df: pd.DataFrame) -> dict:
    if len(df) < 45:
        return {"pass": False, "contraction": None}
    atr_now  = float(atr(df, 14).iloc[-1])
    atr_old  = float(atr(df.iloc[:-30], 14).iloc[-1]) if len(df) >= 45 else atr_now
    if atr_old == 0:
        return {"pass": False, "contraction": None}
    contraction = round((1 - atr_now / atr_old) * 100, 1)
    return {"pass": contraction >= 20, "contraction": contraction}


# ══════════════════════════════════════════════════════════════════════
#  SECTOR STRENGTH SCORING (US only)
# ══════════════════════════════════════════════════════════════════════

def score_sectors(mc: dict, bm_df: pd.DataFrame) -> dict:
    if not mc.get("has_sectors"):
        return {}
    bm_close = bm_df["Close"].squeeze()
    out = {}
    for etf, name in mc.get("sector_etfs", {}).items():
        df = download(etf, period="6mo")
        if df is None or len(df) < 22:
            continue
        cl    = df["Close"].squeeze()
        r1m   = round((float(cl.iloc[-1]) / float(cl.iloc[-22]) - 1) * 100, 2)
        r3m   = round((float(cl.iloc[-1]) / float(cl.iloc[min(-63, -len(cl))]) - 1) * 100, 2)
        rs, _ = calc_rs(cl, bm_close)
        above_sma50 = float(cl.iloc[-1]) > float(sma(cl, 50).iloc[-1]) if len(sma(cl, 50)) else False
        above_sma20 = float(cl.iloc[-1]) > float(sma(cl, 20).iloc[-1]) if len(sma(cl, 20)) else False
        score   = sum([r1m > 0, r3m > 0, rs > 1.0, above_sma50])
        leading = score >= 3
        out[etf] = {"name": name, "score": score, "r1m": r1m, "r3m": r3m,
                    "rs": rs, "leading": leading}
    return out


# ══════════════════════════════════════════════════════════════════════
#  R/R CALCULATOR — 3-TRANCHE EXIT
# ══════════════════════════════════════════════════════════════════════

def calc_rr(entry: float, stop: float, portfolio: float,
            risk_pct: float, currency: str) -> dict:
    if pd.isna(entry) or pd.isna(stop) or pd.isna(portfolio) or pd.isna(risk_pct):
        return {
            "shares": 0, "position": 0.0, "one_r": 0.0,
            "t1": 0.0, "t2": 0.0, "t3": 0.0, "rr_ratio": 0.0
        }
    one_r    = portfolio * risk_pct / 100
    risk_per = max(entry - stop, 0.001)
    if pd.isna(risk_per) or pd.isna(one_r) or risk_per <= 0:
        return {
            "shares": 0, "position": 0.0, "one_r": 0.0,
            "t1": 0.0, "t2": 0.0, "t3": 0.0, "rr_ratio": 0.0
        }
    shares   = max(1, int(one_r / risk_per))
    position = round(shares * entry, 2)
    t1       = round(entry + 1.5 * risk_per, 4)
    t2       = round(entry + 3.0 * risk_per, 4)
    t3       = round(entry + 5.0 * risk_per, 4)
    return {
        "shares":   shares,
        "position": position,
        "one_r":    round(one_r, 2),
        "t1":       t1,
        "t2":       t2,
        "t3":       t3,
        "rr_ratio": round((t1 - entry) / risk_per, 2),
    }


# ══════════════════════════════════════════════════════════════════════
#  FULL TICKER ANALYSIS
# ══════════════════════════════════════════════════════════════════════

def analyze_ticker(ticker: str, mc: dict, bm_df: pd.DataFrame | None,
                   portfolio: float, risk_pct: float) -> dict | None:
    df = download(ticker, period="1y")
    if df is None or len(df) < 50:
        return None

    # Data-quality gate — reject (and log) bad data instead of signalling on it
    is_crypto_t = mc.get("is_crypto", False) or "-USD" in ticker.upper()
    ok, why = data_quality(df, ticker, is_crypto=is_crypto_t)
    if not ok:
        log.warning(f"{ticker}: rejected — {why}")
        return None

    close = df["Close"].squeeze()
    price = round(float(close.iloc[-1]), 4)
    cur   = mc["currency"]

    # Indicators
    minn  = minervini(close)
    sweep = detect_sweep(df)
    vol   = check_volume(df)
    vcp   = detect_vcp(df)
    avwap = calc_avwap(df)

    # RS
    if bm_df is None:
        bm_df = download(mc["benchmark"], period="1y")
    rs_score, rs_pass = (1.0, False)
    if bm_df is not None:
        rs_score, rs_pass = calc_rs(close, bm_df["Close"].squeeze())

    # 8 EMA structure
    ema8_val  = float(ema(close, 8).iloc[-1])
    ema8_hold = price > ema8_val

    # Conditions summary
    c1 = True          # regime checked globally
    c2 = minn["pass"]          # Minervini >= 5/8
    c3 = sweep["pass"]         # liquidity sweep (bonus)
    c4 = vol["pass"]           # volume 1.5x
    c5 = ema8_hold             # above 8 EMA
    conditions_met = sum([c2, c3, c4, c5, rs_pass, vcp["pass"]])

    # Signal — sweep is a bonus, not hard required
    if c2 and c5 and rs_pass and (c3 or c4):
        signal = "BUY TODAY"
    elif c2 and c5 and rs_pass:
        signal = "PREPARE TO BUY"
    elif c2 and c5:
        signal = "WATCH"
    elif c2 or (conditions_met >= 3):
        signal = "WATCH"
    else:
        signal = "DO NOT BUY"

    # ── GUARDRAIL 1: RSI overbought check (Twelve Data, US stocks only) ──
    rsi_val      = None
    is_overbought = False
    is_crypto     = "-USD" in ticker.upper()
    is_india      = ticker.upper().endswith(".NS")
    if not is_india and not is_crypto:
        rsi_val = get_rsi(ticker)
        if rsi_val is not None:
            is_overbought = rsi_val > 75

    # ── GUARDRAIL 2: Extension penalty (price > 10% above 50 SMA) ────────
    s50_series   = sma(close, 50)
    s50_val      = float(s50_series.iloc[-1]) if len(s50_series) > 0 else price
    extension_pct = round((price - s50_val) / s50_val * 100, 1) if s50_val else 0
    is_extended  = extension_pct > 10

    # Downgrade BUY TODAY if overbought or extended — stock needs to breathe
    if signal == "BUY TODAY" and (is_overbought or is_extended):
        signal = "PREPARE TO BUY"

    # Hold time recommendation based on signal & VCP
    if signal == "BUY TODAY":
        hold_days = "5–15 trading days (swing trade)"
    elif signal == "PREPARE TO BUY":
        hold_days = "Wait for entry trigger, then 10–20 days"
    elif signal == "WATCH":
        hold_days = "Not ready yet — check again in 3–5 days"
    else:
        hold_days = "Avoid — no clear setup"

    # Stop & targets
    sweep_low = sweep.get("sweep_low") or float(df["Low"].iloc[-1])
    stop = round(sweep_low * 0.995, 4)

    # ── GUARDRAIL 3: Cap stop loss at 8% below entry ──────────────────────
    max_stop = round(price * 0.92, 4)
    stop     = max(stop, max_stop)  # Use whichever is closer to price (less risk)

    rr = calc_rr(price, stop, portfolio, risk_pct, cur)

    # Win probability (approx)
    base_win  = 55 + conditions_met * 4
    win_prob  = min(int(base_win), 88)

    # Verdict text
    reasons = []
    if not c2:        reasons.append(f"only {minn['score']}/8 Minervini criteria")
    if not c3:        reasons.append("no liquidity sweep today")
    if not c4:        reasons.append(f"volume only {vol['ratio']}x avg (need 1.5x)")
    if not c5:        reasons.append("price below 8 EMA")
    if not rs_pass:   reasons.append(f"RS {rs_score:.2f} underperforming benchmark")
    if is_overbought: reasons.append(f"RSI {rsi_val} overbought (>75) — wait for pullback")
    if is_extended:   reasons.append(f"price {extension_pct}% above 50 SMA — extended")

    if signal == "BUY TODAY":
        verdict = (f"Strong setup — Minervini {minn['score']}/8, RS {rs_score:.2f} outperforming, "
                   f"above 8 EMA. Entry {cur}{price}, stop {cur}{stop}. "
                   f"Target T1 {cur}{rr['t1']} (+1.5R), T2 {cur}{rr['t2']} (+3R), T3 {cur}{rr['t3']} (+5R). "
                   f"Hold {hold_days}.")
    elif signal == "PREPARE TO BUY":
        ob_note = f" RSI {rsi_val} (overbought — wait for pullback)." if is_overbought else ""
        ext_note = f" Extended {extension_pct}% above 50 SMA." if is_extended else ""
        verdict = (f"Good setup but not quite ready.{ob_note}{ext_note} Minervini {minn['score']}/8, RS {rs_score:.2f}. "
                   f"Set alert at {cur}{price}. Targets once triggered: T1 {cur}{rr['t1']}, T2 {cur}{rr['t2']}. "
                   f"Hold plan: {hold_days}.")
    elif signal == "WATCH":
        verdict = f"Partial setup ({conditions_met}/6 conditions met). Issues: {', '.join(reasons[:2]) if reasons else 'monitoring'}. Check again in 3–5 days."
    else:
        verdict = f"Not ready — {', '.join(reasons[:3]) if reasons else 'weak technicals'}. Wait for better market conditions."

    return {
        "ticker":          ticker,
        "price":           price,
        "currency":        cur,
        "signal":          signal,
        "verdict":         verdict,
        "hold_days":       hold_days,
        "win_prob":        win_prob,
        "minervini_score": minn["score"],
        "criteria":        minn["criteria"],
        "rs_score":        round(rs_score, 3),
        "sweep":           sweep,
        "volume":          vol,
        "vcp":             vcp,
        "avwap":           avwap,
        "ema8":            round(ema8_val, 4),
        "entry":           price,
        "stop":            stop,
        "rr":              rr,
        "t1_price":        rr["t1"],
        "t2_price":        rr["t2"],
        "rsi":             rsi_val,
        "is_overbought":   is_overbought,
        "is_extended":     is_extended,
        "extension_pct":   extension_pct,
        "track":           "crypto" if is_crypto_t else "stock",
        "_df":             df,
    }


# ══════════════════════════════════════════════════════════════════════
#  SCREENER — RUN OVER WATCHLIST
# ══════════════════════════════════════════════════════════════════════

def run_screener(watchlist: list, mc: dict, regime: dict,
                 portfolio: float, risk_pct: float) -> list:
    bm_df   = regime.get("_df")
    results = []
    order   = {"BUY TODAY": 0, "PREPARE TO BUY": 1, "WATCH": 2, "DO NOT BUY": 3}
    for ticker in watchlist:
        r = analyze_ticker(ticker, mc, bm_df, portfolio, risk_pct)
        if r:
            results.append(r)
    results.sort(key=lambda x: (order.get(x["signal"], 9), -x["win_prob"]))
    return results


# ══════════════════════════════════════════════════════════════════════
#  PORTFOLIO MONITOR
# ══════════════════════════════════════════════════════════════════════

def monitor_position(pos: dict, mc: dict, time_stop_candles: int = 5) -> dict:
    df = download(pos["ticker"], period="5d", interval="5m")
    if df is None or len(df) < 10:
        df = download(pos["ticker"], period="1mo")
    if df is None:
        return {"error": f"No data for {pos['ticker']}"}

    close    = df["Close"].squeeze()
    current  = round(float(close.iloc[-1]), 4)
    entry    = float(pos["entry"])
    shares   = int(pos["shares"])
    stop     = float(pos.get("stop", entry * 0.97))
    cur      = mc["currency"]

    rr       = calc_rr(entry, stop, shares * entry, 1.0, cur)
    t1       = rr["t1"]; t2 = rr["t2"]
    pnl_usd  = round((current - entry) * shares, 2)
    pnl_pct  = round((current - entry) / entry * 100, 2) if entry else 0
    ema8_val = round(float(ema(close, 8).iloc[-1]), 4)
    ema_hold = current > ema8_val
    t1_hit   = current >= t1
    t2_hit   = current >= t2
    stop_hit = current <= stop

    if stop_hit:
        action, action_col = "🚨 SELL — STOP OUT",       "#FF4D6A"
    elif t2_hit:
        action, action_col = "🎯 SELL — T2 HIT",         "#1D9E75"
    elif t1_hit:
        action, action_col = "💰 SELL 50% — T1 HIT",     "#FFB340"
    elif not ema_hold:
        action, action_col = "⚠️ EXIT — EMA BROKEN",     "#FF7A50"
    else:
        action, action_col = "🟢 HOLD",                  "#1D9E75"

    return {
        "ticker":     pos["ticker"],
        "entry":      round(entry, 4),
        "current":    current,
        "shares":     shares,
        "stop":       round(stop, 4),
        "t1":         round(t1, 4),
        "t2":         round(t2, 4),
        "pnl_usd":    pnl_usd,
        "pnl_pct":    pnl_pct,
        "ema8":       ema8_val,
        "ema_hold":   ema_hold,
        "t1_hit":     t1_hit,
        "t2_hit":     t2_hit,
        "stop_hit":   stop_hit,
        "action":     action,
        "action_col": action_col,
        "currency":   cur,
    }


# ══════════════════════════════════════════════════════════════════════
#  PROFIT PROBABILITY ENGINE
# ══════════════════════════════════════════════════════════════════════

def profit_probability(ticker: str, mc: dict, hold_days: int = 5) -> dict:
    df = download(ticker, period="2y")
    if df is None or len(df) < 60:
        return {"error": f"Not enough data for {ticker}"}

    close = df["Close"].squeeze()
    high  = df["High"].squeeze()
    low   = df["Low"].squeeze()
    price = float(close.iloc[-1])

    # Historical forward returns
    fwd = [(float(close.iloc[i+hold_days]) - float(close.iloc[i])) / float(close.iloc[i])
           for i in range(len(close) - hold_days)]
    fwd = np.array(fwd)
    base_rate = round(float(np.mean(fwd > 0)) * 100, 1)
    avg_gain  = round(float(np.mean(fwd[fwd > 0])) * 100, 2) if any(fwd > 0) else 0
    avg_loss  = round(float(np.mean(fwd[fwd < 0])) * 100, 2) if any(fwd < 0) else 0
    p75 = round(float(np.percentile(fwd, 75)) * 100, 2)
    p50 = round(float(np.median(fwd)) * 100, 2)
    p25 = round(float(np.percentile(fwd, 25)) * 100, 2)

    # Technical conditions
    bm_df = download(mc["benchmark"], period="1y")
    conds = {}
    s50v  = sma(close, 50)
    s200v = sma(close, 200)
    conds["Above 50 SMA"]     = price > float(s50v.iloc[-1])  if len(s50v)  else False
    conds["Above 200 SMA"]    = price > float(s200v.iloc[-1]) if len(s200v) else False
    conds["1M Momentum Up"]   = price > float(close.iloc[-22]) if len(close) >= 22 else False
    conds["RS Outperforming"] = False
    rs_score = 1.0
    if bm_df is not None:
        rs_score, rs_pass = calc_rs(close, bm_df["Close"].squeeze())
        conds["RS Outperforming"] = rs_pass
    atr14 = float(atr(df, 14).iloc[-1])
    atr_pct = round(atr14 / price * 100, 2)
    conds["Volatility OK"]    = atr_pct < 5.0
    vol = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series([1]*len(df))
    v5  = float(vol.iloc[-5:].mean())
    v50 = float(vol.iloc[-50:].mean()) if len(vol) >= 50 else v5
    conds["Volume Supportive"] = v5 > v50 * 0.9
    conds["8 EMA Hold"]        = price > float(ema(close, 8).iloc[-1])

    n_pass  = sum(conds.values())
    win_prob = min(round(base_rate + n_pass * 4.5, 1), 90.0)

    conf = "HIGH" if n_pass >= 6 else "MODERATE" if n_pass >= 4 else "LOW" if n_pass >= 2 else "VERY LOW"
    conf_col = {"HIGH": "#00C48C", "MODERATE": "#1D9E75", "LOW": "#FFB340", "VERY LOW": "#FF4D6A"}[conf]

    bull = round(price * (1 + p75 / 100), 4)
    base = round(price * (1 + p50 / 100), 4)
    bear = round(price * (1 + p25 / 100), 4)

    if win_prob >= 70:
        outlook = f"Bullish outlook — {win_prob:.0f}% historical win rate over {hold_days} day(s). {n_pass}/7 signals active."
    elif win_prob >= 55:
        outlook = f"Cautious — {win_prob:.0f}% win rate. Mixed signals ({n_pass}/7). Trade with smaller size."
    else:
        outlook = f"Bearish setup — only {win_prob:.0f}% win rate here. Wait for better conditions."

    return {
        "ticker":      ticker,
        "price":       round(price, 4),
        "currency":    mc["currency"],
        "hold_days":   hold_days,
        "win_prob":    win_prob,
        "base_rate":   base_rate,
        "confidence":  conf,
        "conf_col":    conf_col,
        "n_pass":      n_pass,
        "conds":       conds,
        "bull":        bull,
        "base":        base,
        "bear":        bear,
        "bull_pct":    p75,
        "base_pct":    p50,
        "bear_pct":    p25,
        "avg_gain":    avg_gain,
        "avg_loss":    avg_loss,
        "atr_pct":     atr_pct,
        "rs_score":    round(rs_score, 3),
        "outlook":     outlook,
    }


# ══════════════════════════════════════════════════════════════════════
#  FUNDAMENTALS
# ══════════════════════════════════════════════════════════════════════

def fetch_fundamentals(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
        rg   = info.get("revenueGrowth")
        eg   = info.get("earningsGrowth")
        rec  = info.get("recommendationKey", "")
        rec_label = {"strong_buy":"Strong Buy","buy":"Buy","hold":"Hold",
                     "underperform":"Underperform","sell":"Sell"}.get(rec, rec.title() if rec else "N/A")
        rec_col = {"Strong Buy":"#00C48C","Buy":"#1D9E75","Hold":"#FFB340",
                   "Underperform":"#FF7A50","Sell":"#FF4D6A"}.get(rec_label, "#4A7FA5")
        return {
            "name":        info.get("shortName", ticker),
            "sector":      info.get("sector", "—"),
            "industry":    info.get("industry", "—"),
            "description": info.get("longBusinessSummary", ""),
            "rev_growth":  round(rg * 100, 1)  if rg  is not None else None,
            "earn_growth": round(eg * 100, 1)  if eg  is not None else None,
            "rec":         rec_label,
            "rec_col":     rec_col,
            "target":      round(info.get("targetMeanPrice", 0), 2) or None,
            "analysts":    info.get("numberOfAnalystOpinions", 0),
            "inst_pct":    round(info.get("heldPercentInstitutions", 0) * 100, 1) or None,
            "pe":          round(info.get("trailingPE", 0), 1) or None,
            "fwd_pe":      round(info.get("forwardPE", 0), 1) or None,
            "peg":         round(info.get("pegRatio", 0), 2) or None,
            "mkt_cap":     info.get("marketCap"),
        }
    except Exception:
        return {"error": True}


# ══════════════════════════════════════════════════════════════════════
#  NEWS + SENTIMENT
# ══════════════════════════════════════════════════════════════════════

def fetch_news(ticker: str, n: int = 6) -> list:
    pos_words = {"surges","beats","record","upgrade","buy","profit","growth",
                 "strong","boost","gain","rises","rally","soars","exceeds"}
    neg_words = {"misses","falls","drops","sell","loss","warning","decline",
                 "cut","downgrade","lawsuit","fraud","risk","plunges","slumps"}
    try:
        raw = yf.Ticker(ticker).news or []
        out = []
        for item in raw[:n]:
            title = item.get("title", "")
            words = set(title.lower().split())
            pos = len(words & pos_words); neg = len(words & neg_words)
            if pos > neg:   sent, col = "🟢 Positive", "#00C48C"
            elif neg > pos: sent, col = "🔴 Negative", "#FF4D6A"
            else:           sent, col = "⚪ Neutral",  "#4A7FA5"
            out.append({"title": title, "link": item.get("link","#"),
                        "pub": item.get("publisher",""), "sent": sent, "col": col})
        return out
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════
#  OPTIONS SNAPSHOT
# ══════════════════════════════════════════════════════════════════════

def fetch_options(ticker: str) -> dict:
    from datetime import datetime
    try:
        t    = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return {"error": "No options listed for this ticker."}
        today = datetime.today()
        exp = exps[0]
        for e in exps:
            if (datetime.strptime(e, "%Y-%m-%d") - today).days >= 20:
                exp = e; break
        chain = t.option_chain(exp)
        calls = chain.calls; puts = chain.puts
        price = (t.info or {}).get("regularMarketPrice") or float(calls["strike"].median())
        def atm(df):
            df = df.copy(); df["d"] = (df["strike"] - price).abs()
            row = df.loc[df["d"].idxmin()]
            return {"strike": float(row["strike"]), "bid": float(row["bid"]),
                    "ask": float(row["ask"]),
                    "iv":  round(float(row.get("impliedVolatility", 0)) * 100, 1),
                    "vol": int(row.get("volume", 0)),
                    "oi":  int(row.get("openInterest", 0))}
        cols = ["strike","bid","ask","volume","openInterest","impliedVolatility"]
        return {
            "expiry": exp,
            "dte":    (datetime.strptime(exp,"%Y-%m-%d") - today).days,
            "price":  price,
            "call":   atm(calls),
            "put":    atm(puts),
            "calls":  calls[[c for c in cols if c in calls.columns]].head(10).reset_index(drop=True),
            "puts":   puts [[c for c in cols if c in puts.columns]].head(10).reset_index(drop=True),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Actionable options trade recommendation ───────────────────────────

def recommend_option(ticker: str, stock_signal: dict, portfolio: float,
                     risk_pct: float = 2.0) -> dict | None:
    """Turn a stock signal into a concrete options trade recommendation.

    Returns None when the setup doesn't qualify:
    - win_prob < 60 (insufficient edge)
    - VIX > 30 (premiums too expensive)
    - no options chain available for the ticker
    - earnings fall inside the contract window
    """
    from datetime import datetime, date
    import math

    win_prob = stock_signal.get("win_prob", 0)
    signal   = stock_signal.get("signal", "")
    t1_price = stock_signal.get("t1_price") or stock_signal.get("rr", {}).get("t1")
    cur_price = stock_signal.get("price") or stock_signal.get("entry")

    if win_prob < 60:
        return {"skip_reason": f"win_prob {win_prob}% < 60 — insufficient edge for options"}

    # direction
    is_bearish = signal in ("SELL", "SELL TODAY", "DO NOT BUY")
    direction  = "PUT" if is_bearish else "CALL"

    # VIX gate
    try:
        vix_data = fetch_vix()
        if vix_data.get("level", 0) > 30:
            return {"skip_reason": f"VIX {vix_data['level']:.1f} > 30 — premiums too expensive"}
    except Exception:
        pass

    try:
        t    = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return {"skip_reason": "No options listed for this ticker"}

        today = datetime.today()

        # pick nearest expiry with 30-50 DTE
        exp = None
        for e in exps:
            dte = (datetime.strptime(e, "%Y-%m-%d") - today).days
            if 30 <= dte <= 50:
                exp = e
                break
        if exp is None:
            # fallback: nearest >= 25 DTE
            for e in exps:
                if (datetime.strptime(e, "%Y-%m-%d") - today).days >= 25:
                    exp = e
                    break
        if exp is None:
            return {"skip_reason": "No expiry with ≥25 DTE available"}

        dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days

        # earnings check
        earnings_in_window = False
        try:
            cal = t.calendar
            if cal is not None:
                earn_col = "Earnings Date" if "Earnings Date" in cal else None
                if earn_col:
                    earn_dates = cal[earn_col]
                    earn_dates = [earn_dates] if not hasattr(earn_dates, "__iter__") else list(earn_dates)
                    exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                    for ed in earn_dates:
                        try:
                            ed_d = ed.date() if hasattr(ed, "date") else date.fromisoformat(str(ed)[:10])
                            if date.today() <= ed_d <= exp_date:
                                earnings_in_window = True
                        except Exception:
                            pass
        except Exception:
            pass

        chain     = t.option_chain(exp)
        contracts = chain.calls if direction == "CALL" else chain.puts

        if contracts.empty:
            return {"skip_reason": f"No {direction} contracts found for {exp}"}

        # current price
        info  = t.info or {}
        price = float(info.get("regularMarketPrice") or cur_price or
                      contracts["strike"].median())

        # strike selection
        contracts = contracts.copy()
        contracts["d"] = (contracts["strike"] - price).abs()
        contracts_sorted = contracts.sort_values("d")

        if win_prob >= 70:
            # slightly OTM — next strike beyond current price
            if direction == "CALL":
                otm = contracts[contracts["strike"] > price].sort_values("strike")
            else:
                otm = contracts[contracts["strike"] < price].sort_values("strike", ascending=False)
            row = otm.iloc[0] if len(otm) > 0 else contracts_sorted.iloc[0]
        else:
            row = contracts_sorted.iloc[0]  # ATM

        strike      = float(row["strike"])
        bid         = float(row.get("bid", 0))
        ask         = float(row.get("ask", 0))
        entry_prem  = ask if ask > 0 else bid
        if entry_prem <= 0:
            return {"skip_reason": "Contract has no valid ask price (illiquid)"}

        delta_raw = float(row.get("delta", 0)) if "delta" in row.index else None
        if delta_raw is None or delta_raw == 0:
            # fallback delta estimate: ATM ≈ 0.50, OTM ≈ 0.35
            delta_raw = 0.50 if abs(strike - price) / price < 0.03 else 0.35
        delta = abs(delta_raw)

        theta = float(row.get("theta", 0)) if "theta" in row.index else None
        vega  = float(row.get("vega",  0)) if "vega"  in row.index else None
        iv    = round(float(row.get("impliedVolatility", 0)) * 100, 1)

        # IV percentile (30-day approximation from chain IV spread)
        try:
            all_ivs = contracts["impliedVolatility"].dropna() * 100
            iv_min  = float(all_ivs.min())
            iv_max  = float(all_ivs.max())
            iv_pct  = (iv - iv_min) / (iv_max - iv_min) if iv_max > iv_min else 0.5
            iv_label = "HIGH" if iv_pct >= 0.70 else "LOW" if iv_pct <= 0.30 else "NORMAL"
        except Exception:
            iv_label = "NORMAL"

        # ── Exit targets using delta + simple gamma correction ────────────
        # At T1: stock moved from price → t1_price. Delta increases as option
        # goes further in-the-money. We add a small gamma bump (+0.10) for T2.
        t2_price = stock_signal.get("t2_price") or stock_signal.get("rr", {}).get("t2")

        if t1_price and cur_price:
            move_t1  = (t1_price - price) if direction == "CALL" else (price - t1_price)
            move_t1  = max(move_t1, 0)
            prem_t1  = round(entry_prem + delta * move_t1, 2)

            # T2 uses delta + 0.10 gamma correction (option is deeper ITM by then)
            if t2_price:
                delta_t2 = min(delta + 0.10, 0.90)
                move_t2  = (t2_price - price) if direction == "CALL" else (price - t2_price)
                move_t2  = max(move_t2, 0)
                prem_t2  = round(entry_prem + delta_t2 * move_t2, 2)
            else:
                prem_t2 = round(prem_t1 * 1.5, 2)
        else:
            prem_t1  = round(entry_prem * 2.0, 2)
            prem_t2  = round(entry_prem * 3.0, 2)

        prem_stop = round(entry_prem * 0.50, 2)

        # Theta-based max hold: how many days before 50% of entry premium decays?
        # If theta unavailable, estimate from DTE (daily theta ≈ premium / DTE * 0.5 for ATM)
        max_hold_days = None
        if theta and abs(theta) > 0:
            max_hold_days = max(3, int(entry_prem * 0.5 / abs(theta)))
        elif dte > 0:
            est_daily_theta = entry_prem / dte * 0.5
            if est_daily_theta > 0:
                max_hold_days = max(3, int(entry_prem * 0.5 / est_daily_theta))
        if max_hold_days:
            max_hold_days = min(max_hold_days, dte - 5)  # never hold to within 5 days of expiry

        # Exit-by date
        from datetime import timedelta
        exit_by_date = (datetime.today() + timedelta(days=max_hold_days)).strftime("%d %b") if max_hold_days else None

        # Breakeven stock price
        breakeven = round(strike + entry_prem, 2) if direction == "CALL" else round(strike - entry_prem, 2)

        # Position sizing: max risk_pct% of portfolio per trade
        max_risk_dollars = portfolio * (risk_pct / 100)
        n_contracts = max(1, int(math.floor(max_risk_dollars / (entry_prem * 100))))
        actual_risk  = round(n_contracts * entry_prem * 100, 2)

        pnl_pct_t1 = round((prem_t1 - entry_prem) / entry_prem * 100, 1) if entry_prem > 0 else 0
        pnl_pct_t2 = round((prem_t2 - entry_prem) / entry_prem * 100, 1) if entry_prem > 0 else 0

        cur_sym = stock_signal.get("currency", "$")

        # ── Trading plan verdict (explicit, actionable) ────────────────
        plan_lines = [
            f"{'ATM' if win_prob < 70 else 'Slightly OTM'} {direction} on {ticker} — {win_prob}% confidence.",
            f"BUY: {n_contracts} contract(s) at {cur_sym}{entry_prem:.2f} premium (max risk {cur_sym}{actual_risk:,.0f}).",
            f"SELL HALF at T1: when premium hits {cur_sym}{prem_t1:.2f} (+{pnl_pct_t1:.0f}%) — stock near {cur_sym}{t1_price}.",
        ]
        if t2_price:
            plan_lines.append(
                f"SELL REST at T2: when premium hits {cur_sym}{prem_t2:.2f} (+{pnl_pct_t2:.0f}%) — stock near {cur_sym}{t2_price}."
            )
        plan_lines.append(
            f"STOP LOSS: exit ALL if premium drops to {cur_sym}{prem_stop:.2f} (-50%). No exceptions."
        )
        if exit_by_date:
            plan_lines.append(
                f"TIME STOP: exit by {exit_by_date} ({max_hold_days} days) — theta accelerates after that."
            )
        if earnings_in_window:
            plan_lines.append("CAUTION: Earnings inside contract window — binary event risk.")
        if iv_label == "HIGH":
            plan_lines.append("CAUTION: IV is elevated — wait for a down-day to enter at lower premium.")

        return {
            "ticker":             ticker,
            "direction":          direction,
            "strike":             strike,
            "expiry":             exp,
            "dte":                dte,
            "premium_entry":      round(entry_prem, 2),
            "premium_t1":         prem_t1,
            "premium_t2":         prem_t2,
            "premium_stop":       prem_stop,
            "premium_target":     prem_t1,      # backward-compat alias
            "breakeven_stock":    breakeven,
            "contracts":          n_contracts,
            "max_risk_usd":       actual_risk,
            "delta":              round(delta, 2),
            "theta":              round(theta, 3) if theta else None,
            "vega":               round(vega,  3) if vega  else None,
            "iv":                 iv,
            "iv_label":           iv_label,
            "earnings_in_window": earnings_in_window,
            "pnl_pct_at_t1":     pnl_pct_t1,
            "pnl_pct_at_t2":     pnl_pct_t2,
            "max_hold_days":      max_hold_days,
            "exit_by_date":       exit_by_date,
            "t1_stock_price":     t1_price,
            "t2_stock_price":     t2_price,
            "verdict":            " ".join(plan_lines),
            "track":              "options",
        }
    except Exception as e:
        return {"skip_reason": f"Options fetch error: {str(e)[:80]}"}


# ══════════════════════════════════════════════════════════════════════
#  COMPOUNDING SIMULATOR
# ══════════════════════════════════════════════════════════════════════

def compound(lump: float, sip: float, cagr: float, inflation: float, years: int = 30) -> dict:
    rate   = cagr / 100 / 12
    infl   = inflation / 100
    val    = lump
    inv    = lump
    yearly = []
    for yr in range(1, years + 1):
        for _ in range(12):
            val += val * rate + sip
            inv += sip
        real = val / (1 + infl) ** yr
        yearly.append({"year": yr, "nominal": round(val, 0),
                       "real": round(real, 0), "invested": round(inv, 0),
                       "gain_pct": round((val - inv) / inv * 100, 1) if inv else 0})
    milestones = [r for r in yearly if r["year"] in (5, 10, 15, 20, 25, 30)]
    return {"yearly": yearly, "milestones": milestones}


# ══════════════════════════════════════════════════════════════════════
#  WEEKLY TREND CONFIRMATION
# ══════════════════════════════════════════════════════════════════════

def check_weekly_trend(ticker: str) -> dict:
    """Weekly close above 10-week EMA = confirmed uptrend."""
    df = download(ticker, period="1y", interval="1wk")
    if df is None or len(df) < 10:
        return {"pass": True, "reason": "no weekly data", "ema10w": None}
    close     = df["Close"].squeeze()
    ema10w    = ema(close, 10)
    price     = round(float(close.iloc[-1]), 4)
    ema10w_v  = round(float(ema10w.iloc[-1]), 4)
    above     = price > ema10w_v
    pct_diff  = round((price - ema10w_v) / ema10w_v * 100, 2) if ema10w_v else 0
    return {"pass": above, "price": price, "ema10w": ema10w_v, "pct_diff": pct_diff}


# ══════════════════════════════════════════════════════════════════════
#  VIX REGIME GATE
# ══════════════════════════════════════════════════════════════════════

_YF_SCREENER = (
    "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
    "?scrIds=day_gainers&count=100&formatted=false"
)
_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36"}


def fetch_market_gainers(threshold_pct: float = 29.0) -> list[dict]:
    """Market-wide intraday gainers via Yahoo Finance screener.
    Returns stocks with regularMarketChangePercent >= threshold_pct.
    No API key needed. Results deduped by symbol."""
    out: dict[str, dict] = {}   # symbol → pick, deduped

    def _parse(url: str, currency: str, market_label: str):
        try:
            r = requests.get(url, headers=_YF_HEADERS, timeout=15)
            if r.status_code != 200:
                return
            docs = ((r.json().get("finance") or {})
                    .get("result") or [{}])[0].get("documents", [])
            for d in docs:
                chg = d.get("regularMarketChangePercent") or 0.0
                sym = d.get("symbol", "")
                if not sym or chg < threshold_pct:
                    continue
                if sym not in out:
                    out[sym] = {
                        "ticker":       sym,
                        "price":        round(d.get("regularMarketPrice") or 0.0, 4),
                        "change_pct":   round(chg, 1),
                        "volume":       int(d.get("regularMarketVolume") or 0),
                        "currency":     currency,
                        "market_label": market_label,
                    }
        except Exception as e:
            log.debug(f"fetch_market_gainers ({market_label}): {e}")

    _parse(_YF_SCREENER, "$", "🇺🇸 US Stocks")
    _parse(_YF_SCREENER + "&region=IN&lang=en-IN", "₹", "🇮🇳 India NSE")
    result = sorted(out.values(), key=lambda x: x["change_pct"], reverse=True)
    log.debug(f"fetch_market_gainers: {len(result)} stock(s) >= {threshold_pct}%")
    return result


# ══════════════════════════════════════════════════════════════════════

def fetch_vix() -> dict:
    """Current VIX level — market fear gauge."""
    df = download("^VIX", period="5d")
    if df is None or len(df) < 1:
        return {"level": 20.0, "regime": "normal", "label": "Normal", "color": "#FFB340", "error": True}
    vix = round(float(df["Close"].squeeze().iloc[-1]), 2)
    if vix < 15:
        regime, label, color = "low",      "Low Fear — Strong Bull",     "#00C48C"
    elif vix < 20:
        regime, label, color = "normal",   "Normal — Proceed",           "#1D9E75"
    elif vix < 28:
        regime, label, color = "elevated", "Elevated — Reduce Size",     "#FFB340"
    elif vix < 35:
        regime, label, color = "high",     "High Fear — Be Cautious",    "#FF7A50"
    else:
        regime, label, color = "extreme",  "Extreme Fear — Avoid Buys",  "#FF4D6A"
    return {"level": vix, "regime": regime, "label": label, "color": color}


# ══════════════════════════════════════════════════════════════════════
#  ALPHA VANTAGE NEWS + SENTIMENT
# ══════════════════════════════════════════════════════════════════════

def fetch_news_av(ticker: str, market_suffix: str = "") -> list:
    """Alpha Vantage NEWS_SENTIMENT — returns richer news with sentiment scores."""
    key = _av_key()
    if not key:
        return []
    # AV uses plain ticker without .NS/.L/.DE etc.
    av_ticker = ticker.split(".")[0] if "." in ticker else ticker
    av_ticker = av_ticker.replace("-USD", "").replace("^", "")
    try:
        url = (f"https://www.alphavantage.co/query"
               f"?function=NEWS_SENTIMENT&tickers={av_ticker}&limit=8&apikey={key}")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "feed" not in data:
            return []
        out = []
        sentiment_map = {
            "Bullish":          ("🟢 Bullish",         "#00C48C"),
            "Somewhat-Bullish": ("🟢 Somewhat Bullish", "#1D9E75"),
            "Neutral":          ("⚪ Neutral",          "#4A7FA5"),
            "Somewhat-Bearish": ("🔴 Somewhat Bearish", "#FF7A50"),
            "Bearish":          ("🔴 Bearish",          "#FF4D6A"),
        }
        for item in data["feed"][:8]:
            lbl = item.get("overall_sentiment_label", "Neutral")
            sent, col = sentiment_map.get(lbl, ("⚪ Neutral", "#4A7FA5"))
            score = round(float(item.get("overall_sentiment_score", 0)), 3)
            out.append({
                "title":  item.get("title", ""),
                "link":   item.get("url", "#"),
                "pub":    item.get("source", ""),
                "sent":   sent,
                "col":    col,
                "score":  score,
                "summary": item.get("summary", ""),
            })
        return out
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════
#  AUTO-SUFFIX HELPER
# ══════════════════════════════════════════════════════════════════════

def auto_suffix(ticker: str, market_key: str) -> str:
    """Add correct market suffix if ticker has none."""
    ticker = ticker.upper().strip()
    suffix_map = {
        "IN":     ".NS",
        "UK":     ".L",
        "EU":     ".DE",
        "CA":     ".TO",
        "JP":     ".T",
        "AU":     ".AX",
    }
    required = suffix_map.get(market_key, "")
    if not required:
        return ticker
    # Already has a suffix (any dot)
    if "." in ticker or "-" in ticker:
        return ticker
    return ticker + required


# ══════════════════════════════════════════════════════════════════════
#  PORTFOLIO SENTIMENT (news + Gemini quick read for held positions)
# ══════════════════════════════════════════════════════════════════════

def portfolio_sentiment(positions: list[dict]) -> dict:
    """
    For each held position, pull the latest news headlines, derive a quick
    colour-coded sentiment label, and ask Gemini for a 2-sentence summary.
    Returns {ticker: {"label": str, "color": str, "summary": str, "headlines": list}}.
    Gracefully degrades when news / Gemini are unavailable.
    """
    import notifier as _notif
    out = {}
    for pos in (positions or []):
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        news = fetch_news(ticker, n=4) or []
        if not news:
            news = fetch_news_av(ticker)[:4] if _av_key() else []
        # majority sentiment
        pos_n = sum(1 for n in news if "Positive" in (n.get("sent") or "") or "Bull" in (n.get("sent") or ""))
        neg_n = sum(1 for n in news if "Negative" in (n.get("sent") or "") or "Bear" in (n.get("sent") or ""))
        if pos_n > neg_n:   label, color = "🟢 Positive",   "#00C48C"
        elif neg_n > pos_n: label, color = "🔴 Negative",   "#FF4D6A"
        else:               label, color = "⚪ Mixed/Neutral", "#4A7FA5"

        headlines = [n.get("title", "") for n in news[:3]]
        # Short Gemini summary (cached). Don't crash the portfolio tab if
        # quota/network/no-key — fall back to a built sentence.
        summary = ""
        if headlines:
            try:
                prompt = (f"In ≤2 sentences, summarise this week's "
                          f"news risk for {ticker}. Headlines: "
                          + " | ".join(headlines[:3]) +
                          " End with 'Not financial advice.'")
                summary = _notif._gemini_cached_call(prompt, kind="briefing")
            except Exception:
                summary = ""
        if not summary:
            summary = f"{ticker}: {label}. {len(news)} recent headlines."
        out[ticker] = {"label": label, "color": color,
                       "summary": summary, "headlines": headlines}
    return out


# ══════════════════════════════════════════════════════════════════════
#  SAFE FUNDAMENTALS (crash-proof version)
# ══════════════════════════════════════════════════════════════════════

def fetch_fundamentals_safe(ticker: str) -> dict:
    """fetch_fundamentals with full crash protection."""
    try:
        return fetch_fundamentals(ticker)
    except Exception:
        return {"error": True}
