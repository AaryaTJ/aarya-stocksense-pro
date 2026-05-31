"""
Aarya StockSense Pro — alpaca_client.py
Alpaca paper-trading + market-data integration.

Used for:
  1. Live option price lookup (current premium → SELL/HOLD/STOP signal)
  2. Live stock quote during market hours
  3. Paper order placement (future)

Keys read from (in order):
  1. aarya_config.json  {"alpaca": {"api_key":…,"secret":…,"base_url":…}}
  2. Streamlit secrets  ALPACA_API_KEY / ALPACA_SECRET / ALPACA_BASE_URL
  3. Environment vars   ALPACA_API_KEY / ALPACA_SECRET / ALPACA_BASE_URL
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime

import requests

from applog import get_logger

log = get_logger("aarya_alpaca")

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aarya_config.json")
_DATA_URL    = "https://data.alpaca.markets"


# ── Credential helpers ────────────────────────────────────────────────

def _creds() -> tuple[str, str, str]:
    """Return (api_key, secret, base_url)."""
    key = secret = base = ""

    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE) as f:
                d = json.load(f)
            alp    = d.get("alpaca", {})
            key    = alp.get("api_key", "")
            secret = alp.get("secret",  "")
            base   = alp.get("base_url","https://paper-api.alpaca.markets/v2")
        except Exception:
            pass

    if not key or not secret:
        try:
            import streamlit as st
            key    = key    or str(st.secrets.get("ALPACA_API_KEY",  ""))
            secret = secret or str(st.secrets.get("ALPACA_SECRET",   ""))
            base   = base   or str(st.secrets.get("ALPACA_BASE_URL",
                                                   "https://paper-api.alpaca.markets/v2"))
        except Exception:
            pass

    if not key:
        key    = os.environ.get("ALPACA_API_KEY",  "")
    if not secret:
        secret = os.environ.get("ALPACA_SECRET",   "")
    if not base:
        base   = os.environ.get("ALPACA_BASE_URL",
                                "https://paper-api.alpaca.markets/v2")

    return key.strip(), secret.strip(), base.strip()


def _headers() -> dict:
    key, secret, _ = _creds()
    return {
        "APCA-API-KEY-ID":     key,
        "APCA-API-SECRET-KEY": secret,
        "accept":              "application/json",
    }


def is_configured() -> bool:
    key, secret, _ = _creds()
    return bool(key and secret)


# ── OCC option symbol builder ─────────────────────────────────────────

def build_occ_symbol(ticker: str, expiry_str: str, direction: str,
                     strike: float) -> str:
    """Build OCC option symbol.

    AAPL  240119  C  00150000
    ^^^^  ^^^^^^  ^  ^^^^^^^^
    root  YYMMDD  C/P  strike * 1000, 8 digits
    """
    root  = ticker.upper().strip()[:6].ljust(6)   # 6-char root, right-padded with spaces
    dt    = datetime.strptime(expiry_str, "%Y-%m-%d")
    date  = dt.strftime("%y%m%d")                 # YYMMDD
    cp    = "C" if direction.upper() == "CALL" else "P"
    stk   = str(int(round(strike * 1000))).zfill(8)
    return f"{root}{date}{cp}{stk}"


# ── Live option quote from Alpaca ─────────────────────────────────────

def get_option_quote(ticker: str, expiry_str: str, direction: str,
                     strike: float) -> dict | None:
    """
    Returns current option mid-price and greeks from Alpaca data API.
    Falls back to yfinance if Alpaca data is unavailable.

    Return dict keys: mid, bid, ask, delta, theta, iv, source
    Returns None on complete failure.
    """
    if not is_configured():
        return _yf_option_quote(ticker, expiry_str, direction, strike)

    occ = build_occ_symbol(ticker, expiry_str, direction, strike)
    try:
        r = requests.get(
            f"{_DATA_URL}/v1beta1/options/snapshots",
            headers=_headers(),
            params={"symbols": occ, "feed": "indicative"},
            timeout=10,
        )
        if r.status_code == 200:
            snapshots = r.json().get("snapshots", {})
            snap      = snapshots.get(occ)
            if snap:
                q   = snap.get("latestQuote", {})
                g   = snap.get("greeks", {})
                bid = float(q.get("bp", 0) or 0)
                ask = float(q.get("ap", 0) or 0)
                mid = round((bid + ask) / 2, 2) if (bid + ask) > 0 else None
                if mid is None or mid == 0:
                    mid = float(snap.get("latestTrade", {}).get("p", 0) or 0) or None
                return {
                    "mid":    round(mid, 2) if mid else None,
                    "bid":    round(bid, 2),
                    "ask":    round(ask, 2),
                    "delta":  round(float(g.get("delta", 0) or 0), 3),
                    "theta":  round(float(g.get("theta", 0) or 0), 3),
                    "iv":     round(float(snap.get("impliedVolatility", 0) or 0) * 100, 1),
                    "source": "Alpaca",
                    "symbol": occ,
                }
        log.debug(f"Alpaca option snapshot status {r.status_code} for {occ}")
    except Exception as e:
        log.debug(f"Alpaca option quote error: {e}")

    return _yf_option_quote(ticker, expiry_str, direction, strike)


def _yf_option_quote(ticker: str, expiry_str: str, direction: str,
                     strike: float) -> dict | None:
    """yfinance fallback for current option price."""
    try:
        import yfinance as yf
        t     = yf.Ticker(ticker)
        chain = t.option_chain(expiry_str)
        df    = chain.calls if direction.upper() == "CALL" else chain.puts
        df    = df[abs(df["strike"] - strike) < 0.01]
        if df.empty:
            df = (chain.calls if direction.upper() == "CALL" else chain.puts).copy()
            df["d"] = (df["strike"] - strike).abs()
            df = df.sort_values("d").head(1)
        if df.empty:
            return None
        row = df.iloc[0]
        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        mid = round((bid + ask) / 2, 2) if (bid + ask) > 0 else None
        iv  = round(float(row.get("impliedVolatility", 0) or 0) * 100, 1)
        return {
            "mid":    mid,
            "bid":    round(bid, 2),
            "ask":    round(ask, 2),
            "delta":  None,
            "theta":  None,
            "iv":     iv,
            "source": "yfinance",
            "symbol": build_occ_symbol(ticker, expiry_str, direction, strike),
        }
    except Exception as e:
        log.debug(f"yfinance option quote fallback error: {e}")
    return None


# ── Live stock quote ──────────────────────────────────────────────────

def get_stock_quote(ticker: str) -> dict | None:
    """Latest trade price from Alpaca data API."""
    if not is_configured():
        return None
    try:
        r = requests.get(
            f"{_DATA_URL}/v2/stocks/{ticker.upper()}/trades/latest",
            headers=_headers(),
            params={"feed": "iex"},
            timeout=8,
        )
        if r.status_code == 200:
            trade = r.json().get("trade", {})
            price = float(trade.get("p", 0) or 0)
            if price > 0:
                return {"price": round(price, 4), "source": "Alpaca/IEX",
                        "timestamp": trade.get("t", "")}
    except Exception as e:
        log.debug(f"Alpaca stock quote error: {e}")
    return None


# ── Option position status — the core "sell/hold/stop" logic ──────────

def check_option_status(rec: dict) -> dict:
    """
    Given an options recommendation dict (from engine.recommend_option),
    fetch the current premium and return a clear status signal.

    Returns:
      {
        "status":       "SELL_T1" | "SELL_T2" | "STOP" | "HOLD" | "ERROR",
        "action":       human-readable action string,
        "color":        hex color for the status,
        "current_mid":  float | None,
        "entry":        float,
        "t1_target":    float,
        "t2_target":    float | None,
        "stop":         float,
        "pnl_pct":      float | None,
        "source":       "Alpaca" | "yfinance",
        "message":      str,
      }
    """
    ticker    = rec.get("ticker", "")
    expiry    = rec.get("expiry", "")
    direction = rec.get("direction", "CALL")
    strike    = rec.get("strike", 0.0)
    entry     = rec.get("premium_entry", 0.0)
    t1        = rec.get("premium_t1") or rec.get("premium_target", 0.0)
    t2        = rec.get("premium_t2")
    stop      = rec.get("premium_stop", 0.0)

    if not (ticker and expiry and strike and entry):
        return {"status": "ERROR", "action": "Missing recommendation data.",
                "color": "#4A7FA5", "current_mid": None, "entry": entry,
                "t1_target": t1, "t2_target": t2, "stop": stop,
                "pnl_pct": None, "source": "—", "message": "No active recommendation."}

    quote = get_option_quote(ticker, expiry, direction, strike)

    if not quote or not quote.get("mid"):
        return {"status": "ERROR", "action": "Cannot fetch live premium.",
                "color": "#4A7FA5", "current_mid": None, "entry": entry,
                "t1_target": t1, "t2_target": t2, "stop": stop,
                "pnl_pct": None, "source": quote.get("source","—") if quote else "—",
                "message": ("Market may be closed, or contract has no bids. "
                             "Check during market hours (9:30 AM–4 PM ET).")}

    mid     = quote["mid"]
    pnl_pct = round((mid - entry) / entry * 100, 1) if entry > 0 else None

    if t2 and mid >= t2:
        status  = "SELL_T2"
        action  = f"SELL ALL — T2 HIT (+{pnl_pct:.0f}%)"
        color   = "#00C48C"
        message = (f"Premium {mid:.2f} has reached T2 target {t2:.2f}. "
                   f"Exit entire position now and lock in +{pnl_pct:.0f}% gain.")
    elif mid >= t1:
        status  = "SELL_T1"
        action  = f"SELL HALF — T1 HIT (+{pnl_pct:.0f}%)"
        color   = "#FFB340"
        message = (f"Premium {mid:.2f} has reached T1 target {t1:.2f}. "
                   f"Sell half your contracts, hold the rest for T2 ({t2:.2f})." if t2 else
                   f"Premium {mid:.2f} reached T1 target {t1:.2f}. Sell all and take profit.")
    elif mid <= stop:
        status  = "STOP"
        action  = f"EXIT ALL — STOP HIT ({pnl_pct:.0f}%)"
        color   = "#FF4D6A"
        message = (f"Premium {mid:.2f} has fallen to/below stop {stop:.2f}. "
                   f"Exit entire position immediately — do not wait.")
    else:
        status  = "HOLD"
        action  = "HOLD — between stop and target"
        color   = "#4A7FA5"
        pct_to_t1 = round((t1 - mid) / mid * 100, 1) if mid > 0 else None
        message = (f"Premium {mid:.2f} is between stop ({stop:.2f}) and T1 ({t1:.2f}). "
                   + (f"Need +{pct_to_t1:.0f}% more to reach T1." if pct_to_t1 else "")
                   + " Hold the position.")

    return {
        "status":      status,
        "action":      action,
        "color":       color,
        "current_mid": mid,
        "bid":         quote.get("bid"),
        "ask":         quote.get("ask"),
        "entry":       entry,
        "t1_target":   t1,
        "t2_target":   t2,
        "stop":        stop,
        "pnl_pct":     pnl_pct,
        "iv":          quote.get("iv"),
        "delta":       quote.get("delta"),
        "theta":       quote.get("theta"),
        "source":      quote.get("source", "—"),
        "message":     message,
    }
