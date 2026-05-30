# Aarya StockSense Pro — Full Restoration Guide

Use this document if the machine is lost, the account changes, or the site needs to be rebuilt from scratch.  
Everything needed to go from zero to fully running is documented here.

---

## What Runs Where

| Component | Platform | What It Does |
|---|---|---|
| Web App | Streamlit Cloud | The main website users log into |
| Database | Supabase | User accounts, settings, portfolio, bot offset |
| Automated Alerts | GitHub Actions | Scans stocks 6×/day, sends email + Telegram |
| Telegram Bot | GitHub Actions | Processes messages from users on Telegram |
| Code Repository | GitHub | Source of truth for all code |

---

## Step 1 — GitHub Repository

Repository: **https://github.com/AaryaTJ/aarya-stocksense-pro**

If rebuilding on a new machine:
```
git clone https://github.com/AaryaTJ/aarya-stocksense-pro.git
cd aarya-stocksense-pro
```

All code, workflows, and the guide are stored here. Push changes here to redeploy the site automatically.

---

## Step 2 — Supabase (Database)

### Project
Create a new project at **https://supabase.com**. Note down:
- **Project URL** — looks like `https://xxxx.supabase.co`
- **Anon public key** — starts with `eyJ...`
- **Service role key** — starts with `eyJ...` (keep secret — full admin access)

### Tables to Create
Run these SQL statements in **Supabase → SQL Editor**:

```sql
-- User profiles (role, block status, last login)
CREATE TABLE public.user_profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role text DEFAULT 'user',
  is_blocked boolean DEFAULT false,
  last_login timestamptz
);
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own profile"
  ON public.user_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Service role full access"
  ON public.user_profiles USING (true) WITH CHECK (true);

-- Per-user settings (watchlists, portfolio, risk settings, telegram chat id)
CREATE TABLE public.user_settings (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  data jsonb DEFAULT '{}'
);
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own settings"
  ON public.user_settings USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Service role full access"
  ON public.user_settings USING (true) WITH CHECK (true);

-- Global settings (Telegram bot offset, etc.)
CREATE TABLE public.settings (
  id text PRIMARY KEY,
  data jsonb DEFAULT '{}'
);
ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access"
  ON public.settings USING (true) WITH CHECK (true);

-- Prediction tracking for the ML feedback loop (every logged pick)
CREATE TABLE public.predictions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz DEFAULT now(),
  pred_date date NOT NULL,
  ticker text NOT NULL,
  market text,
  signal text,
  price numeric, entry numeric, stop numeric,
  t1 numeric, t2 numeric, t3 numeric,
  win_prob numeric, minervini int, rs_score numeric, rsi numeric,
  confidence numeric,
  horizon_days int DEFAULT 10,
  features jsonb DEFAULT '{}',
  status text DEFAULT 'open',          -- open | evaluated
  outcome_pct numeric, hit boolean, evaluated_at timestamptz,
  UNIQUE (ticker, pred_date)
);
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access"
  ON public.predictions USING (true) WITH CHECK (true);

-- Notification de-duplication (don't send the same alert twice/day)
CREATE TABLE public.sent_notifications (
  dedup_key text PRIMARY KEY,
  kind text, ticker text,
  sent_date date DEFAULT current_date,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE public.sent_notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access"
  ON public.sent_notifications USING (true) WITH CHECK (true);

-- ML model state (ensemble weights + rolling accuracy) — used from Phase 3
CREATE TABLE public.model_state (
  id text PRIMARY KEY DEFAULT 'main',
  weights jsonb DEFAULT '{}',
  rolling_acc jsonb DEFAULT '{}',
  locked boolean DEFAULT false,
  updated_at timestamptz DEFAULT now()
);
ALTER TABLE public.model_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access"
  ON public.model_state USING (true) WITH CHECK (true);

-- Gemini response cache (Phase 5 — protects the 250-requests/day free quota)
CREATE TABLE public.gemini_cache (
  key text PRIMARY KEY,
  response text,
  kind text,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE public.gemini_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access"
  ON public.gemini_cache USING (true) WITH CHECK (true);
```

### Authentication Settings (Supabase → Authentication → Settings)
- **Disable email confirmations** — so admin-created users can log in immediately
- **Site URL** — set to your Streamlit app URL (e.g. `https://aarya-stocksense.streamlit.app`)

### Create the First Admin User
In Supabase → Authentication → Users → **Add User** → enter email + password.

Then in SQL Editor run:
```sql
INSERT INTO public.user_profiles (id, role)
VALUES ('<paste-user-uuid-here>', 'admin');
```

---

## Step 3 — API Keys Needed

Collect all of these before setting up secrets:

| Key | Where to Get | Used For |
|---|---|---|
| Supabase URL | Supabase → Settings → API | Database connection |
| Supabase Anon Key | Supabase → Settings → API | App database access |
| Supabase Service Key | Supabase → Settings → API | Admin user management |
| Gemini API Key | https://aistudio.google.com | AI verdicts and Q&A |
| Alpha Vantage Key | https://www.alphavantage.co | News sentiment (optional) |
| Gmail Address | Your Gmail account | Sending alert emails |
| Gmail App Password | Gmail → Security → 2FA → App Passwords | Email authentication |
| Alert Recipient Email(s) | Your email(s) | Where alerts are sent |
| Telegram Bot Token | @BotFather on Telegram → /newbot | Telegram alerts + bot |

### Creating a Telegram Bot (if starting fresh)
1. Open Telegram → message **@BotFather**
2. Send `/newbot`
3. Enter a name (e.g. `Aarya StockSense`)
4. Enter a username ending in `bot` (e.g. `AaryaStocksAlertBot`)
5. Copy the token it gives you

---

## Step 4 — Streamlit Cloud Deployment

1. Go to **https://share.streamlit.io**
2. Sign in with GitHub
3. Click **New app**
4. Select repository: `AaryaTJ/aarya-stocksense-pro`
5. Branch: `main`
6. Main file: `app.py`
7. Click **Deploy**

### Streamlit Secrets
After deploying, go to **Manage app → Settings → Secrets** and paste:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJ..."           # anon key
SUPABASE_SERVICE_KEY = "eyJ..."   # service role key

TELEGRAM_TOKEN = "1234567890:ABC..."

GEMINI_KEY = "AIzaSy..."

ALPHA_VANTAGE_KEY = "your_key"

EMAIL_SENDER = "yourname@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"    # Gmail app password (16 chars)
EMAIL_RECIPIENTS = "alert1@gmail.com,alert2@gmail.com"
```

Click **Save** — the app restarts automatically.

---

## Step 5 — GitHub Actions Secrets

Go to: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

Add each of these:

| Secret Name | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | Supabase **service role** key — required for per-user sell alerts + prediction logging |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your personal Telegram Chat ID (fallback) |
| `TWELVE_DATA_KEY` | Twelve Data API key (RSI for US stocks) |
| `GEMINI_KEY` | Gemini API key |
| `ALPHA_VANTAGE_KEY` | Alpha Vantage key |
| `EMAIL_SENDER` | Gmail address used to send alerts |
| `EMAIL_PASSWORD` | Gmail app password |
| `EMAIL_RECIPIENTS` | Comma-separated alert recipient emails |

> **Important:** `SUPABASE_SERVICE_KEY` (Supabase → Settings → API → `service_role` key) is
> what lets the background scanner read every user's saved positions and send each person
> sell alerts on their own email + Telegram, and write prediction rows. Without it, automated
> per-user sell alerts and ML logging are skipped (the app still works).

### Getting Your Telegram Chat ID
1. Open Telegram → message **@userinfobot** → send `/start`
2. It replies with your Chat ID number
3. Use that as `TELEGRAM_CHAT_ID`

### Updating Secrets Programmatically (optional, faster)
Requires Python 3.10+ with `requests` and `PyNaCl` installed.
Requires a GitHub Personal Access Token (PAT) with `repo` scope from:
**GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**

```python
import requests, base64
from nacl import encoding, public

GH_TOKEN = "ghp_your_token_here"
REPO     = "AaryaTJ/aarya-stocksense-pro"
HEADERS  = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}

pk_resp = requests.get(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=HEADERS)
pk_data = pk_resp.json()
key_id  = pk_data["key_id"]
pub_key = public.PublicKey(pk_data["key"].encode(), encoding.Base64Encoder)

def set_secret(name, value):
    box = public.SealedBox(pub_key)
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{name}",
        headers=HEADERS,
        json={"encrypted_value": enc, "key_id": key_id}
    )
    print(f"{name}: {'OK' if r.status_code in (201,204) else r.text}")

set_secret("TELEGRAM_TOKEN", "your_token_here")
set_secret("GEMINI_KEY", "your_key_here")
# ... repeat for each secret
```

---

## Step 6 — Verify Everything Works

### Test the website
1. Open the Streamlit app URL
2. Log in with admin credentials
3. Go to Settings → Alert Settings → click **Test Telegram** — phone should receive a message
4. Click **Send Test Email** — inbox should receive an email

### Test GitHub Actions
1. Go to GitHub repo → **Actions** tab
2. Click **Aarya Background Monitor** workflow
3. Click **Run workflow** → **Run workflow** (manual trigger)
4. Watch the logs — should complete in ~5 minutes with no errors

### Set Up Telegram for Each User
Each user on the website does:
1. Message **@userinfobot** on Telegram → copy their Chat ID
2. Website → Settings → Alert Settings → 📱 Telegram Notifications → paste ID → Save
3. Message the bot on Telegram → send `/start`

---

## Step 7 — GitHub Actions Schedule

The workflow runs automatically at these times (weekdays only):

| UTC Time | IST Time | Reason |
|---|---|---|
| 03:30 | 09:00 AM | India market open |
| 05:30 | 11:00 AM | Mid-morning |
| 07:30 | 1:00 PM | Post-lunch |
| 09:30 | 3:00 PM | Near India close |
| 13:30 | 7:00 PM | US market open |
| 17:30 | 11:00 PM | US mid-session |

Each run: scans stocks → sends email + Telegram alerts → processes Telegram bot messages.

---

## Accounts Summary

Keep these credentials in a secure password manager:

| Account | Used For |
|---|---|
| GitHub account (AaryaTJ) | Code repository, GitHub Actions |
| Supabase account | Database |
| Streamlit account | Web app hosting |
| Google account (Gemini) | AI API |
| Gmail account (sender) | Sending alert emails |
| Alpha Vantage account | News sentiment API |
| Telegram account | Bot creation via @BotFather |

---

## Files in This Repository

| File | Purpose |
|---|---|
| `app.py` | Main web app — all tabs and UI |
| `engine.py` | Stock analysis engine — all signals and indicators |
| `db.py` | Database operations (Supabase) |
| `notifier.py` | Email and Telegram alert functions |
| `monitor.py` | Background scanner — runs via GitHub Actions |
| `bot_poll.py` | Telegram bot — runs via GitHub Actions |
| `mldb.py` | Supabase store for predictions, notification dedup, ML model state |
| `applog.py` | Shared rotating-file logger (logs/app.log) |
| `config.py` | Market configs, defaults |
| `auth.py` | Login / authentication |
| `supabase_client.py` | Supabase connection |
| `.github/workflows/monitor.yml` | GitHub Actions schedule and steps |
| `requirements.txt` | Python dependencies for Streamlit app |
| `requirements_bot.txt` | Python dependencies for GitHub Actions |
| `Aarya_StockSense_Pro_Guide.md` | User manual |
| `SETUP.md` | This file — full restoration guide |

---

*Keep this file and the User Manual updated whenever major changes are made to the system.*
