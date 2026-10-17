"""Single source of truth for thresholds (Interface 2).

Owner: P3 (values), P2 (calibration). Do not hard-code these numbers anywhere else.
"""

T_SCAM = 0.70
T_SAFE = 0.30
T_OOV = 0.45

# Widened band used while drift is active
T_SCAM_DRIFT = 0.85
T_SAFE_DRIFT = 0.20

DRIFT_WINDOW = 100
DRIFT_SIGNALS_REQUIRED = 2  # drift_active when this many of 4 signals breach
RETRAIN_MIN_LABELS = 50
RETRAIN_MAX_F1_DROP = 0.01  # promotion gate on test macro-F1

FALLBACK_MESSAGE = (
    "We are not sure. Never share your OTP or PIN with anyone. "
    "Call your bank on the number on the back of your card."
)


def verdict_from(scam_prob: float, oov_share: float = 0.0, drift_active: bool = False) -> str:
    """Apply the verdict policy. Returns "scam", "safe" or "unsure"."""
    if oov_share > T_OOV:
        return "unsure"
    t_scam, t_safe = (T_SCAM_DRIFT, T_SAFE_DRIFT) if drift_active else (T_SCAM, T_SAFE)
    if scam_prob >= t_scam:
        return "scam"
    if scam_prob <= t_safe:
        return "safe"
    return "unsure"
