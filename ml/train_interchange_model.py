"""Train XGBoost interchange model and export to ONNX.

Pipeline:
    1. Load synthetic data from ml/data/synthetic_interchange.csv
    2. One-hot encode categoricals (preserve column order)
    3. Train XGBRegressor
    4. Evaluate on held-out test split
    5. Convert to ONNX via onnxmltools
    6. Persist:
         - ml/interchange_model.onnx        (model artifact)
         - ml/feature_metadata.json         (encoder vocabulary)
         - ml/model_card.md                 (already committed; metrics appended)
    7. Optionally upload artifacts to S3 (if --upload flag set)
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from skl2onnx.common.data_types import FloatTensorType
from onnxmltools.convert import convert_xgboost

ML_DIR = Path(__file__).parent
DATA_FILE = ML_DIR / "data" / "synthetic_interchange.csv"
MODEL_FILE = ML_DIR / "interchange_model.onnx"
METADATA_FILE = ML_DIR / "feature_metadata.json"

CATEGORICAL_COLS = ["scheme_id", "card_type", "card_product", "mcc", "merchant_country", "card_country"]
NUMERIC_COLS = ["amount", "cross_border"]
TARGET = "interchange_rate"


def encode(df: pd.DataFrame, encoder: OneHotEncoder):
    cat = encoder.transform(df[CATEGORICAL_COLS])
    num = df[NUMERIC_COLS].to_numpy(dtype=np.float32)
    return np.hstack([cat.astype(np.float32), num])


def main(upload: bool, bucket: str):
    print(f"Loading {DATA_FILE}")
    df = pd.read_csv(DATA_FILE, dtype={"mcc": str})

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoder.fit(df[CATEGORICAL_COLS])

    feature_metadata = {
        "categorical_cols":   CATEGORICAL_COLS,
        "numeric_cols":       NUMERIC_COLS,
        "categories":         {col: list(cats) for col, cats in zip(CATEGORICAL_COLS, encoder.categories_)},
        "feature_count":      sum(len(c) for c in encoder.categories_) + len(NUMERIC_COLS),
    }
    n_features = feature_metadata["feature_count"]
    print(f"  {len(df):,} rows, {n_features} encoded features")

    X = encode(df, encoder)
    y = df[TARGET].to_numpy(dtype=np.float32)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training XGBoost regressor")
    model = XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        objective="reg:squarederror",
        tree_method="hist",
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = r2_score(y_test, y_pred)
    print(f"  MAE:  {mae:.4f}")
    print(f"  RMSE: {rmse:.4f}")
    print(f"  R^2:  {r2:.4f}")

    print(f"Exporting to ONNX: {MODEL_FILE}")
    initial_types = [("input", FloatTensorType([None, n_features]))]
    onnx_model = convert_xgboost(model, initial_types=initial_types, target_opset=15)
    with open(MODEL_FILE, "wb") as f:
        f.write(onnx_model.SerializeToString())

    print(f"Writing metadata: {METADATA_FILE}")
    feature_metadata["metrics"] = {"mae": mae, "rmse": rmse, "r2": r2}
    with open(METADATA_FILE, "w") as f:
        json.dump(feature_metadata, f, indent=2)

    if upload:
        import boto3
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        s3.upload_file(str(MODEL_FILE), bucket, "interchange_model.onnx")
        s3.upload_file(str(METADATA_FILE), bucket, "feature_metadata.json")
        print(f"Uploaded model + metadata to s3://{bucket}/")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Upload artifacts to S3")
    parser.add_argument("--bucket", default="payment-routing-onnx-654654151376",
                        help="S3 bucket for artifact upload")
    args = parser.parse_args()
    main(upload=args.upload, bucket=args.bucket)
