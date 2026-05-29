"""
Aarya StockSense Pro — mldb.py
Supabase-backed persistence for the prediction-tracking / ML feedback loop and
notification de-duplication.

Why Supabase (not SQLite): the app (Streamlit Cloud) and the scanner (GitHub
Actions) run on separate, ephemeral machines. A local SQLite file written by one
is invisible to the other and wiped on restart. Postgres (Supabase) is the only
store both can share and that survives restarts.

Every function degrades to a safe no-op when credentials/tables are missing, so
local runs and first-time setup never crash.

Tables (see SETUP.md for the CREATE statements):
  predictions          — one row per logged pick, evaluated after horizon_days
  sent_notifications   — dedup keys so the same alert isn't sent twice/day
  model_state          — ensemble weights + rolling accuracy (used in Phase 3)
"""

import os
from datetime import datetime, date

import requests

from applog import get_logger

log = get_logger("aarya_mldb")


# ── Credentials (service key preferred, anon fallback) ─────────────────

def _creds() -> tuple[str, str]:
    url = key = ""
    try:
        import streamlit as st
        url = str(st.secrets.get("SUPABASE_URL", ""))
        key = str(st.secrets.get("SUPABASE_SERVICE_KEY", "")
                  or st.secrets.get("SUPABASE_KEY", ""))
    except Exception:
        pass
    if not url:
        url = os.environ.get("SUPABASE_URL", "")
    if not key:
        key = os.environ.get("SUPABASE_SERVICE_KEY",
                             os.environ.get("SUPABASE_KEY", ""))
    return url, key


def _headers(key: str, prefer: str = "") -> dict:
    h = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def available() -> bool:
    url, key = _creds()
    return bool(url and key)


# ── Predictions ────────────────────────────────────────────────────────

def log_prediction(pred: dict) -> bool:
    """
    Upsert one prediction row (dedup on ticker+pred_date so re-running the same
    day overwrites rather than duplicates). `pred` is an engine result dict plus
    market_label. Returns True on success.
    """
    url, key = _creds()
    if not url or not key:
        return False
    rr = pred.get("rr", {}) or {}
    row = {
        "pred_date":    date.today().isoformat(),
        "ticker":       pred.get("ticker", "?"),
        "market":       pred.get("market_label", ""),
        "signal":       pred.get("signal", ""),
        "price":        pred.get("price"),
        "entry":        pred.get("entry"),
        "stop":         pred.get("stop"),
        "t1":           rr.get("t1"),
        "t2":           rr.get("t2"),
        "t3":           rr.get("t3"),
        "win_prob":     pred.get("win_prob"),
        "minervini":    pred.get("minervini_score"),
        "rs_score":     pred.get("rs_score"),
        "rsi":          pred.get("rsi"),
        "confidence":   pred.get("confidence", pred.get("win_prob")),
        "horizon_days": pred.get("horizon_days", 10),
        "features": {
            "is_overbought": pred.get("is_overbought"),
            "is_extended":   pred.get("is_extended"),
            "extension_pct": pred.get("extension_pct"),
            "volume_ratio":  (pred.get("volume", {}) or {}).get("ratio"),
            "sweep":         (pred.get("sweep", {}) or {}).get("pass"),
        },
        "status": "open",
    }
    try:
        r = requests.post(
            f"{url}/rest/v1/predictions?on_conflict=ticker,pred_date",
            headers=_headers(key, "resolution=merge-duplicates,return=minimal"),
            json=row, timeout=12,
        )
        if r.status_code in (200, 201, 204):
            return True
        log.warning(f"log_prediction {row['ticker']}: HTTP {r.status_code} {r.text[:120]}")
    except Exception as e:
        log.warning(f"log_prediction error: {e}")
    return False


def get_open_predictions(older_than_days: int = 10) -> list:
    """Return predictions still status='open' whose pred_date is at least
    `older_than_days` ago — i.e. ready to evaluate. (Used by Phase 3.)"""
    url, key = _creds()
    if not url or not key:
        return []
    try:
        r = requests.get(
            f"{url}/rest/v1/predictions?status=eq.open&select=*",
            headers=_headers(key), timeout=12,
        )
        if r.status_code == 200:
            rows = r.json()
            cutoff = (datetime.utcnow().date()).toordinal() - older_than_days
            return [x for x in rows
                    if _date_ord(x.get("pred_date")) and _date_ord(x.get("pred_date")) <= cutoff]
    except Exception as e:
        log.warning(f"get_open_predictions error: {e}")
    return []


def _date_ord(s):
    try:
        return date.fromisoformat(str(s)[:10]).toordinal()
    except Exception:
        return None


def update_prediction_outcome(pred_id, outcome_pct: float, hit: bool) -> bool:
    """Mark a prediction evaluated with its realised outcome. (Used by Phase 3.)"""
    url, key = _creds()
    if not url or not key:
        return False
    try:
        r = requests.patch(
            f"{url}/rest/v1/predictions?id=eq.{pred_id}",
            headers=_headers(key, "return=minimal"),
            json={"status": "evaluated", "outcome_pct": outcome_pct,
                  "hit": hit, "evaluated_at": datetime.utcnow().isoformat()},
            timeout=12,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        log.warning(f"update_prediction_outcome error: {e}")
    return False


# ── Notification de-duplication ────────────────────────────────────────

def already_sent(dedup_key: str) -> bool:
    """True if a notification with this key was already recorded (today)."""
    url, key = _creds()
    if not url or not key:
        return False                     # no DB → no dedup (old behaviour)
    try:
        r = requests.get(
            f"{url}/rest/v1/sent_notifications?dedup_key=eq.{requests.utils.quote(dedup_key)}&select=dedup_key",
            headers=_headers(key), timeout=10,
        )
        return r.status_code == 200 and bool(r.json())
    except Exception as e:
        log.warning(f"already_sent error: {e}")
        return False


def mark_sent(kind: str, ticker: str, dedup_key: str) -> bool:
    url, key = _creds()
    if not url or not key:
        return False
    try:
        r = requests.post(
            f"{url}/rest/v1/sent_notifications",
            headers=_headers(key, "resolution=merge-duplicates,return=minimal"),
            json={"dedup_key": dedup_key, "kind": kind, "ticker": ticker,
                  "sent_date": date.today().isoformat()},
            timeout=10,
        )
        return r.status_code in (200, 201, 204)
    except Exception as e:
        log.warning(f"mark_sent error: {e}")
    return False


# ── Model state (ensemble weights / rolling accuracy) — Phase 3 ────────

def get_model_state() -> dict:
    url, key = _creds()
    if not url or not key:
        return {}
    try:
        r = requests.get(f"{url}/rest/v1/model_state?id=eq.main&select=*",
                         headers=_headers(key), timeout=10)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        log.warning(f"get_model_state error: {e}")
    return {}


def save_model_state(weights: dict, rolling_acc: dict, locked: bool = False) -> bool:
    url, key = _creds()
    if not url or not key:
        return False
    try:
        r = requests.post(
            f"{url}/rest/v1/model_state",
            headers=_headers(key, "resolution=merge-duplicates,return=minimal"),
            json={"id": "main", "weights": weights, "rolling_acc": rolling_acc,
                  "locked": locked, "updated_at": datetime.utcnow().isoformat()},
            timeout=10,
        )
        return r.status_code in (200, 201, 204)
    except Exception as e:
        log.warning(f"save_model_state error: {e}")
    return False
