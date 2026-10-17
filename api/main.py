# api/main.py (owner: P4 — Backend / DevOps)
"""FastAPI service for OTP Shield.

Consumes Interface 1 (ScamModel) from P2.
Uses thresholds from src/config.py (P3).
Logs predictions when P3's monitor helpers exist; otherwise still returns verdicts.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from src.config import FALLBACK_MESSAGE  # noqa: E402
from src.model import ScamModel  # noqa: E402

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")
MODEL_PATH = os.getenv("MODEL_PATH", "models/model.joblib")

_model: ScamModel | None = None


def get_model() -> ScamModel:
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return _model


def _try_log(row: dict[str, Any]) -> None:
    """Best-effort prediction log. P3 owns the real monitor implementation."""
    try:
        from src import monitor

        if hasattr(monitor, "log_prediction"):
            monitor.log_prediction(row)
    except Exception:
        pass


def _drift_active() -> bool:
    try:
        from src import monitor

        if hasattr(monitor, "drift_status"):
            status = monitor.drift_status()
            if isinstance(status, dict):
                return bool(status.get("drift_active"))
            return bool(status)
    except Exception:
        pass
    return False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _model
    _model = ScamModel(path=MODEL_PATH)
    yield


app = FastAPI(
    title="Vortex OTP Classifier",
    version="0.1.0",
    description="Bank OTP-theft scam checker for Sri Lanka (EN / SI / TA / Singlish).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="api", max_length=40)


class BatchIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=100)
    source: str = Field(default="api", max_length=40)


class PredictOut(BaseModel):
    label: str
    scam_prob: float
    confidence: float
    verdict: str
    reasons: list[str]
    oov_share: float
    lang: str
    model_version: str
    drift_active: bool
    fallback_message: str | None = None


def _require_admin(authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)) -> None:
    token = None
    if x_admin_token:
        token = x_admin_token.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin token required")


def _pack(pred: dict[str, Any], model: ScamModel, drift: bool) -> dict[str, Any]:
    verdict = pred.get("verdict", "unsure")
    body = {
        "label": pred["label"],
        "scam_prob": float(pred["scam_prob"]),
        "confidence": float(pred["confidence"]),
        "verdict": verdict,
        "reasons": list(pred.get("reasons") or []),
        "oov_share": float(pred.get("oov_share") or 0.0),
        "lang": pred.get("lang") or "en",
        "model_version": model.version,
        "drift_active": drift,
        "fallback_message": FALLBACK_MESSAGE if verdict == "unsure" else None,
    }
    return body


@app.get("/health")
def health(model: ScamModel = Depends(get_model)):
    return {
        "status": "ok",
        "model_version": model.version,
        "drift_active": _drift_active(),
    }


@app.post("/predict", response_model=PredictOut)
def predict(body: PredictIn, model: ScamModel = Depends(get_model)):
    drift = _drift_active()
    pred = model.predict([body.text])[0]
    packed = _pack(pred, model, drift)
    _try_log(
        {
            "text": body.text,
            "source": body.source,
            "model_version": model.version,
            "drift_active": drift,
            **pred,
        }
    )
    return packed


@app.post("/predict/batch")
def predict_batch(body: BatchIn, model: ScamModel = Depends(get_model)):
    drift = _drift_active()
    preds = model.predict(body.texts)
    results = []
    for text, pred in zip(body.texts, preds):
        packed = _pack(pred, model, drift)
        _try_log(
            {
                "text": text,
                "source": body.source,
                "model_version": model.version,
                "drift_active": drift,
                **pred,
            }
        )
        results.append(packed)
    return {"count": len(results), "drift_active": drift, "results": results}


@app.get("/drift")
def drift():
    try:
        from src import monitor

        if hasattr(monitor, "drift_status"):
            return monitor.drift_status()
    except Exception as exc:
        return {"drift_active": False, "detail": f"monitor not ready: {exc}"}
    return {"drift_active": False, "detail": "P3 monitor.drift_status() not implemented yet"}


@app.get("/review/queue")
def review_queue(_: None = Depends(_require_admin)):
    try:
        from src import review

        if hasattr(review, "list_pending"):
            return {"items": review.list_pending()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"review not ready: {exc}") from exc
    return {"items": [], "detail": "P3 review.list_pending() not implemented yet"}


class ReviewLabelIn(BaseModel):
    label: str


@app.post("/review/{prediction_id}")
def review_label(prediction_id: str, body: ReviewLabelIn, _: None = Depends(_require_admin)):
    label = body.label.strip().lower()
    if label not in {"scam", "safe"}:
        raise HTTPException(status_code=400, detail="label must be scam or safe")
    try:
        from src import review

        if hasattr(review, "set_label"):
            return review.set_label(prediction_id, label)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"review not ready: {exc}") from exc
    raise HTTPException(status_code=503, detail="P3 review.set_label() not implemented yet")
