"""
Aarya StockSense Pro — notifier.py
Gmail SMTP email alerts + Gemini AI briefings.
"""

import json
import os
import smtplib
import ssl
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aarya_config.json")

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


def send_alert(subject: str, html_body: str) -> tuple[bool, str]:
    keys = load_keys()
    ec   = keys.get("email", {})
    sender     = ec.get("sender_address", "").strip()
    password   = ec.get("sender_app_password", "").strip()
    recipients = ec.get("alert_recipients", [])

    if not sender or not password:
        return False, "Gmail sender not configured. Go to Settings → Alert Settings."
    if not recipients:
        return False, "No recipient emails added yet."

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
        return True, f"Sent to {len(recipients)} recipient(s)"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail authentication failed. Check sender email and app password."
    except Exception as e:
        return False, str(e)


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


def send_sell_alert(pos: dict, monitor: dict) -> tuple[bool, str]:
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
    return send_alert(f"[Aarya] ACTION: {act} — {t} ({pct:+.2f}%)", html)


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


# ── GEMINI AI ──────────────────────────────────────────────────────────

def _gemini_client():
    from google import genai as _genai
    api_key = load_keys().get("gemini", {}).get("api_key", "").strip()
    if not api_key:
        return None, "⚙️ Gemini API key not set. Add it in Settings → Alert Settings."
    return _genai.Client(api_key=api_key), None


def get_gemini_briefing(ticker: str, result: dict = None) -> str:
    client, err = _gemini_client()
    if err:
        return err
    try:
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
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return resp.text
    except Exception as e:
        return f"Gemini error: {e}"


def get_gemini_answer(ticker: str, question: str, result: dict = None) -> str:
    client, err = _gemini_client()
    if err:
        return err
    try:
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
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return resp.text
    except Exception as e:
        return f"Gemini error: {e}"


def get_gemini_compact_verdict(ticker: str, result: dict) -> str:
    """3-line compact verdict for Telegram — why good, why risky, act or avoid."""
    client, err = _gemini_client()
    if err:
        return ""
    try:
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
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return resp.text.strip()
    except Exception as e:
        return ""


def get_gemini_deep_analysis(ticker: str, result: dict) -> str:
    """
    Deep verified analysis for the Telegram bot.
    Explains WHY the signal is what it is, checks fundamentals,
    gives clear pros/cons and a final verdict.
    """
    client, err = _gemini_client()
    if err:
        return err
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
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return resp.text
    except Exception as e:
        return f"Gemini error: {e}"


def get_gemini_question_answer(question: str) -> str:
    """Answer any financial question — stocks, MF, SIP, SWP, market concepts."""
    client, err = _gemini_client()
    if err:
        return err
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
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return resp.text
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


def send_telegram(message: str) -> tuple[bool, str]:
    token, chat_id = _get_tg_creds()
    if not token or not chat_id:
        return False, "Telegram not configured."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
        if r.status_code == 200 and r.json().get("ok"):
            return True, "Telegram sent."
        return False, r.json().get("description", r.text[:120])
    except Exception as e:
        return False, str(e)


def tg_daily_top3(picks: list) -> tuple[bool, str]:
    if not picks:
        return False, "No picks."
    lines = ["📈 *Aarya Top Picks*"]
    for i, p in enumerate(picks[:3], 1):
        cur = p.get("currency", "$")
        rr  = p.get("rr", {})
        lines.append(
            f"\n#{i} *{p.get('ticker','?')}* — {p.get('signal','?')}"
            f"\nEntry: {cur}{p.get('entry','—')} | Stop: {cur}{p.get('stop','—')}"
            f" | T1: {cur}{rr.get('t1','—')} | Win: {p.get('win_prob','?')}%"
        )
    lines.append("\n_Open the app for full analysis\\. Not financial advice\\._")
    return send_telegram("\n".join(lines))


def tg_penny_spikes(spikes: list) -> tuple[bool, str]:
    if not spikes:
        return False, "No spikes."
    lines = [f"⚡ *Penny Spike Alert — {len(spikes)} stock(s)*"]
    for s in spikes:
        cur = s.get("currency", "$")
        lines.append(
            f"\n*{s['ticker']}*: \\+{s['change']:.1f}% @ {cur}{s['price']:.2f}"
            f" \\({s.get('vol_ratio',1):.1f}x vol\\)"
        )
    lines.append("\n⚠️ _High risk\\. Verify live price before acting\\._")
    return send_telegram("\n".join(lines))


def tg_sell_alert(pos: dict, monitor: dict) -> tuple[bool, str]:
    ticker = monitor.get("ticker", "?")
    action = monitor.get("action", "?")
    cur    = monitor.get("currency", "$")
    pnl    = monitor.get("pnl_usd", 0)
    pct    = monitor.get("pnl_pct", 0)
    msg = (
        f"🚨 *ACTION REQUIRED*\n"
        f"*{ticker}* — {action}\n"
        f"Entry: {cur}{monitor.get('entry','—')} → Now: {cur}{monitor.get('current','—')}\n"
        f"P&L: {cur}{pnl:+.2f} \\({pct:+.1f}%\\)\n"
        f"_Open the app to act\\._"
    )
    return send_telegram(msg)
