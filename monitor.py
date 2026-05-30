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
import db
import mldb
import scanner_contrarian
from ml import predictor as ml_predictor
from config import MARKET_CONFIGS
from datetime import date as _date

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

def check_buy_picks(cfg: dict) -> tuple[list, list, dict]:
    """
    Scan US + India watchlists.
    Returns (strong_picks[:3], watch_picks[:3], regimes)
    strong_picks = BUY TODAY / PREPARE TO BUY
    watch_picks  = WATCH signals (shown in daily update when no strong picks)
    regimes      = {"us": regime_dict, "india": regime_dict}
    """
    markets_to_scan = [
        ("🇺🇸 US Stocks", "us",  "$",  10.0),
        ("🇮🇳 India NSE", "india", "₹", 500.0),
    ]
    strong_picks = []
    watch_picks  = []
    regimes      = {}

    for market_name, mkt_key, currency, penny_cutoff in markets_to_scan:
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue

        tickers = list(dict.fromkeys(
            mc.get("growth", []) + mc.get("blue_chips", [])
        ))[:20]

        log.info(f"Scanning {market_name}: {len(tickers)} tickers…")
        try:
            regime = eng.check_regime(mc)
        except Exception as e:
            log.warning(f"{market_name} regime check failed: {e}")
            regime = {"pass": True, "label": "Unknown", "price": "—", "sma200": "—", "pct_above": 0.0}

        regimes[mkt_key] = regime

        for ticker in tickers:
            try:
                r = eng.analyze_ticker(ticker, mc, regime.get("_df"), cfg["portfolio"], cfg["risk_pct"])
                if r is None:
                    continue
                if r.get("price", 999) < penny_cutoff:
                    continue
                r["currency"]     = currency
                r["market_label"] = market_name
                if r["signal"] in ("BUY TODAY", "PREPARE TO BUY"):
                    strong_picks.append(r)
                elif r["signal"] == "WATCH":
                    watch_picks.append(r)
            except Exception as e:
                log.debug(f"{ticker} analysis error: {e}")

    strong_picks.sort(key=_score, reverse=True)
    watch_picks.sort(key=_score, reverse=True)
    log.info(f"Strong picks: {len(strong_picks)} | Watch: {len(watch_picks)}")
    return strong_picks[:3], watch_picks[:3], regimes


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


def check_portfolio_users() -> list:
    """
    Per-user portfolio monitoring sourced from Supabase (each user's own
    positions). Returns list of (user_dict, pos, monitor) tuples needing action.
    Returns [] when Supabase is unavailable (caller falls back to local).
    """
    try:
        users = db.get_all_users_with_settings()
    except Exception as e:
        log.warning(f"Could not load users from Supabase: {e}")
        return []
    if not users:
        return []

    log.info(f"Per-user portfolio check across {len(users)} user(s) with positions/Telegram.")
    alerts = []
    for u in users:
        for pos in u.get("positions", []):
            ticker = pos.get("ticker", "")
            market = pos.get("market", "US")
            mc = next((v for v in MARKET_CONFIGS.values() if v["key"] == market),
                      MARKET_CONFIGS["🇺🇸 US Stocks"])
            try:
                m = eng.monitor_position(pos, mc, u.get("time_stop", 5))
                if "error" in m:
                    log.warning(f"[{u.get('email','?')}] monitor error {ticker}: {m['error']}")
                    continue
                if m.get("action", "🟢 HOLD") != "🟢 HOLD":
                    log.info(f"SELL ALERT [{u.get('email','?')}]: {ticker} → {m['action']}")
                    alerts.append((u, pos, m))
            except Exception as e:
                log.debug(f"{ticker} per-user check error: {e}")
    return alerts


def _dedup_send(kind: str, ticker: str, dedup_key: str, send_fn):
    """Skip a send if its dedup_key was already recorded today; record on success."""
    try:
        if mldb.already_sent(dedup_key):
            log.info(f"Dedup skip → {dedup_key}")
            return True, "deduped"
    except Exception:
        pass
    ok, msg = send_fn()
    if ok:
        try:
            mldb.mark_sent(kind, ticker, dedup_key)
        except Exception:
            pass
    return ok, msg


# ── Contrarian scan (wraps scanner_contrarian for the two main markets) ──

def check_contrarian_picks(cfg: dict) -> list:
    out = []
    for market_name, currency in (("🇺🇸 US Stocks", "$"), ("🇮🇳 India NSE", "₹")):
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue
        try:
            regime = eng.check_regime(mc)
        except Exception:
            regime = {"_df": None}
        try:
            picks = scanner_contrarian.scan_contrarian(mc, regime,
                                                      cfg["portfolio"], cfg["risk_pct"])
            for p in picks:
                p["currency"]     = currency
                p["market_label"] = market_name
            out.extend(picks)
        except Exception as e:
            log.warning(f"Contrarian scan failed for {market_name}: {e}")
    return out


# ── High-Momentum Breakout scan ────────────────────────────────────────

def check_momentum_breakouts(cfg: dict) -> list:
    """
    Picks already-analysed tickers that are also in a fresh breakout state
    (price > 5-day high, RSI 60-70, 2x+ volume, RS > 1.20, Minervini >= 6,
    ML confidence >= 70). Returns a (possibly empty) list of result dicts
    with intraday_pct + vol_ratio + confidence attached.
    """
    out = []
    for market_name, currency in (("🇺🇸 US Stocks", "$"), ("🇮🇳 India NSE", "₹")):
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue
        tickers = list(dict.fromkeys(mc.get("growth", []) + mc.get("blue_chips", [])))[:20]
        try:
            regime = eng.check_regime(mc)
        except Exception:
            regime = {"_df": None}
        for t in tickers:
            try:
                r = eng.analyze_ticker(t, mc, regime.get("_df"),
                                       cfg["portfolio"], cfg["risk_pct"])
                if r is None:
                    continue
                if r.get("minervini_score", 0) < 6:
                    continue
                if (r.get("rs_score") or 0) < 1.20:
                    continue
                rsi = r.get("rsi")
                if rsi is None or not (60 <= rsi <= 70):
                    continue
                vol_ratio = (r.get("volume") or {}).get("ratio", 0)
                if vol_ratio < 2.0:
                    continue
                # 5-day high check (yesterday's rolling 5-day high; today must exceed it)
                df = r.get("_df")
                if df is None or len(df) < 7:
                    continue
                hi5 = float(df["Close"].iloc[-6:-1].max())
                if r["price"] <= hi5:
                    continue
                prev = float(df["Close"].iloc[-2])
                intraday_pct = (r["price"] - prev) / prev * 100 if prev else 0.0

                # ML confidence gate
                try:
                    conf = ml_predictor.score_prediction(r)
                except Exception:
                    conf = float(r.get("win_prob", 50))
                if conf < 70:
                    log.info(f"Momentum skip {t}: confidence {conf}")
                    continue

                r["currency"]     = currency
                r["market_label"] = market_name
                r["intraday_pct"] = round(intraday_pct, 2)
                r["vol_ratio"]    = round(vol_ratio, 2)
                r["confidence"]   = conf
                out.append(r)
                log.info(f"MOMENTUM BREAKOUT: {t} +{intraday_pct:.1f}% on "
                         f"{vol_ratio:.1f}x vol  conf={conf}")
            except Exception as e:
                log.debug(f"{t} momentum error: {e}")
    return out


# ── MAIN ───────────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info(f"Aarya StockSense Pro — Background Monitor")
    log.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    cfg = load_settings()

    # ── Determine forced daily-update session ──────────────────────────
    # Prefer the exact cron that triggered this run (deterministic, immune to
    # GitHub Actions scheduling delays). Fall back to a widened UTC-hour window
    # for local/manual runs where GH_SCHEDULE is not set.
    #   Morning digest   = '30 3 * * 1-5'  (9:00 AM IST)
    #   Afternoon digest = '30 9 * * 1-5'  (3:00 PM IST)
    sched = os.environ.get("GH_SCHEDULE", "").strip()
    if sched:
        if sched == "30 3 * * 1-5":
            force_update, session_name = True, "Morning"
        elif sched == "30 9 * * 1-5":
            force_update, session_name = True, "Afternoon"
        else:
            force_update, session_name = False, ""
        log.info(f"Triggered by cron '{sched}' | Force update: {force_update} ({session_name})")
    else:
        utc_hour = datetime.utcnow().hour
        if utc_hour in (3, 4):
            force_update, session_name = True, "Morning"
        elif utc_hour in (9, 10):
            force_update, session_name = True, "Afternoon"
        else:
            force_update, session_name = False, ""
        log.info(f"No cron env (local/manual). UTC hour {utc_hour} | Force update: {force_update} ({session_name})")

    # Market open/closed status (awareness for 'buy now' wording)
    statuses = {"us": eng.market_status("US"), "india": eng.market_status("IN")}
    log.info(f"Market status — US: {statuses['us']['label']} | India: {statuses['india']['label']}")

    # ── Step 1: Top-3 buy picks ────────────────────────────────────────
    log.info("Step 1/3: Scanning for top buy picks…")
    picks = watches = []
    regimes = {}
    try:
        picks, watches, regimes = check_buy_picks(cfg)
    except Exception as e:
        log.error(f"Buy-picks scan failed: {e}")

    # ── Log every strong pick for the ML feedback loop (cold-start data) ──
    if mldb.available():
        logged = 0
        for p in picks:
            try:
                if mldb.log_prediction(p):
                    logged += 1
            except Exception as e:
                log.debug(f"log_prediction {p.get('ticker','?')} error: {e}")
        log.info(f"Logged {logged}/{len(picks)} prediction(s) to Supabase.")
    else:
        log.info("Supabase ML store not configured — prediction logging skipped.")

    # ── Contrarian / oversold-quality scan ────────────────────────────
    log.info("Step 1b: Scanning contrarian / oversold-quality setups…")
    try:
        contrarian = check_contrarian_picks(cfg)
        log.info(f"Contrarian picks: {len(contrarian)}")
    except Exception as e:
        log.error(f"Contrarian scan failed: {e}")
        contrarian = []
    if mldb.available():
        for p in contrarian:
            try:
                mldb.log_prediction(p)
            except Exception:
                pass

    # ── High-momentum breakout scan (intraday alerts) ─────────────────
    log.info("Step 1c: Scanning for high-momentum breakouts…")
    try:
        momentum = check_momentum_breakouts(cfg)
        log.info(f"Momentum breakouts: {len(momentum)}")
    except Exception as e:
        log.error(f"Momentum scan failed: {e}")
        momentum = []

    # Collect all Telegram chat IDs from website registrations + env fallback
    tg_chat_ids = []
    try:
        tg_chat_ids = db.get_all_telegram_chat_ids()
        log.info(f"Telegram recipients: {len(tg_chat_ids)}")
    except Exception as e:
        log.warning(f"Could not load Telegram chat IDs: {e}")

    today = _date.today().isoformat()

    # Always send daily update email at 9 AM and 3 PM IST (once per session/day)
    if force_update:
        try:
            ok, msg = _dedup_send(
                "email_digest", session_name, f"email:digest:{session_name}:{today}",
                lambda: notifier.send_market_update_email(session_name, regimes, picks, watches, statuses))
            log.info(f"{session_name} market update email: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Market update email error: {e}")
    elif picks:
        # Other runs: only email if strong signals found (once per day)
        try:
            ok, msg = _dedup_send(
                "email_top3", "top3", f"email:top3:{today}",
                lambda: notifier.send_daily_top3_email(picks))
            log.info(f"Daily top-3 email: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Daily top-3 email error: {e}")
    else:
        log.info("No strong buy picks and not a forced run — email skipped.")

    if picks:
        for cid in tg_chat_ids:
            try:
                ok, msg = _dedup_send(
                    "tg_top3", "top3", f"tg:top3:{cid}:{today}",
                    lambda: notifier.tg_daily_top3(picks, cid))
                log.info(f"Daily top-3 Telegram → {cid}: {'✅' if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Daily top-3 Telegram error ({cid}): {e}")

    # ── Step 2: Penny spike scan ───────────────────────────────────────
    log.info("Step 2/3: Scanning for penny spikes…")
    spikes = []
    try:
        spikes = check_penny_spikes(cfg)
    except Exception as e:
        log.error(f"Penny spike scan failed: {e}")

    if spikes:
        try:
            ok, msg = _dedup_send(
                "email_penny", "penny", f"email:penny:{today}",
                lambda: notifier.send_daily_penny_email(spikes))
            log.info(f"Penny spike email: {'✅ ' + msg if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Penny spike email error: {e}")
        for cid in tg_chat_ids:
            try:
                ok, msg = _dedup_send(
                    "tg_penny", "penny", f"tg:penny:{cid}:{today}",
                    lambda: notifier.tg_penny_spikes(spikes, cid))
                log.info(f"Penny spike Telegram → {cid}: {'✅' if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Penny spike Telegram error ({cid}): {e}")
    else:
        log.info("No penny spikes today — penny email skipped.")

    # ── Momentum breakout alerts (one per ticker, deduped per day) ────
    for r in momentum:
        t = r.get("ticker", "?")
        try:
            ok, msg = _dedup_send(
                "email_momentum", t, f"email:momentum:{t}:{today}",
                lambda: notifier.send_momentum_alert(r, confidence=r.get("confidence")))
            log.info(f"Momentum email {t}: {'✅' if ok else '❌ ' + msg}")
        except Exception as e:
            log.error(f"Momentum email error ({t}): {e}")
        for cid in tg_chat_ids:
            try:
                ok, msg = _dedup_send(
                    "tg_momentum", t, f"tg:momentum:{cid}:{t}:{today}",
                    lambda: notifier.tg_momentum_alert(r, confidence=r.get("confidence"), chat_id=cid))
                log.info(f"Momentum TG {t} → {cid}: {'✅' if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Momentum TG error ({t}/{cid}): {e}")

    # ── Step 3: Portfolio sell alerts ──────────────────────────────────
    # Prefer per-user positions from Supabase (each user gets alerts for THEIR
    # own positions, on THEIR email + Telegram). Fall back to local settings
    # (single-user / offline) when Supabase isn't configured.
    log.info("Step 3/3: Checking portfolio for sell alerts…")
    n_alerts = 0
    try:
        user_alerts = check_portfolio_users()
    except Exception as e:
        log.error(f"Per-user portfolio check failed: {e}")
        user_alerts = []

    # Also collect trail-stop opportunities: held positions up >= 1R that
    # haven't yet hit T1 — suggest moving the stop to lock in profit.
    trail_alerts = []
    if mldb.available():
        try:
            for u in db.get_all_users_with_settings():
                for pos in u.get("positions", []):
                    market = pos.get("market", "US")
                    mc = next((v for v in MARKET_CONFIGS.values() if v["key"] == market),
                              MARKET_CONFIGS["🇺🇸 US Stocks"])
                    try:
                        m = eng.monitor_position(pos, mc, u.get("time_stop", 5))
                        if "error" in m or m.get("action") != "🟢 HOLD":
                            continue
                        entry = float(m["entry"])
                        stop  = float(m["stop"])
                        current = float(m["current"])
                        one_r = max(entry - stop, 1e-6)
                        gain  = current - entry
                        # Up at least 1R but T1 not yet hit -> suggest trail to BE
                        if gain >= one_r and current < float(m.get("t1", entry)):
                            suggested = round(entry, 4)  # break-even
                            trail_alerts.append((u, pos, m, suggested))
                    except Exception:
                        continue
        except Exception:
            pass

    if user_alerts:
        for u, pos, m in user_alerts:
            n_alerts += 1
            tkr = pos.get("ticker", "?")
            key = f"sell:{u['user_id']}:{tkr}:{m['action']}:{today}"
            if u.get("email"):
                try:
                    ok, msg = _dedup_send("email_sell", tkr, "email:" + key,
                                          lambda: notifier.send_sell_alert(pos, m, to_email=u["email"]))
                    log.info(f"Sell email [{u['email']}] {tkr}: {'✅' if ok else '❌ ' + msg}")
                except Exception as e:
                    log.error(f"Sell email error ({tkr}): {e}")
            cid = u.get("telegram_chat_id", "")
            if cid:
                try:
                    ok, msg = _dedup_send("tg_sell", tkr, "tg:" + key,
                                          lambda: notifier.tg_sell_alert(pos, m, cid))
                    log.info(f"Sell Telegram [{cid}] {tkr}: {'✅' if ok else '❌ ' + msg}")
                except Exception as e:
                    log.error(f"Sell Telegram error ({tkr}): {e}")

    # Trail-stop alerts
    for u, pos, m, suggested in trail_alerts:
        tkr = pos.get("ticker", "?")
        key = f"trail:{u['user_id']}:{tkr}:{today}"
        if u.get("email"):
            try:
                ok, msg = _dedup_send("email_trail", tkr, "email:" + key,
                                      lambda: notifier.send_trail_stop_email(pos, m, suggested, to_email=u["email"]))
                log.info(f"Trail email [{u['email']}] {tkr}: {'✅' if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Trail email error ({tkr}): {e}")
        cid = u.get("telegram_chat_id", "")
        if cid:
            try:
                ok, msg = _dedup_send("tg_trail", tkr, "tg:" + key,
                                      lambda: notifier.tg_trail_stop(pos, m, suggested, cid))
                log.info(f"Trail TG [{cid}] {tkr}: {'✅' if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Trail TG error ({tkr}): {e}")
    else:
        # Fallback: local settings positions → global recipients + all chat IDs
        try:
            local_alerts = check_portfolio(cfg)
        except Exception as e:
            log.error(f"Local portfolio check failed: {e}")
            local_alerts = []
        for pos, m in local_alerts:
            n_alerts += 1
            tkr = pos.get("ticker", "?")
            key = f"sell:local:{tkr}:{m['action']}:{today}"
            try:
                ok, msg = _dedup_send("email_sell", tkr, "email:" + key,
                                      lambda: notifier.send_sell_alert(pos, m))
                log.info(f"Sell alert email {tkr}: {'✅' if ok else '❌ ' + msg}")
            except Exception as e:
                log.error(f"Sell alert email error: {e}")
            for cid in tg_chat_ids:
                try:
                    ok, msg = _dedup_send("tg_sell", tkr, f"tg:{cid}:" + key,
                                          lambda: notifier.tg_sell_alert(pos, m, cid))
                    log.info(f"Sell alert Telegram → {cid}: {'✅' if ok else '❌ ' + msg}")
                except Exception as e:
                    log.error(f"Sell alert Telegram error ({cid}): {e}")
        if not local_alerts:
            log.info("All portfolio positions are healthy — no sell alerts.")

    # ── Step 4: ML feedback loop (only on the afternoon US-open run) ─
    # Once per day is enough; pick the 13:30 UTC run (7 PM IST, US open) so we
    # have fresh closes from the previous US session and India intraday.
    if mldb.available() and sched == "30 13 * * 1-5":
        log.info("Step 4/4: ML evaluate + train…")
        try:
            n_eval, n_hit, n_soft = ml_predictor.evaluate_open_predictions()
            log.info(f"Evaluator: {n_eval} evaluated  {n_hit} hit  {n_soft} soft-hit")
        except Exception as e:
            log.error(f"ML evaluation failed: {e}")
        try:
            ml_predictor.train_ensemble()
        except Exception as e:
            log.error(f"ML training failed: {e}")

    # ── Step 5: Weekly report (Sunday only) ───────────────────────────
    if sched == "30 12 * * 0":
        try:
            from ml import weekly_report
            weekly_report.send_weekly_report(tg_chat_ids)
        except Exception as e:
            log.error(f"Weekly report failed: {e}")

    log.info(f"Monitor run complete. {len(picks)} trend · {len(contrarian)} contrarian · "
             f"{len(spikes)} penny · {len(momentum)} momentum · "
             f"{n_alerts} sell · {len(trail_alerts)} trail.")
    log.info("=" * 60)


if __name__ == "__main__":
    run()
