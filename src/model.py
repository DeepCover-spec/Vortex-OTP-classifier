"""ScamModel interface (Interface 1). Owner: P2.

STUB so P3, P4 and P5 can build before the real model exists. P2 replaces the body but keeps
the class name, the `version` attribute and the keys returned by predict().
"""
from src.config import verdict_from
from src.text import normalise

SHARE_WORDS = ("share", "send", "reply", "give", "tell")


class ScamModel:
    version = "stub-v0"

    def __init__(self, path: str = "models/model.joblib"):
        self.path = path

    def predict(self, texts: list[str]) -> list[dict]:
        out = []
        for text in texts:
            low = normalise(text).lower()
            asks_otp = "otp" in low and any(w in low for w in SHARE_WORDS)
            p = 0.92 if asks_otp else 0.08
            out.append({
                "label": "scam" if p >= 0.5 else "safe",
                "scam_prob": p,
                "confidence": max(p, 1 - p),
                "verdict": verdict_from(p, 0.0),
                "reasons": ["asks you to share the OTP"] if asks_otp else [],
                "oov_share": 0.0,
                "lang": "en",
            })
        return out
