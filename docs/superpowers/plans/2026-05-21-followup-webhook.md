# Follow-Up Webhook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend-only MVP webhook that sends a signed, minimal follow-up payload when an evaluation reaches a terminal state.

**Architecture:** Evaluation completion writes a durable `webhook_events` row inside the backend database, then Celery delivers that event asynchronously. Delivery failure must not change the evaluation result; retries and status are tracked on the webhook event.

**Tech Stack:** FastAPI service layer, SQLAlchemy 2.0 async, Alembic, Celery, httpx, pytest.

---

### Task 1: Payload And Signature Helpers

**Files:**
- Create: `backend/app/services/followup_webhook_service.py`
- Test: `backend/tests/test_followup_webhook.py`

- [ ] Write failing tests for payload shape and HMAC signature.
- [ ] Implement a minimal `FollowupWebhookService` that builds `evaluation.done` / `evaluation.failed` payloads with string IDs and no raw private data.
- [ ] Verify `uv run pytest tests/test_followup_webhook.py -q` passes.

### Task 2: Durable Webhook Event Storage

**Files:**
- Create: `backend/app/db/models/webhook_event.py`
- Create: `backend/app/db/repositories/webhook_event.py`
- Modify: `backend/app/db/models/__init__.py`
- Create: `backend/alembic/versions/20260521_0001_add_webhook_events.py`
- Test: `backend/tests/test_followup_webhook.py`

- [ ] Write failing tests that an event can be created once per `event_id` and listed for delivery.
- [ ] Add `webhook_events` with base fields, `event_id`, `event_type`, `target_url`, `payload`, `status`, `attempt_count`, `last_error`, `next_attempt_at`, and `delivered_at`.
- [ ] Verify the model works in SQLite tests and PostgreSQL migration defines JSONB payload.

### Task 3: Delivery Task

**Files:**
- Create: `backend/app/tasks/followup_webhook_tasks.py`
- Modify: `backend/app/tasks/celery_app.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_followup_webhook.py`

- [ ] Write failing tests for disabled webhook, successful 2xx delivery, failed non-2xx delivery, and signature headers.
- [ ] Add `FOLLOWUP_WEBHOOK_URL`, `FOLLOWUP_WEBHOOK_SECRET`, and timeout settings.
- [ ] Implement async httpx delivery with timeout, HMAC header, idempotency event id header, status updates, and no secret logging.

### Task 4: Evaluation Completion Integration

**Files:**
- Modify: `backend/app/tasks/evaluation_tasks.py`
- Test: `backend/tests/test_evaluation_tasks.py`

- [ ] Write a failing test that a completed Celery evaluation enqueues one webhook event.
- [ ] Trigger event creation only after terminal `done` or `failed` status is persisted.
- [ ] Keep canceled evaluations silent for MVP.
- [ ] Verify existing evaluation task tests still pass.

### Task 5: Contract And Verification

**Files:**
- Modify: `API_CONTRACT.md`
- Modify: `docs/API_STATUS.md`

- [ ] Document the server-to-server webhook payload, headers, retry behavior, and privacy limits.
- [ ] Run `uv run ruff check .`, `uv run mypy app`, and focused pytest.
- [ ] Report any full-suite or migration verification that could not be run locally.
