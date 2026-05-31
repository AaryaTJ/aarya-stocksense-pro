"""
gemini_cache.py — Supabase-backed cache for Gemini responses + rule-based
fallback so we don't burn the free 250-requests/day quota.

Used by `notifier.get_gemini_*` functions. Falls back gracefully when the
Supabase cache table is unavailable.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import requests

from applog import get_logger
import mldb

log = get_logger("aarya_gemini_cache")

# Per-kind TTL in hours. QA answers can stay longer; briefings should refresh
# every day because news moves.
TTL_HOURS = {"briefing": 24, "qa": 168, "verdict": 24, "deep": 24, "weekly": 72}


def _key(prompt: str, model: str) -> str:
    return hashlib.sha256(f"{model}::{prompt}".encode("utf-8")).hexdigest()


def get_cached(prompt: str, model: str = "gemini-2.5-flash",
               kind: str = "briefing") -> str | None:
    url, key = mldb._creds()
    if not url or not key:
        return None
    k = _key(prompt, model)
    try:
        r = requests.get(
            f"{url}/rest/v1/gemini_cache?key=eq.{k}&select=response,created_at",
            headers=mldb._headers(key), timeout=8,
        )
        if r.status_code != 200 or not r.json():
            return None
        row     = r.json()[0]
        created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "")[:19])
        ttl_h   = TTL_HOURS.get(kind, 24)
        if datetime.utcnow() - created > timedelta(hours=ttl_h):
            return None
        return row.get("response")
    except Exception as e:
        log.debug(f"cache get error: {e}")
    return None


def put_cached(prompt: str, response: str, model: str = "gemini-2.5-flash",
               kind: str = "briefing") -> bool:
    url, key = mldb._creds()
    if not url or not key or not response:
        return False
    k = _key(prompt, model)
    try:
        r = requests.post(
            f"{url}/rest/v1/gemini_cache",
            headers=mldb._headers(key, "resolution=merge-duplicates,return=minimal"),
            json={"key": k, "response": response[:8000], "kind": kind,
                  "created_at": datetime.utcnow().isoformat()},
            timeout=8,
        )
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def rule_based_fallback(ticker: str, signal: str, win_prob, minervini) -> str:
    """Plain-English explanation when the Gemini quota is exhausted."""
    return (f"{ticker}: {signal}. Minervini {minervini}/8 and a "
            f"{win_prob}% rule-based win probability support this read. "
            f"AI explanations are temporarily unavailable (quota / network). "
            f"Verify with your own checks before trading.")
