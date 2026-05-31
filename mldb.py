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

from __future__ import annotations   # allows str | None on Python 3.9

import os
from datetime import datetime, date, timedelta

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


def update_prediction_outcome(pred_id, outcome_pct: float, hit: bool,
                              failure_reason: str | None = None) -> bool:
    """Mark a prediction evaluated with its realised outcome. (Used by Phase 3.)"""
    url, key = _creds()
    if not url or not key:
        return False
    try:
        payload = {"status": "evaluated", "outcome_pct": outcome_pct,
                   "hit": hit, "evaluated_at": datetime.utcnow().isoformat()}
        if failure_reason:
            payload["failure_reason"] = failure_reason
        r = requests.patch(
            f"{url}/rest/v1/predictions?id=eq.{pred_id}",
            headers=_headers(key, "return=minimal"),
            json=payload, timeout=12,
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


# ── Track Record queries ───────────────────────────────────────────────

def get_recent_predictions(days: int = 30, market: str | None = None,
                            track: str | None = None,
                            signal: str | None = None) -> list[dict]:
    """Returns predictions created in the last N days, newest first.
    track / market filters are applied client-side (market stored as free text)."""
    url, key = _creds()
    if not url or not key:
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    query = (f"{url}/rest/v1/predictions?pred_date=gte.{cutoff}"
             f"&order=pred_date.desc&limit=500&select=*")
    if signal:
        query += f"&signal=eq.{requests.utils.quote(signal)}"
    try:
        r = requests.get(query, headers=_headers(key), timeout=15)
        if r.status_code != 200:
            return []
        rows = r.json()
        if market:
            m = market.upper()
            rows = [row for row in rows if m in (row.get("market") or "").upper()]
        if track:
            rows = [row for row in rows if _derive_track(row) == track]
        return rows
    except Exception as e:
        log.warning(f"get_recent_predictions error: {e}")
    return []


def _derive_track(row: dict) -> str:
    """Best-effort track derivation from a predictions row."""
    payload = row.get("payload") or {}
    if isinstance(payload, dict) and payload.get("track"):
        return payload["track"]
    if row.get("track"):
        return row["track"]
    features = row.get("features") or {}
    if isinstance(features, dict) and features.get("is_penny"):
        return "penny"
    mkt = (row.get("market") or "").upper()
    if "CRYPTO" in mkt or "BTC" in mkt:
        return "crypto"
    return "stock"


def get_prediction_by_id(pred_id: int) -> dict | None:
    """Single prediction with full payload + features for drill-down."""
    url, key = _creds()
    if not url or not key:
        return None
    try:
        r = requests.get(f"{url}/rest/v1/predictions?id=eq.{pred_id}&select=*",
                         headers=_headers(key), timeout=10)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        log.warning(f"get_prediction_by_id error: {e}")
    return None


def get_calibration_buckets(days: int = 90) -> list[dict]:
    """Hit-rate per win_prob bucket over the last N days (50-60, 60-70, 70-80, 80+)."""
    url, key = _creds()
    if not url or not key:
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    try:
        r = requests.get(
            f"{url}/rest/v1/predictions?status=eq.evaluated&pred_date=gte.{cutoff}"
            f"&select=win_prob,hit",
            headers=_headers(key), timeout=15,
        )
        if r.status_code != 200:
            return []
        rows = r.json()
        out = []
        for label, lo, hi in [("50-60%", 50, 60), ("60-70%", 60, 70),
                               ("70-80%", 70, 80), ("80%+", 80, 101)]:
            sub = [row for row in rows if lo <= (row.get("win_prob") or 0) < hi]
            if not sub:
                continue
            n_hit = sum(1 for row in sub if row.get("hit"))
            out.append({"bucket": label, "n": len(sub), "hits": n_hit,
                        "hit_rate": round(n_hit / len(sub), 3)})
        return out
    except Exception as e:
        log.warning(f"get_calibration_buckets error: {e}")
    return []


def get_retroactive_hits(hours: int = 24) -> list[dict]:
    """Picks that flipped to HIT in the last N hours."""
    url, key = _creds()
    if not url or not key:
        return []
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    try:
        r = requests.get(
            f"{url}/rest/v1/predictions?status=eq.evaluated&hit=eq.true"
            f"&evaluated_at=gte.{cutoff}&order=evaluated_at.desc&select=*",
            headers=_headers(key), timeout=12,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"get_retroactive_hits error: {e}")
    return []


# ── Per-user notes on predictions ─────────────────────────────────────

def get_user_note(prediction_id: int, user_id: str) -> str:
    url, key = _creds()
    if not url or not key:
        return ""
    try:
        r = requests.get(
            f"{url}/rest/v1/prediction_notes"
            f"?prediction_id=eq.{prediction_id}&user_id=eq.{user_id}&select=note",
            headers=_headers(key), timeout=10,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0].get("note", "")
    except Exception as e:
        log.warning(f"get_user_note error: {e}")
    return ""


def upsert_user_note(prediction_id: int, user_id: str, note: str) -> bool:
    url, key = _creds()
    if not url or not key:
        return False
    try:
        r = requests.post(
            f"{url}/rest/v1/prediction_notes",
            headers=_headers(key, "resolution=merge-duplicates,return=minimal"),
            json={"prediction_id": prediction_id, "user_id": user_id,
                  "note": note, "updated_at": datetime.utcnow().isoformat()},
            timeout=10,
        )
        return r.status_code in (200, 201, 204)
    except Exception as e:
        log.warning(f"upsert_user_note error: {e}")
    return False


def get_user_notes_bulk(prediction_ids: list[int], user_id: str) -> dict[int, str]:
    """Single round-trip for all visible notes — avoids N+1 queries."""
    url, key = _creds()
    if not url or not key or not prediction_ids:
        return {}
    ids_csv = ",".join(str(i) for i in prediction_ids)
    try:
        r = requests.get(
            f"{url}/rest/v1/prediction_notes"
            f"?prediction_id=in.({ids_csv})&user_id=eq.{user_id}"
            f"&select=prediction_id,note",
            headers=_headers(key), timeout=12,
        )
        if r.status_code == 200:
            return {row["prediction_id"]: row.get("note", "") for row in r.json()}
    except Exception as e:
        log.warning(f"get_user_notes_bulk error: {e}")
    return {}
