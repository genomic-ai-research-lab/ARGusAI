"""Optional calibration for alignment confidence."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import json
import math
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationModel:
    """Simple Platt-scaling calibration model."""

    a: float
    b: float

    def apply(self, score: float) -> float:
        normalized = max(0.0, min(score, 100.0)) / 100.0
        value = 1.0 / (1.0 + math.exp(-(self.a + self.b * normalized)))
        return value * 100.0


_CALIBRATION_MODEL: CalibrationModel | None = None
_CALIBRATION_LOADED = False


def get_calibration_model() -> CalibrationModel | None:
    """Load a calibration model from disk once, if configured."""

    global _CALIBRATION_MODEL, _CALIBRATION_LOADED
    if _CALIBRATION_LOADED:
        return _CALIBRATION_MODEL

    _CALIBRATION_LOADED = True
    model_path = settings.CALIBRATION_MODEL_PATH
    if not model_path:
        return None

    path = Path(model_path)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if payload.get("type") != "platt":
        return None

    try:
        a = float(payload.get("a"))
        b = float(payload.get("b"))
    except (TypeError, ValueError):
        return None

    _CALIBRATION_MODEL = CalibrationModel(a=a, b=b)
    logger.info("Calibration model loaded (platt): a=%.6f b=%.6f", a, b)
    return _CALIBRATION_MODEL


def apply_calibration(score: float) -> float:
    """Return calibrated score if a model is configured, else original score."""

    model = get_calibration_model()
    if model is None:
        return score
    return model.apply(score)
