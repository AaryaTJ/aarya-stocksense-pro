"""
Aarya StockSense Pro — notifier.py
Gmail SMTP email alerts + Gemini AI briefings.
"""

import html as _html
import json
import os
import smtplib
import ssl
import time
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from applog import get_logger

log = get_logger("aarya_notifier")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aarya_config.json")


def _esc(s) -> str:
    """Escape a value for Telegram HTML parse mode."""
    return _html.escape(str(s), quote=False)

_DEFAULT_CONFIG = {
    "alpha_vantage": {"api_key": ""},
    "gemini":        {"api_key": ""},
    "email": {
        "sender_address":     "",
        "sender_app_password": "",
        "alert_recipients":   [],
        "smtp_server":        "smtp.gmail.com",
        "smtp_port":          587,
    },
    "zerodha": {"api_key": "", "api_secret": ""},
}


def load_keys() -> dict:
    # 1. Local file (laptop / self-hosted)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            merged = {k: dict(v) if isinstance(v, dict) else v for k, v in _DEFAULT_CONFIG.items()}
            for k, v in data.items():
                if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
        except Exception:
            pass

    # 2. Streamlit Cloud secrets
    try:
        import streamlit as st
        s = st.secrets
        raw = s.get("EMAIL_RECIPIENTS", "")
        recipients = [r.strip() for r in str(raw).split(",") if r.strip()]
        return {
            "alpha_vantage": {"api_key": str(s.get("ALPHA_VANTAGE_KEY", ""))},
            "gemini":        {"api_key": str(s.get("GEMINI_KEY", ""))},
            "email": {
                "sender_address":      str(s.get("EMAIL_SENDER", "")),
                "sender_app_password": str(s.get("EMAIL_PASSWORD", "")),
                "alert_recipients":    recipients,
                "smtp_server":         "smtp.gmail.com",
                "smtp_port":           587,
            },
            "zerodha": {"api_key": "", "api_secret": ""},
        }
    except Exception:
        pass

    # 3. Environment variables (GitHub Actions)
    raw = os.environ.get("EMAIL_RECIPIENTS", "")
    recipients = [r.strip() for r in raw.split(",") if r.strip()]
    av  = os.environ.get("ALPHA_VANTAGE_KEY", "")
    gem = os.environ.get("GEMINI_KEY", "")
    snd = os.environ.get("EMAIL_SENDER", "")
    pwd = os.environ.get("EMAIL_PASSWORD", "")
    if av or gem or snd:
        return {
            "alpha_vantage": {"api_key": av},
            "gemini":        {"api_key": gem},
            "email": {
                "sender_address":      snd,
                "sender_app_password": pwd,
                "alert_recipients":    recipients,
                "smtp_server":         "smtp.gmail.com",
                "smtp_port":           587,
            },
            "zerodha": {"api_key": "", "api_secret": ""},
        }

    return {k: dict(v) if isinstance(v, dict) else v for k, v in _DEFAULT_CONFIG.items()}


def save_keys(data: dict) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # On cloud the file is read-only; keys come from st.secrets


# ── EMAIL CORE ─────────────────────────────────────────────────────────

def _wrap(title: str, accent: str, body: str) -> str:
    ts = datetime.now().strftime("%d %b %Y %H:%M")
    return f"""<html><body style="margin:0;padding:20px;background:#0F1B2D;font-family:Arial,sans-serif;">
<div style="max-width:580px;margin:0 auto;background:#0a1525;border:1px solid #1a2f4a;border-radius:12px;overflow:hidden;">
  <div style="background:{accent};padding:18px 24px;">
    <div style="font-size:20px;font-weight:900;color:#050d15;">Aarya StockSense Pro</div>
    <div style="font-size:13px;color:#050d15;opacity:.85;margin-top:3px;">{title}</div>
  </div>
  <div style="padding:22px 24px;color:#C9D6E3;">{body}</div>
  <div style="padding:12px 24px;border-top:1px solid #1a2f4a;font-size:11px;color:#4A7FA5;">
    {ts} · Aarya StockSense Pro · <i>Not financial advice. Verify before trading.</i>
  </div>
</div></body></html>"""


def send_alert(subject: str, html_body: str, max_attempts: int = 3,
               recipients: list | None = None) -> tuple[bool, str]:
    keys = load_keys()
    ec   = keys.get("email", {})
    sender     = ec.get("sender_address", "").strip()
    password   = ec.get("sender_app_password", "").strip()
    if recipients is None:
        recipients = ec.get("alert_recipients", [])
    recipients = [r for r in recipients if r]

    if not sender or not password:
        log.warning("Email skipped: Gmail sender not configured.")
        return False, "Gmail sender not configured. Go to Settings → Alert Settings."
    if not recipients:
        log.warning("Email skipped: no recipients configured.")
        return False, "No recipient emails added yet."

    last_err = ""
    for attempt in range(1, max_attempts + 1):
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(ec.get("smtp_server", "smtp.gmail.com"),
                              ec.get("smtp_port", 587), timeout=20) as srv:
                srv.ehlo()
                srv.starttls(context=ctx)
                srv.login(sender, password)
                for rcpt in recipients:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"]    = f"Aarya StockSense Pro <{sender}>"
                    msg["To"]      = rcpt
                    msg.attach(MIMEText(html_body, "html"))
                    srv.sendmail(sender, rcpt, msg.as_string())
            log.info(f"Email sent: '{subject}' → {len(recipients)} recipient(s) (attempt {attempt})")
            return True, f"Sent to {len(recipients)} recipient(s)"
        except smtplib.SMTPAuthenticationError:
            log.error("Email auth failed — bad sender/app password. Not retrying.")
            return False, "Gmail authentication failed. Check sender email and app password."
        except Exception as e:
            last_err = str(e)
            log.warning(f"Email attempt {attempt}/{max_attempts} failed: {last_err}")
            if attempt < max_attempts:
                time.sleep(2 ** attempt)   # 2s, 4s backoff

    log.error(f"Email FAILED after {max_attempts} attempts: '{subject}' — {last_err}")
    return False, f"Failed after {max_attempts} attempts: {last_err}"


# ── ALERT TEMPLATES ────────────────────────────────────────────────────

def send_buy_alert(result: dict) -> tuple[bool, str]:
    t   = result.get("ticker", "?")
    sig = result.get("signal", "?")
    cur = result.get("currency", "$")
    rr  = result.get("rr", {})
    col = {"BUY TODAY": "#00C48C", "PREPARE TO BUY": "#1D9E75"}.get(sig, "#FFB340")

    row = lambda lbl, val, vc="#fff": (
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:#4A7FA5;font-size:11px;width:28%;'>{lbl}</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:{vc};font-weight:700;'>{val}</td></tr>"
    )

    body = (
        f"<div style='background:#121e30;border-left:4px solid {col};border-radius:8px;"
        f"padding:14px;margin-bottom:14px;'>"
        f"<div style='font-size:22px;font-weight:900;color:#fff;'>{t}</div>"
        f"<div style='font-size:15px;color:{col};font-weight:700;margin-top:4px;'>{sig}</div>"
        f"<div style='color:#C9D6E3;margin-top:8px;font-size:13px;'>{result.get('verdict','')}</div>"
        f"</div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        + row("ENTRY PRICE", f"{cur}{result.get('entry','—')}", "#fff")
        + row("STOP LOSS",   f"{cur}{result.get('stop','—')}",  "#FF4D6A")
        + row("TARGET 1",    f"{cur}{rr.get('t1','—')}",        "#FFB340")
        + row("TARGET 2",    f"{cur}{rr.get('t2','—')}",        "#1D9E75")
        + row("TARGET 3",    f"{cur}{rr.get('t3','—')}",        "#4A7FA5")
        + row("WIN PROB",    f"{result.get('win_prob','?')}%",   col)
        + row("MINERVINI",   f"{result.get('minervini_score','?')}/8")
        + row("RS SCORE",    str(result.get("rs_score","?")))
        + row("HOLD TIME",   str(result.get("hold_days","—")))
        + "</table>"
    )
    html = _wrap(f"🔔 {sig} — {t}", col, body)
    return send_alert(f"[Aarya] {sig}: {t} @ {cur}{result.get('price','?')}", html)


def send_sell_alert(pos: dict, monitor: dict, to_email: str = "") -> tuple[bool, str]:
    t   = monitor.get("ticker", "?")
    act = monitor.get("action", "?")
    cur = monitor.get("currency", "$")
    col = monitor.get("action_col", "#FF4D6A")
    pnl = monitor.get("pnl_usd", 0)
    pct = monitor.get("pnl_pct", 0)
    pc  = "#1D9E75" if pnl >= 0 else "#FF4D6A"

    row = lambda lbl, val, vc="#fff": (
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:#4A7FA5;font-size:11px;width:28%;'>{lbl}</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:{vc};font-weight:700;'>{val}</td></tr>"
    )

    body = (
        f"<div style='background:#121e30;border-left:4px solid {col};border-radius:8px;"
        f"padding:14px;margin-bottom:14px;'>"
        f"<div style='font-size:22px;font-weight:900;color:#fff;'>{t}</div>"
        f"<div style='font-size:18px;color:{col};font-weight:700;margin-top:4px;'>{act}</div>"
        f"</div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        + row("ENTRY",   f"{cur}{monitor.get('entry','—')}")
        + row("CURRENT", f"{cur}{monitor.get('current','—')}")
        + row("P&L",     f"{cur}{pnl:+.2f}", pc)
        + row("P&L %",   f"{pct:+.2f}%",    pc)
        + row("STOP",    f"{cur}{monitor.get('stop','—')}", "#FF4D6A")
        + row("SHARES",  str(monitor.get("shares","—")))
        + row("T1",      f"{cur}{monitor.get('t1','—')} — {'✅ Hit' if monitor.get('t1_hit') else '⏳ Pending'}")
        + row("T2",      f"{cur}{monitor.get('t2','—')} — {'✅ Hit' if monitor.get('t2_hit') else '⏳ Pending'}")
        + "</table>"
        + f"<div style='margin-top:14px;padding:10px 14px;background:#121e30;"
          f"border:1px solid {col};border-radius:6px;color:#C9D6E3;font-size:13px;'>"
          f"Entry date: {pos.get('date','—')}</div>"
    )
    html = _wrap(f"🚨 Action Required: {act}", col, body)
    rcpts = [to_email] if to_email else None
    return send_alert(f"[Aarya] ACTION: {act} — {t} ({pct:+.2f}%)", html, recipients=rcpts)


def send_penny_spike_alert(ticker: str, price: float, change_pct: float,
                            volume_ratio: float, currency: str = "$") -> tuple[bool, str]:
    body = (
        f"<div style='background:#121e30;border-left:4px solid #FF7A50;border-radius:8px;"
        f"padding:14px;margin-bottom:14px;'>"
        f"<div style='font-size:22px;font-weight:900;color:#fff;'>⚡ {ticker}</div>"
        f"<div style='font-size:15px;color:#FF7A50;font-weight:700;margin-top:4px;'>PENNY STOCK SPIKE</div>"
        f"</div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>PRICE</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#fff;font-weight:700;font-size:18px;'>{currency}{price:.2f}</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>SPIKE TODAY</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#FF7A50;font-weight:700;font-size:18px;'>+{change_pct:.1f}%</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>VOLUME</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#FFB340;font-weight:700;'>{volume_ratio:.1f}x normal</td></tr>"
        f"</table>"
        f"<div style='margin-top:14px;padding:10px 14px;background:#2d1a0a;"
        f"border:1px solid #FF7A50;border-radius:6px;color:#FFB340;font-size:12px;'>"
        f"⚠️ <b>Data is 15-min delayed.</b> Penny stocks move extremely fast. "
        f"Verify live price before acting. High risk — position size carefully.</div>"
    )
    html = _wrap(f"⚡ Penny Spike: {ticker} +{change_pct:.1f}%", "#FF7A50", body)
    return send_alert(
        f"[Aarya] ⚡ PENNY SPIKE: {ticker} +{change_pct:.1f}% @ {currency}{price:.2f}", html
    )


def send_daily_top3_email(picks: list) -> tuple[bool, str]:
    """One email per day: top-3 buy setups across all markets scanned."""
    if not picks:
        return False, "No picks to send."

    row = lambda lbl, val, vc="#fff": (
        f"<tr><td style='padding:6px 10px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:#4A7FA5;font-size:11px;width:30%;'>{lbl}</td>"
        f"<td style='padding:6px 10px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:{vc};font-weight:700;'>{val}</td></tr>"
    )

    sections = ""
    for i, p in enumerate(picks[:3]):
        t   = p.get("ticker", "?")
        sig = p.get("signal", "?")
        cur = p.get("currency", "$")
        rr  = p.get("rr", {})
        col = {"BUY TODAY": "#00C48C", "PREPARE TO BUY": "#1D9E75"}.get(sig, "#FFB340")
        mkt = p.get("market_label", "")
        sections += (
            f"<div style='margin-bottom:18px;'>"
            f"<div style='background:#121e30;border-left:4px solid {col};"
            f"border-radius:8px;padding:12px;margin-bottom:6px;'>"
            f"<span style='font-size:20px;font-weight:900;color:#fff;'>#{i+1} {t}</span>"
            f"&nbsp;&nbsp;<span style='background:{col};color:#050d15;font-size:10px;"
            f"font-weight:700;padding:2px 8px;border-radius:10px;'>{sig}</span>"
            f"{'&nbsp;&nbsp;<span style=' + chr(39) + 'color:#4A7FA5;font-size:11px;' + chr(39) + '>' + mkt + '</span>' if mkt else ''}"
            f"<div style='color:#C9D6E3;font-size:12px;margin-top:6px;'>{p.get('verdict','')[:120]}…</div>"
            f"</div>"
            f"<table style='width:100%;border-collapse:collapse;'>"
            + row("Entry",  f"{cur}{p.get('entry','—')}")
            + row("Stop",   f"{cur}{p.get('stop','—')}",  "#FF4D6A")
            + row("T1",     f"{cur}{rr.get('t1','—')}",    "#FFB340")
            + row("T2",     f"{cur}{rr.get('t2','—')}",    "#1D9E75")
            + row("Win %",  f"{p.get('win_prob','?')}%",   col)
            + row("Minn",   f"{p.get('minervini_score','?')}/8")
            + "</table></div>"
        )

    body = (
        f"<div style='font-size:13px;color:#4A7FA5;margin-bottom:16px;'>"
        f"Daily scan complete. Here are the <b style='color:#00C48C;'>top {len(picks[:3])} strongest setups</b> "
        f"from today's analysis. These are not penny stocks — only quality setups with strong fundamentals.</div>"
        + sections +
        f"<div style='margin-top:14px;padding:10px 14px;background:#121e30;"
        f"border:1px solid #1a2f4a;border-radius:6px;color:#4A7FA5;font-size:11px;'>"
        f"Always verify with live data. Use position sizing rules. Not financial advice.</div>"
    )
    html  = _wrap("📈 Daily Top Picks", "#1D9E75", body)
    tickers = ", ".join(p.get("ticker","?") for p in picks[:3])
    return send_alert(f"[Aarya] 📈 Daily Top 3 Picks: {tickers}", html)


def send_daily_penny_email(penny_spikes: list) -> tuple[bool, str]:
    """Separate daily email: all penny stocks that spiked >29%."""
    if not penny_spikes:
        return False, "No penny spikes to send."

    rows_html = ""
    for ps in penny_spikes:
        cur = ps.get("currency", "$")
        rows_html += (
            f"<tr>"
            f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
            f"font-weight:700;color:#fff;'>{ps['ticker']}</td>"
            f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
            f"color:#FF7A50;font-weight:700;'>+{ps['change']:.1f}%</td>"
            f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
            f"color:#fff;'>{cur}{ps['price']:.2f}</td>"
            f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
            f"color:#FFB340;'>{ps.get('vol_ratio',1):.1f}x vol</td>"
            f"<td style='padding:8px 12px;background:#121e30;border:1px solid #1a2f4a;"
            f"color:#4A7FA5;font-size:11px;'>{ps.get('market_label','')}</td>"
            f"</tr>"
        )

    body = (
        f"<div style='font-size:13px;color:#FF7A50;font-weight:700;margin-bottom:12px;'>"
        f"⚡ {len(penny_spikes)} penny stock(s) spiked &gt;29% today</div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tr style='background:#0a1525;'>"
        f"<th style='padding:8px 12px;color:#4A7FA5;font-size:11px;text-align:left;'>Ticker</th>"
        f"<th style='padding:8px 12px;color:#4A7FA5;font-size:11px;text-align:left;'>Spike</th>"
        f"<th style='padding:8px 12px;color:#4A7FA5;font-size:11px;text-align:left;'>Price</th>"
        f"<th style='padding:8px 12px;color:#4A7FA5;font-size:11px;text-align:left;'>Volume</th>"
        f"<th style='padding:8px 12px;color:#4A7FA5;font-size:11px;text-align:left;'>Market</th>"
        f"</tr>{rows_html}</table>"
        f"<div style='margin-top:14px;padding:10px 14px;background:#2d1a0a;"
        f"border:1px solid #FF7A50;border-radius:6px;color:#FFB340;font-size:11px;'>"
        f"⚠️ Data is 15-min delayed. Penny stocks are extremely volatile. "
        f"Verify live price before acting. High risk — not financial advice.</div>"
    )
    html   = _wrap(f"⚡ Penny Spike Alert — {len(penny_spikes)} stock(s)", "#FF7A50", body)
    tickers = ", ".join(ps["ticker"] for ps in penny_spikes)
    return send_alert(f"[Aarya] ⚡ Penny Spikes Today: {tickers}", html)


def send_test_email() -> tuple[bool, str]:
    keys = load_keys()
    recipients = keys.get("email", {}).get("alert_recipients", [])
    body = (
        f"<div style='background:#121e30;border-left:4px solid #1D9E75;border-radius:8px;padding:18px;'>"
        f"<div style='font-size:18px;font-weight:700;color:#1D9E75;'>✅ Email alerts are working!</div>"
        f"<div style='color:#C9D6E3;margin-top:10px;font-size:14px;line-height:1.8;'>"
        f"You will receive alerts for:<br>"
        f"🟢 <b>Buy signals</b> — when a stock meets entry criteria<br>"
        f"🚨 <b>Sell / Stop alerts</b> — when your position hits stop or target<br>"
        f"⚡ <b>Penny spikes</b> — stocks under $10 / ₹500 spiking 29%+<br><br>"
        f"Recipients configured: <b>{len(recipients)}</b><br>"
        f"Sent at: <b>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</b>"
        f"</div></div>"
    )
    html = _wrap("Test Alert", "#1D9E75", body)
    return send_alert("[Aarya] Test Email — Alerts are working! ✅", html)


def send_market_update_email(
    session: str,           # "Morning" or "Afternoon"
    regimes: dict,          # {"us": regime_dict, "india": regime_dict}
    picks: list,            # BUY TODAY / PREPARE TO BUY picks
    watches: list,          # WATCH picks (shown when no strong picks)
    statuses: dict = None,  # {"us": {open,label}, "india": {open,label}} — optional
) -> tuple[bool, str]:
    """Always-send daily update email for morning (9 AM IST) and afternoon (3 PM IST)."""

    row = lambda lbl, val, vc="#fff": (
        f"<tr><td style='padding:5px 10px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:#4A7FA5;font-size:11px;width:35%;'>{lbl}</td>"
        f"<td style='padding:5px 10px;background:#121e30;border:1px solid #1a2f4a;"
        f"color:{vc};font-weight:700;'>{val}</td></tr>"
    )

    icon = "🌅" if session == "Morning" else "🕒"
    time_str = datetime.now().strftime("%d %b %Y, %H:%M UTC")

    # ── Market regime section ──────────────────────────────────────────
    regime_html = ""
    for mkt_name, r in regimes.items():
        bull  = r.get("pass", True)
        label = r.get("label", "Unknown")
        price = r.get("price", "—")
        pct   = r.get("pct_above", 0.0)
        col   = "#00C48C" if bull else "#FF4D6A"
        flag  = "🇺🇸" if mkt_name == "us" else "🇮🇳"
        cur   = "$" if mkt_name == "us" else "₹"
        bm    = "SPY" if mkt_name == "us" else "Nifty 50"
        regime_html += (
            f"<div style='display:inline-block;background:#121e30;border:1px solid {col};"
            f"border-radius:8px;padding:10px 16px;margin:4px 8px 4px 0;min-width:200px;'>"
            f"<div style='color:#4A7FA5;font-size:10px;'>{flag} {bm}</div>"
            f"<div style='color:{col};font-weight:900;font-size:14px;'>{label.split('—')[0].strip()}</div>"
            f"<div style='color:#C9D6E3;font-size:12px;'>{cur}{price} &nbsp;·&nbsp; "
            f"<span style='color:{col};'>{pct:+.1f}% vs 200 SMA</span></div>"
            f"</div>"
        )

    # ── Picks section ─────────────────────────────────────────────────
    if picks:
        picks_html = f"<div style='color:#00C48C;font-weight:700;font-size:13px;margin:14px 0 8px;'>📈 {len(picks)} Strong Setup(s) Found</div>"
        for i, p in enumerate(picks[:3], 1):
            cur = p.get("currency", "$")
            sig = p.get("signal", "?")
            rr  = p.get("rr", {})
            col = "#00C48C" if sig == "BUY TODAY" else "#1D9E75"
            picks_html += (
                f"<div style='background:#121e30;border-left:4px solid {col};"
                f"border-radius:8px;padding:10px 14px;margin-bottom:10px;'>"
                f"<span style='font-size:16px;font-weight:900;color:#fff;'>#{i} {p.get('ticker','?')}</span>"
                f"&nbsp;&nbsp;<span style='background:{col};color:#050d15;font-size:10px;"
                f"font-weight:700;padding:2px 8px;border-radius:10px;'>{sig}</span>"
                f"<table style='width:100%;border-collapse:collapse;margin-top:8px;'>"
                + row("Entry", f"{cur}{p.get('entry','—')}")
                + row("Stop",  f"{cur}{p.get('stop','—')}", "#FF4D6A")
                + row("T1",    f"{cur}{rr.get('t1','—')}",  "#FFB340")
                + row("Win %", f"{p.get('win_prob','?')}%",  col)
                + f"</table></div>"
            )
    elif watches:
        picks_html = (
            f"<div style='color:#FFB340;font-weight:700;font-size:13px;margin:14px 0 8px;'>"
            f"👀 No strong buys — {len(watches)} stock(s) to watch</div>"
        )
        for p in watches[:3]:
            cur = p.get("currency", "$")
            picks_html += (
                f"<div style='background:#121e30;border-left:4px solid #FFB340;"
                f"border-radius:8px;padding:8px 14px;margin-bottom:8px;'>"
                f"<span style='font-weight:700;color:#fff;'>{p.get('ticker','?')}</span>"
                f"&nbsp;<span style='color:#FFB340;font-size:11px;'>WATCH</span>"
                f"&nbsp;·&nbsp;<span style='color:#4A7FA5;font-size:11px;'>"
                f"Minervini {p.get('minervini_score','?')}/8 · Win {p.get('win_prob','?')}%"
                f" · {cur}{p.get('price','—')}</span></div>"
            )
    else:
        picks_html = (
            f"<div style='background:#121e30;border:1px solid #1a2f4a;border-radius:8px;"
            f"padding:14px;color:#4A7FA5;font-size:13px;margin-top:14px;'>"
            f"🔇 Market is quiet today — no actionable setups found in either US or India. "
            f"This is normal — the engine only signals when conditions are genuinely met. "
            f"Stay patient.</div>"
        )

    # ── Market open/closed status ──────────────────────────────────────
    status_html = ""
    any_open = False
    if statuses:
        chips = ""
        for mkt_name, sdict in statuses.items():
            is_open = sdict.get("open", False)
            any_open = any_open or is_open
            scol = "#00C48C" if is_open else "#FF7A50"
            flag = "🇺🇸" if mkt_name == "us" else "🇮🇳"
            chips += (
                f"<span style='display:inline-block;background:#121e30;border:1px solid {scol};"
                f"border-radius:6px;padding:4px 10px;margin:2px 6px 2px 0;color:{scol};font-size:11px;'>"
                f"{flag} {_esc(sdict.get('label',''))}</span>"
            )
        status_html = f"<div style='margin-bottom:10px;'>{chips}</div>"

    # When picks exist but markets are closed, reframe as 'prepare' not 'buy now'
    closed_note = ""
    if picks and statuses and not any_open:
        closed_note = (
            f"<div style='margin:10px 0;padding:10px 14px;background:#2d1a0a;"
            f"border:1px solid #FF7A50;border-radius:6px;color:#FFB340;font-size:12px;'>"
            f"🕒 Markets are closed right now. Treat these as setups to <b>prepare</b> for the "
            f"next session — plan your entry, don't chase. Re-check live prices at open.</div>"
        )

    body = (
        f"<div style='color:#4A7FA5;font-size:11px;margin-bottom:12px;'>{time_str}</div>"
        + status_html +
        f"<div style='margin-bottom:12px;'>{regime_html}</div>"
        + closed_note
        + picks_html +
        f"<div style='margin-top:16px;padding:10px 14px;background:#121e30;"
        f"border:1px solid #1a2f4a;border-radius:6px;color:#4A7FA5;font-size:11px;'>"
        f"Scans run 6× daily on weekdays. Open the app for full analysis. Not financial advice.</div>"
    )

    subj_emoji = "📈" if picks else ("👀" if watches else "🔇")
    subject    = f"[Aarya] {icon} {session} Market Update — {subj_emoji} {'Buys found' if picks else ('Watching ' + str(len(watches)) if watches else 'Quiet market')}"
    html = _wrap(f"{icon} {session} Market Update", "#1D9E75" if picks else "#FFB340", body)
    return send_alert(subject, html)


# ── GEMINI AI ──────────────────────────────────────────────────────────

def _gemini_client():
    from google import genai as _genai
    api_key = load_keys().get("gemini", {}).get("api_key", "").strip()
    if not api_key:
        return None, "⚙️ Gemini API key not set. Add it in Settings → Alert Settings."
    return _genai.Client(api_key=api_key), None


def _gemini_cached_call(prompt: str, kind: str = "briefing") -> str:
    """Cache-aware Gemini call. Returns cached text when available, otherwise
    calls Gemini and stores the response. Quota / network errors return a
    rule-based fallback string."""
    try:
        import gemini_cache
        cached = gemini_cache.get_cached(prompt, kind=kind)
        if cached:
            return cached
    except Exception:
        gemini_cache = None
    client, err = _gemini_client()
    if err:
        return err
    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        txt = resp.text or ""
        try:
            import gemini_cache as _gc
            _gc.put_cached(prompt, txt, kind=kind)
        except Exception:
            pass
        return txt
    except Exception as e:
        log.warning(f"Gemini call failed ({kind}): {e}")
        return f"AI explanation temporarily unavailable. (Gemini error: {str(e)[:80]})"


def get_gemini_briefing(ticker: str, result: dict = None) -> str:
    sig_ctx = ""
    if result:
        sig_ctx = (f" Technical context: signal={result.get('signal','?')}, "
                   f"price={result.get('currency','$')}{result.get('price','?')}, "
                   f"Minervini={result.get('minervini_score','?')}/8, "
                   f"RS={result.get('rs_score','?')}, win_prob={result.get('win_prob','?')}%.")
    prompt = (
        f"Give a concise 3-sentence investment briefing for {ticker}.{sig_ctx} "
        f"Cover: (1) what the company/asset does, "
        f"(2) one recent relevant news or catalyst, "
        f"(3) one key risk to watch. "
        f"Be factual and specific. End with: 'AI summary — not financial advice.'"
    )
    return _gemini_cached_call(prompt, kind="briefing")


def get_gemini_answer(ticker: str, question: str, result: dict = None) -> str:
    ctx = ""
    if result:
        ctx = (f"Stock data context: ticker={ticker}, "
               f"signal={result.get('signal','?')}, "
               f"price={result.get('currency','$')}{result.get('price','?')}, "
               f"Minervini={result.get('minervini_score','?')}/8, "
               f"RS={result.get('rs_score','?')}. ")
    prompt = (
        f"{ctx}User question about {ticker}: {question}\n\n"
        f"Answer in 2-3 sentences. Be specific and factual. "
        f"End with: 'Note: Not financial advice.'"
    )
    return _gemini_cached_call(prompt, kind="qa")


def get_gemini_compact_verdict(ticker: str, result: dict) -> str:
    """3-line compact verdict for Telegram — why good, why risky, act or avoid."""
    prompt = (
        f"Stock: {ticker} | Signal: {result.get('signal','?')} | "
        f"Price: {result.get('currency','$')}{result.get('price','?')} | "
        f"Minervini: {result.get('minervini_score','?')}/8 | "
        f"RS: {result.get('rs_score','?')}/100 | "
        f"Win prob: {result.get('win_prob','?')}%\n\n"
        f"Reply in EXACTLY 3 lines, no headers:\n"
        f"✅ [One specific reason this is a good setup]\n"
        f"⚠️ [One specific risk right now]\n"
        f"📌 [Direct verdict: act now / wait for entry / avoid — be specific]\n\n"
        f"Max 50 words total. Use real company facts, not generic statements."
    )
    return _gemini_cached_call(prompt, kind="verdict").strip()


def get_gemini_deep_analysis(ticker: str, result: dict) -> str:
    """
    Deep verified analysis for the Telegram bot.
    Explains WHY the signal is what it is, checks fundamentals,
    gives clear pros/cons and a final verdict.
    """
    try:
        cur     = result.get("currency", "$")
        sig     = result.get("signal", "?")
        price   = result.get("price", "?")
        minn    = result.get("minervini_score", "?")
        rs      = result.get("rs_score", "?")
        wp      = result.get("win_prob", "?")
        entry   = result.get("entry", "?")
        stop    = result.get("stop", "?")
        rr      = result.get("rr", {})
        t1, t2  = rr.get("t1", "?"), rr.get("t2", "?")
        verdict = result.get("verdict", "")
        hold    = result.get("hold_days", "?")

        prompt = f"""You are a senior stock analyst for Aarya StockSense Pro. Our technical screening system has just analyzed {ticker} and produced these verified results:

SIGNAL: {sig}
PRICE: {cur}{price}
ENTRY: {cur}{entry} | STOP LOSS: {cur}{stop} | T1: {cur}{t1} | T2: {cur}{t2}
MINERVINI SCORE: {minn}/8  (checks: price above 50MA > 150MA > 200MA, near 52-week high, strong RS vs market)
RS SCORE: {rs}/100  (relative strength — how this stock performs vs the broader market)
WIN PROBABILITY: {wp}%
SUGGESTED HOLD: {hold} days
SYSTEM VERDICT: {verdict}

Now provide a DEEP, VERIFIED, BALANCED analysis with these 5 sections:

1. WHY THIS SIGNAL
Explain specifically what the Minervini score of {minn}/8 and RS score of {rs} tell us about this stock's trend strength. What is the technical data saying?

2. FUNDAMENTAL VERIFICATION
Based on your knowledge of {ticker} — do the earnings, revenue growth, debt levels, and recent news support OR contradict this {sig} signal? Name specific recent catalysts or concerns.

3. WHY IT'S GOOD (bullish case)
Give 2-3 specific, data-backed reasons to be optimistic.

4. WHY IT'S RISKY (bearish case)
Give 2-3 specific risks or red flags — macro, sector, company-specific.

5. FINAL VERDICT
One clear sentence: should the user act on this signal now, wait for a better entry, or avoid entirely? Be direct.

Keep total response under 280 words. Be specific — use numbers, names, facts. Not generic advice.
End with: "⚠️ Not financial advice — always verify before trading."
"""
        return _gemini_cached_call(prompt, kind="deep")
    except Exception as e:
        return f"Gemini error: {e}"


def get_gemini_question_answer(question: str) -> str:
    """Answer any financial question — stocks, MF, SIP, SWP, market concepts."""
    try:
        prompt = f"""You are Aarya, a professional financial advisor assistant for Indian and US markets.

A user asked: "{question}"

Answer this thoroughly covering:
- Direct answer to the question with specific facts/numbers
- If about a mutual fund or SIP/SWP: mention specific fund names, returns, tax implications relevant to India
- If about a stock: mention fundamentals, recent performance, sector outlook
- Pros AND cons / risks
- A clear recommendation or next step

Keep response under 250 words. Be specific — use actual numbers, fund names, percentages.
End with: "⚠️ Not financial advice — consult a SEBI-registered advisor for personal decisions."
"""
        return _gemini_cached_call(prompt, kind="qa")
    except Exception as e:
        return f"Gemini error: {e}"


# ── TELEGRAM ──────────────────────────────────────────────────────────

def _get_tg_creds() -> tuple[str, str]:
    """Return (bot_token, chat_id)."""
    token = chat_id = ""
    # 1. Local config file
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                d = json.load(f)
            tg      = d.get("telegram", {})
            token   = tg.get("token", "")
            chat_id = tg.get("chat_id", "")
        except Exception:
            pass
    # 2. Streamlit secrets
    if not token or not chat_id:
        try:
            import streamlit as st
            token   = token   or str(st.secrets.get("TELEGRAM_TOKEN",   ""))
            chat_id = chat_id or str(st.secrets.get("TELEGRAM_CHAT_ID", ""))
        except Exception:
            pass
    # 3. Environment variables (GitHub Actions)
    if not token:
        token   = os.environ.get("TELEGRAM_TOKEN",   "")
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    return token.strip(), chat_id.strip()


def send_telegram(message: str, chat_id: str = "", max_attempts: int = 3) -> tuple[bool, str]:
    """Send a Telegram message (HTML parse mode) with retry + delivery logging."""
    token, default_cid = _get_tg_creds()
    cid = chat_id.strip() or default_cid
    if not token or not cid:
        log.warning("Telegram skipped: token or chat_id missing.")
        return False, "Telegram not configured."

    last_err = ""
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "text": message, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=15,
            )
            if r.status_code == 200 and r.json().get("ok"):
                log.info(f"Telegram sent → {cid} (attempt {attempt})")
                return True, "Telegram sent."
            # Telegram API rejected the message (bad chat_id, blocked bot, etc.)
            desc = ""
            try:
                desc = r.json().get("description", r.text[:120])
            except Exception:
                desc = r.text[:120]
            # 4xx other than 429 won't fix on retry — bail out
            if r.status_code != 429 and 400 <= r.status_code < 500:
                log.warning(f"Telegram rejected → {cid}: {desc}")
                return False, desc
            last_err = desc
        except Exception as e:
            last_err = str(e)
        log.warning(f"Telegram attempt {attempt}/{max_attempts} failed → {cid}: {last_err}")
        if attempt < max_attempts:
            time.sleep(2 ** attempt)

    log.error(f"Telegram FAILED after {max_attempts} attempts → {cid}: {last_err}")
    return False, f"Failed after {max_attempts} attempts: {last_err}"


def tg_daily_top3(picks: list, chat_id: str = "") -> tuple[bool, str]:
    if not picks:
        return False, "No picks."
    lines = ["📈 <b>Aarya Top Picks</b>"]
    for i, p in enumerate(picks[:3], 1):
        cur = _esc(p.get("currency", "$"))
        rr  = p.get("rr", {})
        lines.append(
            f"\n#{i} <b>{_esc(p.get('ticker','?'))}</b> — {_esc(p.get('signal','?'))}"
            f"\nEntry: {cur}{_esc(p.get('entry','—'))} | Stop: {cur}{_esc(p.get('stop','—'))}"
            f" | T1: {cur}{_esc(rr.get('t1','—'))} | Win: {_esc(p.get('win_prob','?'))}%"
        )
    lines.append("\n<i>Open the app for full analysis. Not financial advice.</i>")
    return send_telegram("\n".join(lines), chat_id)


def tg_penny_spikes(spikes: list, chat_id: str = "") -> tuple[bool, str]:
    if not spikes:
        return False, "No spikes."
    lines = [f"⚡ <b>Penny Spike Alert — {len(spikes)} stock(s)</b>"]
    for s in spikes:
        cur = _esc(s.get("currency", "$"))
        lines.append(
            f"\n<b>{_esc(s['ticker'])}</b>: +{s['change']:.1f}% @ {cur}{s['price']:.2f}"
            f" ({s.get('vol_ratio',1):.1f}x vol)"
        )
    lines.append("\n⚠️ <i>High risk. Verify live price before acting.</i>")
    return send_telegram("\n".join(lines), chat_id)


def tg_sell_alert(pos: dict, monitor: dict, chat_id: str = "") -> tuple[bool, str]:
    ticker = _esc(monitor.get("ticker", "?"))
    action = _esc(monitor.get("action", "?"))
    cur    = _esc(monitor.get("currency", "$"))
    pnl    = monitor.get("pnl_usd", 0)
    pct    = monitor.get("pnl_pct", 0)
    msg = (
        f"🚨 <b>ACTION REQUIRED</b>\n"
        f"<b>{ticker}</b> — {action}\n"
        f"Entry: {cur}{_esc(monitor.get('entry','—'))} → Now: {cur}{_esc(monitor.get('current','—'))}\n"
        f"P&amp;L: {cur}{pnl:+.2f} ({pct:+.1f}%)\n"
        f"<i>Open the app to act.</i>"
    )
    return send_telegram(msg, chat_id)


# ── HIGH-MOMENTUM BREAKOUT ────────────────────────────────────────────

def send_momentum_alert(result: dict, confidence: float = None) -> tuple[bool, str]:
    """Email for a high-momentum breakout. confidence is the ML score (0–100)."""
    t   = result.get("ticker", "?")
    cur = result.get("currency", "$")
    rr  = result.get("rr", {})
    chg = result.get("intraday_pct", 0)
    vol = result.get("vol_ratio", 0)
    col = "#00C48C"
    conf_line = f"<br><span style='color:#FFB340;'>ML confidence: <b>{confidence:.0f}%</b></span>" if confidence is not None else ""

    body = (
        f"<div style='background:#121e30;border-left:4px solid {col};border-radius:8px;"
        f"padding:14px;margin-bottom:14px;'>"
        f"<div style='font-size:24px;font-weight:900;color:#fff;'>💥 {t}</div>"
        f"<div style='font-size:15px;color:{col};font-weight:700;margin-top:4px;'>HIGH MOMENTUM BREAKOUT</div>"
        f"<div style='color:#C9D6E3;margin-top:8px;font-size:13px;'>"
        f"Intraday: <b>+{chg:.1f}%</b>  ·  Volume <b>{vol:.1f}x</b> avg{conf_line}</div></div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;width:30%;'>PRICE</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#fff;font-weight:700;'>{cur}{result.get('price','—')}</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>ENTRY</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#fff;font-weight:700;'>{cur}{result.get('entry','—')}</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>STOP</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#FF4D6A;font-weight:700;'>{cur}{result.get('stop','—')}</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>T1</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#FFB340;font-weight:700;'>{cur}{rr.get('t1','—')}</td></tr>"
        f"</table>"
        f"<div style='margin-top:14px;padding:10px 14px;background:#0e2a1f;"
        f"border:1px solid {col};border-radius:6px;color:#C9D6E3;font-size:12px;'>"
        f"⚡ Breakout with confirmed volume + RS. Move fast — momentum windows are short. "
        f"Verify live before acting.</div>"
    )
    html = _wrap(f"💥 Momentum: {t} +{chg:.1f}%", col, body)
    subj = f"[Aarya] 💥 Momentum: {t} +{chg:.1f}% on {vol:.1f}x vol"
    if confidence is not None:
        subj += f" — confidence {confidence:.0f}%"
    return send_alert(subj, html)


def tg_momentum_alert(result: dict, confidence: float = None,
                      chat_id: str = "") -> tuple[bool, str]:
    t   = _esc(result.get("ticker", "?"))
    cur = _esc(result.get("currency", "$"))
    rr  = result.get("rr", {})
    chg = result.get("intraday_pct", 0)
    vol = result.get("vol_ratio", 0)
    conf = f"\n📊 ML confidence: <b>{confidence:.0f}%</b>" if confidence is not None else ""
    msg = (
        f"💥 <b>HIGH MOMENTUM</b>\n"
        f"<b>{t}</b>  +{chg:.1f}%  ·  {vol:.1f}x vol{conf}\n"
        f"Entry: {cur}{_esc(result.get('entry','—'))} | "
        f"Stop: {cur}{_esc(result.get('stop','—'))} | "
        f"T1: {cur}{_esc(rr.get('t1','—'))}\n"
        f"<i>Breakout — move fast. Verify live.</i>"
    )
    return send_telegram(msg, chat_id)


# ── TRAIL-STOP SUGGESTION (held positions, intraday) ──────────────────

def send_trail_stop_email(pos: dict, monitor_dict: dict, suggested_stop: float,
                          to_email: str = "") -> tuple[bool, str]:
    t   = monitor_dict.get("ticker", "?")
    cur = monitor_dict.get("currency", "$")
    pct = monitor_dict.get("pnl_pct", 0)
    col = "#1D9E75"
    body = (
        f"<div style='background:#121e30;border-left:4px solid {col};border-radius:8px;"
        f"padding:14px;margin-bottom:14px;'>"
        f"<div style='font-size:22px;font-weight:900;color:#fff;'>💰 {t}</div>"
        f"<div style='font-size:15px;color:{col};font-weight:700;margin-top:4px;'>TRAIL STOP — LOCK PROFIT</div>"
        f"<div style='color:#C9D6E3;margin-top:8px;font-size:13px;'>"
        f"Up <b>{pct:+.1f}%</b> since entry. Suggested action: move your stop "
        f"to <b>{cur}{suggested_stop:.2f}</b> to lock in this gain.</div></div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>CURRENT</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#fff;font-weight:700;'>{cur}{monitor_dict.get('current','—')}</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>ENTRY</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#fff;font-weight:700;'>{cur}{monitor_dict.get('entry','—')}</td></tr>"
        f"<tr><td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:#4A7FA5;font-size:11px;'>NEW STOP</td>"
        f"<td style='padding:7px 12px;background:#121e30;border:1px solid #1a2f4a;color:{col};font-weight:700;'>{cur}{suggested_stop:.2f}</td></tr>"
        f"</table>"
    )
    html = _wrap(f"💰 Trail Stop: {t} {pct:+.1f}%", col, body)
    rcpts = [to_email] if to_email else None
    return send_alert(f"[Aarya] 💰 Trail Stop: {t} {pct:+.1f}% — lock profit", html, recipients=rcpts)


def tg_trail_stop(pos: dict, monitor_dict: dict, suggested_stop: float,
                  chat_id: str = "") -> tuple[bool, str]:
    t   = _esc(monitor_dict.get("ticker", "?"))
    cur = _esc(monitor_dict.get("currency", "$"))
    pct = monitor_dict.get("pnl_pct", 0)
    msg = (
        f"💰 <b>TRAIL STOP</b>\n"
        f"<b>{t}</b> is up <b>{pct:+.1f}%</b>.\n"
        f"Suggested: move stop to <b>{cur}{suggested_stop:.2f}</b> to lock in profit.\n"
        f"Current: {cur}{_esc(monitor_dict.get('current','—'))}  |  "
        f"Entry: {cur}{_esc(monitor_dict.get('entry','—'))}"
    )
    return send_telegram(msg, chat_id)
