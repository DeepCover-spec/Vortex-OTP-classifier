"""Shared settings. Change thresholds here only, never in several places."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
MODEL_PATH = ROOT / "models" / "model.joblib"
META_PATH = ROOT / "models" / "meta.json"
REFERENCE_PATH = ROOT / "models" / "reference.json"
REPORTS_DIR = ROOT / "reports"

SEED = 42

# Verdict policy: scam_prob >= T_SCAM -> scam, <= T_SAFE -> safe, otherwise unsure.
T_SCAM = 0.70
T_SAFE = 0.30
# If more than this share of a message's words were never seen in training, say "unsure".
T_OOV = 0.45
# While drift is active, the monitor can widen the unsure band to these values.
T_SCAM_DRIFT = 0.85
T_SAFE_DRIFT = 0.20

FALLBACK_MESSAGE = ("We are not sure about this message. Never share your OTP or PIN with anyone, "
                    "including bank staff. Call your bank on the number on the back of your card.")
