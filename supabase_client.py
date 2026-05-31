"""
Aarya StockSense Pro — supabase_client.py
Cloud settings persistence via Supabase (free tier).
Used automatically when running on Streamlit Cloud (no local aarya_config.json).
"""
from __future__ import annotations

import os

_client       = None
_admin_client = None


def _get_url_and_key() -> tuple[str, str]:
    url = key = ""
    try:
        import streamlit as st
        url = str(st.secrets.get("SUPABASE_URL", ""))
        key = str(st.secrets.get("SUPABASE_KEY", ""))
    except Exception:
        pass
    if not url:
        url = os.environ.get("SUPABASE_URL", "")
    if not key:
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def _get_service_key() -> str:
    """Return the service_role key from SUPABASE_SERVICE_KEY, falling back to SUPABASE_KEY."""
    key = ""
    try:
        import streamlit as st
        key = str(st.secrets.get("SUPABASE_SERVICE_KEY", ""))
        if not key:
            key = str(st.secrets.get("SUPABASE_KEY", ""))
    except Exception:
        pass
    if not key:
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        key = os.environ.get("SUPABASE_KEY", "")
    return key


def _get_client():
    global _client
    if _client is not None:
        return _client
    url, key = _get_url_and_key()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception:
        return None


def _get_admin_client():
    """Return a separate Supabase client initialised with the service_role key."""
    global _admin_client
    if _admin_client is not None:
        return _admin_client
    url, _ = _get_url_and_key()
    key = _get_service_key()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _admin_client = create_client(url, key)
        return _admin_client
    except Exception:
        return None


def is_available() -> bool:
    return _get_client() is not None


def load_settings_cloud(user_id: str = "default") -> dict | None:
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("settings").select("data").eq("id", user_id).execute()
        if result.data:
            return result.data[0]["data"]
    except Exception:
        pass
    return None


def save_settings_cloud(data: dict, user_id: str = "default") -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.table("settings").upsert({"id": user_id, "data": data}).execute()
        return True
    except Exception:
        return False
