# Production Hardening P0 Design

## Goal

Bring the backend closer to production readiness without changing the current product API shape, and without implementing object storage or production-grade content moderation in this round.

## Scope

This round includes four independent workstreams:

1. Fix Backend CD Docker image build.
2. Add production drill and data governance documentation.
3. Improve AI token and cost accounting.
4. Add a recharge/payment-flow skeleton with durable orders and idempotent settlement.

This round explicitly excludes:

- Real object storage integration, because the storage service has not been purchased.
- Production content moderation integration, per user request.
- Real WeChat Pay merchant integration, because merchant credentials, certificates, APIv3 key, and operational policy are not available yet.

## Architecture

### 1. Backend CD Fix

The current CD workflow builds Docker with `backend/` as the context. `backend/pyproject.toml` declares `readme = "README.md"`, but the Dockerfile copies only `pyproject.toml` and `uv.lock` before running `uv sync`. Hatchling validates metadata during package build and fails because `README.md` is missing at that layer.

Fix by copying `README.md` before `uv sync`. This is a minimal Dockerfile-only change and should be verified with a local `docker build`.

### 2. Production Drill And Data Governance Docs

Add operational documentation under `backend/docs/`:

- `PRODUCTION_DRILL.md`: step-by-step rehearsal for HTTPS/domain readiness, migrations, seed import, backup restore, worker failure recovery, rollback, and alert checks.
- `DATA_GOVERNANCE.md`: data categories, retention expectations, deletion approach, logging boundaries, internal access rules, and webhook data handling.

These docs do not change runtime behavior, but they make production acceptance testable.

### 3. AI Cost Accounting

The AI client already extracts usage from streamed chunks and logs it. The gap is that persona answer task persistence still writes `token_input=0`, `token_output=0`, and `cost_yuan=0`.

Introduce a small structured usage container in the AI adapter layer:

- Keep existing public API responses unchanged.
- Let `PersonaAnswerGenerationAdapter.generate_answer` return usage metadata alongside answers.
- Keep mock paths at zero usage.
- Use configurable per-1K-token prices to estimate cost in yuan.
- Persist usage to `answers.token_input`, `answers.token_output`, and `answers.cost_yuan`.

Product and survey generation cost is out of scope for this round because the existing persistence model does not expose matching cost columns. This round only persists persona answer usage because `answers` already has `token_input`, `token_output`, and `cost_yuan`, and evaluation runs can fan out across many personas.

### 4. Recharge/Payment Skeleton

Replace `POST /api/v1/credits/recharge` returning 501 with a production-shaped but provider-neutral internal skeleton:

- Create `credit_recharge_orders` table.
- Add request/response schemas for creating recharge orders.
- `POST /api/v1/credits/recharge` creates a pending order with amount, credits, provider, and order number.
- Add a callback/settlement service method that marks an order paid and credits the user exactly once.
- Expose a testable internal callback endpoint with HMAC signature for now, not a real WeChat Pay endpoint.
- Preserve ledger behavior by writing a `CreditTransaction` with reason `recharge`.

Idempotency is required:

- Repeating settlement for the same provider transaction must not add credits twice.
- Repeating client order creation with the same `Idempotency-Key` must return the first created order for that key and user.

## Error Handling

- CD fix has no runtime errors.
- AI usage extraction must fail soft: if usage is absent, keep zero values rather than failing the evaluation.
- Recharge order creation must reject invalid amount/credits with existing validation and error envelope conventions.
- Settlement must reject bad signatures and unknown orders.
- Settlement must return the existing order state when the order is already paid.

## Testing

Required verification:

- `uv run ruff check .`
- `uv run mypy app`
- `uv run pytest`
- `uv run alembic upgrade head`
- `uv run alembic downgrade -1`
- `uv run alembic upgrade head`
- `docker build -f backend/Dockerfile backend`

Focused tests:

- Dockerfile change can be checked by local build.
- AI usage tests should verify token/cost values are persisted for persona answers.
- Recharge tests should cover order creation, invalid payloads, successful settlement, duplicate settlement, bad signature, and permission boundaries for listing/querying orders if added.

## Rollout

1. Merge CD fix and docs first if needed.
2. Deploy code with recharge order endpoints disabled from UI until product confirms pricing.
3. Configure AI token prices conservatively.
4. Monitor AI cost fields after a mock/deepseek evaluation run.
5. Keep real WeChat Pay and object storage outside this PR.
