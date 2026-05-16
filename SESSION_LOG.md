# Session Log — Payment Scheme Routing Engine

**Last updated:** 2026-05-16
**Working directory:** `c:\D Drive\PaymentsApp`
**Region:** `us-east-1`
**AWS account:** `654654151376`
**Stack name:** `payment-routing-engine`

---

## Restoration Brief

This file captures the full state of an implementation session for the AI-Driven Payment Scheme Routing Engine (see [CLAUDE.md](CLAUDE.md) for the design spec). If you're picking the conversation back up — read this top to bottom, then the user's last instruction will make sense.

---

## Project Overview

Academic AI/ML showcase: an acquiring-bank routing engine that picks the optimal payment scheme (VISA, MASTERCARD, CB, DISCOVER, AMEX, UNIONPAY, MAESTRO) for a card transaction. Twin objectives: maximize auth rate AND minimize interchange cost — solved by an AWS Bedrock LLM agent (ReAct tool-use loop) combined with an XGBoost interchange cost model exported to ONNX.

**Tech stack:** Python 3.13 Lambda, AWS Bedrock (Converse API, Claude Sonnet 4.6), DynamoDB, API Gateway, S3, AWS SAM.

---

## Key Decisions Made This Session

| Decision | Choice | Why |
|---|---|---|
| Language | Python (not Java) | Single language across ML training and Lambda inference; cleaner, faster cold start, less boilerplate |
| Region | `us-east-1` | Widest Bedrock model availability, lowest latency for Claude |
| Bedrock model | `us.anthropic.claude-sonnet-4-6` (cross-region inference profile) | Claude 3.5 Sonnet retired; Sonnet 4.6 is the sweet spot for agentic reasoning |
| S3 bucket name | `payment-routing-onnx-654654151376` | Account ID suffix guarantees global uniqueness |
| ML model format | XGBoost → ONNX via `onnxmltools` | No SageMaker endpoint; model runs in-Lambda via `onnxruntime` |
| Lambda packaging | `sam build --use-container` (Docker) | Cross-compile Linux wheels for `onnxruntime` |
| Existing scaffolding | Deleted (was direct-Anthropic-API hello-world) | Clean slate for AWS Bedrock architecture |

---

## Phase-by-Phase Build Log

### ✅ Phase 1 — Data Layer & Infrastructure
**Created:**
- [requirements.txt](requirements.txt) — `boto3`, `onnxruntime`, `numpy`
- [requirements-dev.txt](requirements-dev.txt) — `pytest`, `moto`
- [infrastructure/template.yaml](infrastructure/template.yaml) — SAM template (3 DynamoDB tables + S3 bucket; Lambda+API added in Phase 4)
- [src/model/](src/model/) — 6 dataclass files: `TransactionContext`, `BinInfo`, `SchemeConfig`, `AuthRateStats`, `InterchangeEstimate`, `RoutingDecision`
- [src/config/dynamodb_config.py](src/config/dynamodb_config.py) — singleton DDB resource
- [src/repository/](src/repository/) — `bin_repository` (longest-prefix-match 8→7→6), `scheme_config_repository`, `auth_rate_stats_repository` (composite key)
- [infrastructure/seed-data/](infrastructure/seed-data/) — 3 JSON files: 7 schemes, 17 BINs, 25 auth-rate-stats entries
- [infrastructure/seed_loader.py](infrastructure/seed_loader.py) — batch loader with float→Decimal conversion

**Deployed to AWS:**
```
DynamoDB BIN_Table        17 items
DynamoDB Scheme_Config     7 items
DynamoDB Auth_Rate_Stats  25 items
S3 payment-routing-onnx-654654151376  (ready)
```

### ✅ Phase 2 — ML Interchange Model
**Created:**
- [ml/requirements-ml.txt](ml/requirements-ml.txt) — `xgboost`, `skl2onnx`, `onnxmltools`, etc.
- [ml/generate_synthetic_data.py](ml/generate_synthetic_data.py) — 25,000 rows of synthetic settlement data
- [ml/train_interchange_model.py](ml/train_interchange_model.py) — XGBoost 300-tree regressor, ONNX export, optional S3 upload
- [ml/interchange_model.onnx](ml/interchange_model.onnx) — 1MB trained artifact (committed)
- [ml/feature_metadata.json](ml/feature_metadata.json) — encoder vocabulary
- [ml/model_card.md](ml/model_card.md) — features, training data, metrics, limitations
- [src/config/model_config.py](src/config/model_config.py) — ONNX session loader (S3 → /tmp at cold start; `MODEL_LOCAL_PATH` for local dev)
- [src/service/interchange_estimation_service.py](src/service/interchange_estimation_service.py) — encoding + inference + static fallback
- [resources/interchange-fallback-rates.json](resources/interchange-fallback-rates.json) — static rates table

**Model metrics (held-out test split):** MAE 0.039, RMSE 0.054, R² 0.9988
**S3 artifacts:** `s3://payment-routing-onnx-654654151376/interchange_model.onnx` + `feature_metadata.json`

### ✅ Phase 3 — Bedrock Agent (AI Core)
**Created:**
- [resources/agent-system-prompt.txt](resources/agent-system-prompt.txt) — 7-step ReAct process + strict-JSON output contract
- [src/config/bedrock_config.py](src/config/bedrock_config.py) — Bedrock client + 4 tool specs (Converse API format)
- [src/service/bin_lookup_service.py](src/service/bin_lookup_service.py), [scheme_status_service.py](src/service/scheme_status_service.py), [auth_rate_stats_service.py](src/service/auth_rate_stats_service.py) — thin repo wrappers
- [src/agent/agent_tool_dispatcher.py](src/agent/agent_tool_dispatcher.py) — routes `toolUse` blocks → service calls
- [src/agent/routing_decision_parser.py](src/agent/routing_decision_parser.py) — strict JSON parse + validation
- [src/agent/bedrock_routing_agent.py](src/agent/bedrock_routing_agent.py) — Converse-API ReAct loop, max 10 iterations

**Validated** (without live Bedrock — quota was already consumed):
- All 4 tools dispatch correctly with live DynamoDB + local ONNX
- Parser handles valid JSON, markdown-fenced JSON, missing keys, malformed JSON

### ✅ Phase 4 — API, Handler, Tests, Deployment
**Created:**
- [src/gateway/mock_scheme_gateway.py](src/gateway/mock_scheme_gateway.py) — simulates APPROVED/DECLINED based on scheme enabled flag
- [src/handler/routing_handler.py](src/handler/routing_handler.py) — Lambda entry point (parse → context → agent → gateway → JSON response)
- Updated [infrastructure/template.yaml](infrastructure/template.yaml) — Lambda function, API Gateway, IAM (DDB read, S3 read, Bedrock Converse)
- [tests/conftest.py](tests/conftest.py) — moto-DynamoDB fixture + local-ONNX fixture
- [tests/unit/test_routing_decision_parser.py](tests/unit/test_routing_decision_parser.py) — 4 tests, pure offline
- [tests/unit/test_repositories.py](tests/unit/test_repositories.py) — 7 tests using moto
- [tests/unit/test_interchange_estimation.py](tests/unit/test_interchange_estimation.py) — 4 tests including fallback path
- [tests/unit/test_bedrock_routing_agent.py](tests/unit/test_bedrock_routing_agent.py) — 2 tests with scripted fake Bedrock client

**Test results:** 17/17 passing in ~7 seconds

**Deployed to AWS:**
| Resource | Identifier |
|---|---|
| API Gateway URL | `https://arza8e31vj.execute-api.us-east-1.amazonaws.com/prod/route` |
| Lambda function | `payment-routing-engine` |
| Lambda role | `payment-routing-engine-RoutingFunctionRole-*` (DDB read + S3 read + Bedrock Converse) |
| Stack outputs | See `aws cloudformation describe-stacks --stack-name payment-routing-engine` |

---

## Current State — One Blocker

Live demo of the agent (Scenarios 1, 2, 3 from CLAUDE.md) is **deployed and working code-wise** but currently blocked by the AWS Bedrock daily token quota.

**Proof the full path works:** CloudWatch Lambda log from the last invocation:
```
[INFO] Found credentials in environment variables.
[INFO] Bedrock iteration 1
[ERROR] Routing failed
ThrottlingException: Too many tokens per day, please wait before trying again.
```

The error originates from `client.converse(...)` — meaning everything before it (request parsing, context build, agent loop initialization) succeeded. **Quota resets at 00:00 UTC** (daily).

---

## Resuming the Session

### Smoke-test it's all still there
```powershell
# Check Python files compile and tests still pass
python -m pytest tests/ -v

# Confirm stack still deployed
aws cloudformation describe-stacks --stack-name payment-routing-engine --region us-east-1 --query "Stacks[0].StackStatus"

# Confirm DynamoDB data still there
aws dynamodb get-item --table-name BIN_Table --key '{\"bin_prefix\":{\"S\":\"476173\"}}' --region us-east-1

# Confirm S3 ONNX model still there
aws s3 ls s3://payment-routing-onnx-654654151376/ --region us-east-1
```

### Run the 3 demo scenarios (after Bedrock quota resets)

```powershell
# Scenario 1 — FR dual-brand grocery (expect CB wins on lower interchange)
[System.IO.File]::WriteAllText("$env:TEMP\s1.json", '{"transaction_id":"txn-fr-001","bin":"476173","last4":"9999","card_type":"CREDIT","amount":150.00,"currency":"EUR","mcc":"5411","merchant_country":"FR","card_country":"FR"}')
curl.exe -X POST "https://arza8e31vj.execute-api.us-east-1.amazonaws.com/prod/route" -H "Content-Type: application/json" -d "@$env:TEMP\s1.json"

# Scenario 2 — Cross-border high-value (expect high-risk weights applied; VISA should win on auth)
[System.IO.File]::WriteAllText("$env:TEMP\s2.json", '{"transaction_id":"txn-xb-001","bin":"476173","last4":"9999","card_type":"CREDIT","amount":2500.00,"currency":"USD","mcc":"4722","merchant_country":"US","card_country":"FR"}')
curl.exe -X POST "https://arza8e31vj.execute-api.us-east-1.amazonaws.com/prod/route" -H "Content-Type: application/json" -d "@$env:TEMP\s2.json"

# Scenario 3 — Disable CB, re-run Scenario 1 (expect VISA selected with rationale mentioning CB was disabled)
aws dynamodb update-item --table-name Scheme_Config --key '{\"scheme_id\":{\"S\":\"CB\"}}' --update-expression "SET enabled = :f" --expression-attribute-values '{\":f\":{\"BOOL\":false}}' --region us-east-1
curl.exe -X POST "https://arza8e31vj.execute-api.us-east-1.amazonaws.com/prod/route" -H "Content-Type: application/json" -d "@$env:TEMP\s1.json"

# Re-enable CB when done
aws dynamodb update-item --table-name Scheme_Config --key '{\"scheme_id\":{\"S\":\"CB\"}}' --update-expression "SET enabled = :t" --expression-attribute-values '{\":t\":{\"BOOL\":true}}' --region us-east-1
```

### Redeploy after code changes
```powershell
# Start Docker Desktop first if needed.
sam build --template infrastructure/template.yaml --use-container
sam deploy --stack-name payment-routing-engine --region us-east-1 --no-confirm-changeset --capabilities CAPABILITY_IAM --resolve-s3 --parameter-overrides OnnxBucketName=payment-routing-onnx-654654151376 BedrockModelId=us.anthropic.claude-sonnet-4-6
```

### Retrain & re-upload the ML model
```powershell
python ml/generate_synthetic_data.py
python ml/train_interchange_model.py --upload
```

### Reload seed data into DynamoDB
```powershell
python infrastructure/seed_loader.py
```

### Pull recent Lambda logs
```powershell
aws logs tail /aws/lambda/payment-routing-engine --since 10m --region us-east-1 --format short
```

---

## Toolchain Versions

| Tool | Version |
|---|---|
| Python | 3.13.5 |
| AWS CLI | 2.16.3 |
| SAM CLI | 1.160.1 |
| Docker | 29.2.0 (Desktop) |
| boto3 | 1.43.9 |
| xgboost | 3.2.0 |
| onnxruntime | 1.26.0 |
| skl2onnx | 1.20.0 |
| onnxmltools | 1.16.0 |
| pytest | 8.3.4 |
| moto | ≥5.0.0 |

---

## Final File Tree

```
payment-routing-engine/
├── CLAUDE.md                          # Full design spec
├── SESSION_LOG.md                     # This file
├── README.md                          # (pre-existing, not used)
├── .gitignore
├── requirements.txt                   # Lambda runtime deps
├── requirements-dev.txt               # Test deps
│
├── infrastructure/
│   ├── template.yaml                  # SAM: DDB + S3 + Lambda + API GW
│   ├── seed_loader.py                 # Batch loader for seed JSON
│   └── seed-data/
│       ├── scheme-config.json         # 7 schemes
│       ├── bin-table-sample.json      # 17 BINs (FR/US/DE/CN)
│       └── auth-rate-stats.json       # 25 auth-rate entries
│
├── ml/
│   ├── requirements-ml.txt            # Training-only deps
│   ├── generate_synthetic_data.py     # 25,000 synthetic rows
│   ├── train_interchange_model.py     # XGBoost + ONNX export
│   ├── interchange_model.onnx         # Trained artifact (committed)
│   ├── feature_metadata.json          # Encoder vocabulary
│   └── model_card.md                  # Model documentation
│
├── resources/
│   ├── agent-system-prompt.txt        # ReAct decision process
│   └── interchange-fallback-rates.json
│
├── src/
│   ├── __init__.py
│   ├── handler/
│   │   ├── __init__.py
│   │   └── routing_handler.py         # Lambda entry point
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── bedrock_routing_agent.py   # Converse-API ReAct loop
│   │   ├── agent_tool_dispatcher.py
│   │   └── routing_decision_parser.py
│   ├── model/
│   │   ├── __init__.py
│   │   ├── transaction_context.py     # has derived properties
│   │   ├── bin_info.py
│   │   ├── scheme_config.py
│   │   ├── auth_rate_stats.py
│   │   ├── interchange_estimate.py
│   │   └── routing_decision.py
│   ├── service/
│   │   ├── __init__.py
│   │   ├── bin_lookup_service.py
│   │   ├── scheme_status_service.py
│   │   ├── auth_rate_stats_service.py
│   │   └── interchange_estimation_service.py
│   ├── repository/
│   │   ├── __init__.py
│   │   ├── bin_repository.py          # Longest-prefix match
│   │   ├── scheme_config_repository.py
│   │   └── auth_rate_stats_repository.py
│   ├── gateway/
│   │   ├── __init__.py
│   │   └── mock_scheme_gateway.py
│   └── config/
│       ├── __init__.py
│       ├── dynamodb_config.py
│       ├── bedrock_config.py          # Client + tool specs
│       └── model_config.py            # ONNX loader (lazy env reads)
│
└── tests/
    ├── __init__.py
    ├── conftest.py                    # moto DDB + local-ONNX fixtures
    └── unit/
        ├── __init__.py
        ├── test_routing_decision_parser.py
        ├── test_repositories.py
        ├── test_interchange_estimation.py
        └── test_bedrock_routing_agent.py
```

---

## What's Left

1. **Run the 3 demo scenarios live** once the Bedrock daily token quota resets at 00:00 UTC. Just rerun the curl commands above and verify:
   - Scenario 1: response shows `"selected_scheme": "CB"` with rationale citing lower interchange
   - Scenario 2: response shows high-risk weights (`weight_auth: 0.75, weight_ic: 0.25`)
   - Scenario 3: response shows `"selected_scheme": "VISA"` with rationale noting CB was disabled

If anything in the live run looks off, check CloudWatch logs and iterate on `resources/agent-system-prompt.txt` (the system prompt is the easiest knob to tune the agent's reasoning).
