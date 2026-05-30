"""
tests/functional_walkthrough.py
Exercises every tab's underlying code path against every market WITHOUT
needing Streamlit's UI. Catches latent bugs (like the avwap one) that pure
unit tests miss because they only trip on real production data.

Run: python tests/functional_walkthrough.py
"""

import os
import sys
import traceback

# Windows cp1252 terminals can't print flag emojis — force UTF-8 stdout.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine as eng
import scanner_contrarian
import scanner_penny
from ml import predictor as ml_predictor, backtest as ml_backtest
from config import MARKET_CONFIGS, FUND_CATALOGUE

_pass = _fail = 0
_failures = []


def check(name: str, fn):
    global _pass, _fail
    try:
        result = fn()
        if result is False:
            print(f"  FAIL  {name}")
            _fail += 1
            _failures.append((name, "returned False"))
        else:
            print(f"  PASS  {name}")
            _pass += 1
    except Exception as e:
        print(f"  FAIL  {name}  {type(e).__name__}: {str(e)[:120]}")
        _fail += 1
        _failures.append((name, f"{type(e).__name__}: {e}"))


# ── Tab 1 — Today's Picks: screener across every market ───────────────
print("\n[Tab 1] Picks screener — every market, every ticker")
for market_name in ("🇺🇸 US Stocks", "🇮🇳 India NSE", "₿ Crypto",
                   "🇬🇧 UK", "🇪🇺 Europe", "🇨🇦 Canada", "🇯🇵 Japan"):
    mc = MARKET_CONFIGS.get(market_name)
    if not mc:
        continue
    def _run(mc=mc, name=market_name):
        regime = eng.check_regime(mc)
        assert "_df" in regime, f"{name}: regime missing _df"
        tickers = list(dict.fromkeys(mc["growth"] + mc["blue_chips"]))[:10]
        errs = []
        for t in tickers:
            try:
                eng.analyze_ticker(t, mc, regime.get("_df"), 10000.0, 1.0)
            except Exception as e:
                errs.append(f"{t}: {type(e).__name__}: {str(e)[:60]}")
        if errs:
            raise RuntimeError("; ".join(errs))
        return True
    check(f"screener over {market_name}", _run)

# ── Tab 1 — Contrarian scanner across the 2 main markets ──────────────
print("\n[Tab 1] Contrarian scanner")
for market_name in ("🇺🇸 US Stocks", "🇮🇳 India NSE"):
    mc = MARKET_CONFIGS[market_name]
    def _c(mc=mc):
        out = scanner_contrarian.scan_contrarian(mc, {"_df": None}, 10000.0, 1.0)
        assert isinstance(out, list)
        return True
    check(f"contrarian over {market_name}", _c)

# ── Tab 1 — VIX gauge ─────────────────────────────────────────────────
print("\n[Tab 1] VIX gauge")
check("fetch_vix()", lambda: "level" in eng.fetch_vix())

# ── Tab 1 — Sector strength (US only) ─────────────────────────────────
print("\n[Tab 1] Sector strength (US)")
mc_us = MARKET_CONFIGS["🇺🇸 US Stocks"]
def _sec():
    regime = eng.check_regime(mc_us)
    sectors = eng.score_sectors(mc_us, regime["_df"])
    assert isinstance(sectors, dict)
    return True
check("score_sectors(US)", _sec)

# ── Tab 3 — Funds compounding simulator ───────────────────────────────
print("\n[Tab 3] Funds + compounding simulator")
check("FUND_CATALOGUE non-empty", lambda: len(FUND_CATALOGUE) >= 10)
def _comp():
    r = eng.compound(lump=10000, sip=500, cagr=12.0, inflation=4.0, years=30)
    assert "yearly" in r and len(r["yearly"]) == 30
    assert "milestones" in r and len(r["milestones"]) == 6
    return True
check("compound(30y)", _comp)

# ── Tab 4 — Stock Checker: full analysis sections ─────────────────────
print("\n[Tab 4] Stock Checker — all 6 sections (probe with AAPL)")
mc_us = MARKET_CONFIGS["🇺🇸 US Stocks"]
def _full():
    r = eng.analyze_ticker("AAPL", mc_us, None, 10000.0, 1.0)
    assert r and r.get("signal")
    return True
check("analyze_ticker(AAPL)", _full)
check("profit_probability(AAPL)", lambda: "win_prob" in eng.profit_probability("AAPL", mc_us, 10))
check("fetch_fundamentals_safe(AAPL)", lambda: isinstance(eng.fetch_fundamentals_safe("AAPL"), dict))
check("fetch_news(AAPL)", lambda: isinstance(eng.fetch_news("AAPL"), list))
check("fetch_options(AAPL)", lambda: isinstance(eng.fetch_options("AAPL"), dict))
check("check_weekly_trend(AAPL)", lambda: "pass" in eng.check_weekly_trend("AAPL"))

# ── Tab 4 — Crypto path (uses Kraken) ─────────────────────────────────
print("\n[Tab 4] Crypto via Kraken")
mc_crypto = MARKET_CONFIGS["₿ Crypto"]
def _btc():
    r = eng.analyze_ticker("BTC-USD", mc_crypto, None, 10000.0, 1.0)
    assert r and r.get("signal")
    return True
check("analyze_ticker(BTC-USD via Kraken)", _btc)

# ── Tab 5 — Portfolio monitor_position ────────────────────────────────
print("\n[Tab 5] Portfolio monitor")
def _mon():
    pos = {"ticker": "AAPL", "entry": 150.0, "shares": 10, "stop": 140.0,
           "date": "2026-05-01"}
    m = eng.monitor_position(pos, mc_us, 5)
    assert m.get("ticker") == "AAPL" or "error" in m
    return True
check("monitor_position(AAPL)", _mon)

# ── Tab 6 — Settings: market status for every market ──────────────────
print("\n[Tab 6] Settings — market_status for every market")
for market_name, mc in MARKET_CONFIGS.items():
    def _ms(k=mc["key"]):
        s = eng.market_status(k)
        assert "open" in s and "label" in s
        return True
    check(f"market_status({mc['key']})", _ms)

# ── Tab 7 — Admin ML status banner code path ──────────────────────────
print("\n[Tab 7] Admin — ML status / predictor scoring")
check("predictor.score_prediction cold-start",
      lambda: abs(ml_predictor.score_prediction({"win_prob": 65}) - 65.0) < 0.1)
check("backtest.run_backtest module surface", lambda: callable(ml_backtest.run_backtest))

# ── Sidebar: regime check for every market ─────────────────────────────
print("\n[Sidebar] Regime check across every market")
for market_name, mc in MARKET_CONFIGS.items():
    def _reg(mc=mc):
        r = eng.check_regime(mc)
        assert "pass" in r and "label" in r
        return True
    check(f"check_regime({mc['key']})", _reg)

# ── Auto-suffix helper (used in Watchlist editor + Portfolio) ─────────
print("\n[Helpers] auto_suffix routing")
check("auto_suffix TCS for IN", lambda: eng.auto_suffix("TCS", "IN") == "TCS.NS")
check("auto_suffix already-suffixed", lambda: eng.auto_suffix("RELIANCE.NS", "IN") == "RELIANCE.NS")
check("auto_suffix crypto no-op", lambda: eng.auto_suffix("BTC-USD", "CRYPTO") == "BTC-USD")
check("auto_suffix US no suffix", lambda: eng.auto_suffix("AAPL", "US") == "AAPL")

# ── Penny scanner — contract check for US + India ─────────────────────
print("\n[Penny Scanner] scan_penny on US + India")
for market_name in ("🇺🇸 US Stocks", "🇮🇳 India NSE"):
    mc_p = MARKET_CONFIGS[market_name]
    def _penny(mc=mc_p, name=market_name):
        out = scanner_penny.scan_penny(mc, {"_df": None}, 10000.0, 1.0)
        assert isinstance(out, list), f"{name}: scan_penny did not return a list"
        for r in out:
            assert "ticker" in r, f"{name}: result missing 'ticker'"
            assert "signal" in r, f"{name}: result missing 'signal'"
            assert r.get("is_penny") is True, f"{name}: is_penny flag not set"
            assert r.get("signal", "").startswith("PENNY"), (
                f"{name}: unexpected signal vocabulary: {r['signal']}")
        return True
    check(f"scan_penny({mc_p['key']})", _penny)

# ── Penny scanner returns [] for non-penny markets ─────────────────────
print("\n[Penny Scanner] non-penny markets return empty list")
for market_name in ("₿ Crypto", "🇬🇧 UK", "🇪🇺 Europe"):
    mc_np = MARKET_CONFIGS[market_name]
    def _no_penny(mc=mc_np):
        out = scanner_penny.scan_penny(mc, {"_df": None}, 10000.0, 1.0)
        assert out == [], f"Expected [] for {mc['key']}, got {len(out)} picks"
        return True
    check(f"scan_penny returns [] for {mc_np['key']}", _no_penny)

# ── auth.request_password_reset surface check ─────────────────────────
print("\n[Auth] request_password_reset function surface")
import auth as _auth
check("request_password_reset exists",
      lambda: callable(_auth.request_password_reset))
def _reset_shape():
    # Must return (bool, str) even when Supabase is not available
    ok, msg = _auth.request_password_reset("test@example.com")
    assert isinstance(ok, bool), f"ok is not bool: {ok!r}"
    assert isinstance(msg, str) and len(msg) > 0, f"msg is empty: {msg!r}"
    return True
check("request_password_reset returns (bool, str)", _reset_shape)

print(f"\n{'='*56}")
print(f"FUNCTIONAL WALKTHROUGH: {_pass} passed, {_fail} failed")
print(f"{'='*56}")
if _failures:
    print("\nFailures detail:")
    for name, err in _failures:
        print(f"  - {name}\n      {err}")
sys.exit(1 if _fail else 0)
