"""
Aarya StockSense Pro — db.py
Per-user database operations and admin user management (Supabase).
"""

import requests
from supabase_client import _get_client
from config import DEFAULTS


# ── Helpers for direct Admin REST API calls ───────────────────────────

def _admin_base() -> tuple[str, dict] | tuple[None, None]:
    """Return (base_url, headers) for Supabase Auth Admin REST calls."""
    import os
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
    if not url or not key:
        return None, None
    headers = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }
    return f"{url}/auth/v1/admin", headers


# ── Per-User Settings ──────────────────────────────────────────────────

def get_user_settings(user_id: str) -> dict:
    client = _get_client()
    if not client:
        return dict(DEFAULTS)
    try:
        r = client.table("user_settings").select("data").eq("user_id", user_id).execute()
        if r.data:
            return {**DEFAULTS, **r.data[0]["data"]}
    except Exception:
        pass
    return dict(DEFAULTS)


def save_user_settings(user_id: str, data: dict) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.table("user_settings").upsert(
            {"user_id": user_id, "data": data},
            on_conflict="user_id",
        ).execute()
        return True
    except Exception:
        return False


# ── Admin: User Management ─────────────────────────────────────────────

def list_users() -> tuple[list, str]:
    """Returns (users_list, error_message). error_message is '' on success."""
    base, headers = _admin_base()
    if not base:
        return [], "Database not connected."
    try:
        r = requests.get(f"{base}/users", headers=headers, timeout=10)
        if r.status_code != 200:
            return [], r.json().get("message", r.text)
        data = r.json()
        # response may be a list or {"users": [...]}
        auth_users = data if isinstance(data, list) else data.get("users", [])

        client = _get_client()
        profiles = {}
        if client:
            pr = client.table("user_profiles").select("*").execute()
            profiles = {p["id"]: p for p in (pr.data or [])}

        result = []
        for u in auth_users:
            pid = str(u.get("id", ""))
            p   = profiles.get(pid, {})
            ll  = str(p.get("last_login") or "Never")[:10]
            ca  = u.get("created_at", "")
            result.append({
                "id":         pid,
                "email":      u.get("email") or "—",
                "created":    ca[:10] if ca else "—",
                "last_login": ll,
                "role":       p.get("role", "user"),
                "blocked":    bool(p.get("is_blocked", False)),
            })
        return sorted(result, key=lambda x: x["created"], reverse=True), ""
    except Exception as e:
        return [], str(e)


def create_user(email: str, password: str) -> tuple[bool, str]:
    base, headers = _admin_base()
    if not base:
        return False, "Database not available."
    try:
        r = requests.post(f"{base}/users", headers=headers, timeout=10, json={
            "email":          email.strip().lower(),
            "password":       password,
            "email_confirm":  True,
        })
        if r.status_code in (200, 201):
            return True, f"User {email} created successfully."
        msg = r.json().get("message", r.text)
        if "already" in msg.lower():
            return False, f"{email} is already registered."
        return False, f"Error: {msg}"
    except Exception as e:
        return False, str(e)


def block_user(user_id: str) -> tuple[bool, str]:
    client = _get_client()
    if not client:
        return False, "DB error"
    try:
        client.table("user_profiles").upsert(
            {"id": user_id, "is_blocked": True}, on_conflict="id"
        ).execute()
        return True, "User blocked."
    except Exception as e:
        return False, str(e)


def unblock_user(user_id: str) -> tuple[bool, str]:
    client = _get_client()
    if not client:
        return False, "DB error"
    try:
        client.table("user_profiles").update(
            {"is_blocked": False}
        ).eq("id", user_id).execute()
        return True, "User unblocked."
    except Exception as e:
        return False, str(e)


def delete_user(user_id: str) -> tuple[bool, str]:
    base, headers = _admin_base()
    if not base:
        return False, "DB error"
    try:
        r = requests.delete(f"{base}/users/{user_id}", headers=headers, timeout=10)
        if r.status_code in (200, 204):
            return True, "User deleted."
        return False, r.json().get("message", r.text)
    except Exception as e:
        return False, str(e)


# ── Telegram Notifications ─────────────────────────────────────────────

def save_telegram_chat_id(user_id: str, chat_id: str) -> tuple[bool, str]:
    settings = get_user_settings(user_id)
    settings["telegram_chat_id"] = chat_id.strip()
    ok = save_user_settings(user_id, settings)
    return ok, "Telegram Chat ID saved." if ok else "Failed to save."


def get_all_telegram_chat_ids() -> list[str]:
    """Returns all configured Telegram chat IDs across all users (for monitor.py)."""
    import os
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

    chat_ids: list[str] = []
    if url and key:
        try:
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
            r = requests.get(
                f"{url}/rest/v1/user_settings?select=data",
                headers=headers, timeout=10,
            )
            if r.status_code == 200:
                for row in r.json():
                    cid = str(row.get("data", {}).get("telegram_chat_id", "")).strip()
                    if cid and cid not in chat_ids:
                        chat_ids.append(cid)
        except Exception:
            pass

    # Fallback: env var (GitHub Actions secret)
    env_cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if env_cid and env_cid not in chat_ids:
        chat_ids.append(env_cid)

    return chat_ids


def get_all_users_with_settings() -> list[dict]:
    """
    For automated per-user alerts (monitor.py). Returns one dict per user:
        {"user_id", "email", "positions", "telegram_chat_id", "time_stop"}
    Requires the SERVICE key to read every user's settings + emails (admin API).
    Returns [] when not configured (caller falls back to local settings).
    """
    import os as _os
    url = key = ""
    try:
        import streamlit as st
        url = str(st.secrets.get("SUPABASE_URL", ""))
        key = str(st.secrets.get("SUPABASE_SERVICE_KEY", "")
                  or st.secrets.get("SUPABASE_KEY", ""))
    except Exception:
        pass
    if not url:
        url = _os.environ.get("SUPABASE_URL", "")
    if not key:
        key = _os.environ.get("SUPABASE_SERVICE_KEY",
                             _os.environ.get("SUPABASE_KEY", ""))
    if not url or not key:
        return []

    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    # settings rows: user_id -> data
    settings_by_id: dict[str, dict] = {}
    try:
        r = requests.get(f"{url}/rest/v1/user_settings?select=user_id,data",
                         headers=headers, timeout=12)
        if r.status_code == 200:
            for row in r.json():
                settings_by_id[str(row.get("user_id"))] = row.get("data", {}) or {}
    except Exception:
        return []

    # emails via admin API (needs service key)
    email_by_id: dict[str, str] = {}
    try:
        ar = requests.get(f"{url}/auth/v1/admin/users", headers=headers, timeout=12)
        if ar.status_code == 200:
            data = ar.json()
            users = data if isinstance(data, list) else data.get("users", [])
            for u in users:
                email_by_id[str(u.get("id"))] = u.get("email", "")
    except Exception:
        pass

    out = []
    for uid, data in settings_by_id.items():
        positions = data.get("positions", []) or []
        cid       = str(data.get("telegram_chat_id", "")).strip()
        if not positions and not cid:
            continue
        out.append({
            "user_id":          uid,
            "email":            email_by_id.get(uid, ""),
            "positions":        positions,
            "telegram_chat_id": cid,
            "time_stop":        data.get("time_stop", 5),
        })
    return out
