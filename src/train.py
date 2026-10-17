"""Train the scam classifier and save models/model.joblib + models/meta.json.

Usage (from the repo root):
    python src/train.py              # default settings
    python src/train.py --C 2 --cv   # try another C and print grouped cross-validation

Model: TF-IDF word 1-2 grams + character 2-5 grams (char n-grams handle Sinhala/Tamil script,
romanised spellings and typos) -> logistic regression with balanced classes, wrapped in
CalibratedClassifierCV so scam_prob is a meaningful probability (the monitor relies on it).
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so "src" imports work when run as a script

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline, FeatureUnion

from src import config
from src.text import normalise, tokens


def build_pipeline(C: float = 4.0) -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(preprocessor=normalise, analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("char", TfidfVectorizer(preprocessor=normalise, analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
    ])
    clf = CalibratedClassifierCV(LogisticRegression(C=C, max_iter=3000, class_weight="balanced"), method="sigmoid", cv=5)
    return Pipeline([("features", features), ("clf", clf)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--C", type=float, default=4.0)
    ap.add_argument("--cv", action="store_true", help="also run GroupKFold cross-validation by template")
    a = ap.parse_args()

    train = pd.read_csv(config.DATA_DIR / "train.csv")
    X, y = train.text, (train.label == "scam").astype(int)

    cv_scores = None
    if a.cv:
        pred = cross_val_predict(build_pipeline(a.C), X, y, groups=train.template_id, cv=GroupKFold(5))
        cv_scores = {"accuracy": round(accuracy_score(y, pred), 4), "macro_f1": round(f1_score(y, pred, average="macro"), 4)}
        print("GroupKFold(5) by template:", cv_scores)

    pipe = build_pipeline(a.C).fit(X, y)
    version = "v" + datetime.now().strftime("%Y%m%d-%H%M")
    vocab = sorted({t for s in X for t in tokens(s)})
    bundle = {"pipeline": pipe, "version": version, "vocab": set(vocab), "C": a.C}

    config.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, config.MODEL_PATH)
    meta = {
        "version": version, "trained_at": datetime.now().isoformat(timespec="seconds"), "C": a.C,
        "n_train": int(len(train)), "n_scam": int(y.sum()), "vocab_size": len(vocab),
        "train_lang_mix": {k: round(v / len(train), 4) for k, v in Counter(train.lang).items()},
        "cv": cv_scores,
    }
    config.META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Saved {config.MODEL_PATH} ({version}), vocab {len(vocab)} words, trained on {len(train)} rows")


if __name__ == "__main__":
    main()
