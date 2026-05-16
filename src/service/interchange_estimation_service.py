"""Interchange rate estimation — wraps the ONNX XGBoost regression model.

Encoding contract:
    The feature vector at inference time must match the one used at training:
    [one_hot(scheme_id), one_hot(card_type), one_hot(card_product),
     one_hot(mcc), one_hot(merchant_country), one_hot(card_country),
     amount, cross_border_int]

    Vocabulary and column order live in feature_metadata.json (loaded by
    model_config). Unseen category values produce a zero vector for that
    block — same as OneHotEncoder(handle_unknown='ignore').

Categories (heuristic mapping based on cross_border and predicted rate band):
    - "domestic-low":    domestic, predicted <= 0.5%
    - "domestic-std":    domestic, predicted <= 1.5%
    - "cross-border-std":  cross-border, predicted <= 2.0%
    - "cross-border-prem": cross-border, predicted >  2.0%

Fallback path: if ONNX session can't be obtained (S3 download failed, missing
file, etc.), we use static rates from resources/interchange-fallback-rates.json.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import model_config
from src.config.model_config import FeatureMetadata
from src.model.interchange_estimate import InterchangeEstimate

LOG = logging.getLogger(__name__)

_FALLBACK_FILE = Path(__file__).parent.parent.parent / "resources" / "interchange-fallback-rates.json"
_fallback_cache: Optional[dict] = None


def _build_input_vector(
    scheme_id: str,
    card_type: str,
    card_product: str,
    mcc: str,
    merchant_country: str,
    card_country: str,
    amount: float,
    cross_border: bool,
    metadata: FeatureMetadata,
) -> np.ndarray:
    inputs = {
        "scheme_id":        scheme_id,
        "card_type":        card_type,
        "card_product":     card_product,
        "mcc":              mcc,
        "merchant_country": merchant_country,
        "card_country":     card_country,
    }
    parts: list[float] = []
    for col in metadata.categorical_cols:
        value = inputs[col]
        for cat in metadata.categories[col]:
            parts.append(1.0 if cat == value else 0.0)
    parts.append(float(amount))
    parts.append(1.0 if cross_border else 0.0)
    return np.array([parts], dtype=np.float32)


def _categorize(pct: float, cross_border: bool) -> str:
    if not cross_border:
        return "domestic-low" if pct <= 0.5 else "domestic-std"
    return "cross-border-std" if pct <= 2.0 else "cross-border-prem"


def _load_fallback() -> dict:
    global _fallback_cache
    if _fallback_cache is None:
        with open(_FALLBACK_FILE) as f:
            _fallback_cache = json.load(f)
    return _fallback_cache


def _fallback_estimate(
    scheme_id: str, card_type: str, cross_border: bool
) -> InterchangeEstimate:
    table = _load_fallback()
    scheme_entry = table.get(scheme_id, {})
    card_entry = scheme_entry.get(card_type, {})
    pct = card_entry.get("cross_border" if cross_border else "domestic", 1.5)
    return InterchangeEstimate(
        scheme_id=scheme_id,
        estimated_interchange_pct=float(pct),
        interchange_category=_categorize(pct, cross_border),
        confidence=0.40,
        cross_border=cross_border,
    )


def estimate_interchange(
    scheme_id: str,
    card_type: str,
    card_product: str,
    mcc: str,
    amount: float,
    merchant_country: str,
    card_country: str,
) -> InterchangeEstimate:
    cross_border = merchant_country != card_country
    try:
        session, metadata = model_config.get_session_and_metadata()
        x = _build_input_vector(
            scheme_id, card_type, card_product, mcc,
            merchant_country, card_country, amount, cross_border, metadata,
        )
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: x})
        predicted_pct = float(np.asarray(outputs[0]).flatten()[0])
        predicted_pct = max(0.05, min(predicted_pct, 4.5))
        return InterchangeEstimate(
            scheme_id=scheme_id,
            estimated_interchange_pct=round(predicted_pct, 4),
            interchange_category=_categorize(predicted_pct, cross_border),
            confidence=0.95,
            cross_border=cross_border,
        )
    except Exception as e:
        LOG.warning("ONNX inference unavailable, using fallback rates: %s", e)
        return _fallback_estimate(scheme_id, card_type, cross_border)
