"""
Aarya StockSense Pro — db.py
Per-user database operations and admin user management (Supabase).
"""

from supabase_client import _get_client
from config import DEFAULTS


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

def list_users() -> list:
    client = _get_client()
    if not client:
        return []
    try:
        auth_users = client.auth.admin.list_users()
        profiles_r = client.table("user_profiles").select("*").execute()
        profiles   = {p["id"]: p for p in (profiles_r.data or [])}
        result = []
        for u in auth_users:
            pid = str(u.id)
            p   = profiles.get(pid, {})
            ll  = str(p.get("last_login") or "Never")[:10]
            result.append({
                "id":         pid,
                "email":      u.email or "—",
                "created":    str(getattr(u, "created_at", ""))[:10],
                "last_login": ll,
                "role":       p.get("role", "user"),
                "blocked":    bool(p.get("is_blocked", False)),
            })
        return sorted(result, key=lambda x: x["created"], reverse=True)
    except Exception:
        return []


def create_user(email: str, password: str) -> tuple[bool, str]:
    client = _get_client()
    if not client:
        return False, "Database not available."
    try:
        resp = client.auth.admin.create_user({
            "email": email.strip().lower(),
            "password": password,
            "email_confirm": True,
        })
        if resp.user:
            return True, f"User {email} created successfully."
        return False, "Failed to create user."
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower():
            return False, f"{email} is already registered."
        return False, f"Error: {msg}"


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
    client = _get_client()
    if not client:
        return False, "DB error"
    try:
        client.auth.admin.delete_user(user_id)
        return True, "User deleted."
    except Exception as e:
        return False, str(e)
