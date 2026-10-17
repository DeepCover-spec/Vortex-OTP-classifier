# Shared interfaces (agree by 10:45)

## Interface 1: model (P2 provides, P3 and P4 consume)
`src/model.py` -> `ScamModel(path="models/model.joblib")` with attribute `version` and
`predict(texts: list[str]) -> list[dict]`. Each dict has exactly these keys:

    label        "scam" | "safe"
    scam_prob    float 0-1
    confidence   float 0.5-1
    verdict      "scam" | "safe" | "unsure"
    reasons      list[str]
    oov_share    float 0-1
    lang         "en" | "si" | "ta" | "singlish" | "tanglish"

`normalise()` lives in `src/text.py` and is used in training AND serving.

## Interface 2: verdict policy (P3 owns thresholds, P2 calibrates)
All thresholds live in `src/config.py`. Never hard-code them elsewhere.
- scam_prob >= T_SCAM (0.70) -> scam; scam_prob <= T_SAFE (0.30) -> safe; else unsure.
- oov_share > T_OOV (0.45) -> force unsure.
- Every unsure goes to the review queue and the user sees FALLBACK_MESSAGE.
- While drift is active the band widens to 0.20-0.85.
`config.verdict_from(scam_prob, oov_share, drift_active)` implements this.

## Interface 3: prediction log (SQLite table `predictions`, P3 owns)
Schema is `SCHEMA_SQL` in `src/monitor.py`. Text is stored masked (codes -> <CODE>,
phones -> <PHONE>, URLs -> <URL>) plus a hash. Never store the raw OTP or number.

## Git rules
main is always runnable. Short branches (p2-model, p3-drift, ...), merge through P1.
Commit at least every 30 minutes. No secrets in the repo.
