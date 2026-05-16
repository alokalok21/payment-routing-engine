"""Tests for the ONNX interchange estimation service.

Uses the locally trained model via MODEL_LOCAL_PATH (set by local_onnx_env fixture).
The tolerances are loose because XGBoost predictions are not exactly the
parametric formula — we mostly want to assert shape, sign, and tier behaviour.
"""

import pytest

from src.service.interchange_estimation_service import estimate_interchange


def test_domestic_cb_is_low(local_onnx_env):
    r = estimate_interchange("CB", "CREDIT", "CLASSIC", "5411", 150.0, "FR", "FR")
    assert r.scheme_id == "CB"
    assert r.cross_border is False
    assert 0.1 <= r.estimated_interchange_pct <= 0.6
    assert r.interchange_category == "domestic-low"
    assert r.confidence == 0.95


def test_cross_border_is_higher_than_domestic(local_onnx_env):
    domestic = estimate_interchange("VISA", "CREDIT", "CLASSIC", "5411", 150.0, "FR", "FR")
    cross    = estimate_interchange("VISA", "CREDIT", "CLASSIC", "5411", 150.0, "US", "FR")
    assert cross.cross_border is True
    assert cross.estimated_interchange_pct > domestic.estimated_interchange_pct


def test_amex_premium_is_higher_than_visa_classic(local_onnx_env):
    amex = estimate_interchange("AMEX", "CREDIT", "PLATINUM", "5812", 80.0, "US", "US")
    visa = estimate_interchange("VISA", "CREDIT", "CLASSIC",  "5812", 80.0, "US", "US")
    assert amex.estimated_interchange_pct > visa.estimated_interchange_pct


def test_fallback_when_model_unavailable(monkeypatch):
    """If the ONNX session can't be obtained, the service uses static rates."""
    from src.config import model_config

    def fail(*_args, **_kw):
        raise RuntimeError("Simulated S3 / ONNX failure")

    monkeypatch.setattr(model_config, "get_session_and_metadata", fail)
    r = estimate_interchange("CB", "CREDIT", "CLASSIC", "5411", 150.0, "FR", "FR")
    assert r.scheme_id == "CB"
    assert r.cross_border is False
    assert r.confidence == 0.40  # fallback confidence
    assert r.estimated_interchange_pct > 0
