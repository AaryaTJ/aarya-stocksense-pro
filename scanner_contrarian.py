from __future__ import annotations
"""
scanner_contrarian.py — mean-reversion / oversold-quality scanner.

Complement (not replacement) to the trend-following Minervini scanner. Finds
quality stocks knocked down to 52-week-range lows so they can be bought when
the market is weak and ride the recovery.

Selection rules:
  • price in bottom 15 % of 52-week range
  • RSI 14 < 35 (oversold)        — via engine.get_rsi
  • volume ≥ 1.2× 50-day avg      — capitulation/accumulation signature
  • distance to 200-SMA ≤ 20 %    — still on the larger map
  • fundamentals quality gate     — rev growth > 0 OR analyst rec Buy/Strong-Buy
  • stop = recent swing low × 0.99 OR 12 % below price, whichever closer

Signal labels (distinct vocabulary from Minervini track):
  OVERSOLD BUY | OVERSOLD WATCH | AVOID
"""

from applog import get_logger
import engine as eng

log = get_logger("aarya_contrarian")


def _swing_low(df, lookback: int = 10) -> float:
    try:
        return float(df["Low"].iloc[-lookback:].min())
    except Exception:
        return float(df["Low"].iloc[-1])


def analyze_contrarian(ticker: str, mc: dict, bm_df, portfolio: float,
                       risk_pct: float) -> dict | None:
    df = eng.download(ticker, period="1y")
    if df is None or len(df) < 60:
        return None

    is_crypto = mc.get("is_crypto", False) or "-USD" in ticker.upper()
    ok, why = eng.data_quality(df, ticker, is_crypto=is_crypto)
    if not ok:
        log.debug(f"{ticker}: rejected — {why}")
        return None

    close = df["Close"].squeeze()
    price = round(float(close.iloc[-1]), 4)
    cur   = mc["currency"]

    hi52 = float(close.rolling(252).max().iloc[-1])
    lo52 = float(close.rolling(252).min().iloc[-1])
    rng  = max(hi52 - lo52, 1e-9)
    pct_range = round((price - lo52) / rng * 100, 1)            # 0 = at low, 100 = at high
    near_low  = pct_range <= 15

    s200 = eng.sma(close, 200)
    sma200_val = float(s200.iloc[-1]) if len(s200) else price
    dist_200 = round(abs(price - sma200_val) / sma200_val * 100, 1) if sma200_val else 100
    on_map   = dist_200 <= 20

    # RSI — only available for US tickers via Twelve Data; skip the filter
    # when we can't fetch it (don't block India/crypto).
    rsi_val = None
    is_oversold = True
    is_india    = ticker.upper().endswith(".NS")
    if not is_india and not is_crypto:
        rsi_val = eng.get_rsi(ticker)
        if rsi_val is not None:
            is_oversold = rsi_val < 35

    vol = eng.check_volume(df, multiplier=1.2)

    fund = eng.fetch_fundamentals_safe(ticker) or {}
    rg   = fund.get("rev_growth")
    rec  = (fund.get("rec") or "").lower()
    quality_ok = (rg is not None and rg > 0) or rec in ("buy", "strong buy")

    conditions = {
        "near_52w_low":    near_low,
        "oversold":        is_oversold,
        "volume_support":  vol["pass"],
        "on_map":          on_map,
        "quality":         quality_ok,
    }
    score = sum(conditions.values())

    if near_low and is_oversold and quality_ok and (vol["pass"] or on_map):
        signal = "OVERSOLD BUY"
    elif near_low and (is_oversold or quality_ok):
        signal = "OVERSOLD WATCH"
    else:
        signal = "AVOID"

    swing_low = _swing_low(df, 10)
    stop_swing = round(swing_low * 0.99, 4)
    stop_cap   = round(price * 0.88, 4)       # contrarian gets a wider 12% cap
    stop = max(stop_swing, stop_cap)          # closer of the two = less risk

    # Resistance proxy: 50-SMA above price (if any) is the first natural lid
    s50 = eng.sma(close, 50)
    sma50_val = float(s50.iloc[-1]) if len(s50) else price * 1.05
    resistance = max(sma50_val, price * 1.05)

    risk_per = max(price - stop, 0.001)
    t1 = round(price + 1 * risk_per, 4)
    t2 = round(price + 2 * risk_per, 4)
    t3 = round(min(resistance, price + 3 * risk_per), 4)

    rr = eng.calc_rr(price, stop, portfolio, risk_pct, cur)
    rr["t1"], rr["t2"], rr["t3"] = t1, t2, t3                   # override targets

    win_prob = min(45 + score * 6, 80)                          # cap optimism

    verdict = (f"Oversold setup — {pct_range:.0f}% of 52w range, "
               f"{'RSI ' + str(rsi_val) if rsi_val is not None else 'no RSI feed'}, "
               f"{int(vol['ratio']*10)/10}x volume. "
               f"Quality gate: {'PASS' if quality_ok else 'NO'} "
               f"({'rev +' + str(rg) + '%' if rg else 'rec ' + (fund.get('rec') or 'N/A')}). "
               f"Entry {cur}{price}, stop {cur}{stop} (-{(price-stop)/price*100:.1f}%), "
               f"T1 {cur}{t1}, T2 {cur}{t2}, T3 {cur}{t3}.")

    return {
        "ticker":          ticker,
        "price":           price,
        "currency":        cur,
        "signal":          signal,
        "verdict":         verdict,
        "hold_days":       "Until 50-SMA reclaim or stop",
        "win_prob":        win_prob,
        "minervini_score": 0,                # not applicable for contrarian
        "rs_score":        None,
        "rsi":             rsi_val,
        "is_overbought":   False,
        "is_extended":     False,
        "extension_pct":   0.0,
        "entry":           price,
        "stop":            stop,
        "rr":              rr,
        "t1_price":        t1,
        "t2_price":        t2,
        "score":           score,
        "pct_range":       pct_range,
        "dist_200":        dist_200,
        "volume":          vol,
        "sweep":           {"pass": False},
        "track":           "contrarian",
        "_df":             df,
    }


def scan_contrarian(mc: dict, regime: dict, portfolio: float,
                    risk_pct: float, max_tickers: int = 25) -> list[dict]:
    bm_df = regime.get("_df")
    tickers = list(dict.fromkeys(
        mc.get("growth", []) + mc.get("blue_chips", [])
    ))[:max_tickers]

    picks, watches = [], []
    for t in tickers:
        try:
            r = analyze_contrarian(t, mc, bm_df, portfolio, risk_pct)
            if r is None:
                continue
            if r["signal"] == "OVERSOLD BUY":
                picks.append(r)
            elif r["signal"] == "OVERSOLD WATCH":
                watches.append(r)
        except Exception as e:
            log.debug(f"{t} contrarian error: {e}")

    picks.sort(key=lambda r: r.get("win_prob", 0), reverse=True)
    watches.sort(key=lambda r: r.get("win_prob", 0), reverse=True)
    log.info(f"Contrarian scan: {len(picks)} BUY, {len(watches)} WATCH "
             f"across {len(tickers)} tickers.")
    return picks[:5] + watches[:3]
