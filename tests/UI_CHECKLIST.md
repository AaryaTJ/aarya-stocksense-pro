# Aarya StockSense Pro — Manual UI Checklist

Streamlit button clicks can't be exercised by `smoke_test.py` head-lessly. This
list is what to walk through after every meaningful deploy. Tick each item.

---

## Authentication

- [ ] Open the app URL in a private/incognito window → login screen appears.
- [ ] Log in with wrong password → red "Incorrect email or password." shown.
- [ ] Log in with correct password + **Remember me** checked → land on Today's Picks.
- [ ] Close the tab, reopen the same browser, go back to the app URL → still logged in (no login screen).
- [ ] Sidebar → click your email → click **🚪 Logout** → returns to login screen.
- [ ] Log in with **Remember me unchecked** → close + reopen browser → asked to log in again.

## Sidebar

- [ ] Market selector changes regime badge + market-hours badge (🟢 Open / 🔴 Closed).
- [ ] Position-sizing inputs update the "Each 1R = …" card in real-time.
- [ ] Auto-refresh slider at 1m / 5m actually refreshes the page after that interval.

## Tab 1 — Today's Picks

- [ ] Regime banner shows BULL or BEAR + VIX badge.
- [ ] At least one of: BUY TODAY / PREPARE TO BUY / WATCH / DO NOT BUY sections rendered.
- [ ] **🔻 Contrarian / Oversold-Quality Picks** section appears at the bottom — either with cards or "No contrarian setups in this market right now."
- [ ] **🤖 Ask Aarya about today's picks** expander opens; typing a question + clicking Ask returns an answer (cached on repeat).
- [ ] If a penny spike exists, the orange "⚡ PENNY STOCK SPIKE ALERT" banner appears at the top.
- [ ] "📧 Email Buy Signals" button at the bottom triggers a confirmation toast.

## Tab 2 — AI Copilot

- [ ] All 7 persona cards render without error.
- [ ] "Aarya Executive Summary" at the bottom renders a synthesis paragraph.

## Tab 3 — Funds & ETF Planner

- [ ] Fund catalogue table renders ≥ 15 rows.
- [ ] "📥 Load into Simulator" populates the simulator inputs.
- [ ] Compounding simulator chart shows three lines (nominal / real / invested).

## Tab 4 — Stock Checker

- [ ] Type `AAPL` + click "🔍 Analyse Now" → all 6 sections render.
- [ ] "✨ Generate AI Briefing" returns a 3-sentence briefing. **Same click again** returns instantly (cache hit).
- [ ] "Ask" question box returns a Gemini answer.

## Tab 5 — Portfolio

- [ ] "➕ Log New Position" form accepts a position and shows it in the list.
- [ ] Each position card shows live Current / P&L / Stop / EMA / T1 / T2.
- [ ] "🗑️ Close" removes the position after a rerun.
- [ ] On the same position with current > entry by ≥ 1R: the next monitor cron should emit a **💰 Trail Stop** email + Telegram (verify in your inbox + phone next session).

## Tab 6 — Settings

- [ ] Watchlist Editor — add `MSFT` for US → appears in the chip list → 🗑️ removes it.
- [ ] Risk Settings — Time Stop + Max Positions persist after Save Risk Settings.
- [ ] Alert Settings — type a recipient email + ➕ Add → appears → 🗑️ removes it.
- [ ] Save Gmail Settings → success toast.
- [ ] Save Alpha Vantage Key / Save Gemini Key → success toasts.
- [ ] 📱 Telegram Chat ID — paste your numeric ID + Save → "✅ Telegram alerts active".
- [ ] Test buttons:
  - [ ] 📧 Send Test Email → inbox receives a test email within ~10s.
  - [ ] 📱 Test Telegram → phone receives a test message within ~5s, properly bold-formatted (no `\` backslashes).
  - [ ] 🤖 Test Gemini → returns a short factual sentence.

## Tab 7 — Admin (admins only)

- [ ] **ML status banner** at the top shows one of: 🧊 COLD START / ⚪ SHADOW / ✅ LIVE.
- [ ] Rolling hit-rate row appears once ≥ 7 days of evaluated predictions exist.
- [ ] **🔒 Lock model / 🔓 Unlock model** button toggles the locked flag.
- [ ] **📊 Run backtest now** runs in 1–2 minutes and prints PASS/FAIL + metrics.
- [ ] **➕ Add New User** with a fresh email + 8+ char password → success.
- [ ] **Block / Unblock / Delete** buttons on a non-admin row work as expected.

## Error states

- [ ] Disconnect the internet → reload picks tab → no crash, you see a "Screener error" warning instead of a traceback.
- [ ] Type an unknown ticker in Stock Checker → "No data" message, no crash.
- [ ] Stop the Streamlit server, restart, log back in → state preserved (settings + portfolio).

## End-to-end email + Telegram sanity (next monitor cron)

- [ ] After the next 9 AM IST cron, you receive the morning digest email **and** Telegram message.
- [ ] After the next 3 PM IST cron, you receive the afternoon digest.
- [ ] If a logged position triggers a sell/stop action, you receive both an email *and* Telegram alert routed to YOUR address (not just the global recipients) — confirms Phase 2 per-user routing.
- [ ] Sunday 5:30 PM IST: you receive the **📊 Weekly Performance** report.

---

When everything above is ticked, the system is verified.
