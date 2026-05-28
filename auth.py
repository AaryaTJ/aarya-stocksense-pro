"""
Aarya StockSense Pro — auth.py
User authentication and persistent session management.
"""

import streamlit as st
from datetime import datetime, timedelta
from supabase_client import _get_client

ADMIN_EMAILS = frozenset({
    "tjbarot316@gmail.com",
    "ketty54011@gmail.com",
    "tbrahmbhatt316@gmail.com",
})

_COOKIE_NAME = "aarya_session"
_COOKIE_DAYS = 30


def _cookie_ctrl():
    try:
        from streamlit_cookies_controller import CookieController
        return CookieController(key="__aarya_ck__")
    except Exception:
        return None


def get_current_user() -> dict | None:
    """Return the logged-in user dict, or None if not authenticated."""
    if st.session_state.get("_aarya_auth"):
        user = st.session_state["_aarya_auth"]
        if not st.session_state.get("_block_chk"):
            st.session_state["_block_chk"] = True
            if _is_blocked(user["id"]):
                _clear_all()
                return None
        return user

    ctrl = _cookie_ctrl()
    if ctrl:
        try:
            token = ctrl.get(_COOKIE_NAME)
            if token:
                user = _validate_token(token)
                if user:
                    st.session_state["_aarya_auth"] = user
                    st.session_state["_block_chk"]  = True
                    return user
                ctrl.remove(_COOKIE_NAME)
        except Exception:
            pass
    return None


def login(email: str, password: str) -> tuple[dict | None, str]:
    """Sign in. Returns (user_dict, error_string)."""
    client = _get_client()
    if not client:
        return None, "Database not configured — check Streamlit secrets."
    try:
        resp = client.auth.sign_in_with_password({
            "email": email.strip().lower(),
            "password": password,
        })
    except Exception as e:
        err = str(e)
        if any(x in err for x in ("Invalid login", "invalid_grant", "credentials")):
            return None, "Incorrect email or password."
        return None, f"Login error: {err}"

    if not resp or not resp.user:
        return None, "Login failed. Please try again."

    uid       = resp.user.id
    email_low = resp.user.email.lower()
    r_token   = resp.session.refresh_token if resp.session else None

    _ensure_profile(uid, email_low)
    if _is_blocked(uid):
        return None, "Your account has been suspended. Contact the admin."

    user = {"id": uid, "email": email_low,
            "is_admin": email_low in ADMIN_EMAILS, "refresh_token": r_token}

    st.session_state["_aarya_auth"] = user
    st.session_state["_block_chk"]  = True

    ctrl = _cookie_ctrl()
    if ctrl and r_token:
        try:
            ctrl.set(_COOKIE_NAME, f"{uid}:{r_token}",
                     expires=datetime.now() + timedelta(days=_COOKIE_DAYS))
        except Exception:
            pass

    _touch_last_login(uid)
    return user, ""


def logout():
    _clear_all()
    st.rerun()


def _clear_all():
    for k in ("_aarya_auth", "_block_chk"):
        st.session_state.pop(k, None)
    ctrl = _cookie_ctrl()
    if ctrl:
        try:
            ctrl.remove(_COOKIE_NAME)
        except Exception:
            pass


def _validate_token(token_str: str) -> dict | None:
    client = _get_client()
    if not client or ":" not in token_str:
        return None
    try:
        _, refresh_token = token_str.split(":", 1)
        resp = client.auth.refresh_session(refresh_token)
        if resp and resp.user:
            uid       = resp.user.id
            email_low = resp.user.email.lower()
            if _is_blocked(uid):
                return None
            return {"id": uid, "email": email_low,
                    "is_admin": email_low in ADMIN_EMAILS,
                    "refresh_token": resp.session.refresh_token if resp.session else None}
    except Exception:
        pass
    return None


def _is_blocked(user_id: str) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        r = client.table("user_profiles").select("is_blocked").eq("id", user_id).execute()
        return bool(r.data and r.data[0].get("is_blocked"))
    except Exception:
        return False


def _ensure_profile(user_id: str, email: str):
    client = _get_client()
    if not client:
        return
    try:
        role = "admin" if email in ADMIN_EMAILS else "user"
        client.table("user_profiles").upsert(
            {"id": user_id, "role": role, "is_blocked": False},
            on_conflict="id",
        ).execute()
    except Exception:
        pass


def _touch_last_login(user_id: str):
    client = _get_client()
    if not client:
        return
    try:
        client.table("user_profiles").update(
            {"last_login": datetime.utcnow().isoformat()}
        ).eq("id", user_id).execute()
    except Exception:
        pass
