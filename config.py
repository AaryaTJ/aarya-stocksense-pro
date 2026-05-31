"""
Aarya StockSense Pro — config.py
Market configurations, focus modes, settings persistence.
All settings saved locally to aarya_settings.json.
"""

import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "aarya_settings.json")
_CONFIG_FILE  = os.path.join(os.path.dirname(__file__), "aarya_config.json")


def _is_cloud() -> bool:
    """True when running on Streamlit Cloud (no local aarya_config.json)."""
    return not os.path.exists(_CONFIG_FILE)

# ══════════════════════════════════════════════════════════════════════
#  MARKET CONFIGURATIONS
# ══════════════════════════════════════════════════════════════════════

MARKET_CONFIGS = {
    "🇺🇸 US Stocks": {
        "key":          "US",
        "benchmark":    "SPY",
        "currency":     "$",
        "suffix":       "",
        "min_volume":   500_000,
        "hours":        "09:30–16:00 ET",
        "has_sectors":  True,
        "is_crypto":    False,
        "sector_etfs": {
            "XLK":  "Technology",
            "SOXX": "Semiconductors",
            "XLF":  "Financials",
            "XLE":  "Energy",
            "XLV":  "Healthcare",
            "XLY":  "Consumer Discret.",
            "XLI":  "Industrials",
            "XLC":  "Communication",
        },
        "blue_chips": [
            "AAPL","MSFT","GOOGL","AMZN","META","NVDA","JPM","V",
            "MA","UNH","HD","PG","JNJ","BRK-B","KO","PEP","WMT","MCD",
        ],
        "growth": [
            "NVDA","TSLA","PLTR","CRWD","MSTR","SMCI","AXON","CELH",
            "ENPH","DKNG","AFRM","IONQ","RKLB","ARM","AVGO","AMD",
        ],
        "default": ["NVDA","MSFT","AAPL","GOOGL","AMZN","META","TSLA","PLTR"],
        "penny_extras": [
            # AI / tech small-caps (typically $2–$9)
            "SOUN","BBAI","KULR","ARQT","TDUP","AEYE",
            # Space / mobility
            "JOBY","ACHR","LUNR","RDW","SPCE","RCAT",
            # EV & clean energy
            "CHPT","BLNK","EVGO","PLUG","CLNE","NKLA",
            # Crypto miners (highly variable — scanner will filter by price)
            "BITF","CIFR","HIVE","BTBT","HUT","RIOT",
            # LiDAR / autonomy
            "LAZR","MVIS","OUST","AEVA",
            # Fintech / consumer
            "OPEN","GRAB","CLOV","ATAI",
            # Uranium / metals
            "DNN","UEC","NXE","VALE",
            # Biotech micro-caps
            "IBRX","IMVT","NUVL","PRAX",
            # Other active small-caps
            "DM","WKHS","MMAT","GNUS","EXPR",
        ],
    },

    "🇮🇳 India NSE": {
        "key":         "IN",
        "benchmark":   "^NSEI",
        "currency":    "₹",
        "suffix":      ".NS",
        "min_volume":  100_000,
        "hours":       "09:15–15:30 IST",
        "has_sectors": False,
        "is_crypto":   False,
        "blue_chips": [
            "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
            "HINDUNILVR.NS","BAJFINANCE.NS","SBIN.NS","LT.NS","ITC.NS",
            "WIPRO.NS","ASIANPAINT.NS","TITAN.NS","MARUTI.NS","ULTRACEMCO.NS",
        ],
        "growth": [
            "POLYCAB.NS","ETERNAL.NS","RVNL.NS","IRFC.NS","NHPC.NS",
            "TATAPOWER.NS","M&M.NS","ADANIGREEN.NS","SUZLON.NS","IREDA.NS",
        ],
        "default": [
            "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS",
            "ICICIBANK.NS","BAJFINANCE.NS","M&M.NS","WIPRO.NS",
        ],
        "penny_extras": [
            # PSU banks & NBFCs (₹20–₹200)
            "YESBANK.NS","IDEA.NS","IDFCFIRSTB.NS","PNB.NS","BANKBARODA.NS",
            "CANBK.NS","UNIONBANK.NS","IOB.NS","MAHABANK.NS","UCOBANK.NS",
            # Power & infra (₹50–₹280)
            "TATAPOWER.NS","NHPC.NS","IRFC.NS","RVNL.NS","IREDA.NS",
            # Other active small-caps under ₹300
            "SUZLON.NS","SAIL.NS","GPIL.NS","NMDC.NS","COALINDIA.NS",
            "HUDCO.NS","RECLTD.NS","SJVN.NS","BPCL.NS","NALCO.NS",
            "RCOM.NS","JPASSOCIAT.NS","HFCL.NS","GTPL.NS","OPTIEMUS.NS",
        ],
    },

    "₿ Crypto": {
        "key":         "CRYPTO",
        "benchmark":   "BTC-USD",
        "currency":    "$",
        "suffix":      "-USD",
        "min_volume":  0,
        "hours":       "24/7",
        "has_sectors": False,
        "is_crypto":   True,
        "blue_chips": [
            "BTC-USD","ETH-USD","BNB-USD","XRP-USD","SOL-USD","ADA-USD",
        ],
        "growth": [
            "AVAX-USD","DOGE-USD","DOT-USD","LINK-USD","LTC-USD",
            "MATIC-USD","ATOM-USD","NEAR-USD","UNI-USD","ALGO-USD",
        ],
        "default": ["BTC-USD","ETH-USD","SOL-USD","XRP-USD","BNB-USD","AVAX-USD"],
    },

    "🇬🇧 UK": {
        "key":         "UK",
        "benchmark":   "^FTSE",
        "currency":    "£",
        "suffix":      ".L",
        "min_volume":  50_000,
        "hours":       "08:00–16:30 GMT",
        "has_sectors": False,
        "is_crypto":   False,
        "blue_chips":  ["SHEL.L","AZN.L","HSBA.L","ULVR.L","BP.L","GSK.L","RIO.L","LLOY.L"],
        "growth":      ["AUTO.L","EXPN.L","OCDO.L","WEIR.L","BARC.L"],
        "default":     ["SHEL.L","AZN.L","HSBA.L","BP.L","GSK.L"],
    },

    "🇪🇺 Europe": {
        "key":         "EU",
        "benchmark":   "^STOXX50E",
        "currency":    "€",
        "suffix":      ".DE",
        "min_volume":  10_000,
        "hours":       "09:00–17:30 CET",
        "has_sectors": False,
        "is_crypto":   False,
        "blue_chips":  ["SAP.DE","SIE.DE","ALV.DE","BAYN.DE","BMW.DE","VOW3.DE","DBK.DE"],
        "growth":      ["SAP.DE","SIE.DE","BAYN.DE","BMW.DE"],
        "default":     ["SAP.DE","SIE.DE","ALV.DE","BMW.DE","BAYN.DE"],
    },

    "🇨🇦 Canada": {
        "key":         "CA",
        "benchmark":   "^GSPTSE",
        "currency":    "C$",
        "suffix":      ".TO",
        "min_volume":  50_000,
        "hours":       "09:30–16:00 ET",
        "has_sectors": False,
        "is_crypto":   False,
        "blue_chips":  ["RY.TO","TD.TO","BNS.TO","BMO.TO","CNR.TO","ENB.TO","SU.TO"],
        "growth":      ["SHOP.TO","CSU.TO","TFII.TO","ATD.TO","WCN.TO"],
        "default":     ["RY.TO","TD.TO","SHOP.TO","ENB.TO","CNR.TO"],
    },

    "🇯🇵 Japan": {
        "key":         "JP",
        "benchmark":   "^N225",
        "currency":    "¥",
        "suffix":      ".T",
        "min_volume":  10_000,
        "hours":       "09:00–15:30 JST",
        "has_sectors": False,
        "is_crypto":   False,
        "blue_chips":  ["7203.T","9432.T","6758.T","9984.T","8306.T","7267.T","4502.T"],
        "growth":      ["9984.T","6758.T","6861.T","8035.T","4523.T"],
        "default":     ["7203.T","9984.T","6758.T","4502.T","8306.T"],
    },
}

# ── FOCUS MODES ────────────────────────────────────────────────────────
FOCUS_MODES = {
    "🏛️ Blue-Chips":           "blue_chips",
    "🚀 High-Growth Leaders":  "growth",
    "📋 My Custom List":        "custom",
}

# ── FUND CATALOGUE ─────────────────────────────────────────────────────
# (symbol, name, type, expense_ratio%, est_10y_cagr%, region)
FUND_CATALOGUE = [
    ("SPY",            "SPDR S&P 500 ETF",         "Large-Cap Index",  0.09, 13.2, "US"),
    ("QQQ",            "Invesco NASDAQ-100",         "Tech Index",       0.20, 18.5, "US"),
    ("VOO",            "Vanguard S&P 500",           "Large-Cap Index",  0.03, 13.2, "US"),
    ("VTI",            "Vanguard Total Market",      "Total Market",     0.03, 12.8, "US"),
    ("VGT",            "Vanguard IT Sector",         "Technology",       0.10, 20.1, "US"),
    ("SCHD",           "Schwab Dividend ETF",        "Dividend Growth",  0.06, 11.4, "US"),
    ("ARKK",           "ARK Innovation ETF",         "Disruptive Tech",  0.75,  8.4, "US"),
    ("IWM",            "iShares Russell 2000",       "Small-Cap Index",  0.19, 10.1, "US"),
    ("0P0000XVKY.BO",  "Parag Parikh Flexi Cap",    "Flexi-Cap",        0.88, 20.5, "India"),
    ("0P00007T6S.BO",  "Mirae Asset ELSS",          "ELSS Tax Saver",   1.15, 19.1, "India"),
    ("0P0000XVKY.BO",  "Nippon India Growth",       "Mid-Cap Growth",   1.20, 18.3, "India"),
    ("0P0000XVKZ.BO",  "SBI Blue Chip",             "Large-Cap",        1.10, 14.2, "India"),
    ("VEA",            "Vanguard Dev Markets",       "International",    0.05,  8.2, "Global"),
    ("VWO",            "Vanguard Emerging Mkts",    "Emerging Markets",  0.08,  7.4, "Global"),
    ("GLD",            "SPDR Gold ETF",              "Commodity",        0.40,  7.8, "Global"),
]

# ── DEFAULT SETTINGS ───────────────────────────────────────────────────
DEFAULTS = {
    "market":       "🇺🇸 US Stocks",
    "focus":        "🚀 High-Growth Leaders",
    "portfolio":    10000.0,
    "risk_pct":     1.0,
    "time_stop":    5,
    "refresh":      300,
    "positions":    [],
    "watchlists":   {},
}


# ── HELPERS ────────────────────────────────────────────────────────────
def load_settings() -> dict:
    if not _is_cloud() and os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                return {**DEFAULTS, **json.load(f)}
        except Exception:
            pass
    if _is_cloud():
        try:
            from supabase_client import load_settings_cloud
            data = load_settings_cloud()
            if data:
                return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(cfg: dict) -> None:
    if not _is_cloud():
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
            return
        except Exception:
            pass
    try:
        from supabase_client import save_settings_cloud
        save_settings_cloud(cfg)
    except Exception:
        pass


def get_watchlist(cfg: dict, market: str) -> list:
    mc    = MARKET_CONFIGS[market]
    focus = cfg.get("focus", "🚀 High-Growth Leaders")
    # Custom list stored per market
    if focus == "📋 My Custom List":
        custom = cfg.get("watchlists", {}).get(market, [])
        return custom if custom else mc["default"]
    key = FOCUS_MODES.get(focus, "growth")
    return mc.get(key, mc["default"])


def save_custom_watchlist(cfg: dict, market: str, tickers: list) -> dict:
    if "watchlists" not in cfg:
        cfg["watchlists"] = {}
    cfg["watchlists"][market] = tickers
    save_settings(cfg)
    return cfg
