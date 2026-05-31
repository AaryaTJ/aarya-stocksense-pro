"""
ml/predictor.py — the self-improving ML feedback loop.

Three jobs, called from monitor.py:
  evaluate_open_predictions() — pulls every open prediction past its horizon,
      downloads what the price actually did, writes outcome back to Supabase.
  train_ensemble()            — once 30+ predictions are evaluated, trains a
      3-model ensemble (logistic + tree + weighted rules) via walk-forward,
      saves weights + rolling accuracy to `model_state`.
  score_prediction(pred)      — called BEFORE sending a candidate alert. Uses
      stored ensemble weights to return confidence (0–100). Cold-start
      fallback: returns the engine's rule-based win_prob unchanged.

Design notes
- sklearn is only needed at training time (runs in GitHub Actions, where we
  install it). Scoring is pure-Python: logistic coefs and the tree are stored
  as JSON / nested dicts so app.py + bot_poll don't need sklearn.
- 20 % MFE (max-favourable-excursion) over `HORIZON_DAYS` is treated as a
  hit. A soft 5 % bar is also recorded for diagnostics so a sane "less
  aggressive" reality check is always available.
- Every step is wrapped — a missing DB, missing sklearn, or zero data must
  never crash the monitor cron.
"""

import math
from datetime import datetime, date, timedelta

import requests

from applog import get_logger
import engine as eng
import mldb

log = get_logger("aarya_predictor")

HORIZON_DAYS                   = 10
HIT_THRESHOLD_PCT              = 20.0     # stock default
PENNY_HIT_THRESHOLD_PCT        = 25.0     # higher bar: 20% is noise for pennies
CRYPTO_HIT_THRESHOLD_PCT       = 15.0     # crypto is choppier; 15% is meaningful
OPTIONS_HIT_THRESHOLD_PCT      = 50.0     # options trades target +50% premium
SOFT_HIT_PCT                   = 5.0
MIN_EVALUATED_FOR_TRAINING     = 30

FEATURES = [
    "minervini", "rs_score", "rsi", "extension_pct",
    "volume_ratio", "sweep", "is_overbought", "is_extended", "win_prob",
]


# ── Feature extraction (works for both stored rows and live engine results) ──

def _feature_vector(row: dict) -> list[float]:
    f = row.get("features") or {}
    return [
        float(row.get("minervini") or 0),
        float(row.get("rs_score")  or 1.0),
        float(row.get("rsi")       or 50.0),
        float(f.get("extension_pct") if f.get("extension_pct") is not None
              else (row.get("extension_pct") or 0)),
        float(f.get("volume_ratio") or 1.0),
        1.0 if f.get("sweep")          else 0.0,
        1.0 if f.get("is_overbought")  else 0.0,
        1.0 if f.get("is_extended")    else 0.0,
        float(row.get("win_prob") or 50),
    ]


def _pred_to_row(pred: dict) -> dict:
    """Live engine result → row-like dict for scoring."""
    return {
        "minervini": pred.get("minervini_score") or pred.get("minervini"),
        "rs_score":  pred.get("rs_score"),
        "rsi":       pred.get("rsi"),
        "win_prob":  pred.get("win_prob"),
        "features": {
            "extension_pct": pred.get("extension_pct"),
            "volume_ratio":  (pred.get("volume", {}) or {}).get("ratio"),
            "sweep":         (pred.get("sweep",  {}) or {}).get("pass"),
            "is_overbought": pred.get("is_overbought"),
            "is_extended":   pred.get("is_extended"),
        },
    }


# ── Per-track hit threshold ───────────────────────────────────────────

def _classify_failure(payload: dict, sub, entry: float) -> str:
    """Classify why a pick failed. Returns one of four tags."""
    rsi_entry = (payload or {}).get("rsi", 0) or 0
    if rsi_entry >= 75:
        return "rsi_overheated_at_entry"
    try:
        closes = sub["Close"].squeeze()
        sma50 = closes.rolling(50, min_periods=10).mean()
        if (closes < sma50).any():
            return "broke_50dma"
        vol = sub["Volume"].squeeze()
        if len(vol) >= 10:
            vol_early = float(vol.iloc[:5].mean())
            vol_late  = float(vol.iloc[-5:].mean())
            if vol_early > 0 and vol_late / vol_early < 0.5:
                return "volume_dried_up"
    except Exception:
        pass
    return "general_drawdown"


def _hit_threshold_for(payload: dict) -> float:
    """Return the MFE hit threshold for a prediction payload based on its track."""
    track = (payload or {}).get("track", "stock")
    if track == "options": return OPTIONS_HIT_THRESHOLD_PCT
    if track == "crypto":  return CRYPTO_HIT_THRESHOLD_PCT
    if (payload or {}).get("is_penny") or track == "penny": return PENNY_HIT_THRESHOLD_PCT
    return HIT_THRESHOLD_PCT


# ── Outcome evaluation ────────────────────────────────────────────────

def evaluate_open_predictions() -> tuple[int, int, int]:
    """Returns (n_evaluated, n_hit_20pct, n_hit_5pct)."""
    rows = mldb.get_open_predictions(older_than_days=HORIZON_DAYS)
    n = n_hit = n_soft = 0
    for r in rows:
        try:
            ticker = r.get("ticker")
            entry  = float(r.get("entry") or r.get("price") or 0)
            if not ticker or entry <= 0:
                continue
            pred_dt = date.fromisoformat(str(r["pred_date"])[:10])
            df = eng.download(ticker, period="3mo")
            if df is None or len(df) < 2:
                continue
            try:
                sub = df.loc[str(pred_dt):]
            except Exception:
                sub = df
            if len(sub) < 2:
                continue
            final_close = float(sub["Close"].iloc[-1])
            high_after  = float(sub["High"].iloc[1:].max()) if len(sub) > 1 else final_close
            mfe         = (high_after  - entry) / entry * 100   # max favourable excursion
            outcome_pct = round((final_close - entry) / entry * 100, 2)
            payload  = r.get("payload") or r
            hit_bar  = _hit_threshold_for(payload)
            hit      = mfe >= hit_bar
            soft        = mfe >= SOFT_HIT_PCT
            failure_reason = None if hit else _classify_failure(payload, sub, entry)
            if mldb.update_prediction_outcome(r["id"], outcome_pct, hit, failure_reason):
                n += 1
                n_hit  += 1 if hit  else 0
                n_soft += 1 if soft else 0
        except Exception as e:
            log.debug(f"eval {r.get('ticker','?')} error: {e}")
    log.info(f"Evaluator: {n} predictions evaluated  ({n_hit} hit 20% MFE,  {n_soft} hit 5% MFE)")
    return n, n_hit, n_soft


# ── Ensemble training (sklearn → JSON weights) ────────────────────────

def _fetch_evaluated(limit: int = 2000) -> list[dict]:
    url, key = mldb._creds()
    if not url or not key:
        return []
    try:
        r = requests.get(
            f"{url}/rest/v1/predictions?status=eq.evaluated"
            f"&order=created_at.desc&limit={limit}&select=*",
            headers=mldb._headers(key), timeout=15,
        )
        if r.status_code == 200:
            return list(reversed(r.json()))     # chronological
    except Exception as e:
        log.warning(f"_fetch_evaluated error: {e}")
    return []


def _tree_to_dict(tree, node_id: int = 0) -> dict:
    """Serialise a sklearn DecisionTreeClassifier to a JSON-safe nested dict."""
    left  = int(tree.children_left[node_id])
    right = int(tree.children_right[node_id])
    if left == -1:           # leaf
        v = tree.value[node_id][0]
        prob = float(v[1] / v.sum()) if v.sum() > 0 else 0.5
        return {"leaf": True, "prob": prob}
    return {
        "feature":   int(tree.feature[node_id]),
        "threshold": float(tree.threshold[node_id]),
        "left":      _tree_to_dict(tree, left),
        "right":     _tree_to_dict(tree, right),
    }


def _score_tree(node: dict, x: list[float]) -> float:
    while not node.get("leaf"):
        node = node["left"] if x[node["feature"]] <= node["threshold"] else node["right"]
    return float(node["prob"])


def _score_logistic(coef: list[float], intercept: float, x: list[float]) -> float:
    z = intercept + sum(c * v for c, v in zip(coef, x))
    z = max(min(z, 50), -50)                  # clip for stability
    return 1.0 / (1.0 + math.exp(-z))


def _score_rules(weights: dict, x: list[float]) -> float:
    z = sum(weights.get(k, 0.0) * v for k, v in zip(FEATURES, x))
    z = max(min(z, 50), -50)
    return 1.0 / (1.0 + math.exp(-z))


def _rolling_accuracy(rows: list[dict]) -> dict:
    out = {}
    for w in (7, 14, 30):
        cutoff = datetime.utcnow().date() - timedelta(days=w)
        bucket = []
        for r in rows:
            ea = r.get("evaluated_at")
            if not ea:
                continue
            try:
                d = date.fromisoformat(str(ea)[:10])
            except Exception:
                continue
            if d >= cutoff:
                bucket.append(r)
        if not bucket:
            out[f"{w}d"] = None
            continue
        nhit = sum(1 for r in bucket if r.get("hit"))
        out[f"{w}d"] = round(nhit / len(bucket), 3)
    return out


def train_ensemble() -> dict:
    """Walk-forward train 3 models, save weights + rolling accuracy. Returns weights dict."""
    rows = _fetch_evaluated(limit=2000)
    if len(rows) < MIN_EVALUATED_FOR_TRAINING:
        log.info(f"Training skipped: only {len(rows)} evaluated rows "
                 f"(need {MIN_EVALUATED_FOR_TRAINING}).")
        return {}
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.tree         import DecisionTreeClassifier
        from sklearn.metrics      import accuracy_score
    except Exception as e:
        log.warning(f"sklearn unavailable, training skipped: {e}")
        return {}

    X = np.array([_feature_vector(r) for r in rows], dtype=float)
    y = np.array([1 if r.get("hit") else 0 for r in rows], dtype=int)
    if y.sum() < 5 or (len(y) - y.sum()) < 5:
        log.info(f"Training skipped — class imbalance "
                 f"({int(y.sum())} hits / {int(len(y) - y.sum())} misses).")
        return {}

    split = max(1, int(len(X) * 0.7))
    Xtr, Xte = X[:split], X[split:]
    ytr, yte = y[:split], y[split:]
    if len(Xte) == 0:
        Xte, yte = Xtr, ytr               # degenerate but safe

    lr = LogisticRegression(class_weight="balanced", max_iter=1000)
    lr.fit(Xtr, ytr)
    lr_acc = float(accuracy_score(yte, lr.predict(Xte)))

    dt = DecisionTreeClassifier(max_depth=4, class_weight="balanced", random_state=42)
    dt.fit(Xtr, ytr)
    dt_acc = float(accuracy_score(yte, dt.predict(Xte)))

    # Weighted-rule baseline: correlation of each feature with the label
    corrs = []
    for j in range(X.shape[1]):
        col = Xtr[:, j]
        if float(col.std()) < 1e-9:
            corrs.append(0.0); continue
        corrs.append(float(np.corrcoef(col, ytr)[0, 1]))
    rule_weights = {FEATURES[j]: corrs[j] for j in range(len(FEATURES))}
    rule_acc = float(accuracy_score(
        yte,
        [int(_score_rules(rule_weights, list(Xte[i])) > 0.5) for i in range(len(Xte))]))

    coef_lr, int_lr = list(map(float, lr.coef_[0])), float(lr.intercept_[0])
    tree_dict = _tree_to_dict(dt.tree_)

    # Ensemble on held-out
    ens_preds = []
    for i in range(len(Xte)):
        x = list(Xte[i])
        p = (_score_logistic(coef_lr, int_lr, x)
             + _score_tree(tree_dict, x)
             + _score_rules(rule_weights, x)) / 3
        ens_preds.append(1 if p > 0.5 else 0)
    ens_acc = float(accuracy_score(yte, ens_preds))

    weights = {
        "logistic":   {"coef": coef_lr, "intercept": int_lr},
        "tree":       tree_dict,
        "rules":      rule_weights,
        "features":   FEATURES,
        "trained_n":  int(len(Xtr)),
        "tested_n":   int(len(Xte)),
        "acc":        {"logistic": lr_acc, "tree": dt_acc,
                       "rules":    rule_acc, "ensemble": ens_acc},
        "trained_at": datetime.utcnow().isoformat(),
    }
    rolling = _rolling_accuracy(rows)
    saved = mldb.save_model_state(weights, rolling)
    log.info(f"Trained. ensemble_acc={ens_acc:.2f} on {len(Xte)} held-out  "
             f"(lr={lr_acc:.2f}  tree={dt_acc:.2f}  rules={rule_acc:.2f})  saved={saved}")
    return weights


# ── Live scoring (pure Python, no sklearn at runtime) ────────────────

def score_prediction(pred: dict) -> float:
    """Return ensemble confidence (0–100) for a candidate pick.
    Cold start / shadow mode → returns the engine's rule-based win_prob unchanged."""
    state   = mldb.get_model_state()
    weights = (state or {}).get("weights") or {}
    if not weights or weights.get("shadow"):
        return float(pred.get("win_prob") or 50)

    x = _feature_vector(_pred_to_row(pred))
    try:
        lg = weights["logistic"]
        p_lr = _score_logistic(lg["coef"], lg["intercept"], x)
    except Exception:
        p_lr = float(pred.get("win_prob") or 50) / 100.0
    try:
        p_dt = _score_tree(weights["tree"], x)
    except Exception:
        p_dt = p_lr
    try:
        p_rl = _score_rules(weights.get("rules", {}), x)
    except Exception:
        p_rl = p_lr
    return round((p_lr + p_dt + p_rl) / 3 * 100, 1)
