"""Evaluate the trained model on the held-out test set and the shifted (drift) set.

Usage (from the repo root):
    python src/evaluate.py

Writes:
    reports/metrics.json            all numbers below, for the README and the deck
    reports/confusion_test.png      confusion matrix on the held-out test set
    reports/confusion_shifted.png   confusion matrix on the shifted set
    models/reference.json           reference statistics for drift monitoring (from the TEST set,
                                    because training-set confidence is inflated)
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score

from src import config
from src.model import ScamModel

KEYWORD_RULE = re.compile(r"(otp|code|pin|reference|කේත|குறியீ).{0,60}(reply|send|share|tell|read|kiyanna|ewanna|sollunga|anupunga|එවන්න|කියන්න|அனுப்ப|சொல்)|"
                          r"(reply|send|share|tell|read|kiyanna|ewanna|sollunga|anupunga|එවන්න|කියන්න|அனுப்ப|சொல்).{0,60}(otp|code|pin|reference|කේත|குறியீ)", re.I)


def scores(y_true, y_pred, subtype):
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    genuine = np.asarray(subtype.isin(["bank_genuine", "shift_genuine"]))
    return {
        "n": int(len(y_true)),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro"), 4),
        "scam_recall": round(recall_score(y_true, y_pred, pos_label="scam", zero_division=0), 4),
        "false_alarm_rate_genuine_bank": round(float((y_pred[genuine] == "scam").mean()), 4) if genuine.any() else None,
        "false_alarm_rate_all_safe": round(float((y_pred[y_true == "safe"] == "scam").mean()), 4),
    }


def plot_cm(y_true, y_pred, title, path):
    cm = confusion_matrix(y_true, y_pred, labels=["safe", "scam"])
    fig, ax = plt.subplots(figsize=(3.6, 3.2), dpi=150)
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i, j], ha="center", va="center", color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=12)
    ax.set_xticks([0, 1], ["safe", "scam"]); ax.set_yticks([0, 1], ["safe", "scam"])
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual"); ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def main():
    m = ScamModel()
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {"model_version": m.version}

    for name in ("test", "shifted"):
        df = pd.read_csv(config.DATA_DIR / f"{name}.csv")
        preds = m.predict(df.text.tolist())
        label = np.array([p["label"] for p in preds])
        verdict = np.array([p["verdict"] for p in preds])

        r = {"model": scores(df.label, label, df.subtype)}
        r["baseline_always_safe"] = scores(df.label, np.array(["safe"] * len(df)), df.subtype)
        r["baseline_keyword_rule"] = scores(df.label, np.array(["scam" if KEYWORD_RULE.search(t) else "safe" for t in df.text]), df.subtype)
        r["by_language"] = {k: round(float(v), 4) for k, v in pd.Series(label == df.label.values).groupby(df.lang.values).mean().items()}
        r["by_subtype"] = {k: round(float(v), 4) for k, v in pd.Series(label == df.label.values).groupby(df.subtype.values).mean().items()}
        r["verdicts"] = {k: round(v / len(df), 4) for k, v in Counter(verdict).items()}
        # how often a confident verdict (not unsure) is wrong: what the user actually experiences
        sure = verdict != "unsure"
        r["confident_verdict_error_rate"] = round(float((verdict[sure] != df.label.values[sure]).mean()), 4) if sure.any() else None
        r["mean_confidence"] = round(float(np.mean([p["confidence"] for p in preds])), 4)
        r["mean_oov_share"] = round(float(np.mean([p["oov_share"] for p in preds])), 4)
        if name == "shifted":
            for part in ("shifted_review", "shifted_eval"):
                mask = (df.split == part).values
                r[part] = scores(df.label[mask], label[mask], df.subtype[mask])
        results[name] = r
        plot_cm(df.label, label, f"{name} set (n={len(df)})", config.REPORTS_DIR / f"confusion_{name}.png")

        if name == "test":
            ref = {"model_version": m.version, "source": "held-out test set",
                   "mean_confidence": r["mean_confidence"], "mean_oov_share": r["mean_oov_share"],
                   "unsure_share": r["verdicts"].get("unsure", 0.0),
                   "lang_mix": {k: round(v / len(preds), 4) for k, v in Counter(p["lang"] for p in preds).items()}}
            config.REFERENCE_PATH.write_text(json.dumps(ref, indent=2), encoding="utf-8")

    (config.REPORTS_DIR / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # readable summary for the terminal / README
    print(f"Model {m.version}\n")
    print(f"{'set':10s} {'acc':>6s} {'macroF1':>8s} {'scamRec':>8s} {'FA bank':>8s} {'conf':>6s} {'OOV':>6s} {'unsure':>7s}")
    for name in ("test", "shifted"):
        r, s = results[name], results[name]["model"]
        print(f"{name:10s} {s['accuracy']:6.3f} {s['macro_f1']:8.3f} {s['scam_recall']:8.3f} {s['false_alarm_rate_genuine_bank']:8.3f} "
              f"{r['mean_confidence']:6.3f} {r['mean_oov_share']:6.3f} {r['verdicts'].get('unsure', 0):7.3f}")
    t = results["test"]
    print(f"\nTest baselines  always-safe acc {t['baseline_always_safe']['accuracy']:.3f} | keyword rule acc {t['baseline_keyword_rule']['accuracy']:.3f}, "
          f"F1 {t['baseline_keyword_rule']['macro_f1']:.3f}")
    print("Test accuracy by language:", t["by_language"])
    print("Test accuracy by subtype: ", t["by_subtype"])
    print("Confident-verdict error rate: test", t["confident_verdict_error_rate"], "| shifted", results["shifted"]["confident_verdict_error_rate"])
    print(f"\nWrote reports/metrics.json, reports/confusion_*.png, models/reference.json")


if __name__ == "__main__":
    main()
