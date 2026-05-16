"""ONNX model loader.

In Lambda: downloads the model + feature metadata from S3 to /tmp at cold
start, then loads them. Subsequent invocations reuse the cached files and
the cached onnxruntime InferenceSession.

Local/test: if MODEL_LOCAL_PATH is set, loads directly from disk (no S3).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import boto3
import onnxruntime as ort

_LAMBDA_TMP = Path("/tmp")


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Lazy env-var reader so test fixtures that monkeypatch envs work
    even when this module is imported before the fixture runs."""
    return os.environ.get(name, default)


@dataclass(frozen=True)
class FeatureMetadata:
    categorical_cols: List[str]
    numeric_cols: List[str]
    categories: Dict[str, List[str]]
    feature_count: int


_session: Optional[ort.InferenceSession] = None
_metadata: Optional[FeatureMetadata] = None


def _download_from_s3(key: str, dest: Path) -> Path:
    s3 = boto3.client("s3", region_name=_env("AWS_REGION", "us-east-1"))
    bucket = _env("ONNX_BUCKET", "payment-routing-onnx-654654151376")
    s3.download_file(bucket, key, str(dest))
    return dest


def _resolve_paths() -> tuple[Path, Path]:
    local_model = _env("MODEL_LOCAL_PATH")
    local_metadata = _env("METADATA_LOCAL_PATH")
    if local_model and local_metadata:
        return Path(local_model), Path(local_metadata)
    tmp_root = _LAMBDA_TMP if _LAMBDA_TMP.exists() else Path(_env("TEMP", "."))
    model_path = tmp_root / "interchange_model.onnx"
    metadata_path = tmp_root / "feature_metadata.json"
    if not model_path.exists():
        _download_from_s3(_env("ONNX_MODEL_KEY", "interchange_model.onnx"), model_path)
    if not metadata_path.exists():
        _download_from_s3(_env("ONNX_METADATA_KEY", "feature_metadata.json"), metadata_path)
    return model_path, metadata_path


def get_session_and_metadata() -> tuple[ort.InferenceSession, FeatureMetadata]:
    global _session, _metadata
    if _session is None or _metadata is None:
        model_path, metadata_path = _resolve_paths()
        _session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        with open(metadata_path) as f:
            raw = json.load(f)
        _metadata = FeatureMetadata(
            categorical_cols=raw["categorical_cols"],
            numeric_cols=raw["numeric_cols"],
            categories=raw["categories"],
            feature_count=raw["feature_count"],
        )
    return _session, _metadata


def reset_cache():
    """Test hook — forces the next call to re-load the session."""
    global _session, _metadata
    _session = None
    _metadata = None
