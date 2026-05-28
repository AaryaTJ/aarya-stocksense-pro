"""
Aarya StockSense Pro — engine.py
Full strategy engine: indicators, Minervini, sweeps, RS, R/R,
fundamentals, news, options, compounding, profit probability.
"""

import warnings
warnings.filterwarnings("ignore")

import json
import os
import numpy as np
import pandas as pd
import yfinance as yf
import requests

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
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False, threads=False)
        if df is None or len(df) < 10:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.ffill().bfill()
        df = df.dropna(subset=["Close", "High", "Low", "Open"])
        if len(df) < 10:
            return None
        return df
    except Exception:
        return None


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
    rr   = calc_rr(price, stop, portfolio, risk_pct, cur)

    # Win probability (approx)
    base_win  = 55 + conditions_met * 4
    win_prob  = min(int(base_win), 88)

    # Verdict text
    reasons = []
    if not c2:   reasons.append(f"only {minn['score']}/8 Minervini criteria")
    if not c3:   reasons.append("no liquidity sweep today")
    if not c4:   reasons.append(f"volume only {vol['ratio']}x avg (need 1.5x)")
    if not c5:   reasons.append("price below 8 EMA")
    if not rs_pass: reasons.append(f"RS {rs_score:.2f} underperforming benchmark")

    if signal == "BUY TODAY":
        verdict = (f"Strong setup — Minervini {minn['score']}/8, RS {rs_score:.2f} outperforming, "
                   f"above 8 EMA. Entry {cur}{price}, stop {cur}{stop}. "
                   f"Target T1 {cur}{rr['t1']} (+1.5R), T2 {cur}{rr['t2']} (+3R), T3 {cur}{rr['t3']} (+5R). "
                   f"Hold {hold_days}.")
    elif signal == "PREPARE TO BUY":
        verdict = (f"Good setup but waiting for volume/sweep trigger. Minervini {minn['score']}/8, RS {rs_score:.2f}. "
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
#  SAFE FUNDAMENTALS (crash-proof version)
# ══════════════════════════════════════════════════════════════════════

def fetch_fundamentals_safe(ticker: str) -> dict:
    """fetch_fundamentals with full crash protection."""
    try:
        return fetch_fundamentals(ticker)
    except Exception:
        return {"error": True}
