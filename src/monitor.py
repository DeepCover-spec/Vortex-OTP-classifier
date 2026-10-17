"""Monitoring and drift. Owner: P3.

SCHEMA_SQL is Interface 3, the shared prediction log. P3 adds log_prediction, drift_status,
build_reference and the alert rules below it.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id            TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,          -- ISO 8601
    model_version TEXT NOT NULL,
    text_masked   TEXT NOT NULL,          -- codes -> <CODE>, phones -> <PHONE>, URLs -> <URL>
    text_hash     TEXT NOT NULL,
    lang          TEXT,
    n_tokens      INTEGER,
    oov_share     REAL,
    scam_prob     REAL,
    confidence    REAL,
    verdict       TEXT,                   -- scam | safe | unsure
    drift_active  INTEGER DEFAULT 0,
    source        TEXT,                   -- ui | api | demo_test | demo_shifted
    review_status TEXT DEFAULT 'none',    -- none | pending | labelled
    review_label  TEXT                    -- scam | safe | NULL
);
"""
