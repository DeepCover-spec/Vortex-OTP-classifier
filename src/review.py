"""Human-review queue. Unsure predictions, and everything seen while drift is active, wait here
for a person to label them scam or safe. Labels feed the retraining trigger.

    from src import review
    review.queue()                 # pending items (masked text only)
    review.label(pid, "scam")      # store a human label
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.monitor import connect


def queue(limit: int = 50) -> list:
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, ts, text_masked, lang, scam_prob, verdict, drift_active, source FROM predictions "
            "WHERE review_status='pending' ORDER BY seq LIMIT ?", (limit,))]


def label(pid: str, value: str) -> bool:
    if value not in ("scam", "safe"):
        raise ValueError("label must be 'scam' or 'safe'")
    with connect() as con:
        cur = con.execute("UPDATE predictions SET review_status='labelled', review_label=?, reviewed_at=? WHERE id=?",
                          (value, datetime.now().isoformat(timespec="seconds"), pid))
        return cur.rowcount == 1


def labelled() -> list:
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, text_masked, review_label, lang FROM predictions WHERE review_status='labelled'")]
