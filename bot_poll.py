"""
Aarya StockSense Pro — bot_poll.py
Telegram bot polling mode for GitHub Actions.
Runs once per GitHub Actions execution, processes any pending messages, replies, exits.
Offset (last processed message ID) is stored in Supabase so no messages are double-processed.
"""

import os
import re
import sys
import logging

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("aarya_bot_poll")

TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
SB_URL   = os.environ.get("SUPABASE_URL", "")
SB_KEY   = os.environ.get("SUPABASE_KEY", "")
API_BASE = f"https://api.telegram.org/bot{TOKEN}"

_NOT_TICKER = {
    "I","A","AN","THE","IS","IT","IN","ON","AT","TO","DO","BE","ME","MY","OR",
    "IF","OF","BY","UP","AS","AM","OK","HI","NO","YES","SIP","SWP","MF","ETF",
    "NFO","IPO","PE","EPS","RS","US","BUY","SELL","GOOD","BAD","BEST","WHAT",
    "HOW","WHY","WHEN","CAN","WILL","ARE","FOR","WITH","THIS","THAT","GIVE",
    "SHOW","GET","CHECK","NOW","ALL","ANY","NEW","OLD","TOP","LOW","HIGH",
    "HELP","START","STOP","HOLD","WAIT","AVOID","PICK","SCAN","LIST","INFO",
}


# ── Offset persistence (Supabase) ─────────────────────────────────────

def _sb_headers():
    return {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

def get_offset() -> int:
    if not SB_URL or not SB_KEY:
        return 0
    try:
        r = requests.get(
            f"{SB_URL}/rest/v1/settings?id=eq.tg_bot_offset&select=data",
            headers=_sb_headers(), timeout=10,
        )
        data = r.json()
        if data:
            return int(data[0].get("data", {}).get("offset", 0))
    except Exception as e:
        log.warning(f"get_offset error: {e}")
    return 0

def save_offset(offset: int):
    if not SB_URL or not SB_KEY:
        return
    try:
        requests.post(
            f"{SB_URL}/rest/v1/settings",
            headers=_sb_headers(),
            json={"id": "tg_bot_offset", "data": {"offset": offset}},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"save_offset error: {e}")


# ── Telegram helpers ──────────────────────────────────────────────────

def send(text: str, chat_id: str):
    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        try:
            requests.post(
                f"{API_BASE}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=15,
            )
        except Exception as e:
            log.error(f"Send error: {e}")

def fetch_updates(offset: int) -> list:
    try:
        r = requests.get(
            f"{API_BASE}/getUpdates",
            params={"offset": offset, "limit": 20, "timeout": 5},
            timeout=10,
        )
        return r.json().get("result", [])
    except Exception as e:
        log.error(f"getUpdates error: {e}")
        return []


# ── Stock helpers ─────────────────────────────────────────────────────

def _get_market(text_upper: str):
    from config import MARKET_CONFIGS
    indian = {"RELIANCE","TCS","INFY","INFOSYS","HDFC","ICICI","WIPRO","HCLTECH",
              "BAJAJ","TATA","TATAMOTORS","TATASTEEL","SUNPHARMA","ADANI","AXIS",
              "KOTAK","SBIN","SBI","HINDALCO","ULTRACEMCO","ASIANPAINT","ITC"}
    for h in indian:
        if h in text_upper:
            return MARKET_CONFIGS.get("🇮🇳 India NSE")
    return MARKET_CONFIGS.get("🇺🇸 US Stocks")

def _extract_ticker(text: str):
    words = re.findall(r'\b([A-Z]{2,6})\b', text.upper())
    for w in words:
        if w not in _NOT_TICKER:
            return w
    return None


# ── Handlers ──────────────────────────────────────────────────────────

def handle_stock(ticker: str, chat_id: str, mc=None):
    import engine as eng
    import notifier
    from config import MARKET_CONFIGS

    send(f"🔍 Analyzing {ticker}... (10-20 sec)", chat_id)
    if mc is None:
        mc = _get_market(ticker)
    try:
        try:
            regime = eng.check_regime(mc)
        except Exception:
            regime = {"pass": True, "label": "Unknown",
                      "price": "—", "sma200": "—", "pct_above": 0.0}

        result = eng.analyze_ticker(ticker, mc, regime, 10000, 1.0)

        # Try other market if not found
        if result is None:
            alt = (MARKET_CONFIGS.get("🇮🇳 India NSE")
                   if mc == MARKET_CONFIGS.get("🇺🇸 US Stocks")
                   else MARKET_CONFIGS.get("🇺🇸 US Stocks"))
            try:
                regime2 = eng.check_regime(alt)
            except Exception:
                regime2 = regime
            result = eng.analyze_ticker(ticker, alt, regime2, 10000, 1.0)
            if result:
                mc = alt

        if result is None:
            send(f"❌ No data for {ticker}. Check the ticker symbol.", chat_id)
            return

        cur  = result.get("currency", "$")
        sig  = result.get("signal", "?")
        rr   = result.get("rr", {})
        icon = {"BUY TODAY": "🟢", "PREPARE TO BUY": "🟡",
                "WAIT": "⏳", "AVOID": "🔴"}.get(sig, "⚪")

        # Get compact 3-line AI verdict
        ai = notifier.get_gemini_compact_verdict(ticker, result)

        msg = (
            f"📊 {ticker}  {icon} {sig}\n"
            f"{'─'*28}\n"
            f"Price:  {cur}{result.get('price','—')}\n"
            f"Entry:  {cur}{result.get('entry','—')}  |  Stop: {cur}{result.get('stop','—')}\n"
            f"T1:     {cur}{rr.get('t1','—')}  |  T2:   {cur}{rr.get('t2','—')}\n"
            f"Win:    {result.get('win_prob','?')}%"
            f"  |  Minervini: {result.get('minervini_score','?')}/8\n"
        )
        if ai:
            msg += f"\n{ai}\n"
        msg += "\n⚠️ Not financial advice."

        send(msg, chat_id)

    except Exception as e:
        log.error(f"handle_stock error {ticker}: {e}")
        send(f"❌ Error analyzing {ticker}: {str(e)[:150]}", chat_id)


def handle_picks(chat_id: str):
    import engine as eng
    from config import MARKET_CONFIGS

    send("🔍 Scanning US + India for top setups (~60 sec)...", chat_id)
    all_picks = []

    for market_name, currency, cutoff in [
        ("🇺🇸 US Stocks", "$", 10.0),
        ("🇮🇳 India NSE", "₹", 500.0),
    ]:
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue
        tickers = list(dict.fromkeys(mc.get("growth", []) + mc.get("blue_chips", [])))[:15]
        try:
            regime = eng.check_regime(mc)
        except Exception:
            regime = {"pass": True, "label": "Unknown",
                      "price": "—", "sma200": "—", "pct_above": 0.0}
        for t in tickers:
            try:
                r = eng.analyze_ticker(t, mc, regime, 10000, 1.0)
                if r and r.get("price", 999) >= cutoff and \
                        r["signal"] in ("BUY TODAY", "PREPARE TO BUY"):
                    r["currency"]     = currency
                    r["market_label"] = market_name
                    all_picks.append(r)
            except Exception:
                pass

    all_picks.sort(
        key=lambda r: r.get("win_prob", 0) * 0.5
                    + r.get("minervini_score", 0) * 5
                    + r.get("rs_score", 0) * 10,
        reverse=True,
    )

    if not all_picks:
        send("No strong buy setups right now. Market may be weak.", chat_id)
        return

    lines = [f"📈 Top {min(3,len(all_picks))} Setups Today\n{'─'*28}"]
    for i, p in enumerate(all_picks[:3], 1):
        cur  = p.get("currency", "$")
        rr   = p.get("rr", {})
        icon = "🟢" if p["signal"] == "BUY TODAY" else "🟡"
        lines.append(
            f"#{i} {icon} {p.get('ticker','?')} — {p.get('signal','?')}\n"
            f"Entry: {cur}{p.get('entry','—')} | Stop: {cur}{p.get('stop','—')}\n"
            f"T1: {cur}{rr.get('t1','—')} | Win: {p.get('win_prob','?')}%"
        )
    lines.append("\n⚠️ Not financial advice.")
    send("\n\n".join(lines), chat_id)


def handle_question(text: str, chat_id: str):
    import notifier
    send("🤖 Thinking...", chat_id)
    try:
        answer = notifier.get_gemini_question_answer(text)
        send(f"🤖 {answer}", chat_id)
    except Exception as e:
        send(f"Error: {e}", chat_id)


def handle_help(chat_id: str):
    send(
        "🤖 Aarya StockSense Bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 STOCK ANALYSIS\n"
        "Just type a ticker:\n"
        "  AAPL, TSLA, RELIANCE, TCS\n\n"
        "⚡ COMMANDS\n"
        "  /picks  — Top 3 buy setups today\n"
        "  /help   — This menu\n\n"
        "💬 ASK ANYTHING\n"
        "  'Is NVDA a good buy?'\n"
        "  'Best SIP for 5000/month'\n"
        "  'How does SWP work?'\n\n"
        "⏱ Replies within 2 hours\n"
        "⚠️ Not financial advice.",
        chat_id,
    )


def process(text: str, chat_id: str):
    text  = text.strip()
    lower = text.lower()

    if text.startswith("/start") or text.startswith("/help"):
        handle_help(chat_id)
    elif text.startswith("/picks"):
        handle_picks(chat_id)
    elif text.startswith("/check"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            handle_stock(parts[1].strip().upper(), chat_id)
        else:
            send("Usage: /check TICKER  e.g. /check AAPL", chat_id)
    else:
        ticker = _extract_ticker(text)
        words  = text.split()
        is_ticker_query = (
            len(words) <= 3
            or any(kw in lower for kw in ("check","analyse","analyze","analysis",
                                           "signal","what about","how is","should i"))
        )
        if ticker and is_ticker_query:
            handle_stock(ticker, chat_id)
        else:
            handle_question(text, chat_id)


# ── Main ──────────────────────────────────────────────────────────────

def run():
    if not TOKEN:
        log.warning("TELEGRAM_TOKEN not set — skipping bot poll.")
        return

    offset = get_offset()
    log.info(f"Bot poll starting. Current offset: {offset}")

    updates = fetch_updates(offset)
    if not updates:
        log.info("No new Telegram messages.")
        return

    log.info(f"{len(updates)} new message(s) to process.")
    new_offset = offset

    for upd in updates:
        new_offset = upd["update_id"] + 1
        try:
            msg  = upd.get("message", {})
            text = msg.get("text", "").strip()
            cid  = str(msg.get("chat", {}).get("id", ""))
            if text and cid:
                log.info(f"Processing: [{cid}] {text[:60]}")
                process(text, cid)
        except Exception as e:
            log.error(f"Process error: {e}")

    save_offset(new_offset)
    log.info(f"Bot poll done. New offset: {new_offset}")


if __name__ == "__main__":
    run()
