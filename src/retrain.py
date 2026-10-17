"""Retraining trigger with a promotion gate.

When enough human-reviewed labels exist (config.RETRAIN_MIN_LABELS), retrain on
train.csv + reviewed messages, then compare old vs new model:
  - held-out test macro-F1 must not drop by more than config.PROMOTION_MAX_F1_DROP (no regression)
  - shifted_eval (never trained on, different phrasings) shows whether we adapted to the new tactics
Only if the gate passes is the new model promoted; the old one is kept in models/versions/.

Usage:
    python src/retrain.py            # uses labels from the monitoring database
    python src/retrain.py --force    # ignore the minimum-label rule (demo)
"""
import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, recall_score

from src import config
from src.monitor import connect, init_db
from src.review import labelled
from src.text import tokens
from src.train import build_pipeline


def _scores(pipe, df):
    p = np.where(pipe.predict_proba(df.text)[:, 1] >= 0.5, "scam", "safe")
    return {"accuracy": round(accuracy_score(df.label, p), 4),
            "macro_f1": round(f1_score(df.label, p, average="macro"), 4),
            "scam_recall": round(recall_score(df.label, p, pos_label="scam"), 4)}


def _reference(bundle, test):
    """Recompute drift reference stats for the promoted model (from the held-out test set)."""
    from src.model import ScamModel
    m = ScamModel.__new__(ScamModel)
    m.pipeline, m.vocab, m.version = bundle["pipeline"], bundle["vocab"], bundle["version"]
    preds = m.predict(test.text.tolist())
    n = len(preds)
    return {"model_version": m.version, "source": "held-out test set",
            "mean_confidence": round(float(np.mean([p["confidence"] for p in preds])), 4),
            "mean_oov_share": round(float(np.mean([p["oov_share"] for p in preds])), 4),
            "unsure_share": round(sum(p["verdict"] == "unsure" for p in preds) / n, 4),
            "lang_mix": {k: round(v / n, 4) for k, v in Counter(p["lang"] for p in preds).items()}}


def retrain(force: bool = False) -> dict:
    init_db()
    new = pd.DataFrame(labelled())
    if len(new) < config.RETRAIN_MIN_LABELS and not force:
        return {"status": "skipped", "reason": f"only {len(new)} reviewed labels (need {config.RETRAIN_MIN_LABELS})"}
    if new.empty:
        return {"status": "skipped", "reason": "no reviewed labels"}

    train = pd.read_csv(config.DATA_DIR / "train.csv")
    test = pd.read_csv(config.DATA_DIR / "test.csv")
    shifted = pd.read_csv(config.DATA_DIR / "shifted.csv")
    shifted_eval = shifted[shifted.split == "shifted_eval"]

    old = joblib.load(config.MODEL_PATH)
    extra = pd.DataFrame({"text": new.text_masked, "label": new.review_label})
    X = pd.concat([train.text, extra.text], ignore_index=True)
    y = (pd.concat([train.label, extra.label], ignore_index=True) == "scam").astype(int)
    pipe = build_pipeline(old.get("C", 4.0)).fit(X, y)

    before = {"test": _scores(old["pipeline"], test), "shifted_eval": _scores(old["pipeline"], shifted_eval)}
    after = {"test": _scores(pipe, test), "shifted_eval": _scores(pipe, shifted_eval)}
    drop = before["test"]["macro_f1"] - after["test"]["macro_f1"]
    promoted = drop <= config.PROMOTION_MAX_F1_DROP

    version = "v" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-rt"
    result = {"status": "promoted" if promoted else "rejected", "old_version": old["version"], "new_version": version,
              "n_new_labels": int(len(extra)), "label_mix": extra.label.value_counts().to_dict(),
              "before": before, "after": after, "test_macro_f1_drop": round(drop, 4),
              "gate": f"test macro-F1 drop <= {config.PROMOTION_MAX_F1_DROP}"}

    if promoted:
        config.VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(config.MODEL_PATH, config.VERSIONS_DIR / f"{old['version']}.joblib")
        vocab = {t for s in X for t in tokens(s)}
        bundle = {"pipeline": pipe, "version": version, "vocab": vocab, "C": old.get("C", 4.0)}
        joblib.dump(bundle, config.MODEL_PATH)
        config.REFERENCE_PATH.write_text(json.dumps(_reference(bundle, test), indent=2), encoding="utf-8")

    with connect() as con:
        con.execute("INSERT INTO retrain_log (ts, old_version, new_version, n_new_labels, promoted, details) VALUES (?,?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), old["version"], version, len(extra), int(promoted), json.dumps(result)))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    print(json.dumps(retrain(ap.parse_args().force), indent=2))
