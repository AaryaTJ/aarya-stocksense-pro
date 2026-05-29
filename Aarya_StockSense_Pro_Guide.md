# Aarya StockSense Pro — User Manual

---

## What Is It?

**Aarya StockSense Pro** is a personal stock analysis and alert platform for active traders and long-term investors. It runs as a secure web application — no installation required. It fetches live market data, runs a multi-layer technical analysis engine, gives clear actionable signals, and sends automatic alerts to your email and Telegram.

It is not connected to any broker. It is purely an **analysis and decision-support tool**. No trades are placed automatically.

> ⚠️ All signals and analysis are for educational and informational purposes only. Not financial advice.

---

## Getting Started

### Accessing the App

Open your browser and go to:
**https://aarya-stocksense.streamlit.app**

Access is by invitation only. Contact the admin to request an account.

### Logging In

1. Enter your email address and password
2. Click **Login**

Your settings, watchlists, and portfolio are saved to your account — accessible from any device.

### Logging Out

Click your email address in the left sidebar → **Logout**

---

## Setting Up Telegram Alerts (Recommended — Do This First)

Telegram is the fastest way to receive stock alerts. Once set up, buy signals, penny spikes, and sell alerts arrive on your phone automatically — no action needed on your part.

### Step 1 — Get Your Telegram Chat ID

1. Open Telegram on your phone
2. Search for **@userinfobot** and tap it
3. Send `/start`
4. It instantly replies with your **Chat ID** — a number like `987654321`
5. Copy that number

### Step 2 — Save It on the Website

1. Log in to the website
2. Go to **Settings** tab → **Alert Settings**
3. Scroll down to **📱 Telegram Notifications**
4. Paste your Chat ID in the box
5. Click **Save**
6. You will see: ✅ Telegram alerts active

### Step 3 — Start the Bot

1. Open Telegram
2. Search for the bot username (ask your admin for the exact username)
3. Tap it → Send `/start`

### Step 4 — Test It

Back on the website, under **📱 Telegram Notifications**, click **Test Telegram**.
You should receive a confirmation message on your phone within seconds.

That's it. You will now automatically receive:
- 📈 Daily top buy picks
- ⚡ Penny spike alerts
- 🚨 Sell / stop-out alerts for your portfolio positions

### Using the Bot Interactively

You can also message the bot directly to ask about any stock:

| What you type | What happens |
|---|---|
| `AAPL` | Full analysis: signal, price, entry, stop, targets, AI verdict |
| `TSLA` | Same for Tesla |
| `RELIANCE` | Indian stock analysis |
| `/picks` | Top 3 buy setups right now across US + India |
| `/help` | Shows all commands |
| Any question | e.g. "Is NVDA a good buy?" → Gemini AI answers |

> **Note:** The bot checks for new messages every 1–2 hours (GitHub Actions schedule). Replies are not instant but arrive within that window.

---

## Setting Up Email Alerts

Email alerts are sent automatically by the system 6 times per day on market days. No setup is needed on your part — alerts go to the email address registered in your account.

To verify or change the alert email:
1. Go to **Settings** → **Alert Settings** → **📬 Alert Recipients**
2. Your registered email should appear there
3. To add another email, type it in the box and click **➕ Add**

**When are alerts sent?**

| Time (IST) | Reason |
|---|---|
| 9:00 AM | Indian market open |
| 11:00 AM | Mid-morning scan |
| 1:00 PM | Post-lunch scan |
| 3:00 PM | Near India close |
| 7:00 PM | US market open |
| 11:00 PM | US mid-session |

Alerts are only sent when there is something to report. If there are no strong buy setups that run, no email is sent — this is normal.

---

## The 6 Tabs

---

### Tab 1 — 📈 Today's Picks

The core of the app. Scans your entire watchlist and assigns one of four signals to every stock.

**Signal Categories:**

| Signal | Meaning |
|---|---|
| 🟢 BUY TODAY | Strong setup — all key conditions met. Enter now. |
| 🟦 PREPARE TO BUY | Good setup but waiting for volume or sweep trigger. Set alert. |
| 🟡 WATCH | Partial setup. Not ready yet. Check again in 3–5 days. |
| 🔴 DO NOT BUY | Weak technicals. Avoid. |

**What Each Signal Card Shows:**
- Signal badge + Minervini score (out of 8) + RS score + Win probability %
- Plain-English verdict explaining exactly why the signal was given
- Entry price, Stop loss, T1 (+1.5R), T2 (+3R), T3 (+5R) targets
- Recommended hold time
- All 8 Minervini criteria shown as ✅ / ❌
- Expandable full breakdown: Fundamentals, News sentiment, Candlestick chart

**Market Regime Banner:**
- Shows BULL or BEAR based on benchmark vs 200 SMA
- In BEAR regime, signals are hidden by default with an override toggle

**Sector Strength (US only):**
- Shows 8 sector ETFs scored on momentum and relative strength
- Labels each as Leading or Lagging

**Auto-refresh:** Off / 1 min / 5 min / 10 min / 15 min

---

### Tab 2 — 🤖 AI Copilot

7 analyst personas, each with a different investment style:

| Persona | Focus |
|---|---|
| 💼 Hedge Fund | Institutional sector flow — which sectors are being accumulated |
| 💎 Value Analyst | Undervalued stocks with P/E < 25, PEG < 1.5, positive revenue growth |
| 🎯 Swing Trader | Live 2:1+ risk-reward setups |
| 📊 Earnings Scanner | Binary event plays — earnings dates, options strategy |
| 📈 Wealth Compounder | Best ETFs ranked by expense ratio and 10Y CAGR |
| 🗓️ Weekly Screener | DCA/SIP signals — weekly close above 10 EMA |
| 🌐 Global Builder | Cross-market themes firing across US + India + Crypto |

**Aarya Executive Summary** at the bottom consolidates all personas into a single recommended action list.

---

### Tab 3 — 📊 Mutual Funds & ETF Planner

**Fund Catalogue:**
- 15 pre-loaded funds across US, India, and Global markets
- Filter by region, search by name or symbol
- Load any fund into the Compounding Simulator in one click

**Compounding Simulator:**
- Inputs: Lump sum, Monthly SIP/DCA, CAGR %, Inflation %
- Simulates 30 years month-by-month
- Shows milestone table at years 5, 10, 15, 20, 25, 30
- Chart shows: Nominal growth vs Real value vs Cash invested

---

### Tab 4 — 🔍 Stock Checker

Deep analysis on any single stock, crypto, ETF, or index.

**Inputs:** Ticker symbol, Hold period (days), Investment amount

**Output — 6 Sections:**
1. **Trade Verdict** — Signal with plain-English explanation
2. **Profit Probability** — Win % based on 2 years of historical data + 7 live conditions, with Bull/Base/Bear price scenarios
3. **Company Profile** — Revenue growth, earnings growth, analyst rating, P/E, PEG, institutional holding %
4. **News & Sentiment** — Latest headlines, colour-coded 🟢 / ⚪ / 🔴
5. **Options Chain** — ATM call and put with IV, volume, open interest (US stocks only)
6. **Candlestick Chart** — 180 days with 200/150/50 SMA, 8 EMA, AVWAP, entry/stop/target lines

---

### Tab 5 — 💼 My Portfolio

Log and monitor your open positions in real time.

**Log a Position:** Ticker, Entry price, Number of shares, Stop loss

**Live Monitor — Each Position Shows:**
- Current live price + P&L in currency and %
- Stop loss status, T1 and T2 hit status, 8 EMA health

**Action Recommendations:**
| Action | Meaning |
|---|---|
| 🟢 HOLD | Everything healthy |
| 🚨 SELL — STOP OUT | Price hit your stop loss |
| 💰 SELL 50% — T1 HIT | Take half off, move stop to break-even |
| 🎯 SELL — T2 HIT | Take more profits |
| ⚠️ EXIT — EMA BROKEN | Short-term momentum broken |

Automatic sell alerts are sent via **email and Telegram** when any action is triggered.

---

### Tab 6 — ⚙️ Settings

Three sub-tabs:

**📋 Watchlist Editor**
- Add or remove tickers per market
- Suffix is added automatically (e.g. type `TCS` for India → saves as `TCS.NS`)

**🛠️ Risk Settings**
- Time Stop: days before auto-exit alert (1–30)
- Max Open Positions: 1–20
- Live display of 1R value

**📧 Alert Settings**
- Manage email recipients
- Save Gmail sender credentials (local deployment only)
- Save API keys (Alpha Vantage, Gemini)
- **📱 Telegram Notifications** — save your Chat ID for phone alerts
- Test buttons: Send Test Email / Test Telegram / Test Gemini

---

## Markets Supported

| Market | Benchmark | Currency | Example Tickers |
|---|---|---|---|
| 🇺🇸 US Stocks | SPY (S&P 500) | $ | NVDA, AAPL, TSLA |
| 🇮🇳 India NSE | ^NSEI (Nifty 50) | ₹ | RELIANCE.NS, TCS.NS |
| ₿ Crypto | BTC-USD | $ | BTC-USD, ETH-USD |
| 🇬🇧 UK | ^FTSE (FTSE 100) | £ | SHEL.L, AZN.L |
| 🇪🇺 Europe | ^STOXX50E | € | SAP.DE, SIE.DE |
| 🇨🇦 Canada | ^GSPTSE (TSX) | C$ | RY.TO, SHOP.TO |
| 🇯🇵 Japan | ^N225 (Nikkei) | ¥ | 7203.T, 9984.T |

---

## Ticker Formats

| Market | Format | Example |
|---|---|---|
| US Stocks | Plain symbol | NVDA, AAPL |
| India NSE | Symbol + .NS | RELIANCE.NS, TCS.NS |
| Crypto | Symbol + -USD | BTC-USD, ETH-USD |
| UK | Symbol + .L | SHEL.L, AZN.L |
| Europe | Symbol + .DE | SAP.DE |
| Canada | Symbol + .TO | SHOP.TO |
| Japan | Number + .T | 7203.T |

The Watchlist Editor adds the suffix automatically. The Stock Checker accepts any Yahoo Finance ticker.

---

## How the Analysis Engine Works

Every signal combines 6 independent technical checks:

### C1 — Market Regime
Is the benchmark index above its 200-day SMA? BULL = pass, BEAR = signals suppressed.

### C2 — Minervini 8-Criteria (most important)
Score out of 8. Pass = 5 or more. A stock cannot get BUY TODAY with fewer than 5.

| Criterion | Meaning |
|---|---|
| Price > 200 SMA | Long-term uptrend confirmed |
| Price > 150 SMA | Mid-term trend healthy |
| Price > 50 SMA | Short-term trend healthy |
| 150 SMA > 200 SMA | Moving averages properly stacked |
| 50 SMA > 150 SMA | Acceleration confirmed |
| 200 SMA trending up | Long-term trend improving |
| Within 25% of 52W high | Near strength, not broken |
| 30%+ above 52W low | Recovery confirmed |

### C3 — Liquidity Sweep
Did the stock dip below recent lows then recover above them on the same day? Indicates institutional accumulation.

### C4 — Volume Confirmation
Is today's volume ≥ 1.5× the 50-day average? Confirms institutional participation.

### C5 — 8 EMA Hold
Is price above the 8-day Exponential Moving Average? Short-term momentum check.

### C6 — Relative Strength
Is this stock outperforming its benchmark over 3 and 6 months? Leaders outperform; laggards lag.

### Signal Logic

```
BUY TODAY       = Minervini ≥5/8  AND  Above 8 EMA  AND  RS Outperforming  AND  (Volume OR Sweep)
PREPARE TO BUY  = Minervini ≥5/8  AND  Above 8 EMA  AND  RS Outperforming
WATCH           = Minervini ≥5/8  AND  Above 8 EMA   OR   3+ conditions met
DO NOT BUY      = Everything else
```

---

## Position Sizing Formula

```
1R Amount  = Portfolio Value × Risk% ÷ 100
Shares     = 1R Amount ÷ (Entry Price − Stop Loss)
Position   = Shares × Entry Price

Exit Plan:
  T1 = Entry + 1.5 × (Entry − Stop)  →  Sell 50%, move stop to break-even
  T2 = Entry + 3.0 × (Entry − Stop)  →  Sell 25%, trail stop
  T3 = Entry + 5.0 × (Entry − Stop)  →  Close remaining 25%
```

Example: Portfolio = ₹1,00,000 | Risk = 1% | Entry = ₹500 | Stop = ₹480
- 1R = ₹1,000
- Shares = 1,000 ÷ 20 = 50 shares
- Position = ₹25,000

---

## Admin Panel (Admin Users Only)

Accessible as an extra tab when logged in as an admin.

**Create User:**
- Enter email and temporary password → click Create User
- New user can log in immediately

**Manage Users:**
- View all registered users with their role, join date, last login
- Block / Unblock a user (blocked users cannot log in)
- Delete a user permanently

---

## Frequently Asked Questions

**Why did I not receive an email today?**
Alerts are only sent when the engine finds strong signals. If there are no BUY TODAY or PREPARE TO BUY stocks that session, no email is sent. This is correct behavior — no false alarms.

**Why is the bot reply taking so long?**
The bot processes messages during scheduled GitHub Actions runs (every 1–2 hours on weekdays). This is by design — the service is free.

**The bot replied with "No data for TICKER"**
Check the ticker symbol. For Indian stocks, type just the name (e.g. `RELIANCE`) — the bot tries both markets. For US stocks, use the plain symbol (`AAPL`, `NVDA`).

**Can I use the bot from a second phone?**
Yes. The second person should follow the same 3 steps: get their Chat ID from @userinfobot, save it in Settings on the website, and send /start to the bot. Each person's alerts are sent to their own phone independently.

**My settings are not saving**
Make sure you are logged in. Settings require an active login to save to the database.

**I see BEAR regime — should I still trade?**
In BEAR regime, signals are suppressed as a safety measure. You can override this in the regime banner if you want to see signals anyway, but reduce your position sizes significantly.

---

## Gemini AI — What It Does

The app uses **Google Gemini 2.5 Flash** as its AI layer. It powers three things:

**1. Telegram Bot Compact Verdict**
Every stock analysis sent via Telegram ends with a 3-line AI summary:
- ✅ One specific reason the setup is good
- ⚠️ One specific risk right now
- 📌 Direct verdict: act now / wait for entry / avoid

**2. Telegram Bot Q&A**
When you ask the bot a question (not a ticker), Gemini answers it:
- "Is NVDA a good buy right now?"
- "Best SIP for ₹5000/month?"
- "How does SWP work?"
- "Explain P/E ratio"

It answers as "Aarya", a financial advisor aware of both Indian and US markets.

**3. AI Copilot (Tab 2)**
Powers the deep analysis verdicts shown for each analyst persona.

> **For users:** No setup required. Gemini is configured at the system level — it works automatically for everyone.
>
> **For admin:** The Gemini API key (`GEMINI_KEY`) must be set in both Streamlit Cloud secrets and GitHub Actions secrets. Get a free key at [aistudio.google.com](https://aistudio.google.com).

---

## What the App Does NOT Do

- Does not place trades automatically
- Does not connect to any broker
- Does not provide personalised financial advice
- Options data available for US stocks only
- Sector strength dashboard for US market only

---

## Technology

| Component | Technology |
|---|---|
| Web App | Streamlit (Streamlit Cloud) |
| Database | Supabase (user accounts, settings, portfolio) |
| Market Data | Yahoo Finance via yfinance |
| Charts | Plotly (interactive candlesticks) |
| Analysis Engine | NumPy, Pandas |
| AI Verdicts | Google Gemini 2.5 Flash |
| Automated Alerts | GitHub Actions (6× per day, weekdays) |
| Email | Gmail SMTP |
| Telegram | Telegram Bot API |

---

*Aarya StockSense Pro — Built for personal use. All analysis is based on publicly available market data.*
