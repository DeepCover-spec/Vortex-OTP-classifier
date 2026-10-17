"""End-to-end drift demo: normal traffic -> scammers change tactics -> alert -> human review -> retrain.

Usage (from the repo root, after python data/generate.py and python src/train.py):
    python scripts/run_shift_demo.py            # runs in-process, no server needed
    python scripts/run_shift_demo.py --fast     # fewer messages, for a quick rehearsal

What it shows:
 1. 200 messages from the held-out test set   -> signals near reference, no alert
 2. 400 messages in the new style (shifted_review: new senders, SL-UDI and "reference number" pretexts,
    Tanglish surge) -> unseen-word share and unsure share rise, confidence and language mix shift,
    drift ALERT fires, safe fallback widens the unsure band, messages go to the review queue
 3. Reviewers label the queued messages (simulated with the true labels)
 4. Retraining trigger -> promotion gate -> new model
 5. shifted_eval (never trained on, different phrasings) before vs after retraining
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src import config, monitor, review
from src.model import ScamModel
from src.retrain import retrain


def line(t=""):
    print(("\n== " + t + " " + "=" * max(0, 70 - len(t))) if t else "")


def show(status):
    s = status["signals"]
    print(f"   window={status['n_window']:3d}  OOV={s.get('mean_oov_share', 0):.3f}  conf={s.get('mean_confidence', 0):.3f}  "
          f"unsure={s.get('unsure_share', 0):.3f}  lang_shift={s.get('lang_mix_shift', 0):.3f}  "
          f"DRIFT={'YES' if status['drift_active'] else 'no '}  pending_review={status['pending_reviews']}")


def stream(model, df, source, truth, every=50):
    status = monitor.drift_status(raise_alert=False)
    for i, (text, label) in enumerate(zip(df.text, df.label), 1):
        res = model.predict([text], drift_active=status["drift_active"])[0]
        pid = monitor.log_prediction(text, res, source=source, drift_active=status["drift_active"])
        truth[pid] = label
        if i % 10 == 0:
            status = monitor.drift_status()
        if i % every == 0:
            show(status)
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    n_test, n_shift = (100, 200) if a.fast else (200, 400)

    # keep the original model safe so the demo can be re-run
    backup = config.MODEL_PATH.with_suffix(".demo-backup")
    ref_backup = config.REFERENCE_PATH.with_suffix(".demo-backup")
    shutil.copy(config.MODEL_PATH, backup); shutil.copy(config.REFERENCE_PATH, ref_backup)

    monitor.reset_db()
    model = ScamModel()
    test = pd.read_csv(config.DATA_DIR / "test.csv").sample(n_test, random_state=1)
    shifted = pd.read_csv(config.DATA_DIR / "shifted.csv")
    s_review = shifted[shifted.split == "shifted_review"].sample(frac=1, random_state=1).head(n_shift)
    s_eval = shifted[shifted.split == "shifted_eval"]
    truth = {}

    line(f"1. Launch day: {n_test} normal messages (model {model.version})")
    stream(model, test, "demo_test", truth)

    line(f"2. Scammers change tactics: {len(s_review)} new-style messages")
    status = stream(model, s_review, "demo_shifted", truth)
    for al in monitor.alerts(1):
        print(f"   ALERT at {al['ts']}: {al['message']}")
    print(f"   Response: unsure band widened to {config.T_SAFE_DRIFT}-{config.T_SCAM_DRIFT}, "
          f"unsure users see the 'never share your OTP, call your bank' advice, {status['pending_reviews']} messages queued for review")

    line("3. Human review (simulated with the true labels)")
    # Reviewers label only the new-style traffic. Held-out TEST messages are never labelled or
    # trained on, otherwise the "test score" after retraining would be leaked and meaningless.
    q = [item for item in review.queue(limit=10_000) if item["source"] == "demo_shifted"]
    for item in q:
        review.label(item["id"], truth[item["id"]])
    print(f"   Reviewers labelled {len(q)} new-style messages (test-set messages are never used for training)")

    line("4. Retraining trigger + promotion gate")
    r = retrain(force=False)
    if r["status"] == "skipped":
        print("  ", r["reason"]); return
    b, af = r["before"], r["after"]
    print(f"   New labels: {r['n_new_labels']} {r['label_mix']}")
    print(f"   Held-out test   macro-F1 {b['test']['macro_f1']:.3f} -> {af['test']['macro_f1']:.3f}   (gate: drop <= {config.PROMOTION_MAX_F1_DROP})")
    print(f"   shifted_eval    accuracy {b['shifted_eval']['accuracy']:.3f} -> {af['shifted_eval']['accuracy']:.3f}   "
          f"scam recall {b['shifted_eval']['scam_recall']:.3f} -> {af['shifted_eval']['scam_recall']:.3f}")
    print(f"   Decision: {r['status'].upper()}  ({r['old_version']} -> {r['new_version'] if r['status'] == 'promoted' else 'kept old'})")

    line("5. After retraining: the same kind of new-style traffic (shifted_eval, never trained on)")
    model = ScamModel()
    stream(model, s_eval.sample(frac=1, random_state=2).head(200), "demo_after", truth)

    print(f"\nOriginal model backed up at {backup.name}. To restore it: copy it over models/model.joblib "
          f"(and {ref_backup.name} over models/reference.json), or simply run python src/train.py again.")


if __name__ == "__main__":
    main()
