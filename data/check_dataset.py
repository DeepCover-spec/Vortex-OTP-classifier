"""Sanity checks for the generated dataset. Writes reports/dataset_report.md.

Usage:
    python data/check_dataset.py --data data/processed --report reports/dataset_report.md

Checks:
 1. Size and balance: rows per split, per language x label (each language should be near 50/50).
 2. Leakage: no duplicate text (after normalising digits/case/punctuation) within or across splits,
    and no template_id shared between train and test (test wording is truly unseen).
 3. Shortcuts: for common surface cues (codes, links, phones, urgency, "never share", script),
    the scam share when the cue is present should be far from 0% or 100%.
    Also lists any single word that predicts the label almost perfectly with high support.
 4. Learnability: GroupKFold CV on train (grouped by template), then held-out test and shifted.
 5. Drift signal: confidence and unseen-word share should differ between test and shifted.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, recall_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline, make_union


def norm_key(t):
    t = re.sub(r"\d", "0", str(t).lower())
    t = re.sub(r"[^\w\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


CUES = {
    "has 6-digit code": lambda s: bool(re.search(r"\b\d{6}\b", s)),
    "has link": lambda s: "http" in s.lower(),
    "has phone (masked)": lambda s: "xxx" in s.lower(),
    "mentions OTP": lambda s: "otp" in s.lower(),
    "urgency (act now/urgent/ikmanata/udane)": lambda s: bool(re.search(r"act now|urgent|ikmanata|udane|do this today", s.lower())),
    "says don't share / never share": lambda s: bool(re.search(r"never share|do not share|don't share|kiyanna epa|share pannadheenga|sollaadheenga|பகிர வேண்டாம்|නොකියන්න", s.lower())),
    "Sinhala script": lambda s: bool(re.search(r"[඀-෿]", s)),
    "Tamil script": lambda s: bool(re.search(r"[஀-௿]", s)),
    "emoji / !!": lambda s: bool(re.search(r"[🙏⚠😊]|!!", s)),
}


def model():
    return make_pipeline(
        make_union(TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, min_df=2),
                   TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)),
        LogisticRegression(C=4, max_iter=3000, class_weight="balanced"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/processed")
    ap.add_argument("--report", default="reports/dataset_report.md")
    a = ap.parse_args()
    d = Path(a.data)
    tr, te, sh = (pd.read_csv(d / f"{n}.csv") for n in ("train", "test", "shifted"))
    L = []
    w = L.append

    w("# Dataset report\n")
    w("## 1. Size and balance\n")
    w("| split | rows | scam | safe |\n|---|---|---|---|")
    for n, df in (("train", tr), ("test", te), ("shifted", sh)):
        w(f"| {n} | {len(df)} | {(df.label == 'scam').sum()} | {(df.label == 'safe').sum()} |")
    w("\nScam share per language (should be close to 0.5 so the script never predicts the label):\n")
    w("| lang | train rows | train scam share | test rows | test scam share | shifted rows |\n|---|---|---|---|---|---|")
    for lang in ["en", "singlish", "si", "ta", "tanglish"]:
        a1, b1, c1 = tr[tr.lang == lang], te[te.lang == lang], sh[sh.lang == lang]
        w(f"| {lang} | {len(a1)} | {(a1.label == 'scam').mean():.2f} | {len(b1)} | {(b1.label == 'scam').mean():.2f} | {len(c1)} |")
    w("\nSubtypes (train): " + ", ".join(f"{k} {v}" for k, v in tr.subtype.value_counts().items()))

    w("\n## 2. Leakage\n")
    keys = {n: set(df.text.map(norm_key)) for n, df in (("train", tr), ("test", te), ("shifted", sh))}
    dup_within = {n: len(df) - df.text.map(norm_key).nunique() for n, df in (("train", tr), ("test", te), ("shifted", sh))}
    w(f"- Duplicates within a split (normalised text): {dup_within}")
    w(f"- Train/test overlap: {len(keys['train'] & keys['test'])} · train/shifted: {len(keys['train'] & keys['shifted'])} · test/shifted: {len(keys['test'] & keys['shifted'])}")
    syn_tr = set(tr.template_id[tr.template_id != 'uci']); syn_te = set(te.template_id[te.template_id != 'uci'])
    w(f"- Templates shared between train and test: {len(syn_tr & syn_te)} (of {len(syn_te)} test templates)")
    rv, ev = sh[sh.split == "shifted_review"], sh[sh.split == "shifted_eval"]
    w(f"- Shifted templates shared between review and eval: {len(set(rv.template_id) & set(ev.template_id))} "
      f"(only where a language has a single phrasing) · review rows {len(rv)}, eval rows {len(ev)}")

    w("\n## 3. Shortcut check (train)\n")
    w("A cue is a shortcut if its scam share is near 0 or 1 while it is common. Base scam share: "
      f"{(tr.label == 'scam').mean():.2f}.\n")
    w("| cue | present in | scam share when present |\n|---|---|---|")
    for k, f in CUES.items():
        x = tr.text.map(f)
        w(f"| {k} | {x.mean():.0%} | {(tr.label[x] == 'scam').mean():.2f} |")
    cnt_s, cnt_a = Counter(), Counter()
    for t, l in zip(tr.text, tr.label):
        for tok in set(re.findall(r"\w\w+", t.lower())):
            cnt_a[tok] += 1; cnt_s[tok] += l == "scam"
    pure = sorted([(tok, n, cnt_s[tok] / n) for tok, n in cnt_a.items() if n >= 60 and (cnt_s[tok] / n > 0.97 or cnt_s[tok] / n < 0.03)],
                  key=lambda z: -z[1])[:15]
    w("\nWords in 60+ messages that are >97% one class (expected: genuine scam/benign vocabulary, not artefacts):\n")
    w(", ".join(f"`{t}` ({n}, {p:.2f})" for t, n, p in pure) or "none")

    w("\n## 4. Learnability (TF-IDF word + char n-grams, logistic regression)\n")
    m = model()
    cv = cross_val_predict(m, tr.text, tr.label, groups=tr.template_id, cv=GroupKFold(5))
    w(f"- GroupKFold(5) by template on train: accuracy {accuracy_score(tr.label, cv):.3f}, macro-F1 {f1_score(tr.label, cv, average='macro'):.3f}")
    m.fit(tr.text, tr.label)
    w("\n| set | accuracy | macro-F1 | scam recall | false alarms on genuine bank msgs |\n|---|---|---|---|---|")
    for n, df in (("test", te), ("shifted", sh), ("shifted_eval", ev)):
        p = m.predict(df.text)
        gen = df.subtype.isin(["bank_genuine", "shift_genuine"])
        fa = (p[gen.values] == "scam").mean()
        w(f"| {n} | {accuracy_score(df.label, p):.3f} | {f1_score(df.label, p, average='macro'):.3f} | "
          f"{recall_score(df.label, p, pos_label='scam'):.3f} | {fa:.3f} |")
    pt = m.predict(te.text)
    w("\nTest accuracy by language: " + ", ".join(f"{k} {v:.2f}" for k, v in te.assign(ok=pt == te.label).groupby("lang").ok.mean().items()))
    w("\nTest accuracy by subtype: " + ", ".join(f"{k} {v:.2f}" for k, v in te.assign(ok=pt == te.label).groupby("subtype").ok.mean().items()))

    w("\n## 5. Drift signal (should separate test from shifted)\n")
    vocab = set(m.steps[0][1].transformer_list[0][1].vocabulary_)
    oov = lambda df: df.text.map(lambda s: np.mean([t not in vocab for t in re.findall(r"\w\w+", s.lower())] or [0])).mean()
    conf = lambda df: m.predict_proba(df.text).max(1).mean()
    w("| set | mean confidence | unseen-word share |\n|---|---|---|")
    for n, df in (("test", te), ("shifted", sh)):
        w(f"| {n} | {conf(df):.3f} | {oov(df):.3f} |")

    out = Path(a.report); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
