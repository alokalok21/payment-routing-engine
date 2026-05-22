# ONNX in Payment Routing Engine — Detailed Explanation

## 🎯 What is ONNX and Why It's Used Here

**ONNX** (Open Neural Network Exchange) is an **open-source standard format** for representing trained machine learning models in a runtime-agnostic way. Think of it as a "universal binary" for ML models — once trained and exported to ONNX, the model can run anywhere: Python, C++, Java, .NET, browsers, etc.

---

## 📊 ONNX in This Project — The Context

### The Problem Being Solved

In the payment routing engine, every transaction needs an **interchange cost estimate** for each eligible payment scheme:

```
Transaction: €150, FR → FR, Visa+CB dual-brand card

Question: What's the predicted interchange rate for:
  1. Routing via VISA?
  2. Routing via CB (Cartes Bancaires)?

Agent uses these rates to score: score = (auth_rate × 0.6) - (interchange × 0.4)
```

### The Naive Approach (❌ Not Used)

**Option 1: Real-time SageMaker Endpoint**
```
Payment Flow:
  API Gateway → Lambda → [lookup BIN] → [call SageMaker endpoint] → SageMaker Instance
                                             ↓ Network latency (50-200ms)
                                    (another AWS service)
                                             ↓
                                    Return prediction
                        → Bedrock Agent continues...
```

**Problems:**
- ⏱️ **Cold-start latency**: SageMaker endpoint may take 50-200ms per request
- 🌐 **Network hop**: Extra AWS service call = potential failure point
- 💰 **Cost**: SageMaker endpoint + provisioned instances = ~$50/day
- 🔗 **Coupling**: Tightly bound to AWS SageMaker (not portable)

### The ONNX Approach (✅ Chosen)

```
Payment Flow:
  API Gateway → Lambda
     ↓
  [Load ONNX from S3 once at cold start] ← Cached in Lambda memory
     ↓
  [BIN lookup, auth rates]
     ↓
  [Interchange estimation] → onnxruntime.run() ← LOCAL INFERENCE (5-15ms)
     ↓
  Bedrock Agent → Final decision
```

**Advantages:**
- ⚡ **Ultra-low latency**: Model runs inside Lambda process (~10ms per call)
- 🚀 **No network hop**: Inference is in-process, not over the network
- 💵 **Zero cost**: Model is just a binary file in S3 (pay only for S3 storage, not compute)
- 📦 **Portable**: Same ONNX file runs on any platform (Python, C++, edge devices)
- 🔒 **Reproducible**: Model artifact committed to repo; deterministic inference

---

## 🏗️ How ONNX Works in This Project

### Step 1: Model Training (Offline, One-Time)

**File**: [ml/train_interchange_model.py](ml/train_interchange_model.py)

```python
# 1. Load synthetic training data
df = pd.read_csv("data/synthetic_interchange.csv")

# 2. One-hot encode categorical features
encoder = OneHotEncoder(handle_unknown="ignore")
encoder.fit(df[CATEGORICAL_COLS])

# 3. Train XGBoost regressor
model = XGBRegressor(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.08,
    ...
)
model.fit(X_train, y_train)

# 4. ★ Export to ONNX format ★
from onnxmltools.convert import convert_xgboost

onnx_model = convert_xgboost(model)
onnx_model.save("interchange_model.onnx")
```

**Key Package**: `onnxmltools`
- Bridges XGBoost → ONNX format
- Handles feature encoding, tree conversion, operator mapping
- Result: Binary `.onnx` file (~1-5MB for typical models)

### Step 2: Model Storage

**File**: [ml/interchange_model.onnx](ml/interchange_model.onnx)

```
ml/
├── interchange_model.onnx          ← Binary ONNX artifact (~2MB)
├── feature_metadata.json           ← Feature order & vocabularies
└── model_card.md                   ← Metrics & documentation
```

The `.onnx` file is **committed to GitHub** for reproducibility:
- ✅ Deterministic: Always produces the same prediction given same input
- ✅ Version-controlled: Can revert to old models if needed
- ✅ Lightweight: ~2MB, easy to store in S3

### Step 3: Lambda Deployment

**File**: [infrastructure/template.yaml](infrastructure/template.yaml)

```yaml
Resources:
  OnnxModelBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: payment-routing-onnx-654654151376
      # ...

  RoutingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src/handler/routing_handler.lambda_handler
      Runtime: python3.13
      Layers: []  # ← No special ML layer needed
      Environment:
        Variables:
          ONNX_BUCKET: payment-routing-onnx-654654151376
          ONNX_MODEL_KEY: interchange_model.onnx
          ONNX_METADATA_KEY: feature_metadata.json
```

**Dependencies**: Only `onnxruntime` package
```
requirements.txt:
  boto3>=1.34.0
  onnxruntime>=1.18.0    ← Tiny footprint (~10MB), pure Python
  numpy>=1.26.0
```

### Step 4: Model Loading at Lambda Cold Start

**File**: [src/config/model_config.py](src/config/model_config.py)

```python
import onnxruntime as ort
import boto3

_session = None  # Singleton cache

def get_session_and_metadata():
    global _session
    if _session is None:
        # ★ First call (cold start): Download from S3 ★
        s3 = boto3.client("s3")
        s3.download_file(
            bucket="payment-routing-onnx-654654151376",
            key="interchange_model.onnx",
            filename="/tmp/interchange_model.onnx"
        )
        
        # ★ Load ONNX session ★
        _session = ort.InferenceSession(
            "/tmp/interchange_model.onnx",
            providers=["CPUExecutionProvider"]
        )
    
    # ★ Subsequent calls: Reuse cached session ★
    return _session
```

**Timeline for 1 Lambda Container:**
```
Cold Start (first invocation):     ~150ms  (S3 download + model load)
Subsequent invocations:            ~10ms   (cached session reuse)
```

### Step 5: Inference at Routing Time

**File**: [src/service/interchange_estimation_service.py](src/service/interchange_estimation_service.py)

```python
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
        # 1. Get cached ONNX session
        session, metadata = model_config.get_session_and_metadata()
        
        # 2. Build feature vector matching training encoding
        x = _build_input_vector(
            scheme_id, card_type, card_product, mcc,
            merchant_country, card_country, amount, cross_border, metadata,
        )
        # x: numpy array, shape (1, 46), dtype float32
        # [one_hot(scheme), one_hot(card_type), ..., amount, cross_border]
        
        # 3. ★ Run inference ★ (this is where ONNX shines)
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: x})
        
        # 4. Extract & validate prediction
        predicted_pct = float(outputs[0][0][0])
        predicted_pct = max(0.05, min(predicted_pct, 4.5))  # Clamp to realistic range
        
        # 5. Return typed result
        return InterchangeEstimate(
            scheme_id=scheme_id,
            estimated_interchange_pct=predicted_pct,
            interchange_category=_categorize(predicted_pct, cross_border),
            confidence=0.95,
            cross_border=cross_border,
        )
    
    except Exception as e:
        # ★ Fallback: Static rates if ONNX unavailable ★
        LOG.warning("ONNX inference failed, using fallback: %s", e)
        return _fallback_estimate(scheme_id, card_type, cross_border)
```

---

## 🔬 The Feature Vector — Encoding Contract

### Training-Time Encoding

```python
# XGBoost training (ml/train_interchange_model.py)
categorical_cols = ["scheme_id", "card_type", "card_product", "mcc", "merchant_country", "card_country"]
numeric_cols = ["amount", "cross_border"]

# One-hot encode
encoder = OneHotEncoder()
X_train = encoder.fit_transform(df[categorical_cols]).toarray()
X_train = np.hstack([X_train, df[numeric_cols]])

# Save vocabulary for inference
feature_metadata = {
    "categories": {
        "scheme_id": ["VISA", "MASTERCARD", "CB", "DISCOVER", "AMEX", "UNIONPAY", "MAESTRO"],
        "card_type": ["CREDIT", "DEBIT", "PREPAID"],
        "card_product": ["CLASSIC", "GOLD", "PLATINUM", "INFINITE"],
        ...
    },
    "feature_count": 46
}
```

### Inference-Time Encoding (Must Match!)

```python
# Interchange estimation (src/service/interchange_estimation_service.py)
def _build_input_vector(..., metadata):
    inputs = {
        "scheme_id": scheme_id,           # e.g., "VISA"
        "card_type": card_type,           # e.g., "CREDIT"
        "card_product": card_product,     # e.g., "CLASSIC"
        "mcc": mcc,                       # e.g., "5411"
        "merchant_country": merchant_country,  # e.g., "FR"
        "card_country": card_country,     # e.g., "US"
    }
    
    parts = []
    # ★ One-hot encode in same order as training ★
    for col in metadata.categorical_cols:  # Order matters!
        value = inputs[col]
        for cat in metadata.categories[col]:
            parts.append(1.0 if cat == value else 0.0)
    
    parts.append(float(amount))           # Numeric: raw
    parts.append(1.0 if cross_border else 0.0)  # Boolean → 0/1
    
    return np.array([parts], dtype=np.float32)
```

**Example:**
```
Input: scheme_id="CB", card_type="CREDIT", amount=150.00, cross_border=False

Encoding:
[
  0, 0, 1, 0, 0, 0, 0,    ← CB is 3rd scheme (one-hot) = [0,0,1,0,0,0,0]
  1, 0, 0,                ← CREDIT is 1st card_type = [1,0,0]
  1, 0, 0, 0,             ← CLASSIC is 1st product = [1,0,0,0]
  ...                     ← rest of one-hot blocks
  150.0,                  ← amount (numeric)
  0.0                     ← cross_border (boolean)
]
↓
shape: (1, 46), dtype: float32
```

**Critical**: If encoding at inference doesn't match training, predictions are garbage!
This is why `feature_metadata.json` is stored alongside the model.

---

## ⚡ Why ONNX Over Alternatives

### Option 1: SageMaker Endpoint

| Aspect | ONNX (Chosen) | SageMaker Endpoint |
|---|---|---|
| **Latency** | 10-20ms | 50-200ms (network) |
| **Cost** | ~$0.01/month | ~$50/month (24/7 instance) |
| **Portability** | Any platform | AWS-only |
| **Dependencies** | `onnxruntime` (10MB) | boto3 + SageMaker API |
| **Failure modes** | Falls back to static JSON | Service unavailable → error |
| **Version control** | Model in Git | SageMaker registry |
| **Cold start** | 150ms (first time) | Not applicable (always running) |

### Option 2: Lambda Layer with scikit-learn

```
❌ scikit-learn: ~150MB zipped → oversized Lambda layer
❌ XGBoost: Model + libs → 200MB+ compressed
✅ ONNX: 2-5MB model file + onnxruntime 10MB → lean
```

### Option 3: PyTorch/TensorFlow Models

```
❌ PyTorch: 500MB+ weights, slow inference in serverless
❌ TensorFlow: Bloated runtime, rarely used in tabular models
✅ ONNX: Purpose-built for model interoperability, lightweight
```

### Option 4: Pre-compute All Rates (Static JSON)

```
❌ Combinatorial explosion:
   7 schemes × 3 card types × 4 products × 10 MCCs × 10 countries × 10 countries
   = 84,000 entries
   
✅ ONNX: One model, predicts any combination
```

---

## 🛡️ Fallback Strategy

### Why Fallback Matters

ONNX inference can fail for reasons:
- S3 download timeout (rare)
- Corrupted model file (very rare)
- OOM during load (extremely rare)
- Unsupported operator in `onnxruntime` (caught during training)

**Solution**: Static fallback rates

**File**: [resources/interchange-fallback-rates.json](resources/interchange-fallback-rates.json)

```python
# When ONNX inference fails:
def _fallback_estimate(scheme_id: str, card_type: str, cross_border: bool):
    table = _load_fallback()
    scheme_entry = table.get(scheme_id, {})
    card_entry = scheme_entry.get(card_type, {})
    
    # Return pre-computed rate (lower confidence)
    pct = card_entry.get("cross_border" if cross_border else "domestic", 1.5)
    
    return InterchangeEstimate(
        scheme_id=scheme_id,
        estimated_interchange_pct=float(pct),
        confidence=0.40,  # ← Lower confidence (fallback)
        cross_border=cross_border,
    )
```

**Flow:**
```
try:
    ← ONNX inference
    confidence = 0.95
except:
    ← Fallback JSON
    confidence = 0.40  ← Signals "degraded mode" to agent
```

The agent still routes, but with lower confidence score in `score_breakdown`.

---

## 📈 Performance Characteristics

### Latency Breakdown (Per Transaction)

```
Cold Start (first invocation):
  S3 download model            80ms
  Load ONNX session             50ms
  Parse features                 2ms
  onnxruntime.run()             10ms
  ────────────────────────────────
  Total                         142ms
  
Warm Start (cached Lambda):
  Parse features                 2ms
  onnxruntime.run()             10ms
  ────────────────────────────────
  Total                         12ms
```

### Comparison

| Approach | Latency | Notes |
|---|---|---|
| ONNX (in-process) | 10-15ms | ⭐ Chosen |
| SageMaker endpoint | 100-200ms | Network + service |
| Pre-computed JSON | 1-2ms | Only 84K combinations |
| Call scheme API | 500-2000ms | Real payment network |

**Real-world p99**: ~270ms total (Bedrock latency dominates, not ONNX)

---

## 🔄 Model Updates / Retraining

### Current State (Academic Demo)

The model is **one-time trained and committed to repo**:
```
ml/
├── interchange_model.onnx         ← Version-controlled
├── feature_metadata.json          ← Version-controlled
└── train_interchange_model.py     ← Reproducible training script
```

### For Production Use

1. **Monthly retraining** (new historical data):
   ```bash
   python ml/generate_synthetic_data.py  # Generate from latest settlement data
   python ml/train_interchange_model.py --upload  # Train + upload to S3
   ```

2. **Blue-green deployment**:
   ```
   S3: old_model.onnx
   S3: new_model.onnx  ← Deployed
   ```

3. **Lambda updates model key** via CloudFormation parameter

4. **Gradual rollout**: Route percentage of traffic to new model, validate metrics

---

## 🎓 Key Takeaways

| Aspect | Why ONNX |
|---|---|
| **Latency** | 10ms inference vs. 100-200ms network hop |
| **Cost** | No provisioned endpoints; model is just an S3 file |
| **Portability** | Same .onnx file runs Python, C++, .NET, browsers |
| **Reliability** | In-process execution, fallback to static JSON |
| **Size** | 2-5MB model + 10MB runtime vs. 500MB+ frameworks |
| **Version control** | Model artifact in Git for reproducibility |
| **Encoding** | Feature order locked in `feature_metadata.json` |
| **Determinism** | Predictions are identical given same input |

---

## 📚 Files to Study

| File | Purpose |
|---|---|
| [ml/train_interchange_model.py](ml/train_interchange_model.py) | XGBoost training → ONNX export |
| [ml/feature_metadata.json](ml/feature_metadata.json) | Feature encoding contract |
| [src/config/model_config.py](src/config/model_config.py) | ONNX session loading & caching |
| [src/service/interchange_estimation_service.py](src/service/interchange_estimation_service.py) | Feature vector building + inference |
| [resources/interchange-fallback-rates.json](resources/interchange-fallback-rates.json) | Static fallback rates |
| [ml/model_card.md](ml/model_card.md) | Model architecture & metrics |

---

## 🔗 ONNX Ecosystem

**Official Resources:**
- [ONNX.ai](https://onnx.ai/) — Format specification
- [`onnxruntime`](https://onnxruntime.ai/) — Inference runtime (Python, C++, .NET, JS, etc.)
- [`onnxmltools`](https://github.com/onnx/onnxmltools) — Scikit-learn/XGBoost → ONNX converter
- [`skl2onnx`](https://github.com/onnx/sklearn-onnx) — Pure scikit-learn → ONNX

**Model Zoo:**
- Vision: ResNet, MobileNet, EfficientNet
- NLP: BERT, GPT (quantized variants)
- Tabular: XGBoost, LightGBM, scikit-learn

**Deployment Platforms:**
- **AWS**: Lambda, SageMaker (inference)
- **Azure**: Container Instances, Functions, IoT Edge
- **GCP**: Cloud Run, Vertex AI
- **Edge**: TensorRT, OpenVINO, CoreML
- **Browser**: ONNX.js, WebAssembly

---

## 💡 Summary

**ONNX enables this project to:**
1. ✅ Run ML inference **inside Lambda** (not over network)
2. ✅ Keep **latency low** (~10ms inference vs. 100-200ms endpoint call)
3. ✅ **Eliminate operational complexity** (no SageMaker endpoint management)
4. ✅ **Version-control the model** (reproducible, immutable artifact)
5. ✅ **Fail gracefully** (fallback to static rates)
6. ✅ **Stay portable** (same model runs anywhere ONNX Runtime is available)

This is why ONNX was chosen over SageMaker, PyTorch, or pre-computed static rates. It's the **sweet spot** for serverless ML inference: lightweight, fast, portable, and deterministic.
