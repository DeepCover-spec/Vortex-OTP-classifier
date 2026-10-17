"""ScamModel: the only thing the API needs to import.

    from src.model import ScamModel
    m = ScamModel()                       # loads models/model.joblib
    m.predict(["Hela Bank: share the OTP ..."])
    -> [{"label": "scam", "scam_prob": 0.97, "confidence": 0.97, "verdict": "scam",
         "reasons": [...], "oov_share": 0.05, "lang": "en", "model_version": "v2026..."}]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np

from src import config
from src.text import detect_lang, explain, safe_signs, tokens


class ScamModel:
    def __init__(self, path=config.MODEL_PATH):
        self.load(path)

    def load(self, path=config.MODEL_PATH):
        b = joblib.load(path)
        self.pipeline, self.vocab, self.version = b["pipeline"], b["vocab"], b["version"]
        return self

    def oov_share(self, text: str) -> float:
        toks = tokens(text)
        return float(np.mean([t not in self.vocab for t in toks])) if toks else 0.0

    def predict(self, texts, drift_active: bool = False) -> list:
        texts = [str(t) for t in texts]
        probs = self.pipeline.predict_proba(texts)[:, 1]
        t_scam = config.T_SCAM_DRIFT if drift_active else config.T_SCAM
        t_safe = config.T_SAFE_DRIFT if drift_active else config.T_SAFE
        out = []
        for text, p in zip(texts, probs):
            oov = self.oov_share(text)
            if oov > config.T_OOV:
                verdict = "unsure"
            elif p >= t_scam:
                verdict = "scam"
            elif p <= t_safe:
                verdict = "safe"
            else:
                verdict = "unsure"
            reasons = explain(text) if verdict != "safe" else safe_signs(text)
            if verdict == "unsure" and oov > config.T_OOV:
                reasons = ["Wording is unlike anything the model was trained on"] + reasons
            out.append({
                "label": "scam" if p >= 0.5 else "safe",
                "scam_prob": round(float(p), 4),
                "confidence": round(float(max(p, 1 - p)), 4),
                "verdict": verdict,
                "reasons": reasons,
                "advice": config.FALLBACK_MESSAGE if verdict == "unsure" else
                          ("Do not reply or share any code. Your bank will never ask for your OTP." if verdict == "scam" else ""),
                "oov_share": round(oov, 4),
                "lang": detect_lang(text),
                "model_version": self.version,
            })
        return out


if __name__ == "__main__":
    m = ScamModel()
    for r in m.predict(sys.argv[1:] or [
        "Hela Bank: Your OTP is 482913. Never share this code with anyone, including bank staff.",
        "LankaSave: Your account has been blocked. Reply with the OTP sent to your phone to reactivate it.",
        "Serendib Pay agent here. To finish your SL-UDI enrolment, tell me the number you just got. It is only a reference number.",
    ]):
        print(r)
