"""
ml/backtest.py — 90-day historical backtest + deploy gate.

Simulates the engine's BUY-style trigger across the last `days` weekdays, holds
10 days, records realised return + max favourable excursion. Reports hit-rate
(at the 20% MFE bar — your stretch goal), average return, Sharpe, max drawdown,
and a pass/fail against the deploy gate.

Deploy gate:  hit_rate_20 >= 55 %   (stretches your 20-% profit target rule).
              If failed → ML stays in shadow mode (alerts driven by rules only).

Usage:
    from ml import backtest
    report = backtest.run_backtest(days=90)
    gate   = backtest.check_deploy_gate()

CLI:
    python -m ml.backtest --days 90
"""

import argparse
import json
import math
from datetime import datetime

import engine as eng
from applog import get_logger
from config import MARKET_CONFIGS

log = get_logger("aarya_backtest")

MIN_HISTORY_BARS = 260       # need ≥1y so 200-SMA + Minervini are meaningful
HOLD_DAYS        = 10
HIT_THRESHOLD    = 20.0


def _signal_at(sub_df, mc) -> bool:
    """Reproduce the engine's BUY-style trigger using only `sub_df` history."""
    if len(sub_df) < MIN_HISTORY_BARS:
        return False
    close = sub_df["Close"].squeeze()
    minn  = eng.minervini(close)
    if not minn["pass"]:
        return False
    # Above 8 EMA (short-term momentum)
    if float(close.iloc[-1]) <= float(eng.ema(close, 8).iloc[-1]):
        return False
    # Volume confirmation
    vol = eng.check_volume(sub_df, multiplier=1.5)
    if not vol["pass"]:
        return False
    # No RS check here (would require benchmark slice per day); accept on
    # the other 3 conditions — this gives a slightly more permissive picture
    # than live signal, which matches "did the rule-based signal want to fire?"
    return True


def run_backtest(days: int = 90, tickers: list = None) -> dict:
    """Returns a dict of summary metrics + a `trades` list."""
    if tickers is None:
        mc_us = MARKET_CONFIGS["🇺🇸 US Stocks"]
        tickers = list(dict.fromkeys(mc_us["growth"] + mc_us["blue_chips"]))[:15]

    trades = []
    for t in tickers:
        df = eng.download(t, period="2y")
        if df is None or len(df) < MIN_HISTORY_BARS + days + HOLD_DAYS:
            log.debug(f"{t}: not enough history")
            continue

        n = len(df)
        # Start such that we have `days` worth of trigger evaluations
        start_i = max(MIN_HISTORY_BARS, n - days - HOLD_DAYS - 1)
        for i in range(start_i, n - HOLD_DAYS - 1):
            sub = df.iloc[: i + 1]
            if not _signal_at(sub, None):
                continue
            entry = float(sub["Close"].iloc[-1])
            future = df.iloc[i + 1 : i + 1 + HOLD_DAYS]
            if len(future) < 3:
                continue
            high_after = float(future["High"].max())
            close_after = float(future["Close"].iloc[-1])
            mfe = (high_after - entry) / entry * 100
            ret = (close_after - entry) / entry * 100
            trades.append({
                "ticker": t,
                "i": i,
                "entry": round(entry, 2),
                "ret_pct": round(ret, 2),
                "mfe_pct": round(mfe, 2),
                "hit_20":  mfe >= HIT_THRESHOLD,
                "hit_10":  mfe >= 10.0,
            })

    if not trades:
        return {"n_trades": 0, "hit_rate_20": 0.0, "avg_return": 0.0,
                "sharpe": 0.0, "max_drawdown": 0.0, "trades": [],
                "note": "no trades generated — relax signal or extend history"}

    n_t   = len(trades)
    hit20 = sum(1 for x in trades if x["hit_20"]) / n_t * 100
    hit10 = sum(1 for x in trades if x["hit_10"]) / n_t * 100
    rets  = [x["ret_pct"] for x in trades]
    mfes  = [x["mfe_pct"] for x in trades]
    avg_r = sum(rets) / n_t
    avg_m = sum(mfes) / n_t
    var   = sum((r - avg_r) ** 2 for r in rets) / n_t
    std   = math.sqrt(var)
    # Annualise Sharpe assuming ~25 non-overlapping 10-day trades per year
    sharpe = (avg_r / std) * math.sqrt(25) if std > 1e-9 else 0.0

    # Sequential equity curve (simple sum of returns)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for r in rets:
        eq += r
        peak = max(peak, eq)
        mdd  = max(mdd, peak - eq)

    return {
        "n_trades":     n_t,
        "hit_rate_20":  round(hit20, 2),
        "hit_rate_10":  round(hit10, 2),
        "avg_return":   round(avg_r, 2),
        "avg_mfe":      round(avg_m, 2),
        "sharpe":       round(sharpe, 2),
        "max_drawdown": round(mdd, 2),
        "trades":       trades,
        "tickers":      list({t["ticker"] for t in trades}),
        "ran_at":       datetime.utcnow().isoformat(),
    }


def check_deploy_gate(min_hit_rate_20: float = 55.0,
                      min_avg_mfe: float = 10.0) -> dict:
    """Run backtest + return pass/fail + summary."""
    res = run_backtest()
    passed = (res.get("hit_rate_20", 0) >= min_hit_rate_20
              and res.get("avg_mfe", 0) >= min_avg_mfe)
    res["pass"] = bool(passed)
    res["gate"] = {"min_hit_rate_20": min_hit_rate_20,
                   "min_avg_mfe":     min_avg_mfe}
    if not passed:
        res["note"] = ("Deploy gate FAILED — ML will stay in shadow mode "
                       "(alerts driven by rules, predictions still logged).")
    else:
        res["note"] = "Deploy gate PASSED — ML may drive alerts."
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--gate", action="store_true",
                   help="Run gate check + print pass/fail")
    args = p.parse_args()
    res = check_deploy_gate() if args.gate else run_backtest(days=args.days)
    # Trim trades to summary for readability
    summary = {k: v for k, v in res.items() if k != "trades"}
    summary["n_trades_logged"] = len(res.get("trades", []))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
