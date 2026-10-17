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

# ---------------------------------------------------------------- monitoring (P3)
DB_PATH = ROOT / "data" / "monitor.db"          # SQLite: predictions, alerts, retrain log (gitignored)
VERSIONS_DIR = ROOT / "models" / "versions"
DRIFT_WINDOW = 100                              # number of recent predictions the monitor looks at
# Drift thresholds, calibrated by replaying the test set vs the shifted set in windows of 100
# (python src/monitor.py --calibrate prints the numbers and the suggested values).
DRIFT_THRESHOLDS = {
    "mean_oov_share": 0.255,    # alert if ABOVE (test windows 0.16-0.21, shifted 0.30-0.32)
    "mean_confidence": 0.846,   # alert if BELOW (test 0.85-0.89, shifted 0.82-0.85)
    "unsure_share": 0.30,       # alert if ABOVE (test 0.18-0.30, shifted 0.30-0.40)
    "lang_mix_shift": 0.128,    # (test 0.04-0.10, shifted 0.16-0.21) total-variation distance from the reference language mix, alert if ABOVE
}
DRIFT_MIN_SIGNALS = 2           # drift is active when at least this many signals breach (fewer false alarms)
RETRAIN_MIN_LABELS = 50         # retraining trigger: number of human-reviewed labels needed
PROMOTION_MAX_F1_DROP = 0.01    # promote a retrained model only if test macro-F1 drops by no more than this
