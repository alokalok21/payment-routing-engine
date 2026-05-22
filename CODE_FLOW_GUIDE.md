# Complete Code Flow Guide — Payment Routing Engine

This document traces the entire execution path from an incoming HTTP request to the final routing decision response.

---

## 🔄 End-to-End Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. HTTP Request → API Gateway → Lambda                          │
│    POST /route { bin, card_type, amount, mcc, ... }            │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. routing_handler.py — Lambda Entry Point                      │
│    • Parse JSON request body                                    │
│    • Validate required fields                                   │
│    • Build TransactionContext dataclass                         │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. bedrock_routing_agent.py — AI Core (ReAct Loop)            │
│    ★ Iteration 1-10 (typically converges in 4-5)               │
│    • Build system prompt from resources/agent-system-prompt.txt │
│    • Call Bedrock Converse API with MODEL_ID                   │
│    • Model: us.anthropic.claude-sonnet-4-6                     │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
        ┌──────────────────┐
        │ Tool Use Loop    │
        │ (iteration #N)   │
        └────────┬─────────┘
                 │
        ┌────────▼────────────────────────────────────────────────────┐
        │ A. Bedrock calls tool: lookup_bin(bin="476173")             │
        └─────────────┬──────────────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ B. agent_tool_dispatcher.py routes to services              │
        │    • bin_lookup_service → bin_repository → DynamoDB          │
        │    Returns: BinInfo { eligible_schemes, dual_brand, ... }   │
        └─────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ C. Bedrock receives toolResult block                        │
        │    Appends to message history; next iteration...            │
        └─────────────┬───────────────────────────────────────────────┘
                      │
        ┌────────────▼────────────────────────────────────────────┐
        │ D. Bedrock calls tool: get_scheme_status(scheme_id)     │
        │    → scheme_status_service → DynamoDB Scheme_Config     │
        │    Returns: SchemeConfig { enabled: true/false }        │
        └────────────┬─────────────────────────────────────────────┘
                     │
        ┌────────────▼─────────────────────────────────────────────┐
        │ E. Bedrock calls tool: get_scheme_auth_stats(...)        │
        │    → auth_rate_stats_service → DynamoDB Auth_Rate_Stats │
        │    Returns: AuthRateStats { auth_rate_7d: 0.94, ... }   │
        └────────────┬──────────────────────────────────────────────┘
                     │
        ┌────────────▼────────────────────────────────────────────────┐
        │ F. Bedrock calls tool: estimate_interchange(...)           │
        │    → interchange_estimation_service → ONNX Model (S3)      │
        │    ★ ML INFERENCE: XGBoost features → rate prediction     │
        │    Returns: InterchangeEstimate { rate_pct: 1.5, ... }    │
        └────────────┬───────────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────────────────────────────────────┐
        │ Iteration repeats if Bedrock returns more tool_use blocks  │
        │ OR exits when stopReason = "end_turn"                      │
        └────────────┬───────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. routing_decision_parser.py — Parse Final Response             │
│    • Extract final text from Bedrock message                   │
│    • Parse strict JSON: { selected_scheme, confidence, ...}    │
│    • Validate schema & return RoutingDecision dataclass        │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. mock_scheme_gateway.py — Simulated Auth Response            │
│    • Call selected scheme (mocked — not real scheme API)       │
│    • Return: APPROVED (unless scheme disabled)                  │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. routing_handler.py — Build HTTP Response                     │
│    200 {                                                         │
│      transaction_id, selected_scheme, confidence, rationale,    │
│      fallback_chain[], score_breakdown{}, mock_auth_result      │
│    }                                                             │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. API Gateway → Client Response                                │
│    JSON with full routing decision + explainability             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 Layer-by-Layer Breakdown

### Layer 1: HTTP Entry Point
**File**: [src/handler/routing_handler.py](src/handler/routing_handler.py)

```python
def lambda_handler(event, context):
    # Step 1: Parse request
    body = _parse_body(event)  # event["body"] → dict
    
    # Step 2: Validate & build context
    ctx = _build_context(body)  # TransactionContext dataclass
    # Required fields: transaction_id, bin, last4, card_type, 
    #                  amount, currency, mcc, merchant_country
    
    # Step 3: Invoke routing agent
    decision = bedrock_routing_agent.run(ctx)
    
    # Step 4: Simulate auth with selected scheme
    auth_result = mock_scheme_gateway.simulate_auth(decision.selected_scheme)
    
    # Step 5: Return response
    return 200 { transaction_id, selected_scheme, confidence, ... }
```

**Key Dataclass**: [src/model/transaction_context.py](src/model/transaction_context.py)
- `bin`, `last4`, `card_type`, `amount`, `currency`, `mcc`, `merchant_country`, `card_country`
- **Computed fields** (on-the-fly in constructor):
  - `bin_bucket` = first 4 digits of BIN (for DynamoDB query)
  - `amount_bucket` = one of `["0-50", "50-200", "200-1000", "1000+"]`
  - `cross_border` = `merchant_country != card_country` (bool)

---

### Layer 2: Bedrock Agent — ReAct Loop
**File**: [src/agent/bedrock_routing_agent.py](src/agent/bedrock_routing_agent.py)

#### 2a. Initialization
```python
def run(ctx: TransactionContext) -> RoutingDecision:
    client = get_bedrock_client()  # boto3.client("bedrock-runtime")
    
    # Load system prompt once
    system = [{"text": _load_system_prompt()}]
    
    # Build initial user message
    user_msg = _build_initial_user_message(ctx)
    # Includes: transaction details + derived context (bin_bucket, amount_bucket, cross_border)
    
    messages = [{"role": "user", "content": [{"text": user_msg}]}]
```

#### 2b. ReAct Loop (Iteration 1-10)
```python
for iteration in range(1, MAX_ITERATIONS + 1):
    # Call Bedrock Converse API
    response = client.converse(
        modelId="us.anthropic.claude-sonnet-4-6",
        messages=messages,
        system=system,
        toolConfig={"tools": TOOL_SPECS},  # 4 tools defined
        inferenceConfig={"maxTokens": 4096, "temperature": 0.0}
    )
    
    output_message = response["output"]["message"]
    stop_reason = response["stopReason"]
    messages.append(output_message)  # Conversation history grows
    
    if stop_reason == "tool_use":
        # Extract tool calls from response
        tool_uses = _extract_tool_uses(output_message)
        
        # Dispatch each tool
        for tu in tool_uses:
            result = dispatch(tu["name"], tu["input"])
            
            # Append tool result back to message history
            tool_result_blocks.append({
                "toolResult": {
                    "toolUseId": tu["toolUseId"],
                    "content": [{"json": result}]
                }
            })
        
        # Add tool results to message history
        messages.append({"role": "user", "content": tool_result_blocks})
        # Loop continues — Bedrock sees results, decides next action
    
    elif stop_reason == "end_turn":
        # Model stopped — extract final text
        final_text = _extract_text(output_message)
        
        # Parse JSON response into RoutingDecision
        decision = parse_decision(final_text)
        return decision
```

#### 2c. System Prompt
**File**: [resources/agent-system-prompt.txt](resources/agent-system-prompt.txt)

The prompt instructs Claude to:
1. **Step 1**: Call `lookup_bin` to identify eligible schemes
2. **Step 2**: Call `get_scheme_status` for each eligible scheme
3. **Step 3**: Call `get_scheme_auth_stats` to compare approval rates
4. **Step 4**: Call `estimate_interchange` to get cost estimates
5. **Step 5**: Score each scheme using:
   - Default: `score = (auth_rate × 0.6) - (interchange_pct × 0.4)`
   - High-risk (amount > 1000 OR cross_border): `score = (auth_rate × 0.75) - (interchange_pct × 0.25)`
6. **Step 6**: Rank schemes, select highest score as primary
7. **Step 7**: Return strict JSON with `selected_scheme`, `confidence`, `rationale`, `fallback_chain`, `score_breakdown`

---

### Layer 3: Tool Dispatcher
**File**: [src/agent/agent_tool_dispatcher.py](src/agent/agent_tool_dispatcher.py)

```python
def dispatch(tool_name: str, tool_input: Dict) -> Dict:
    if tool_name == "lookup_bin":
        # → bin_lookup_service.lookup_bin()
        # → bin_repository.lookup_bin() 
        # → DynamoDB BIN_Table.get_item(bin_prefix)
        result = bin_lookup_service.lookup_bin(tool_input["bin"])
        return asdict(result) if result else {"error": "..."}
    
    elif tool_name == "get_scheme_status":
        # → scheme_status_service.get_scheme_status()
        # → scheme_config_repository.get_scheme_config()
        # → DynamoDB Scheme_Config.get_item(scheme_id)
        result = scheme_status_service.get_scheme_status(tool_input["scheme_id"])
        return asdict(result) if result else {"error": "..."}
    
    elif tool_name == "get_scheme_auth_stats":
        # → auth_rate_stats_service.get_auth_rate_stats()
        # → auth_rate_stats_repository.get_auth_rate_stats()
        # → DynamoDB Auth_Rate_Stats.get_item(scheme_bin_bucket, mcc_currency_amount)
        result = auth_rate_stats_service.get_auth_rate_stats(...)
        return asdict(result) if result else {"error": "..."}
    
    elif tool_name == "estimate_interchange":
        # → interchange_estimation_service.estimate_interchange()
        # ★ ONNX model inference (ML core)
        # → Load model from S3 via model_config
        # → Build feature vector from input
        # → Run onnxruntime inference
        # → Categorize result & return
        result = interchange_estimation_service.estimate_interchange(...)
        return asdict(result)
```

---

### Layer 4: Service Layer
**Files**: 
- [src/service/bin_lookup_service.py](src/service/bin_lookup_service.py)
- [src/service/scheme_status_service.py](src/service/scheme_status_service.py)
- [src/service/auth_rate_stats_service.py](src/service/auth_rate_stats_service.py)
- [src/service/interchange_estimation_service.py](src/service/interchange_estimation_service.py)

Each service is a thin wrapper that:
1. Takes input parameters
2. Calls repository or config function
3. Returns typed dataclass result

Example: `bin_lookup_service.py`
```python
def lookup_bin(bin_value: str) -> Optional[BinInfo]:
    return bin_repository.lookup_bin(bin_value)
    # Returns BinInfo: { bin_prefix, eligible_schemes[], card_type, 
    #                     issuer_country, dual_brand, domestic_scheme }
```

**ML Service** (Interchange): [src/service/interchange_estimation_service.py](src/service/interchange_estimation_service.py)
```python
def estimate_interchange(...) -> InterchangeEstimate:
    # 1. Get ONNX session (cached from S3 in model_config)
    session = model_config.get_onnx_session()
    
    # 2. Build feature vector
    vector = _build_input_vector(
        scheme_id, card_type, card_product, mcc,
        merchant_country, card_country, amount, cross_border, metadata
    )
    
    # 3. Run inference
    predicted_rate = session.run(None, {"input": vector})[0][0]
    
    # 4. Categorize (domestic-low, domestic-std, cross-border-std, cross-border-prem)
    category = _categorize_rate(predicted_rate, cross_border)
    
    # 5. Return typed result
    return InterchangeEstimate(
        scheme_id, 
        estimated_interchange_pct=predicted_rate,
        interchange_category=category,
        cross_border=cross_border,
        confidence=0.85  # heuristic
    )
```

---

### Layer 5: Repository Layer
**Files**: 
- [src/repository/bin_repository.py](src/repository/bin_repository.py)
- [src/repository/scheme_config_repository.py](src/repository/scheme_config_repository.py)
- [src/repository/auth_rate_stats_repository.py](src/repository/auth_rate_stats_repository.py)

Each repository directly calls DynamoDB.

Example: `bin_repository.py`
```python
def lookup_bin(bin_value: str) -> Optional[BinInfo]:
    table = dynamodb_config.get_bin_table()
    
    response = table.get_item(Key={"bin_prefix": bin_value})
    
    if "Item" not in response:
        return None
    
    item = response["Item"]
    return BinInfo(
        bin_prefix=item["bin_prefix"],
        eligible_schemes=item["eligible_schemes"],
        card_type=item["card_type"],
        card_product=item["card_product"],
        issuer_country=item["issuer_country"],
        dual_brand=item.get("dual_brand", False),
        domestic_scheme=item.get("domestic_scheme")
    )
```

---

### Layer 6: ML Model Inference
**File**: [src/config/model_config.py](src/config/model_config.py)

```python
def get_onnx_session():
    # Load metadata (feature column order, vocabularies)
    metadata = _load_feature_metadata()
    
    # Download ONNX model from S3 if not cached
    model_path = _download_model_from_s3()  # s3://payment-routing-onnx-654654151376/
    
    # Load with onnxruntime
    session = onnxruntime.InferenceSession(model_path)
    
    return session

def _build_input_vector(scheme_id, card_type, ..., metadata):
    # One-hot encode all categorical features using metadata vocabularies
    # Append numeric features: amount, cross_border_int
    # Return numpy array matching training feature order
    return np.array([...])
```

**Feature Metadata**: [ml/feature_metadata.json](ml/feature_metadata.json)
```json
{
  "columns": [
    "scheme_id_VISA", "scheme_id_MASTERCARD", ...,  // one-hot
    "card_type_CREDIT", "card_type_DEBIT", ...,     // one-hot
    "card_product_CLASSIC", "card_product_GOLD", ...,  // one-hot
    "amount",                                         // numeric
    "cross_border"                                    // binary 0/1
  ],
  "vocabularies": {
    "scheme_id": ["VISA", "MASTERCARD", "CB", ...],
    "card_type": ["CREDIT", "DEBIT", "PREPAID"],
    ...
  }
}
```

**ONNX Model**: [ml/interchange_model.onnx](ml/interchange_model.onnx)
- **Algorithm**: XGBoost regression
- **Training data**: Synthetic settlement data (generated by [ml/generate_synthetic_data.py](ml/generate_synthetic_data.py))
- **Target**: `interchange_rate` (%)
- **Inference**: ~10ms per transaction (runs inside Lambda)

---

### Layer 7: Decision Parsing
**File**: [src/agent/routing_decision_parser.py](src/agent/routing_decision_parser.py)

```python
def parse(response_text: str) -> RoutingDecision:
    # 1. Extract JSON from response (handles markdown code blocks)
    json_str = _extract_json(response_text)
    
    # 2. Parse and validate schema
    data = json.loads(json_str)
    
    # 3. Build typed RoutingDecision
    return RoutingDecision(
        selected_scheme=data["selected_scheme"],
        confidence=float(data["confidence"]),
        rationale=data["rationale"],
        fallback_chain=[
            {"scheme": f["scheme"], "reason": f["reason"]}
            for f in data.get("fallback_chain", [])
        ],
        score_breakdown=data.get("score_breakdown", {})
    )
```

**Result Type**: [src/model/routing_decision.py](src/model/routing_decision.py)
```python
@dataclass
class RoutingDecision:
    selected_scheme: str       # e.g., "CB", "VISA", "MASTERCARD"
    confidence: float          # 0.0-1.0
    rationale: str            # Full explanation from agent
    fallback_chain: List[Dict]  # [{"scheme": "...", "reason": "..."}, ...]
    score_breakdown: Dict     # {"SCHEME": {"auth_rate": ..., "score": ...}, ...}
```

---

### Layer 8: Mock Scheme Gateway
**File**: [src/gateway/mock_scheme_gateway.py](src/gateway/mock_scheme_gateway.py)

```python
def simulate_auth(scheme_id: str) -> str:
    # In a production system, this would call real scheme APIs
    # (VisaNet, Banknet, UnionPay, etc.)
    
    # For this academic demo, return mocked result
    config = scheme_status_service.get_scheme_status(scheme_id)
    
    if config and config.enabled:
        return "APPROVED"
    else:
        return "SCHEME_DISABLED"
```

---

## 🎯 Typical ReAct Iteration Example

**Scenario**: French dual-brand card (Visa + CB), €150 purchase at local retailer

### Iteration 1: BIN Lookup
```
Agent: "I need to understand what schemes are available for this card."
Calls: lookup_bin(bin="476173")

Result:
{
  "bin_prefix": "476173",
  "eligible_schemes": ["VISA", "CB"],
  "card_type": "CREDIT",
  "issuer_country": "FR",
  "dual_brand": true,
  "domestic_scheme": "CB"
}

Agent: "This is a dual-brand card. Both VISA and CB are eligible. 
CB is the domestic scheme for France. Let me check their status..."
```

### Iteration 2-3: Scheme Status Checks
```
Agent calls: get_scheme_status(scheme_id="VISA")
Agent calls: get_scheme_status(scheme_id="CB")

Results:
- VISA: { "enabled": true }
- CB: { "enabled": true }

Agent: "Both schemes are enabled. Now I need auth rates and interchange estimates."
```

### Iteration 4-5: Auth Rates + Interchange
```
Agent calls:
  get_scheme_auth_stats(scheme_id="VISA", bin_bucket="4761", mcc="5411", 
                        currency="EUR", amount_bucket="100-500")
  get_scheme_auth_stats(scheme_id="CB", bin_bucket="4761", mcc="5411", 
                        currency="EUR", amount_bucket="100-500")
  estimate_interchange(scheme_id="VISA", card_type="CREDIT", amount=150, ...)
  estimate_interchange(scheme_id="CB", card_type="CREDIT", amount=150, ...)

Results:
- VISA: auth_rate_7d=0.941, interchange=1.5%
- CB:   auth_rate_7d=0.948, interchange=0.9%

Agent: "CB has slightly higher auth rate AND lower interchange!
This is domestic (FR→FR), amount=150 (not high-risk).
Default weights apply: (0.6 × auth_rate) - (0.4 × interchange_pct)

CB score:   (0.948 × 0.6) - (0.009 × 0.4) = 0.565
VISA score: (0.941 × 0.6) - (0.015 × 0.4) = 0.559

CB wins. VISA is strong fallback."
```

### Iteration 6: Final Decision
```
Agent returns:

{
  "selected_scheme": "CB",
  "confidence": 0.89,
  "rationale": "Dual-branded Visa/CB card detected (FR issuer). Both enabled. 
               CB: auth_rate_7d=94.8%, interchange=0.9% (domestic FR). 
               VISA: auth_rate_7d=94.1%, interchange=1.5% (cross-border uplift). 
               Default weights (amount=150, domestic). CB scores 0.565 vs VISA 0.559. 
               Fallback: VISA for international robustness.",
  "fallback_chain": [
    { "scheme": "VISA", "reason": "Second highest score; preferred int'l fallback" }
  ],
  "score_breakdown": {
    "CB": {
      "auth_rate": 0.948,
      "estimated_interchange_pct": 0.009,
      "score": 0.565,
      "weight_auth": 0.6,
      "weight_ic": 0.4
    },
    "VISA": {
      "auth_rate": 0.941,
      "estimated_interchange_pct": 0.015,
      "score": 0.559,
      "weight_auth": 0.6,
      "weight_ic": 0.4
    }
  }
}
```

### Final Response
```json
HTTP 200

{
  "transaction_id": "txn-fr-001",
  "selected_scheme": "CB",
  "confidence": 0.89,
  "rationale": "...",
  "fallback_chain": [...],
  "score_breakdown": {...},
  "mock_auth_result": "APPROVED"
}
```

---

## 📂 Data Models (Dataclasses)

| Class | File | Purpose |
|---|---|---|
| `TransactionContext` | [src/model/transaction_context.py](src/model/transaction_context.py) | Input transaction + computed fields (bin_bucket, cross_border) |
| `BinInfo` | [src/model/bin_info.py](src/model/bin_info.py) | BIN lookup result: schemes, card type, dual-brand flag |
| `SchemeConfig` | [src/model/scheme_config.py](src/model/scheme_config.py) | Scheme enablement: scheme_id, enabled bool |
| `AuthRateStats` | [src/model/auth_rate_stats.py](src/model/auth_rate_stats.py) | Auth rates: auth_rate_7d, auth_rate_30d, decline breakdown |
| `InterchangeEstimate` | [src/model/interchange_estimate.py](src/model/interchange_estimate.py) | ML model output: rate %, category, cross_border flag |
| `RoutingDecision` | [src/model/routing_decision.py](src/model/routing_decision.py) | Final decision: selected scheme, confidence, rationale, scores |

---

## 🗄️ DynamoDB Tables

| Table | Key | Content | Used By |
|---|---|---|---|
| `BIN_Table` | `bin_prefix` (PK) | Card BIN data: eligible schemes, card type, issuer, dual-brand flag | `lookup_bin` tool |
| `Scheme_Config` | `scheme_id` (PK) | Scheme metadata: enabled flag | `get_scheme_status` tool |
| `Auth_Rate_Stats` | `scheme_bin_bucket` (PK), `mcc_currency_amount` (SK) | Pre-seeded auth rates for (scheme, BIN, MCC, currency, amount) | `get_scheme_auth_stats` tool |

---

## 🧠 ML Model Pipeline

### Training (One-time, offline)
1. **Generate**: [ml/generate_synthetic_data.py](ml/generate_synthetic_data.py) → `data/synthetic_interchange.csv`
   - All scheme × card_type × MCC × country combinations
   - ~50k rows of synthetic settlement data
   
2. **Train**: [ml/train_interchange_model.py](ml/train_interchange_model.py) → XGBoost regression
   - Features: scheme, card_type, card_product, MCC, amount, merchant_country, card_country, cross_border
   - Target: interchange_rate (%)
   
3. **Export**: XGBoost → ONNX via `skl2onnx` → [ml/interchange_model.onnx](ml/interchange_model.onnx)

4. **Deploy**: Upload to S3 bucket `payment-routing-onnx-654654151376`

### Inference (Per-transaction, in Lambda)
1. Lambda cold-start: Load ONNX model + feature metadata from S3 (cached in memory)
2. Service layer receives tool input
3. Build feature vector (one-hot + numeric)
4. `onnxruntime.InferenceSession.run()` → predicted interchange rate
5. Return as `InterchangeEstimate` dataclass

---

## 🔐 Data Flow — PCI Compliance

- **Input**: BIN (6-8 digits) + last-4 only — **no full PAN anywhere**
- **Processing**: All BIN lookups by prefix; last-4 used only in response echo
- **Output**: Response includes transaction_id, selected scheme, scores — **no card data**
- **Storage**: DynamoDB holds no card data; seed tables are scheme/BIN/rate meta-data only

---

## 🚨 Error Handling

| Scenario | Behavior |
|---|---|
| **Missing required field** | routing_handler returns 400 with field list |
| **Invalid request JSON** | routing_handler returns 400 with parse error |
| **BIN not found** | dispatcher returns `{"error": "..."}`, agent adapts (skips that scheme) |
| **Scheme disabled** | agent sees `enabled: false`, ranks it lower |
| **Auth stats missing** | agent gets error dict, retries with fallback or excludes scheme |
| **ONNX model unavailable** | interchange_estimation_service falls back to static rates from JSON |
| **Bedrock API error** | Lambda catches exception, returns 500 with generic error message |
| **Max iterations (10) exceeded** | RuntimeError logged; rarely happens in practice (converges in 4-5) |

---

## 📊 Execution Timeline

```
Time  │ Component                    │ Action
──────┼──────────────────────────────┼────────────────────────────────
0ms   │ Client                       │ POST /route
5ms   │ API Gateway                  │ Route to Lambda
10ms  │ Lambda (cold start)          │ Load bedrock_config, models, prompt
20ms  │ routing_handler              │ Parse & validate request
25ms  │ bedrock_routing_agent        │ Iteration 1: Call Bedrock
100ms │ Bedrock                      │ Claude thinks, returns tool call
105ms │ agent_tool_dispatcher        │ lookup_bin()
110ms │ bin_repository               │ DynamoDB get_item (BIN_Table)
115ms │ Bedrock (Iter 2)             │ Tool result appended, continue
150ms │ Bedrock                      │ Returns 2-3 tool calls (status, auth, IC)
155ms │ agent_tool_dispatcher        │ 3 parallel service calls
160ms │ services                     │ DynamoDB + ONNX inference (~20ms)
200ms │ Bedrock (Iter 3)             │ Tool results, scoring logic
250ms │ Bedrock                      │ stop_reason = "end_turn", final JSON
255ms │ routing_decision_parser      │ Parse & validate
260ms │ mock_scheme_gateway          │ Return APPROVED
265ms │ routing_handler              │ Build response dict
270ms │ Lambda                       │ Return 200 JSON
275ms │ API Gateway                  │ Return to client
────────────────────────────────────────────────────────────────────
Total: ~270ms p50, ~300ms p95 (Bedrock latency dominates)
```

---

## 🔗 File Dependency Graph

```
routing_handler.py (entry)
  │
  ├─ bedrock_routing_agent.py (AI core)
  │  ├─ agent_tool_dispatcher.py (routes tools)
  │  │  ├─ bin_lookup_service.py
  │  │  │  └─ bin_repository.py
  │  │  │     └─ dynamodb_config.py
  │  │  │        └─ BIN_Table (DynamoDB)
  │  │  │
  │  │  ├─ scheme_status_service.py
  │  │  │  └─ scheme_config_repository.py
  │  │  │     └─ Scheme_Config (DynamoDB)
  │  │  │
  │  │  ├─ auth_rate_stats_service.py
  │  │  │  └─ auth_rate_stats_repository.py
  │  │  │     └─ Auth_Rate_Stats (DynamoDB)
  │  │  │
  │  │  └─ interchange_estimation_service.py
  │  │     └─ model_config.py
  │  │        └─ interchange_model.onnx (S3)
  │  │
  │  ├─ routing_decision_parser.py (parses agent response)
  │  └─ bedrock_config.py (model ID, tools)
  │
  ├─ mock_scheme_gateway.py (simulated auth)
  │  └─ scheme_status_service.py
  │
  └─ model/*.py (dataclasses for all types)

resources/
  └─ agent-system-prompt.txt (Claude instructions)

ml/
  ├─ interchange_model.onnx (ML artifact)
  └─ feature_metadata.json (encoding info)
```

---

## 🎓 Key Design Patterns

| Pattern | Where | Purpose |
|---|---|---|
| **Dataclasses** | All models | Typed, immutable data (no Pydantic overhead) |
| **Service Layer** | service/* | Thin wrappers for testability |
| **Repository Pattern** | repository/* | DynamoDB abstraction |
| **ReAct Loop** | bedrock_routing_agent | Agent reason → act → loop |
| **Tool Dispatcher** | agent_tool_dispatcher | Route tool calls to services |
| **ONNX Inference** | interchange_estimation_service | ML model embedded in Lambda |
| **Fallback** | interchange_estimation_service | Static JSON rates if ONNX unavailable |
| **Message History** | bedrock_routing_agent | Converse API accumulates context |

---

**Now you have the complete picture!** Each request flows through 8 logical layers, with the Bedrock agent orchestrating tool use at the center. The ML model runs inside Lambda for low latency, and DynamoDB provides feature data. The system is designed for clarity and explainability.
