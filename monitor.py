"""
Aarya StockSense Pro — monitor.py
Standalone background monitoring script.
Runs WITHOUT the Streamlit app open.

What it does each run:
  1. Scans US + India watchlists → picks top 3 strongest buy setups (non-penny)
     → sends one daily digest email
  2. Detects penny spikes (price < $10 / ₹500, change > 29%)
     → sends a separate penny spike email
  3. Checks every portfolio position for sell / stop alerts
     → sends individual sell warning emails

Run manually:
    python monitor.py

Run via Windows Task Scheduler (see schedule_aarya.bat):
    Scheduled daily at market open + mid-day
"""

import json
import logging
import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import engine as eng
import notifier
from config import MARKET_CONFIGS

# ── Logging ────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(BASE_DIR, "monitor.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("aarya_monitor")

SETTINGS_FILE = os.path.join(BASE_DIR, "aarya_settings.json")


# ── Helpers ────────────────────────────────────────────────────────────

def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"portfolio": 10000, "risk_pct": 1.0, "positions": [], "time_stop": 5}


def _score(r: dict) -> float:
    return r.get("win_prob", 0) * 0.5 + r.get("minervini_score", 0) * 5 + r.get("rs_score", 0) * 10


# ── 1. Daily Top-3 Buy Picks ───────────────────────────────────────────

def check_buy_picks(cfg: dict) -> list:
    """
    Scan US + India watchlists. Return up to 3 best non-penny setups
    sorted by composite score (win_prob + Minervini + RS).
    """
    markets_to_scan = [
        ("🇺🇸 US Stocks",  "$",  10.0),
        ("🇮🇳 India NSE",  "₹",  500.0),
    ]
    all_picks = []

    for market_name, currency, penny_cutoff in markets_to_scan:
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue

        # Use growth + blue_chips list (max 20 tickers to stay within free API limits)
        tickers = list(dict.fromkeys(
            mc.get("growth", []) + mc.get("blue_chips", [])
        ))[:20]

        log.info(f"Scanning {market_name}: {len(tickers)} tickers…")
        try:
            regime = eng.check_regime(mc)
        except Exception as e:
            log.warning(f"{market_name} regime check failed: {e}")
            regime = {"pass": True, "label": "Unknown", "price": "—", "sma200": "—", "pct_above": 0.0}

        for ticker in tickers:
            try:
                r = eng.analyze_ticker(ticker, mc, regime, cfg["portfolio"], cfg["risk_pct"])
                if r is None:
                    continue
                # Skip penny stocks for the daily top-3
                if r.get("price", 999) < penny_cutoff:
                    continue
                if r["signal"] in ("BUY TODAY", "PREPARE TO BUY"):
                    r["currency"]     = currency
                    r["market_label"] = market_name
                    all_picks.append(r)
            except Exception as e:
                log.debug(f"{ticker} analysis error: {e}")

    all_picks.sort(key=_score, reverse=True)
    log.info(f"Buy picks found: {len(all_picks)} total — top 3: "
             f"{[p['ticker'] for p in all_picks[:3]]}")
    return all_picks[:3]


# ── 2. Penny Spike Scanner ─────────────────────────────────────────────

def check_penny_spikes(cfg: dict) -> list:
    """
    Scan US + India watchlists for penny stocks (< $10 / ₹500)
    that spiked more than 29% today.
    """
    markets_to_scan = [
        ("🇺🇸 US Stocks",  "$",  10.0),
        ("🇮🇳 India NSE",  "₹",  500.0),
    ]
    spikes = []

    for market_name, currency, penny_cutoff in markets_to_scan:
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue
        tickers = list(dict.fromkeys(
            mc.get("growth", []) + mc.get("blue_chips", [])
        ))[:20]

        for ticker in tickers:
            try:
                df = eng.download(ticker, period="5d")
                if df is None or len(df) < 2:
                    continue
                price = float(df["Close"].squeeze().iloc[-1])
                if price >= penny_cutoff:
                    continue
                prev  = float(df["Close"].squeeze().iloc[-2])
                chg   = (price - prev) / prev * 100 if prev else 0
                if chg < 29.0:
                    continue
                # Volume ratio
                vol_series = df["Volume"].squeeze()
                vol_avg    = float(vol_series.iloc[:-1].mean()) if len(vol_series) > 1 else 1
                vol_ratio  = float(vol_series.iloc[-1]) / vol_avg if vol_avg else 1.0
                spikes.append({
                    "ticker":       ticker,
                    "price":        price,
                    "change":       chg,
                    "vol_ratio":    round(vol_ratio, 1),
                    "currency":     currency,
                    "market_label": market_name,
                })
                log.info(f"PENNY SPIKE: {ticker} +{chg:.1f}% @ {currency}{price:.2f}")
            except Exception as e:
                log.debug(f"{ticker} penny check error: {e}")

    return spikes


# ── 3. Portfolio Sell-Alert Check ──────────────────────────────────────

def check_portfolio(cfg: dict) -> list:
    """
    Check every logged position. Return list of positions that need action.
    """
    positions = cfg.get("positions", [])
    if not positions:
        log.info("No portfolio positions to monitor.")
        return []

    alerts = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        market = pos.get("market", "US")

        # Find matching market config
        mc = next(
            (v for v in MARKET_CONFIGS.values() if v["key"] == market),
            MARKET_CONFIGS["🇺🇸 US Stocks"]
        )

        try:
            m = eng.monitor_position(pos, mc, cfg.get("time_stop", 5))
            if "error" in m:
                log.warning(f"Portfolio monitor error for {ticker}: {m['error']}")
                continue
            action = m.get("action", "🟢 HOLD")
            if action != "🟢 HOLD":
                log.info(f"SELL ALERT: {ticker} → {action} (P&L {m.get('pnl_pct',0):+.1f}%)")
                alerts.append((pos, m))
        except Exception as e:
            log.debug(f"{ticker} portfolio check error: {e}")

    return alerts


# ── MAIN ───────────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info(f"Aarya StockSense Pro — Background Monitor")
    log.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    cfg = load_settings()

    # ── Step 1: Top-3 buy picks ────────────────────────────────────────
    log.info("Step 1/3: Scanning for top buy picks…")
    picks = []
    try:
        picks = check_buy_picks(cfg)
    except Exception as e:
        log.error(f"Buy-picks scan failed: {e}")

    if picks:
        try:
            ok, msg = notifier.send_daily_top3_email(picks)
            log.info(f"Daily top-3 email: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Daily top-3 email error: {e}")
        try:
            ok, msg = notifier.wa_daily_top3(picks)
            log.info(f"Daily top-3 WhatsApp: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Daily top-3 WhatsApp error: {e}")
    else:
        log.info("No strong buy picks found today — daily email skipped.")

    # ── Step 2: Penny spike scan ───────────────────────────────────────
    log.info("Step 2/3: Scanning for penny spikes…")
    spikes = []
    try:
        spikes = check_penny_spikes(cfg)
    except Exception as e:
        log.error(f"Penny spike scan failed: {e}")

    if spikes:
        try:
            ok, msg = notifier.send_daily_penny_email(spikes)
            log.info(f"Penny spike email: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Penny spike email error: {e}")
        try:
            ok, msg = notifier.wa_penny_spikes(spikes)
            log.info(f"Penny spike WhatsApp: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Penny spike WhatsApp error: {e}")
    else:
        log.info("No penny spikes today — penny email skipped.")

    # ── Step 3: Portfolio sell alerts ──────────────────────────────────
    log.info("Step 3/3: Checking portfolio for sell alerts…")
    sell_alerts = []
    try:
        sell_alerts = check_portfolio(cfg)
    except Exception as e:
        log.error(f"Portfolio check failed: {e}")

    if sell_alerts:
        for pos, m in sell_alerts:
            try:
                ok, msg = notifier.send_sell_alert(pos, m)
                log.info(f"Sell alert for {pos.get('ticker','?')}: {'✅ ' + msg if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Sell alert email error: {e}")
            try:
                ok, msg = notifier.wa_sell_alert(pos, m)
                log.info(f"Sell alert WhatsApp for {pos.get('ticker','?')}: {'✅ ' + msg if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Sell alert WhatsApp error: {e}")
    else:
        log.info("All portfolio positions are healthy — no sell alerts.")

    log.info(f"Monitor run complete. {len(picks)} picks · {len(spikes)} penny spikes · "
             f"{len(sell_alerts)} sell alert(s).")
    log.info("=" * 60)


if __name__ == "__main__":
    run()
