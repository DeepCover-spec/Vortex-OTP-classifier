"""Prediction logging, drift detection and alerts (SQLite, no extra services).

    from src import monitor
    monitor.init_db()
    pid = monitor.log_prediction(text, result, source="api")   # result = one dict from ScamModel.predict
    status = monitor.drift_status()                            # signals, drift_active, reasons
    monitor.history()                                          # rolling windows for the dashboard chart

Drift signals (each compared with models/reference.json, built from the held-out test set):
 1. mean_oov_share  - share of words never seen in training rises (new wording, new language mix)
 2. mean_confidence - the model becomes less sure
 3. unsure_share    - more messages fall into the "unsure" band
 4. lang_mix_shift  - total-variation distance between the recent language mix and the reference mix
Drift is active when DRIFT_MIN_SIGNALS of the 4 breach their thresholds.

Privacy: only MASKED text is stored (codes, phone numbers and amounts replaced), plus a hash.

Usage:
    python src/monitor.py --calibrate     # replay test vs shifted, print signal values and suggested thresholds
    python src/monitor.py --status        # print the current drift status from the database
"""
import argparse
import hashlib
import json
import re
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config

SIGNALS_ABOVE = ("mean_oov_share", "unsure_share", "lang_mix_shift")   # alert when value is above threshold
SIGNALS_BELOW = ("mean_confidence",)                                   # alert when value is below threshold


# ---------------------------------------------------------------- storage
@contextmanager
def connect():
    """Open the database, commit on success, and always close the connection."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, ts TEXT, model_version TEXT,
            text_masked TEXT, text_hash TEXT, lang TEXT, n_tokens INTEGER, oov_share REAL,
            scam_prob REAL, confidence REAL, verdict TEXT, drift_active INTEGER, source TEXT,
            review_status TEXT DEFAULT 'none', review_label TEXT, reviewed_at TEXT);
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, message TEXT, signals TEXT);
        CREATE TABLE IF NOT EXISTS retrain_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, old_version TEXT, new_version TEXT,
            n_new_labels INTEGER, promoted INTEGER, details TEXT);
        """)


def reset_db():
    """Demo only: clear everything."""
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    init_db()


def mask(text: str) -> str:
    t = re.sub(r"\b\d{4,8}\b", "<CODE>", str(text))
    t = re.sub(r"\b0\d{1,2}[x\d]?[-\s]?[x\d]{3}[-\s]?[x\d]{4}\b", "<PHONE>", t, flags=re.I)
    return re.sub(r"\d[\d,]{2,}", "<NUM>", t)


def log_prediction(text: str, result: dict, source: str = "api", drift_active: bool = False) -> str:
    """Store one prediction. Unsure verdicts, and everything seen while drift is active,
    go to the human-review queue."""
    pid = uuid.uuid4().hex[:12]
    review = "pending" if (result["verdict"] == "unsure" or drift_active) else "none"
    with connect() as con:
        con.execute(
            "INSERT INTO predictions (id, ts, model_version, text_masked, text_hash, lang, n_tokens, oov_share, scam_prob,"
            " confidence, verdict, drift_active, source, review_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, datetime.now().isoformat(timespec="seconds"), result.get("model_version"), mask(text),
             hashlib.sha256(str(text).encode()).hexdigest()[:16], result.get("lang"), len(str(text).split()),
             result["oov_share"], result["scam_prob"], result["confidence"], result["verdict"], int(drift_active), source, review))
    return pid


# ---------------------------------------------------------------- drift signals
def load_reference() -> dict:
    return json.loads(config.REFERENCE_PATH.read_text(encoding="utf-8"))


def compute_signals(rows, reference) -> dict:
    """rows: dicts with oov_share, confidence, verdict, lang."""
    n = len(rows)
    if n == 0:
        return {}
    mix = Counter(r["lang"] for r in rows)
    langs = set(mix) | set(reference["lang_mix"])
    tvd = 0.5 * sum(abs(mix.get(l, 0) / n - reference["lang_mix"].get(l, 0)) for l in langs)
    return {
        "mean_oov_share": round(sum(r["oov_share"] for r in rows) / n, 4),
        "mean_confidence": round(sum(r["confidence"] for r in rows) / n, 4),
        "unsure_share": round(sum(r["verdict"] == "unsure" for r in rows) / n, 4),
        "lang_mix_shift": round(tvd, 4),
    }


def evaluate_signals(signals: dict) -> tuple:
    th = config.DRIFT_THRESHOLDS
    breaches = []
    for k in SIGNALS_ABOVE:
        if k in signals and signals[k] > th[k]:
            breaches.append(f"{k} {signals[k]:.3f} > {th[k]:.3f}")
    for k in SIGNALS_BELOW:
        if k in signals and signals[k] < th[k]:
            breaches.append(f"{k} {signals[k]:.3f} < {th[k]:.3f}")
    return len(breaches) >= config.DRIFT_MIN_SIGNALS, breaches


def recent(n=config.DRIFT_WINDOW):
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM predictions ORDER BY seq DESC LIMIT ?", (n,))][::-1]


def drift_status(window: int = config.DRIFT_WINDOW, raise_alert: bool = True) -> dict:
    rows = recent(window)
    ref = load_reference()
    signals = compute_signals(rows, ref)
    # only judge a FULL window: small samples are noisy and cause false alarms
    active, breaches = evaluate_signals(signals) if len(rows) >= window else (False, [])
    status = {
        "n_window": len(rows), "window": window, "signals": signals,
        "reference": {k: ref.get(k) for k in ("mean_oov_share", "mean_confidence", "unsure_share")},
        "thresholds": config.DRIFT_THRESHOLDS, "min_signals": config.DRIFT_MIN_SIGNALS,
        "drift_active": active, "reasons": breaches,
        "pending_reviews": pending_count(), "labelled_reviews": labelled_count(),
        "retrain_ready": labelled_count() >= config.RETRAIN_MIN_LABELS,
    }
    if active and raise_alert:
        _alert_once(status)
    return status


def _alert_once(status):
    """Write one alert per drift episode (not one per request)."""
    with connect() as con:
        last = con.execute("SELECT ts FROM alerts WHERE kind='drift' ORDER BY id DESC LIMIT 1").fetchone()
        last_seq = con.execute("SELECT MAX(seq) FROM predictions").fetchone()[0] or 0
        if last:
            n_since = con.execute("SELECT COUNT(*) FROM predictions WHERE ts > ?", (last["ts"],)).fetchone()[0]
            if n_since < status["window"]:
                return
        msg = "Drift detected: " + "; ".join(status["reasons"])
        con.execute("INSERT INTO alerts (ts, kind, message, signals) VALUES (?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), "drift", msg, json.dumps(status["signals"])))
    print(f"[ALERT] {msg} (after prediction #{last_seq})", flush=True)


def alerts(limit=20):
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]


def history(step: int = 25, window: int = config.DRIFT_WINDOW) -> list:
    """Rolling signal values every `step` predictions, for the dashboard line chart."""
    with connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM predictions ORDER BY seq")]
    ref, out = load_reference(), []
    for end in range(max(step, window), len(rows) + 1, step):
        chunk = rows[max(0, end - window):end]
        s = compute_signals(chunk, ref)
        active, _ = evaluate_signals(s)
        out.append({"n": end, "ts": chunk[-1]["ts"], **s, "drift_active": active})
    return out


def pending_count():
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM predictions WHERE review_status='pending'").fetchone()[0]


def labelled_count():
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM predictions WHERE review_status='labelled'").fetchone()[0]


# ---------------------------------------------------------------- threshold calibration
def calibrate():
    """Replay the held-out test set and the shifted set in windows and print each signal, so
    thresholds can be set between the two distributions (written into config.DRIFT_THRESHOLDS by hand)."""
    import pandas as pd
    from src.model import ScamModel
    m, ref = ScamModel(), load_reference()
    w = config.DRIFT_WINDOW
    res = {}
    for name in ("test", "shifted"):
        df = pd.read_csv(config.DATA_DIR / f"{name}.csv").sample(frac=1, random_state=config.SEED)
        preds = m.predict(df.text.tolist())
        res[name] = [compute_signals(preds[i:i + w], ref) for i in range(0, len(preds) - w + 1, w)]
    print(f"Signal values per window of {w} (min / mean / max):")
    for k in ("mean_oov_share", "mean_confidence", "unsure_share", "lang_mix_shift"):
        t = [s[k] for s in res["test"]]; s_ = [s[k] for s in res["shifted"]]
        if k in SIGNALS_BELOW:
            suggest = (min(t) + max(s_)) / 2
        else:
            suggest = (max(t) + min(s_)) / 2
        print(f"  {k:16s} test {min(t):.3f} / {sum(t)/len(t):.3f} / {max(t):.3f}   shifted {min(s_):.3f} / {sum(s_)/len(s_):.3f} / {max(s_):.3f}"
              f"   suggested threshold {suggest:.3f}   (current {config.DRIFT_THRESHOLDS[k]})")
    fa = sum(evaluate_signals(s)[0] for s in res["test"]); hit = sum(evaluate_signals(s)[0] for s in res["shifted"])
    print(f"With current thresholds: drift flagged in {fa}/{len(res['test'])} test windows (false alarms) "
          f"and {hit}/{len(res['shifted'])} shifted windows (detections).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.calibrate:
        calibrate()
    if a.status:
        init_db(); print(json.dumps(drift_status(raise_alert=False), indent=2))
