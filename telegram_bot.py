"""
Aarya StockSense Pro — telegram_bot.py
Interactive Telegram bot. Runs 24/7 on Render.com (free tier).

Features:
  - Type any ticker (AAPL, RELIANCE, TSLA) → full technical analysis + Gemini verification
  - /picks → scan and return today's top 3 buy setups
  - /penny → penny stocks spiking today
  - Any question (SIP, SWP, mutual funds, market) → Gemini answers
"""

import os
import re
import sys
import time
import logging

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("aarya_bot")

TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
API_BASE = f"https://api.telegram.org/bot{TOKEN}"
_offset  = 0

# Words that look like tickers but aren't
_NOT_TICKER = {
    "I", "A", "AN", "THE", "IS", "IT", "IN", "ON", "AT", "TO", "DO", "BE",
    "ME", "MY", "OR", "IF", "OF", "BY", "UP", "AS", "AM", "OK", "HI", "NO",
    "YES", "SIP", "SWP", "MF", "ETF", "NFO", "IPO", "PE", "EPS", "RS", "US",
    "BUY", "SELL", "GOOD", "BAD", "BEST", "WHAT", "HOW", "WHY", "WHEN", "CAN",
    "WILL", "ARE", "FOR", "WITH", "THIS", "THAT", "GIVE", "SHOW", "GET",
    "CHECK", "NOW", "ALL", "ANY", "NEW", "OLD", "TOP", "LOW", "HIGH", "HELP",
    "START", "STOP", "HOLD", "WAIT", "AVOID", "PICK", "SCAN", "LIST", "INFO",
}


# ── Telegram helpers ──────────────────────────────────────────────────

def send(text: str, chat_id: str = None):
    """Send a message, splitting if over 4000 chars."""
    cid = chat_id or CHAT_ID
    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        try:
            requests.post(
                f"{API_BASE}/sendMessage",
                json={"chat_id": cid, "text": chunk},
                timeout=15,
            )
        except Exception as e:
            log.error(f"Send error: {e}")


def get_updates() -> list:
    global _offset
    try:
        r = requests.get(
            f"{API_BASE}/getUpdates",
            params={"offset": _offset, "timeout": 30},
            timeout=35,
        )
        updates = r.json().get("result", [])
        if updates:
            _offset = updates[-1]["update_id"] + 1
        return updates
    except Exception as e:
        log.error(f"getUpdates error: {e}")
        time.sleep(5)
        return []


# ── Market config helper ──────────────────────────────────────────────

def _get_market(text_upper: str):
    from config import MARKET_CONFIGS
    indian_hints = {
        "RELIANCE", "TCS", "INFY", "INFOSYS", "HDFC", "ICICI", "WIPRO",
        "HCLTECH", "BAJAJ", "TATA", "TATAMOTORS", "TATASTEEL", "SUNPHARMA",
        "ADANI", "AXIS", "KOTAK", "SBIN", "SBI", "NIFTY", "SENSEX",
        "NSE", "BSE", "HINDALCO", "ULTRACEMCO", "ASIANPAINT", "ITC",
    }
    for hint in indian_hints:
        if hint in text_upper:
            return MARKET_CONFIGS.get("🇮🇳 India NSE"), "₹"
    return MARKET_CONFIGS.get("🇺🇸 US Stocks"), "$"


def _extract_ticker(text: str) -> str | None:
    """Pull first plausible ticker from text (2–6 uppercase letters)."""
    words = re.findall(r'\b([A-Z]{2,6})\b', text.upper())
    for w in words:
        if w not in _NOT_TICKER:
            return w
    return None


# ── Analysis ──────────────────────────────────────────────────────────

def analyze_stock(ticker: str, chat_id: str, mc=None):
    import engine as eng
    import notifier
    from config import MARKET_CONFIGS

    send(f"🔍 Analyzing {ticker}... please wait (10-20 sec)", chat_id)

    if mc is None:
        mc, _ = _get_market(ticker)

    try:
        try:
            regime = eng.check_regime(mc)
        except Exception:
            regime = {"pass": True, "label": "Unknown",
                      "price": "—", "sma200": "—", "pct_above": 0.0}

        result = eng.analyze_ticker(ticker, mc, regime, 10000, 1.0)

        if result is None:
            # Try the other market
            alt_mc = (MARKET_CONFIGS.get("🇮🇳 India NSE")
                      if mc == MARKET_CONFIGS.get("🇺🇸 US Stocks")
                      else MARKET_CONFIGS.get("🇺🇸 US Stocks"))
            try:
                regime2 = eng.check_regime(alt_mc)
            except Exception:
                regime2 = regime
            result = eng.analyze_ticker(ticker, alt_mc, regime2, 10000, 1.0)
            if result:
                mc = alt_mc

        if result is None:
            send(
                f"❌ No data found for {ticker}.\n"
                f"Make sure you're using the correct ticker symbol "
                f"(e.g. AAPL, RELIANCE, TSLA, TCS).",
                chat_id,
            )
            return

        cur  = result.get("currency", mc.get("currency", "$"))
        sig  = result.get("signal", "?")
        rr   = result.get("rr", {})
        minn = result.get("minervini_score", "?")
        rs   = result.get("rs_score", "?")
        wp   = result.get("win_prob", "?")

        sig_icon = {"BUY TODAY": "🟢", "PREPARE TO BUY": "🟡",
                    "WAIT": "⏳", "AVOID": "🔴"}.get(sig, "⚪")

        tech = (
            f"{'═'*32}\n"
            f"📊  {ticker}  —  {sig_icon} {sig}\n"
            f"{'═'*32}\n\n"
            f"💰  Price:   {cur}{result.get('price','—')}\n\n"
            f"📈  TRADE LEVELS\n"
            f"    Entry   {cur}{result.get('entry','—')}\n"
            f"    Stop    {cur}{result.get('stop','—')}\n"
            f"    T1      {cur}{rr.get('t1','—')}\n"
            f"    T2      {cur}{rr.get('t2','—')}\n"
            f"    T3      {cur}{rr.get('t3','—')}\n\n"
            f"📐  SCORES\n"
            f"    Minervini   {minn}/8\n"
            f"    RS Score    {rs}/100\n"
            f"    Win Prob    {wp}%\n"
            f"    Hold Time   {result.get('hold_days','?')} days\n"
        )
        send(tech, chat_id)

        # Deep Gemini analysis
        send("🤖 Running AI verification & deep analysis...", chat_id)
        ai = notifier.get_gemini_deep_analysis(ticker, result)
        send(f"🤖  AI DEEP ANALYSIS\n{'─'*30}\n{ai}", chat_id)

    except Exception as e:
        log.error(f"analyze_stock error for {ticker}: {e}")
        send(f"❌ Error analyzing {ticker}: {str(e)[:150]}", chat_id)


def handle_picks(chat_id: str):
    import engine as eng
    from config import MARKET_CONFIGS

    send("🔍 Scanning US + India markets for top setups...\nThis takes ~60 seconds.", chat_id)

    all_picks = []
    for market_name, currency, cutoff in [
        ("🇺🇸 US Stocks", "$", 10.0),
        ("🇮🇳 India NSE", "₹", 500.0),
    ]:
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue
        tickers = list(dict.fromkeys(
            mc.get("growth", []) + mc.get("blue_chips", [])
        ))[:15]
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

    def _score(r):
        return (r.get("win_prob", 0) * 0.5
                + r.get("minervini_score", 0) * 5
                + r.get("rs_score", 0) * 10)

    all_picks.sort(key=_score, reverse=True)

    if not all_picks:
        send("No strong buy setups found right now. Market conditions may be weak.", chat_id)
        return

    send(f"✅ Found {len(all_picks)} setups. Top 3:", chat_id)
    for i, p in enumerate(all_picks[:3], 1):
        cur  = p.get("currency", "$")
        rr   = p.get("rr", {})
        icon = "🟢" if p["signal"] == "BUY TODAY" else "🟡"
        msg  = (
            f"#{i} {icon} {p.get('ticker','?')}  —  {p.get('signal','?')}\n"
            f"Market: {p.get('market_label','')}\n"
            f"Entry:  {cur}{p.get('entry','—')}  |  Stop: {cur}{p.get('stop','—')}\n"
            f"T1: {cur}{rr.get('t1','—')}  T2: {cur}{rr.get('t2','—')}\n"
            f"Win: {p.get('win_prob','?')}%  |  Minervini: {p.get('minervini_score','?')}/8\n"
            f"RS: {p.get('rs_score','?')}/100"
        )
        send(msg, chat_id)


def handle_penny(chat_id: str):
    import engine as eng
    from config import MARKET_CONFIGS

    send("⚡ Scanning for penny stock spikes (>29%)...", chat_id)
    spikes = []

    for market_name, currency, cutoff in [
        ("🇺🇸 US Stocks", "$", 10.0),
        ("🇮🇳 India NSE", "₹", 500.0),
    ]:
        mc = MARKET_CONFIGS.get(market_name)
        if not mc:
            continue
        tickers = list(dict.fromkeys(
            mc.get("growth", []) + mc.get("blue_chips", [])
        ))[:15]
        for t in tickers:
            try:
                df = eng.download(t, period="5d")
                if df is None or len(df) < 2:
                    continue
                price = float(df["Close"].squeeze().iloc[-1])
                if price >= cutoff:
                    continue
                prev = float(df["Close"].squeeze().iloc[-2])
                chg  = (price - prev) / prev * 100 if prev else 0
                if chg >= 29.0:
                    spikes.append({
                        "ticker": t, "price": price, "change": chg,
                        "currency": currency, "market": market_name,
                    })
            except Exception:
                pass

    if not spikes:
        send("No penny spikes found right now.", chat_id)
        return

    lines = [f"⚡ {len(spikes)} penny spike(s) detected:\n"]
    for s in spikes:
        lines.append(
            f"{s['ticker']}: +{s['change']:.1f}% @ {s['currency']}{s['price']:.2f}  ({s['market']})"
        )
    lines.append("\n⚠️ High risk. Verify live price before acting.")
    send("\n".join(lines), chat_id)


def handle_question(text: str, chat_id: str):
    """Gemini answers any financial question."""
    import notifier
    send("🤖 Thinking...", chat_id)
    try:
        answer = notifier.get_gemini_question_answer(text)
        send(f"🤖 {answer}", chat_id)
    except Exception as e:
        send(f"Error: {e}", chat_id)


def handle_help(chat_id: str):
    send(
        "🤖  Aarya StockSense Bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊  STOCK ANALYSIS\n"
        "Just type any ticker:\n"
        "  AAPL  →  Apple full analysis\n"
        "  RELIANCE  →  Reliance Industries\n"
        "  TSLA  →  Tesla\n"
        "  HDFC  →  HDFC Bank\n\n"
        "⚡  COMMANDS\n"
        "  /picks  →  Today's top 3 buy setups\n"
        "  /penny  →  Penny stocks spiking >29%\n"
        "  /help   →  Show this menu\n\n"
        "💬  ASK ANYTHING\n"
        "  'Is NVDA a good buy now?'\n"
        "  'Best SIP funds for 5000/month'\n"
        "  'How does SWP work?'\n"
        "  'Compare HDFC vs ICICI Bank'\n"
        "  'What is Minervini score?'\n\n"
        "Results include:\n"
        "✅ Same analysis as the website\n"
        "✅ Gemini AI verification & explanation\n"
        "✅ WHY it's good + WHY it's risky\n"
        "✅ Final verdict\n\n"
        "⚠️  Not financial advice.",
        chat_id,
    )


# ── Message router ────────────────────────────────────────────────────

def process_message(text: str, chat_id: str):
    text  = text.strip()
    lower = text.lower()

    if text.startswith("/start") or text.startswith("/help"):
        handle_help(chat_id)

    elif text.startswith("/picks"):
        handle_picks(chat_id)

    elif text.startswith("/penny"):
        handle_penny(chat_id)

    elif text.startswith("/check"):
        # /check AAPL
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            ticker = parts[1].strip().upper()
            mc, _  = _get_market(ticker)
            analyze_stock(ticker, chat_id, mc)
        else:
            send("Usage: /check TICKER  (e.g. /check AAPL)", chat_id)

    else:
        # Is it a ticker? (short word, or all caps, or starts with known pattern)
        ticker = _extract_ticker(text)

        # Only treat as ticker if the message is short (≤3 words) or clearly a check request
        words       = text.split()
        looks_like_ticker_query = (
            len(words) <= 3
            or any(kw in lower for kw in ("check", "analyse", "analyze", "analysis",
                                           "signal", "buy", "sell", "what about",
                                           "how is", "should i"))
        )

        if ticker and looks_like_ticker_query:
            mc, _ = _get_market(text.upper())
            analyze_stock(ticker, chat_id, mc)
        else:
            # General financial question → Gemini
            handle_question(text, chat_id)


# ── Main loop ─────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        log.error("TELEGRAM_TOKEN not set. Exiting.")
        sys.exit(1)

    log.info("Aarya StockSense Telegram Bot started.")
    send(
        "🟢  Aarya StockSense Bot is online!\n\n"
        "Type any stock ticker for full analysis with AI verification.\n"
        "Send /help to see all commands."
    )

    while True:
        updates = get_updates()
        for update in updates:
            try:
                msg  = update.get("message", {})
                text = msg.get("text", "").strip()
                cid  = str(msg.get("chat", {}).get("id", ""))
                if text and cid:
                    log.info(f"[{cid}] {text[:60]}")
                    process_message(text, cid)
            except Exception as e:
                log.error(f"Message handling error: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()
