"""
scanner_penny.py — proactive penny-stock momentum scanner.

Complement (not replacement) to the trend-following Minervini scanner and the
contrarian scanner. Surfaces quality penny stocks that are showing momentum so
the ML loop can learn from them the same way it learns from regular picks.

Selection rules (penny-specific — different from Minervini + contrarian):
  • price < PENNY_THRESHOLD[$10 US / ₹300 India] (hard gate)
  • volume ratio ≥ 1.5× 20-day average (accumulation / momentum signature)
  • data_quality gate pass                       — via engine.data_quality
  • RSI 14 between 30 and 80                    — not extreme either way
  • 30-day annualised volatility ≤ 150%         — reject pure lottery tickets
  • stop = max(20-bar swing low × 0.97, entry × 0.85) — never wider than 15%

Signal vocabulary (distinct so they don't collide with other tracks):
  PENNY MOMENTUM BUY   — vol ≥ 2x AND RSI 50–70 AND above 10-day high
  PENNY MOMENTUM WATCH — vol ≥ 1.5x AND positive momentum (below breakout)
  PENNY CAUTION        — momentum present but RSI > 75 (likely exhausted)

Targets (realistic for pennies):
  T1 = +25%, T2 = +50%, T3 = +100%

Only enabled for US and India markets.
"""

import math
from applog import get_logger
import engine as eng

log = get_logger("aarya_penny")

# Penny thresholds per market key
PENNY_THRESHOLD = {"US": 10.0, "IN": 300.0}

# Markets that support penny scanning
_PENNY_MARKETS = set(PENNY_THRESHOLD.keys())


def _swing_low(df, lookback: int = 20) -> float:
    try:
        return float(df["Low"].iloc[-lookback:].min())
    except Exception:
        return float(df["Low"].iloc[-1])


def _annualised_vol(close, days: int = 30) -> float:
    """30-day annualised realised volatility as a percentage."""
    try:
        returns = close.pct_change().dropna()
        if len(returns) < days:
            return 0.0
        daily_std = float(returns.iloc[-days:].std())
        return daily_std * math.sqrt(252) * 100
    except Exception:
        return 0.0


def analyze_penny(ticker: str, mc: dict, bm_df, portfolio: float,
                  risk_pct: float) -> dict | None:
    """Analyse a single ticker for penny-momentum conditions.
    Returns a result dict compatible with signal_card() / mldb.log_prediction(),
    or None if the ticker doesn't qualify."""
    market_key = mc.get("key", "")
    if market_key not in _PENNY_MARKETS:
        return None

    cutoff = PENNY_THRESHOLD[market_key]
    cur    = mc["currency"]

    df = eng.download(ticker, period="1y")
    if df is None or len(df) < 30:
        return None

    is_crypto = mc.get("is_crypto", False) or "-USD" in ticker.upper()
    ok, why = eng.data_quality(df, ticker, is_crypto=is_crypto)
    if not ok:
        log.debug(f"{ticker}: data quality fail — {why}")
        return None

    close = df["Close"].squeeze()
    price = round(float(close.iloc[-1]), 4)

    # Hard penny gate
    if price >= cutoff:
        return None

    # --- Volume ratio (20-day average) ---
    try:
        vol_series = df["Volume"].squeeze()
        vol_avg20  = float(vol_series.iloc[-21:-1].mean()) if len(vol_series) > 21 else float(vol_series.mean())
        vol_today  = float(vol_series.iloc[-1])
        vol_ratio  = vol_today / vol_avg20 if vol_avg20 > 0 else 1.0
    except Exception:
        vol_ratio = 1.0

    if vol_ratio < 1.5:
        return None

    # --- RSI ---
    rsi_val = None
    is_india = ticker.upper().endswith(".NS")
    if not is_india and not is_crypto:
        rsi_val = eng.get_rsi(ticker)
    # For India/crypto: estimate RSI from price data
    if rsi_val is None and len(close) >= 15:
        try:
            delta  = close.diff().dropna()
            gain   = delta.clip(lower=0).rolling(14).mean()
            loss   = (-delta.clip(upper=0)).rolling(14).mean()
            rs     = gain / loss.replace(0, 1e-9)
            rsi_s  = 100 - (100 / (1 + rs))
            rsi_val = round(float(rsi_s.iloc[-1]), 1)
        except Exception:
            rsi_val = 50.0

    rsi = rsi_val if rsi_val is not None else 50.0

    # RSI quality gate: not extreme
    if not (30 <= rsi <= 80):
        return None

    # --- Volatility gate ---
    ann_vol = _annualised_vol(close, days=30)
    if ann_vol > 150:
        log.debug(f"{ticker}: rejected — ann_vol {ann_vol:.0f}% > 150%")
        return None

    # --- 10-day high (breakout check) ---
    try:
        hi10 = float(close.iloc[-11:-1].max())
        above_10d_high = price > hi10
    except Exception:
        above_10d_high = False

    # --- Signal logic ---
    if vol_ratio >= 2.0 and 50 <= rsi <= 70 and above_10d_high:
        signal = "PENNY MOMENTUM BUY"
    elif rsi > 75:
        signal = "PENNY CAUTION"
    elif vol_ratio >= 1.5:
        signal = "PENNY MOMENTUM WATCH"
    else:
        signal = "PENNY CAUTION"

    # --- Stop: max(swing_low × 0.97, price × 0.85) — never wider than 15% ---
    swing_l = _swing_low(df, lookback=20)
    stop_swing = round(swing_l * 0.97, 4)
    stop_cap   = round(price * 0.85, 4)        # 15% max loss
    stop       = max(stop_swing, stop_cap)     # closer to current = less risk

    # --- Targets: +25%, +50%, +100% ---
    t1 = round(price * 1.25, 4)
    t2 = round(price * 1.50, 4)
    t3 = round(price * 2.00, 4)

    rr = eng.calc_rr(price, stop, portfolio, risk_pct, cur)
    rr["t1"], rr["t2"], rr["t3"] = t1, t2, t3

    # --- Win probability (penny-specific, more modest) ---
    score = 0
    if vol_ratio >= 2.0:    score += 2
    elif vol_ratio >= 1.5:  score += 1
    if 50 <= rsi <= 70:     score += 2
    if above_10d_high:      score += 2
    win_prob = min(35 + score * 7, 72)          # cap at 72 — realistic for pennies

    # --- RS score (simplified: price change vs market) ---
    rs_score = None
    try:
        if bm_df is not None and len(bm_df) >= 20:
            bm_close = bm_df["Close"].squeeze()
            stock_ret = float(close.iloc[-1] / close.iloc[-20] - 1)
            bm_ret    = float(bm_close.iloc[-1] / bm_close.iloc[-20] - 1) if len(bm_close) >= 20 else 0.0
            rs_score  = round(stock_ret / max(abs(bm_ret), 0.001), 2)
    except Exception:
        rs_score = None

    verdict = (f"Penny momentum setup — {cur}{price:.2f}, vol {vol_ratio:.1f}x avg, "
               f"RSI {rsi:.0f}, {'above' if above_10d_high else 'below'} 10-day high. "
               f"Targets: T1 {cur}{t1} (+25%), T2 {cur}{t2} (+50%), T3 {cur}{t3} (+100%). "
               f"Stop: {cur}{stop} (-{(price-stop)/price*100:.0f}%). "
               f"High risk — position-size carefully.")

    hold_days = "1–5 trading days (short-term swing)"
    if signal == "PENNY CAUTION":
        hold_days = "Watch only — wait for RSI to cool below 70"

    conditions = {
        "price_under_threshold": True,
        "volume_2x+":            vol_ratio >= 2.0,
        "volume_1.5x+":          vol_ratio >= 1.5,
        "rsi_healthy_(30-80)":   30 <= rsi <= 80,
        "rsi_momentum_(50-70)":  50 <= rsi <= 70,
        "above_10d_high":        above_10d_high,
        "vol_lt_150pct":         ann_vol <= 150,
    }

    return {
        "ticker":          ticker,
        "price":           price,
        "currency":        cur,
        "signal":          signal,
        "verdict":         verdict,
        "hold_days":       hold_days,
        "win_prob":        win_prob,
        "minervini_score": 0,              # not applicable for penny track
        "rs_score":        rs_score,
        "rsi":             rsi,
        "is_overbought":   rsi > 75,
        "is_extended":     False,
        "extension_pct":   0.0,
        "entry":           price,
        "stop":            stop,
        "rr":              rr,
        "t1_price":        t1,
        "t2_price":        t2,
        "criteria":        conditions,
        "volume":          {"pass": vol_ratio >= 1.5, "ratio": vol_ratio},
        "sweep":           {"pass": False},
        "score":           score,
        "vol_ratio":       round(vol_ratio, 2),
        "ann_vol":         round(ann_vol, 1),
        "is_penny":        True,           # marker for ML outcome threshold (25% vs 20%)
        "track":           "penny",
        "_df":             df,
    }


def scan_penny(mc: dict, regime: dict, portfolio: float,
               risk_pct: float, max_tickers: int = 30) -> list[dict]:
    """Public entrypoint. Returns penny picks sorted by signal strength.

    Only runs for US and India markets; returns [] for all others.
    """
    market_key = mc.get("key", "")
    if market_key not in _PENNY_MARKETS:
        return []

    bm_df  = regime.get("_df")
    extras = mc.get("penny_extras", [])
    base   = list(dict.fromkeys(mc.get("growth", []) + mc.get("blue_chips", []) + extras))
    cutoff = PENNY_THRESHOLD[market_key]

    # Pre-filter: only scan tickers that are plausibly pennies (skip known large-caps)
    # We still scan all because prices change, but cap to max_tickers for speed.
    tickers = base[:max_tickers]

    buys, watches, cautions = [], [], []
    for t in tickers:
        try:
            r = analyze_penny(t, mc, bm_df, portfolio, risk_pct)
            if r is None:
                continue
            sig = r["signal"]
            if sig == "PENNY MOMENTUM BUY":
                buys.append(r)
            elif sig == "PENNY MOMENTUM WATCH":
                watches.append(r)
            elif sig == "PENNY CAUTION":
                cautions.append(r)
        except Exception as e:
            log.debug(f"{t} penny error: {e}")

    buys.sort(key=lambda r: r.get("win_prob", 0), reverse=True)
    watches.sort(key=lambda r: r.get("vol_ratio", 0), reverse=True)

    log.info(f"Penny scan ({mc['key']}): {len(buys)} BUY, {len(watches)} WATCH, "
             f"{len(cautions)} CAUTION across {len(tickers)} tickers.")

    return buys[:5] + watches[:3] + cautions[:2]
