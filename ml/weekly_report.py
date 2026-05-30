"""
ml/weekly_report.py — Sunday performance digest.

Pulls the last 7 days of evaluated predictions from Supabase, computes a quick
performance snapshot, surfaces failure patterns, and sends a single combined
email + Telegram message via notifier.
"""

from datetime import date, timedelta

import requests

from applog import get_logger
import mldb
import notifier

log = get_logger("aarya_weekly")


def _fetch_last_week_evaluated() -> list[dict]:
    url, key = mldb._creds()
    if not url or not key:
        return []
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    try:
        r = requests.get(
            f"{url}/rest/v1/predictions?status=eq.evaluated"
            f"&evaluated_at=gte.{cutoff}&select=*",
            headers=mldb._headers(key), timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"fetch last week error: {e}")
    return []


def _failure_patterns(rows: list[dict]) -> list[str]:
    """Buckets with hit_rate < 40 % on n ≥ 8 are flagged."""
    buckets = {
        "RSI > 70 at entry":         lambda r: (r.get("rsi") or 0) > 70,
        "Minervini < 6":             lambda r: (r.get("minervini") or 0) < 6,
        "Price under $5":            lambda r: 0 < (r.get("price") or 999) < 5,
        "Extended > 8 % above 50":   lambda r: ((r.get("features") or {}).get("extension_pct") or 0) > 8,
        "RS < 1.0 (lagging market)": lambda r: (r.get("rs_score") or 1.0) < 1.0,
    }
    out = []
    for name, fn in buckets.items():
        sub = [r for r in rows if fn(r)]
        if len(sub) < 8:
            continue
        nhit = sum(1 for r in sub if r.get("hit"))
        rate = nhit / len(sub)
        if rate < 0.40:
            out.append(f"{name}: {rate*100:.0f}% hit on {len(sub)} picks → down-weighting")
    return out


def _per_track_stats(rows: list[dict]) -> list[dict]:
    """Break out hit-rate by prediction track (stock/penny/crypto/options)."""
    buckets: dict[str, list] = {}
    for r in rows:
        payload = r.get("payload") or r
        track   = payload.get("track", "penny" if payload.get("is_penny") else "stock")
        buckets.setdefault(track, []).append(r)
    out = []
    for track, items in sorted(buckets.items()):
        n_t   = len(items)
        n_hit = sum(1 for i in items if i.get("hit"))
        rate  = n_hit / n_t
        warn  = " ⚠" if rate < 0.50 and n_t >= 20 else ""
        out.append({"track": track, "n": n_t, "hits": n_hit,
                    "rate": rate, "warn": warn})
    return out


def send_weekly_report(tg_chat_ids: list[str] | None = None) -> tuple[bool, str]:
    rows = _fetch_last_week_evaluated()
    if not rows:
        log.info("Weekly report: no evaluated predictions in the last week — skipping.")
        return False, "no data"

    n      = len(rows)
    n_hit  = sum(1 for r in rows if r.get("hit"))
    hit_rate = n_hit / n
    avg_ret  = sum((r.get("outcome_pct") or 0) for r in rows) / n
    best  = sorted(rows, key=lambda r: r.get("outcome_pct") or 0, reverse=True)[:3]
    worst = sorted(rows, key=lambda r: r.get("outcome_pct") or 0)[:3]
    patterns = _failure_patterns(rows)
    track_stats = _per_track_stats(rows)

    # ── HTML email ────────────────────────────────────────────────
    def li(r):
        return (f"<div style='color:#fff;font-size:13px;margin:3px 0;'>"
                f"<b>{r.get('ticker','?')}</b>: "
                f"{(r.get('outcome_pct') or 0):+.1f}%</div>")

    # Per-track table
    track_rows_html = "".join(
        f"<tr><td style='padding:4px 10px;color:#C9D6E3;'>{ts['track']}</td>"
        f"<td style='padding:4px 10px;text-align:center;'>{ts['n']}</td>"
        f"<td style='padding:4px 10px;text-align:center;'>{ts['hits']}</td>"
        f"<td style='padding:4px 10px;text-align:center;"
        f"color:{'#FF4D6A' if ts['rate'] < 0.5 else '#1D9E75'};font-weight:700;'>"
        f"{ts['rate']*100:.1f}%{ts['warn']}</td></tr>"
        for ts in track_stats
    )
    track_html = (
        "<h4 style='color:#4A7FA5;margin:18px 0 6px;'>📊 Per-Track Accuracy</h4>"
        "<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
        "<tr style='background:#121e30;'>"
        "<th style='padding:4px 10px;text-align:left;color:#4A7FA5;'>Track</th>"
        "<th style='padding:4px 10px;color:#4A7FA5;'>Picks</th>"
        "<th style='padding:4px 10px;color:#4A7FA5;'>Hits</th>"
        "<th style='padding:4px 10px;color:#4A7FA5;'>Hit-Rate</th></tr>"
        + track_rows_html + "</table>"
    ) if track_stats else ""

    pat_html = ""
    if patterns:
        pat_html = ("<h4 style='color:#FFB340;margin:18px 0 6px;'>&#9888; Failure patterns this week</h4>"
                    "<ul style='color:#C9D6E3;font-size:13px;padding-left:18px;'>"
                    + "".join(f"<li>{p}</li>" for p in patterns) + "</ul>")

    body = (
        f"<div style='font-size:13px;color:#C9D6E3;margin-bottom:14px;'>"
        f"Weekly hit rate: <b style='color:#00C48C;font-size:16px;'>{hit_rate*100:.1f}%</b> "
        f"on <b>{n}</b> evaluated picks  ·  "
        f"Avg return: <b style='color:{'#00C48C' if avg_ret >= 0 else '#FF4D6A'};'>{avg_ret:+.1f}%</b></div>"
        + track_html
        + f"<h4 style='color:#00C48C;margin:18px 0 6px;'>&#127942; Top winners</h4>"
        + "".join(li(r) for r in best)
        + f"<h4 style='color:#FF4D6A;margin:18px 0 6px;'>&#128201; Worst picks</h4>"
        + "".join(li(r) for r in worst)
        + pat_html
    )
    html = notifier._wrap(
        f"Weekly Performance — {hit_rate*100:.0f}% hit rate",
        "#1D9E75" if hit_rate >= 0.55 else "#FFB340",
        body,
    )
    subj = (f"[Aarya] Weekly Performance — "
            f"{hit_rate*100:.0f}% hit, {avg_ret:+.1f}% avg")
    ok, msg = notifier.send_alert(subj, html)
    log.info(f"Weekly email: {'OK' if ok else msg}")

    # ── Telegram ──────────────────────────────────────────────────
    track_tg = "\n".join(
        f"  {ts['track']}: {ts['rate']*100:.1f}% ({ts['hits']}/{ts['n']}){ts['warn']}"
        for ts in track_stats
    )
    tg_msg = (
        f"Weekly Performance\n"
        f"Hit rate: <b>{hit_rate*100:.1f}%</b> on {n} picks\n"
        f"Avg return: <b>{avg_ret:+.1f}%</b>\n"
        + (f"\nPer track:\n{track_tg}\n" if track_tg else "")
        + "\nTop: "
        + ", ".join(f"{r.get('ticker','?')} {(r.get('outcome_pct') or 0):+.0f}%" for r in best) + "\n"
        + "Bottom: "
        + ", ".join(f"{r.get('ticker','?')} {(r.get('outcome_pct') or 0):+.0f}%" for r in worst)
    )
    if patterns:
        tg_msg += "\n\nFailure patterns:\n" + "\n".join(f"- {p}" for p in patterns)

    for cid in (tg_chat_ids or []):
        try:
            notifier.send_telegram(tg_msg, cid)
        except Exception as e:
            log.warning(f"weekly TG -> {cid}: {e}")

    return ok, msg
