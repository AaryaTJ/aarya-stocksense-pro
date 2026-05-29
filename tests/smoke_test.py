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
check("all core modules import", True)


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


# ── Summary ────────────────────────────────────────────────────────────
print(f"\n{'='*48}\nSMOKE TEST: {_passed} passed, {_failed} failed\n{'='*48}")
sys.exit(1 if _failed else 0)
