"""
Aarya StockSense Pro — tests/smoke_test.py
Fast, offline smoke test for the Phase 1 + 2 hardening work. Verifies the logic
that does NOT require Streamlit UI or live cloud credentials:

  • all core modules import
  • market-hours status
  • data-quality gate (NaN / non-positive / stale rejection)
  • Telegram HTML rendering (no stray backslashes, proper <b> tags)
  • email digest renders for open/closed markets (send mocked out)
  • SMTP retry path returns a clean failure after N attempts
  • mldb + per-user db helpers degrade gracefully with no credentials

Run:  python tests/smoke_test.py
Exits non-zero if any check fails.

NOTE: Streamlit button clicks cannot be exercised head-lessly; those are listed
in the manual UI checklist in the final report. This file tests the functions
behind the buttons.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


# ── 1. Imports ─────────────────────────────────────────────────────────
print("\n[1] Module imports")
import applog, engine as eng, notifier, mldb, db, monitor, config, auth  # noqa
import scanner_contrarian, scanner_penny, gemini_cache                    # noqa
from ml import predictor as ml_predictor, backtest as ml_backtest, weekly_report  # noqa
check("all core modules import", True)
check("engine.portfolio_sentiment present", hasattr(eng, "portfolio_sentiment"))
check("scanner_contrarian.scan_contrarian present", hasattr(scanner_contrarian, "scan_contrarian"))
check("scanner_penny.scan_penny present", hasattr(scanner_penny, "scan_penny"))
check("ml_predictor.score_prediction present", hasattr(ml_predictor, "score_prediction"))
check("ml_backtest.check_deploy_gate present", hasattr(ml_backtest, "check_deploy_gate"))
check("notifier.send_momentum_alert present", hasattr(notifier, "send_momentum_alert"))
check("notifier.send_trail_stop_email present", hasattr(notifier, "send_trail_stop_email"))
check("notifier.send_penny_momentum_email present", hasattr(notifier, "send_penny_momentum_email"))
check("notifier.tg_penny_momentum present", hasattr(notifier, "tg_penny_momentum"))
check("auth.request_password_reset present", hasattr(auth, "request_password_reset"))


# ── 2. Market hours ────────────────────────────────────────────────────
print("\n[2] Market status")
for k in ("US", "IN", "UK", "EU", "CA", "JP", "CRYPTO"):
    s = eng.market_status(k)
    check(f"market_status({k}) shape", isinstance(s, dict) and "open" in s and "label" in s, str(s))
check("crypto always open", eng.market_status("CRYPTO")["open"] is True)


# ── 3. Data-quality gate ───────────────────────────────────────────────
print("\n[3] Data-quality gate")
import pandas as pd, numpy as np
fresh = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0},
                     index=pd.date_range(end=pd.Timestamp.now(), periods=20))
check("fresh data accepted", eng.data_quality(fresh)[0] is True)
stale = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0},
                     index=pd.date_range("2020-01-01", periods=20))
check("stale data rejected", eng.data_quality(stale)[0] is False)
neg = fresh.copy(); neg.iloc[-1, neg.columns.get_loc("Close")] = -1
check("non-positive price rejected", eng.data_quality(neg)[0] is False)
nan = fresh.copy(); nan.iloc[-1, nan.columns.get_loc("Close")] = np.nan
check("NaN price rejected", eng.data_quality(nan)[0] is False)


# ── 4. Telegram HTML rendering ─────────────────────────────────────────
print("\n[4] Telegram HTML rendering")
_captured = {}
_orig_send = notifier.send_telegram
notifier.send_telegram = lambda msg, cid="", **k: (_captured.update(msg=msg) or (True, "ok"))
picks = [{"ticker": "NVDA", "signal": "BUY TODAY", "currency": "$",
          "entry": 100, "stop": 95, "rr": {"t1": 108}, "win_prob": 80}]
notifier.tg_daily_top3(picks, "123")
msg = _captured.get("msg", "")
check("top3 uses <b> tags", "<b>NVDA</b>" in msg, msg)
check("top3 has no MarkdownV2 backslashes", "\\" not in msg, msg)
notifier.tg_penny_spikes([{"ticker": "ABC", "change": 33.3, "price": 4.2,
                           "vol_ratio": 3.0, "currency": "$"}], "123")
check("penny has no backslashes", "\\" not in _captured.get("msg", ""))
notifier.send_telegram = _orig_send


# ── 5. Email digest rendering (send mocked) ────────────────────────────
print("\n[5] Email digest rendering")
_orig_alert = notifier.send_alert
_cap = {}
notifier.send_alert = lambda s, h, **k: (_cap.update(subj=s, html=h) or (True, "dry"))
regimes = {"us": {"pass": True, "label": "BULL", "price": 500, "pct_above": 3.2},
           "india": {"pass": False, "label": "BEAR", "price": 22000, "pct_above": -1.1}}
statuses = {"us": {"open": False, "label": "Closed (weekend)"},
            "india": {"open": False, "label": "Closed"}}
ok, _ = notifier.send_market_update_email("Morning", regimes, picks, [], statuses)
check("digest sends", ok is True)
check("closed-market note present when closed+picks", "Markets are closed" in _cap.get("html", ""))
notifier.send_alert = _orig_alert


# ── 6. SMTP retry path ─────────────────────────────────────────────────
print("\n[6] SMTP retry/backoff")
import smtplib, time as _t
_orig_smtp, _orig_sleep, _orig_keys = smtplib.SMTP, _t.sleep, notifier.load_keys
_t.sleep = lambda *_: None
notifier.load_keys = lambda: {"email": {"sender_address": "x@y.com",
    "sender_app_password": "pw", "alert_recipients": ["a@b.com"],
    "smtp_server": "smtp.invalid", "smtp_port": 587}}
class _BoomSMTP:
    def __init__(self, *a, **k): raise OSError("boom")
smtplib.SMTP = _BoomSMTP
ok, m = notifier.send_alert("subj", "<p>x</p>", max_attempts=3)
check("smtp fails cleanly after retries", ok is False and "Failed after 3" in m, m)
smtplib.SMTP, _t.sleep, notifier.load_keys = _orig_smtp, _orig_sleep, _orig_keys


# ── 7. Graceful no-DB degradation ──────────────────────────────────────
print("\n[7] No-credential degradation")
# Ensure no creds leak from env for this check
for v in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY"):
    os.environ.pop(v, None)
check("mldb.available() False w/o creds", mldb.available() is False)
check("log_prediction no-op returns False", mldb.log_prediction(picks[0]) is False)
check("already_sent False w/o creds", mldb.already_sent("k") is False)
check("get_all_users_with_settings returns []", db.get_all_users_with_settings() == [])
ok, m = monitor._dedup_send("k", "T", "key", lambda: (True, "sent"))
check("_dedup_send passes through when no DB", ok is True)


# ── 8. ML predictor cold-start fallback ────────────────────────────────
print("\n[8] ML predictor cold-start")
# With no DB / no trained model, score_prediction must return win_prob unchanged
score = ml_predictor.score_prediction({"win_prob": 72, "minervini_score": 7, "rs_score": 1.3})
check("cold-start score returns win_prob", abs(score - 72.0) < 0.1, f"got {score}")
fv = ml_predictor._feature_vector({"minervini": 7, "rs_score": 1.3, "rsi": 55,
                                    "win_prob": 72, "features": {"extension_pct": 3,
                                                                  "volume_ratio": 2.1,
                                                                  "sweep": True}})
check("feature vector length", len(fv) == 9)


# ── 9. Momentum + trail-stop Telegram render (HTML, no backslashes) ─────
print("\n[9] Momentum + trail-stop telegram render")
_orig_send = notifier.send_telegram
_cap = {}
notifier.send_telegram = lambda m, c="", **k: (_cap.update(msg=m) or (True, "ok"))
notifier.tg_momentum_alert({"ticker": "NVDA", "currency": "$", "price": 500,
                             "entry": 500, "stop": 480, "rr": {"t1": 550},
                             "intraday_pct": 4.3, "vol_ratio": 3.1}, confidence=78)
check("momentum TG has <b>", "<b>NVDA</b>" in _cap.get("msg", ""))
check("momentum TG includes confidence", "78" in _cap.get("msg", ""))
notifier.tg_trail_stop({}, {"ticker": "AAPL", "currency": "$", "current": 210,
                             "entry": 190, "pnl_pct": 10.5}, 200.0)
check("trail TG has TRAIL STOP", "TRAIL STOP" in _cap.get("msg", ""))
check("trail TG has no backslashes", "\\" not in _cap.get("msg", ""))
notifier.send_telegram = _orig_send


# ── 10. Gemini cache no-creds graceful path ────────────────────────────
print("\n[10] Gemini cache graceful no-creds")
check("get_cached returns None w/o creds",  gemini_cache.get_cached("prompt") is None)
check("put_cached returns False w/o creds", gemini_cache.put_cached("p", "r") is False)
fallback = gemini_cache.rule_based_fallback("NVDA", "BUY TODAY", 78, 7)
check("rule_based_fallback contains ticker", "NVDA" in fallback)


# ── 11. Contrarian scanner basic shape ─────────────────────────────────
print("\n[11] Contrarian scanner contract")
# scan_contrarian must accept the standard mc/regime/portfolio/risk args and
# return a list (possibly empty). We monkeypatch analyze to avoid network.
_orig_analyze = scanner_contrarian.analyze_contrarian
scanner_contrarian.analyze_contrarian = lambda *a, **k: None
out = scanner_contrarian.scan_contrarian(
    {"key": "US", "currency": "$", "is_crypto": False, "growth": ["AAPL"], "blue_chips": []},
    {"_df": None}, 10000.0, 1.0)
check("scan_contrarian returns list", isinstance(out, list))
scanner_contrarian.analyze_contrarian = _orig_analyze


# ── 12. Backtest API + deploy gate shape (no execution, just structure) ─
print("\n[12] Backtest module surface")
check("run_backtest exists",        callable(ml_backtest.run_backtest))
check("check_deploy_gate exists",   callable(ml_backtest.check_deploy_gate))
check("backtest constants sane",
      ml_backtest.HIT_THRESHOLD == 20.0 and ml_backtest.HOLD_DAYS == 10)


# ── 13. Penny scanner contract (offline — monkeypatched) ───────────────
print("\n[13] Penny scanner contract")
_orig_penny_analyze = scanner_penny.analyze_penny
scanner_penny.analyze_penny = lambda *a, **k: None
mc_us_p  = config.MARKET_CONFIGS["🇺🇸 US Stocks"]
mc_uk_p  = config.MARKET_CONFIGS["🇬🇧 UK"]
out_us   = scanner_penny.scan_penny(mc_us_p,  {"_df": None}, 10000.0, 1.0)
out_uk   = scanner_penny.scan_penny(mc_uk_p,  {"_df": None}, 10000.0, 1.0)
check("scan_penny returns list", isinstance(out_us, list))
check("scan_penny returns [] for UK (non-penny market)", out_uk == [])
scanner_penny.analyze_penny = _orig_penny_analyze

# signal vocabulary check (inline, no network)
fake_penny = {
    "ticker": "SOFI", "price": 8.50, "currency": "$",
    "signal": "PENNY MOMENTUM BUY", "verdict": "Test", "hold_days": "1d",
    "win_prob": 55, "minervini_score": 0, "rs_score": None, "rsi": 60,
    "is_overbought": False, "is_extended": False, "extension_pct": 0.0,
    "entry": 8.50, "stop": 7.22, "rr": {"t1": 10.62, "t2": 12.75, "t3": 17.0},
    "t1_price": 10.62, "t2_price": 12.75,
    "criteria": {}, "volume": {"pass": True, "ratio": 2.5},
    "sweep": {"pass": False}, "score": 6, "vol_ratio": 2.5,
    "ann_vol": 80.0, "is_penny": True, "track": "penny", "_df": None,
}
check("penny result has is_penny flag", fake_penny.get("is_penny") is True)
check("penny signal starts with PENNY", fake_penny["signal"].startswith("PENNY"))

# Penny momentum email renders
_orig_alert2 = notifier.send_alert
_cap2 = {}
notifier.send_alert = lambda s, h, **k: (_cap2.update(subj=s, html=h) or (True, "dry"))
ok2, m2 = notifier.send_penny_momentum_email([fake_penny])
check("penny_momentum_email sends", ok2 is True, m2)
check("penny email subject has ticker", "SOFI" in _cap2.get("subj", ""))
notifier.send_alert = _orig_alert2

# Penny Telegram render
_orig_tg = notifier.send_telegram
_cap3 = {}
notifier.send_telegram = lambda m, c="", **k: (_cap3.update(msg=m) or (True, "ok"))
notifier.tg_penny_momentum([fake_penny], "123")
check("tg_penny_momentum renders", "SOFI" in _cap3.get("msg", ""), _cap3.get("msg", ""))
check("tg_penny_momentum no backslashes", "\\" not in _cap3.get("msg", ""))
notifier.send_telegram = _orig_tg


# ── 14. Password reset surface ─────────────────────────────────────────
print("\n[14] Forgot-password surface")
check("auth.request_password_reset callable", callable(auth.request_password_reset))
ok_r, msg_r = auth.request_password_reset("test@example.com")
check("reset returns (bool, str)", isinstance(ok_r, bool) and isinstance(msg_r, str))
check("reset message non-empty", len(msg_r) > 5, msg_r)

# PENNY_HIT_THRESHOLD_PCT defined in predictor
check("predictor.PENNY_HIT_THRESHOLD_PCT == 25",
      ml_predictor.PENNY_HIT_THRESHOLD_PCT == 25.0)


# ── 15. Per-track ML thresholds ────────────────────────────────────────
print("\n[15] Per-track ML thresholds")
check("CRYPTO_HIT_THRESHOLD_PCT == 15",  ml_predictor.CRYPTO_HIT_THRESHOLD_PCT  == 15.0)
check("OPTIONS_HIT_THRESHOLD_PCT == 50", ml_predictor.OPTIONS_HIT_THRESHOLD_PCT == 50.0)
check("_hit_threshold_for stock",   ml_predictor._hit_threshold_for({"track": "stock"})   == 20.0)
check("_hit_threshold_for crypto",  ml_predictor._hit_threshold_for({"track": "crypto"})  == 15.0)
check("_hit_threshold_for penny",   ml_predictor._hit_threshold_for({"is_penny": True})   == 25.0)
check("_hit_threshold_for options", ml_predictor._hit_threshold_for({"track": "options"}) == 50.0)


# ── 16. fetch_crypto_overview surface ──────────────────────────────────
print("\n[16] fetch_crypto_overview")
import engine as _eng_smoke
_cov = _eng_smoke.fetch_crypto_overview()
check("fetch_crypto_overview returns dict", isinstance(_cov, dict))
check("fetch_crypto_overview has _ok key", "_ok" in _cov)


# ── 17. recommend_option skips when win_prob < 60 ──────────────────────
print("\n[17] recommend_option gate checks")
_low_signal = {"win_prob": 55, "signal": "WATCH", "price": 100, "entry": 100,
               "t1_price": 110, "rr": {"t1": 110}}
_orec_skip = _eng_smoke.recommend_option("AAPL", _low_signal, 10000.0)
check("recommend_option skips win_prob<60",
      _orec_skip is not None and "skip_reason" in _orec_skip)


# ── 18. Notifier: crypto + options templates surface ───────────────────
print("\n[18] Crypto + options notifier surface")
check("send_crypto_momentum_email present", hasattr(notifier, "send_crypto_momentum_email"))
check("tg_crypto_momentum present",         hasattr(notifier, "tg_crypto_momentum"))
check("send_options_recommendation_email present",
      hasattr(notifier, "send_options_recommendation_email"))
check("tg_options_recommendation present", hasattr(notifier, "tg_options_recommendation"))

# Verify crypto email renders without crashing (no picks → returns False cleanly)
ok_ce, _ = notifier.send_crypto_momentum_email([])
check("crypto email empty-list returns False", ok_ce is False)

# Verify options TG renders for a skip_reason rec (returns False cleanly)
ok_ot, _ = notifier.tg_options_recommendation({"skip_reason": "test"})
check("options TG skip_reason returns False", ok_ot is False)


# ── 19. New mldb helpers degrade gracefully (no creds) ────────────────
print("\n[19] mldb Track Record helpers (no-creds graceful degradation)")
check("get_recent_predictions returns list (no creds)",
      isinstance(mldb.get_recent_predictions(days=7), list))
check("get_prediction_by_id returns None (no creds)",
      mldb.get_prediction_by_id(1) is None)
check("get_calibration_buckets returns list (no creds)",
      isinstance(mldb.get_calibration_buckets(), list))
check("get_retroactive_hits returns list (no creds)",
      isinstance(mldb.get_retroactive_hits(), list))
check("get_user_note returns str (no creds)",
      isinstance(mldb.get_user_note(1, "u"), str))
check("upsert_user_note returns False (no creds)",
      mldb.upsert_user_note(1, "u", "x") is False)
check("get_user_notes_bulk returns dict (no creds)",
      isinstance(mldb.get_user_notes_bulk([1, 2], "u"), dict))


# ── 20. _classify_failure returns valid tag ────────────────────────────
print("\n[20] _classify_failure auto-tagging")
import pandas as _pd_smoke
_VALID_TAGS = {"rsi_overheated_at_entry", "broke_50dma", "volume_dried_up", "general_drawdown"}

# High RSI → rsi_overheated_at_entry
_tag1 = ml_predictor._classify_failure({"rsi": 80}, _pd_smoke.DataFrame(), 100.0)
check("classify_failure high RSI", _tag1 == "rsi_overheated_at_entry")

# No data → general_drawdown (graceful)
_tag2 = ml_predictor._classify_failure({}, _pd_smoke.DataFrame(), 100.0)
check("classify_failure empty df -> general_drawdown", _tag2 == "general_drawdown")

# Normal payload with valid DataFrame → one of the known tags
_n = 20
_fake_df = _pd_smoke.DataFrame({
    "Close":  [100.0] * _n,
    "Volume": [1_000_000] * _n,
})
_tag3 = ml_predictor._classify_failure({"rsi": 55}, _fake_df, 100.0)
check("classify_failure returns valid tag", _tag3 in _VALID_TAGS, _tag3)

# update_prediction_outcome signature accepts failure_reason kwarg
import inspect as _insp
_params = list(_insp.signature(mldb.update_prediction_outcome).parameters)
check("update_prediction_outcome has failure_reason param", "failure_reason" in _params)


# ── 21. weekly_report has _failure_reason_counts ──────────────────────
print("\n[21] weekly_report failure-reason counts")
check("_failure_reason_counts present", hasattr(weekly_report, "_failure_reason_counts"))
_fc = weekly_report._failure_reason_counts([
    {"hit": False, "failure_reason": "broke_50dma"},
    {"hit": False, "failure_reason": "broke_50dma"},
    {"hit": True,  "failure_reason": None},
])
check("_failure_reason_counts counts correctly", _fc.get("broke_50dma") == 2)
check("_failure_reason_counts ignores hits",     "None" not in str(_fc))


# ── Summary ────────────────────────────────────────────────────────────
print(f"\n{'='*48}\nSMOKE TEST: {_passed} passed, {_failed} failed\n{'='*48}")
sys.exit(1 if _failed else 0)
