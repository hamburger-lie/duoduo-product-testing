# Production Hardening P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the backend CD build, document production rehearsals and data governance, persist persona-answer AI token/cost usage, and replace the 501 recharge endpoint with a durable provider-neutral recharge skeleton.

**Architecture:** Keep the existing FastAPI layering: routers call services, services own transactions, AI usage stays in `app.ai`, and database changes go through SQLAlchemy models plus Alembic. Object storage, production content moderation, and real WeChat Pay are intentionally out of scope.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, Celery, uv, pytest, ruff, mypy, Docker.

---

## File Structure

- Modify `backend/Dockerfile`: copy `README.md` before `uv sync --frozen --no-dev`.
- Create `backend/docs/PRODUCTION_DRILL.md`: production rehearsal checklist for deploy, migration, rollback, backup restore, worker recovery, and alert checks.
- Create `backend/docs/DATA_GOVERNANCE.md`: data categories, retention, deletion, masking, and internal-access rules.
- Modify `backend/app/core/config.py`: add AI token pricing config and recharge callback secret config.
- Create `backend/app/ai/usage.py`: typed usage/result helpers shared by AI client and adapters.
- Modify `backend/app/ai/client.py`: add `complete_json_with_usage(...)` while preserving existing `complete_json(...)`.
- Modify `backend/app/ai/adapters/structured_generation.py`: return persona-answer usage metadata from the adapter.
- Modify `backend/app/services/evaluation_service.py`: persist sync persona-answer token/cost values.
- Modify `backend/app/tasks/evaluation_tasks.py`: persist Celery persona-answer token/cost values.
- Modify `backend/app/db/models/credit.py`: add `CreditRechargeOrder`.
- Modify `backend/app/db/models/user.py`: add relationship to recharge orders.
- Modify `backend/app/db/models/__init__.py`: export `CreditRechargeOrder`.
- Modify `backend/app/db/repositories/credit.py`: add `CreditRechargeOrderRepository` if existing repo style supports it.
- Modify `backend/app/schemas/credit.py`: add recharge create/callback request and response schemas.
- Modify `backend/app/services/credit_service.py`: add order creation, idempotent client creation, HMAC verification, and exactly-once settlement.
- Modify `backend/app/routers/credit.py`: replace recharge 501 and add signed internal callback endpoint.
- Modify `API_CONTRACT.md`: document the new recharge request/response and callback behavior.
- Modify `backend/README.md`: update the credit status line from recharge 501 to recharge skeleton.
- Create `backend/alembic/versions/20260523_0001_add_credit_recharge_orders.py`: migration for recharge orders.
- Modify tests:
  - `backend/tests/ai/test_client.py`
  - `backend/tests/ai/test_adapters.py`
  - `backend/tests/test_evaluation_tasks.py`
  - `backend/tests/test_credit.py`
  - `backend/tests/test_db_metadata.py`
  - `backend/tests/test_error_codes.py`

## Task 1: Fix Backend CD Docker Build

**Files:**
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Confirm the failing condition**

Run:

```bash
docker build -f backend/Dockerfile backend
```

Expected before the fix: the build may fail during `uv sync --frozen --no-dev` because `pyproject.toml` declares `readme = "README.md"` and that file has not been copied into the image layer.

- [ ] **Step 2: Apply the minimal Dockerfile fix**

Change:

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
```

To:

```dockerfile
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev
```

- [ ] **Step 3: Verify Docker build**

Run:

```bash
docker build -f backend/Dockerfile backend
```

Expected: Docker reaches a successful image build instead of failing on missing `README.md`.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile
git commit -m "fix: include backend readme in docker build"
```

## Task 2: Add Production Drill And Data Governance Docs

**Files:**
- Create: `backend/docs/PRODUCTION_DRILL.md`
- Create: `backend/docs/DATA_GOVERNANCE.md`
- Modify: `backend/README.md`

- [ ] **Step 1: Create production drill document**

Create `backend/docs/PRODUCTION_DRILL.md` with these concrete sections:

```markdown
# Production Drill

## Purpose

Run this rehearsal before opening the mini program to real users.

## Prerequisites

- Production-like host is reachable by SSH.
- HTTPS domain is configured.
- PostgreSQL, Redis, Qdrant, API, Celery worker, and nginx are configured.
- Current release image has passed Backend CI.
- `.env` contains no development secrets.

## Drill 1: Deploy And Health

1. Deploy the current image.
2. Run `GET /health`.
3. Run `GET /api/v1/health/deep` if enabled for internal operators.
4. Confirm API, Redis, PostgreSQL, Qdrant, and worker status are healthy.

## Drill 2: Migration Forward And Back

1. Run `uv run alembic upgrade head`.
2. Run a login smoke test.
3. Run `uv run alembic downgrade -1`.
4. Run `uv run alembic upgrade head`.
5. Confirm no data loss in existing business tables.

## Drill 3: Backup Restore

1. Create a PostgreSQL backup.
2. Restore the backup into a clean database.
3. Run `uv run alembic upgrade head`.
4. Verify user, product, survey, evaluation, answer, report, conversation, credit, and recharge-order tables.

## Drill 4: Worker Failure

1. Start one evaluation task.
2. Stop the Celery worker.
3. Confirm task state becomes observable and no duplicate credit deduction occurs.
4. Restart the worker.
5. Confirm failed or unfinished work is visible for operator action.

## Drill 5: Rollback

1. Record current image tag and database revision.
2. Deploy the previous image tag.
3. Run the compatible downgrade only when the migration says it is safe.
4. Confirm `GET /health` and login still work.

## Drill 6: Alerts

1. Trigger an application error in staging.
2. Confirm logs contain `request_id` and no secrets.
3. Confirm operator notification channel receives the alert.
```

- [ ] **Step 2: Create data governance document**

Create `backend/docs/DATA_GOVERNANCE.md` with these concrete sections:

```markdown
# Data Governance

## Data Categories

- User identity: `openid`, nickname, avatar URL.
- Product data: product name, category, image key or mock URL, AI summary.
- Survey data: generated questions and original answer content.
- AI data: persona answers, report content, chat messages, token usage, cost estimate.
- Credit data: balance, transactions, recharge orders, provider transaction ids.
- Operational data: request id, task id, webhook delivery status, error code.

## Retention

- Soft-deleted business data keeps `deleted_at`.
- Hard deletion is scheduled after the configured retention period.
- Logs must be rotated and must not become the long-term source of user content.

## Deletion Flow

1. Authenticate the user or operator action.
2. Mark product/evaluation/report/conversation records with `deleted_at`.
3. Keep credit ledger rows for reconciliation unless legal deletion is required.
4. Queue physical cleanup for files and generated artifacts after retention expires.

## Logging Boundaries

Never log JWT, WeChat code, Ark API key, object-storage signed URL, raw product images, or full original answer content.

## Internal Access

Only operators with a production need may access user content. Access must be logged with operator identity, request id, purpose, and timestamp.

## Webhook Data

Follow-up webhook payloads may include openid, nickname, product image key, original answers, task id, and token/cost fields. Configure destinations carefully and rotate secrets when staff or vendors change.
```

- [ ] **Step 3: Update README production status**

In `backend/README.md`, update the credit status line that says recharge is `P1 / 501` so it says recharge has a provider-neutral skeleton and real merchant payment is still P1.

- [ ] **Step 4: Verify docs are present**

Run:

```bash
Test-Path backend/docs/PRODUCTION_DRILL.md
Test-Path backend/docs/DATA_GOVERNANCE.md
```

Expected: both commands print `True`.

- [ ] **Step 5: Commit**

```bash
git add backend/docs/PRODUCTION_DRILL.md backend/docs/DATA_GOVERNANCE.md backend/README.md
git commit -m "docs: add production drill and data governance"
```

## Task 3: Add AI Usage Result Plumbing

**Files:**
- Create: `backend/app/ai/usage.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/ai/client.py`
- Test: `backend/tests/ai/test_client.py`

- [ ] **Step 1: Write failing client usage tests**

Add tests that assert:

```python
from decimal import Decimal

from app.ai.client import MockAIClient
from app.ai.usage import AIUsage, estimate_cost_yuan


def test_estimate_cost_yuan_from_configured_prices() -> None:
    usage = AIUsage(input_tokens=1000, output_tokens=500)

    result = estimate_cost_yuan(
        usage,
        input_price_per_1k=Decimal("0.0020"),
        output_price_per_1k=Decimal("0.0060"),
    )

    assert result == Decimal("0.0050")


async def test_mock_client_complete_json_with_usage_returns_zero_usage() -> None:
    client = MockAIClient()

    result = await client.complete_json_with_usage(system="sys", user="hello", endpoint_id="ep-json")

    assert result.content
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
    assert result.usage.cost_yuan == Decimal("0.0000")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd backend
uv run pytest tests/ai/test_client.py -q
```

Expected: imports or method lookups fail because `app.ai.usage` and `complete_json_with_usage` do not exist yet.

- [ ] **Step 3: Implement usage helpers**

Create `backend/app/ai/usage.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class AIUsage:
    """Token usage and estimated model cost for one AI call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_yuan: Decimal = Decimal("0.0000")

    @property
    def total_tokens(self) -> int:
        """Return total token count."""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class AITextResult:
    """Text response plus usage metadata."""

    content: str
    usage: AIUsage


def estimate_cost_yuan(
    usage: AIUsage,
    *,
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
) -> Decimal:
    """Estimate yuan cost from per-1K input and output token prices."""

    raw = (
        Decimal(usage.input_tokens) / Decimal(1000) * input_price_per_1k
        + Decimal(usage.output_tokens) / Decimal(1000) * output_price_per_1k
    )
    return raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
```

- [ ] **Step 4: Add pricing config**

In `backend/app/core/config.py`, add decimal settings:

```python
from decimal import Decimal

ai_input_price_yuan_per_1k: Decimal = Field(default=Decimal("0.0000"), alias="AI_INPUT_PRICE_YUAN_PER_1K")
ai_output_price_yuan_per_1k: Decimal = Field(default=Decimal("0.0000"), alias="AI_OUTPUT_PRICE_YUAN_PER_1K")
recharge_callback_secret: str = Field(default="", alias="RECHARGE_CALLBACK_SECRET")
```

- [ ] **Step 5: Add `complete_json_with_usage` while preserving old API**

In `backend/app/ai/client.py`:

1. Add `complete_json_with_usage(...) -> AITextResult` to the client protocol/base interface.
2. Make `complete_json(...)` call `complete_json_with_usage(...)` and return `.content` where practical.
3. Make `MockAIClient.complete_json_with_usage(...)` return `AITextResult(content=existing_json, usage=AIUsage())`.
4. In the Ark client, collect streamed usage and return `AITextResult(content=collected_text, usage=AIUsage(input_tokens=..., output_tokens=..., cost_yuan=estimate_cost_yuan(...)))`.
5. If a provider response has no usage chunk, return zero usage instead of failing.

- [ ] **Step 6: Run client tests**

Run:

```bash
cd backend
uv run pytest tests/ai/test_client.py -q
```

Expected: tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/ai/usage.py backend/app/core/config.py backend/app/ai/client.py backend/tests/ai/test_client.py
git commit -m "feat: expose ai json usage metadata"
```

## Task 4: Persist Persona Answer Token And Cost Usage

**Files:**
- Modify: `backend/app/ai/adapters/structured_generation.py`
- Modify: `backend/app/services/evaluation_service.py`
- Modify: `backend/app/tasks/evaluation_tasks.py`
- Test: `backend/tests/ai/test_adapters.py`
- Test: `backend/tests/test_evaluation_tasks.py`

- [ ] **Step 1: Write adapter usage test**

In `backend/tests/ai/test_adapters.py`, add a fake client with `complete_json_with_usage(...)` returning non-zero usage, then assert persona answer generation exposes that usage:

```python
from decimal import Decimal

from app.ai.usage import AITextResult, AIUsage


class _PersonaClientWithUsage:
    async def complete_json_with_usage(self, *, system: str, user: str, endpoint_id: str) -> AITextResult:
        return AITextResult(
            content='{"answers":[{"question_id":"q1","answer_text":"yes","score":4}],"overall_intent":"buy","sentiment":"positive","summary_comment":"ok","thinking_process":"clear"}',
            usage=AIUsage(input_tokens=123, output_tokens=45, cost_yuan=Decimal("0.0088")),
        )


async def test_persona_answer_adapter_returns_usage() -> None:
    from app.ai.adapters.structured_generation import PersonaAnswerGenerationAdapter

    adapter = PersonaAnswerGenerationAdapter(ai_client=_PersonaClientWithUsage())

    result = await adapter.generate_answer_with_usage(
        product={"name": "p"},
        questions=[{"id": "q1", "content": "will buy?"}],
        persona={"name": "buyer"},
        endpoint_id="ep",
    )

    assert result.usage.input_tokens == 123
    assert result.usage.output_tokens == 45
    assert result.usage.cost_yuan == Decimal("0.0088")
```

- [ ] **Step 2: Run the failing adapter test**

Run:

```bash
cd backend
uv run pytest tests/ai/test_adapters.py::test_persona_answer_adapter_returns_usage -q
```

Expected: fails because `generate_answer_with_usage` does not exist.

- [ ] **Step 3: Implement adapter result**

In `backend/app/ai/adapters/structured_generation.py`, add:

```python
from dataclasses import dataclass
from decimal import Decimal
from app.ai.usage import AIUsage


@dataclass(frozen=True)
class PersonaAnswerGenerationResult:
    """Validated persona answers plus model usage."""

    answers: list[dict[str, object]]
    overall_intent: str
    sentiment: str
    summary_comment: str
    thinking_process: str
    usage: AIUsage
```

Add `generate_answer_with_usage(...) -> PersonaAnswerGenerationResult`. Keep the existing `generate_answer(...)` method as a compatibility wrapper returning the existing 5-tuple, so older tests and call sites do not break immediately.

- [ ] **Step 4: Update evaluation service persistence**

In `backend/app/services/evaluation_service.py`, update the AI path so new `Answer(...)` rows use:

```python
token_input=result.usage.input_tokens
token_output=result.usage.output_tokens
cost_yuan=result.usage.cost_yuan
```

Keep mock/non-AI fallback values as:

```python
token_input=0
token_output=0
cost_yuan=Decimal("0.0000")
```

- [ ] **Step 5: Update Celery task persistence**

In `backend/app/tasks/evaluation_tasks.py`, add usage fields to the persona outcome dataclass and set saved answer rows from those fields. For success outcomes:

```python
token_input=outcome.token_input
token_output=outcome.token_output
cost_yuan=outcome.cost_yuan
```

For mock/fallback/error rows keep zeros.

- [ ] **Step 6: Write persistence test**

In `backend/tests/test_evaluation_tasks.py`, add or update a focused test that builds a successful persona outcome with non-zero usage and asserts the saved `Answer` row has:

```python
assert answer.token_input == 123
assert answer.token_output == 45
assert answer.cost_yuan == Decimal("0.0088")
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd backend
uv run pytest tests/ai/test_adapters.py tests/test_evaluation_tasks.py -q
```

Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/ai/adapters/structured_generation.py backend/app/services/evaluation_service.py backend/app/tasks/evaluation_tasks.py backend/tests/ai/test_adapters.py backend/tests/test_evaluation_tasks.py
git commit -m "feat: persist persona answer ai usage"
```

## Task 5: Add Recharge Order Model And Migration

**Files:**
- Modify: `backend/app/db/models/credit.py`
- Modify: `backend/app/db/models/user.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/db/repositories/credit.py`
- Create: `backend/alembic/versions/20260523_0001_add_credit_recharge_orders.py`
- Test: `backend/tests/test_db_metadata.py`

- [ ] **Step 1: Write metadata test**

In `backend/tests/test_db_metadata.py`, add `credit_recharge_orders` to the expected table set.

- [ ] **Step 2: Run failing metadata test**

Run:

```bash
cd backend
uv run pytest tests/test_db_metadata.py -q
```

Expected: fails because the table is not in metadata.

- [ ] **Step 3: Add SQLAlchemy model**

In `backend/app/db/models/credit.py`, add `CreditRechargeOrder` with:

```python
__tablename__ = "credit_recharge_orders"

user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
provider: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
provider_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
amount_yuan: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
credits: Mapped[int] = mapped_column(Integer, nullable=False)
status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
raw_callback: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
user: Mapped["User"] = relationship(back_populates="credit_recharge_orders")
```

Add indexes:

```python
Index("ix_credit_recharge_orders_user_created_at_desc", "user_id", desc("created_at"))
Index("uq_credit_recharge_orders_user_idempotency_key", "user_id", "idempotency_key", unique=True)
```

- [ ] **Step 4: Wire model exports**

In `backend/app/db/models/user.py`, add:

```python
credit_recharge_orders: Mapped[list["CreditRechargeOrder"]] = relationship(back_populates="user")
```

In `backend/app/db/models/__init__.py`, import/export `CreditRechargeOrder`.

In `backend/app/db/repositories/credit.py`, add `CreditRechargeOrderRepository` following the existing repository pattern.

- [ ] **Step 5: Add migration**

Create `backend/alembic/versions/20260523_0001_add_credit_recharge_orders.py` that creates the table with columns and indexes matching the model. `downgrade()` must drop indexes and table only for `credit_recharge_orders`.

- [ ] **Step 6: Run metadata and migration checks**

Run:

```bash
cd backend
uv run pytest tests/test_db_metadata.py -q
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: metadata test passes and Alembic can move forward/back/forward.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/models/credit.py backend/app/db/models/user.py backend/app/db/models/__init__.py backend/app/db/repositories/credit.py backend/alembic/versions/20260523_0001_add_credit_recharge_orders.py backend/tests/test_db_metadata.py
git commit -m "feat: add credit recharge orders table"
```

## Task 6: Implement Recharge API Skeleton

**Files:**
- Modify: `backend/app/schemas/credit.py`
- Modify: `backend/app/services/credit_service.py`
- Modify: `backend/app/routers/credit.py`
- Modify: `API_CONTRACT.md`
- Modify: `backend/tests/test_credit.py`
- Modify: `backend/tests/test_error_codes.py`

- [ ] **Step 1: Replace 501 test with recharge order tests**

In `backend/tests/test_credit.py`, replace `test_recharge_returns_501` with tests for:

```python
async def test_recharge_creates_pending_order(ctx: CreditContext) -> None:
    token = await _login(ctx, "credit_recharge_create")
    r = await ctx.client.post(
        "/api/v1/credits/recharge",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-1"},
        json={"amount_yuan": "9.90", "credits": 990, "provider": "manual"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["credits"] == 990
    assert body["amount_yuan"] == "9.90"


async def test_recharge_idempotency_key_returns_same_order(ctx: CreditContext) -> None:
    token = await _login(ctx, "credit_recharge_idem")
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-same"}
    payload = {"amount_yuan": "19.90", "credits": 1990, "provider": "manual"}
    first = await ctx.client.post("/api/v1/credits/recharge", headers=headers, json=payload)
    second = await ctx.client.post("/api/v1/credits/recharge", headers=headers, json=payload)
    assert second.status_code == 200
    assert second.json()["order_no"] == first.json()["order_no"]
```

Add callback tests:

```python
async def test_recharge_callback_settles_once(ctx: CreditContext) -> None:
    # create order, sign callback body with RECHARGE_CALLBACK_SECRET, call callback twice,
    # assert balance increases once and exactly one recharge transaction exists.
```

Add bad signature test:

```python
async def test_recharge_callback_rejects_bad_signature(ctx: CreditContext) -> None:
    # create order and call callback with X-Recharge-Signature: bad
    # assert 401/403 app error and balance unchanged.
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd backend
uv run pytest tests/test_credit.py tests/test_error_codes.py -q
```

Expected: recharge tests fail because route still returns 501 and schemas do not exist.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas/credit.py`, add:

```python
class CreditRechargeRequest(BaseModel):
    """Create a pending recharge order."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount_yuan: Decimal = Field(gt=Decimal("0.00"), max_digits=10, decimal_places=2)
    credits: int = Field(gt=0, le=1_000_000)
    provider: Literal["manual"] = "manual"


class CreditRechargeResponse(BaseModel):
    """Recharge order response."""

    id: str
    order_no: str
    provider: str
    amount_yuan: Decimal
    credits: int
    status: str
    created_at: datetime
    paid_at: datetime | None = None


class CreditRechargeCallbackRequest(BaseModel):
    """Signed internal recharge settlement callback."""

    order_no: str
    provider_transaction_id: str
    paid_at: datetime | None = None
```

- [ ] **Step 4: Implement service methods**

In `backend/app/services/credit_service.py`, add:

```python
async def create_recharge_order(
    self,
    user: User,
    request: CreditRechargeRequest,
    *,
    idempotency_key: str | None,
) -> CreditRechargeResponse:
    """Create or return a pending recharge order for this user."""
```

Behavior:

- If `idempotency_key` exists and an order for `(user_id, idempotency_key)` exists, return that order.
- Generate `order_no` with a stable prefix such as `rch_` plus random URL-safe bytes.
- Create order with `status="pending"`.
- Do not change `user.credit_balance` at creation time.

Add:

```python
async def settle_recharge_order(
    self,
    request: CreditRechargeCallbackRequest,
    *,
    raw_callback: dict[str, object],
) -> CreditRechargeResponse:
    """Mark a pending recharge order paid and credit the user exactly once."""
```

Behavior:

- Find order by `order_no`.
- If missing, raise existing `AppError` with `NOT_FOUND`.
- If already `paid`, return current order without adding credits.
- If another order already has the same `provider_transaction_id`, return that paid order without adding credits again.
- Set `status="paid"`, `provider_transaction_id`, `paid_at`, `raw_callback`.
- Increase `user.credit_balance` by `order.credits`.
- Write `CreditTransaction(amount=order.credits, reason="recharge", ref_type="credit_recharge_order", ref_id=order.id, balance_after=user.credit_balance)`.

Add:

```python
def verify_recharge_callback_signature(body: bytes, signature: str, secret: str) -> None:
    """Verify HMAC-SHA256 callback signature."""
```

Behavior:

- If `secret` is empty, reject with an app error instead of accepting unsigned production callbacks.
- Signature format is lowercase hex HMAC-SHA256 of the raw request body.
- Use `hmac.compare_digest`.

- [ ] **Step 5: Implement router endpoints**

In `backend/app/routers/credit.py`, replace 501 route:

```python
@router.post("/recharge", response_model=CreditRechargeResponse)
async def recharge(
    request: CreditRechargeRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CreditRechargeResponse:
    return await CreditService(session).create_recharge_order(
        current_user,
        request,
        idempotency_key=idempotency_key,
    )
```

Add signed callback:

```python
@router.post("/recharge/callback", response_model=CreditRechargeResponse)
async def recharge_callback(
    raw_request: Request,
    signature: str = Header(alias="X-Recharge-Signature"),
    session: AsyncSession = Depends(get_session),
) -> CreditRechargeResponse:
    body = await raw_request.body()
    CreditService.verify_recharge_callback_signature(body, signature, settings.recharge_callback_secret)
    payload = CreditRechargeCallbackRequest.model_validate_json(body)
    return await CreditService(session).settle_recharge_order(payload, raw_callback=payload.model_dump(mode="json"))
```

- [ ] **Step 6: Update API contract**

In `API_CONTRACT.md`, replace the recharge section that says `POST /credits/recharge — 返回 501 NOT_IMPLEMENTED` with the request/response body for the new pending order and the signed internal callback. Explicitly state real WeChat Pay is not implemented.

- [ ] **Step 7: Run focused recharge tests**

Run:

```bash
cd backend
uv run pytest tests/test_credit.py tests/test_error_codes.py -q
```

Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/credit.py backend/app/services/credit_service.py backend/app/routers/credit.py API_CONTRACT.md backend/tests/test_credit.py backend/tests/test_error_codes.py
git commit -m "feat: add recharge order skeleton"
```

## Task 7: Full Verification And Branch Readiness

**Files:**
- No new code unless verification exposes a defect.

- [ ] **Step 1: Run formatting/lint/type/test checks**

Run:

```bash
cd backend
uv run ruff check .
uv run mypy app
uv run pytest
```

Expected: all pass.

- [ ] **Step 2: Run migration round trip**

Run:

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all pass.

- [ ] **Step 3: Run Docker build**

Run:

```bash
docker build -f backend/Dockerfile backend
```

Expected: build succeeds.

- [ ] **Step 4: Inspect working tree**

Run:

```bash
git status --short
```

Expected: only pre-existing user changes remain unstaged if they are unrelated:

```text
 M backend/app/ai/prompts/persona_answer.j2
 M backend/scripts/persona_full_survey_test.py
```

- [ ] **Step 5: Commit any verification fixes**

If verification required fixes, commit them with:

```bash
git add <changed files>
git commit -m "fix: address prod hardening verification"
```

## Self-Review

- Spec coverage: CD fix, production drill docs, data governance docs, AI persona-answer token/cost persistence, and recharge skeleton are all covered.
- Explicit exclusions: real object storage, production content moderation, and real WeChat Pay merchant integration remain out of scope.
- API discipline: the only contract change is replacing the documented 501 recharge placeholder with a documented skeleton endpoint.
- Migration discipline: recharge order table is introduced through Alembic and verified with upgrade/downgrade/upgrade.
- Risk note: local Docker and migration checks may require Docker/PostgreSQL services to be available on the machine.
