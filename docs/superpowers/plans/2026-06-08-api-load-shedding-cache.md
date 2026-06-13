# API Load Shedding And Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make 2C2G production behavior degrade cleanly under DB pool saturation and reduce database pressure from hot read endpoints.

**Architecture:** Add a global SQLAlchemy pool-timeout exception handler that returns the existing API error envelope with HTTP 503 and `Retry-After`. Add thin response caching at the router boundary for `GET /api/v1/personas` and `GET /api/v1/products`, using the existing fail-open `RedisCache` wrapper and Pydantic JSON-mode dumps.

**Tech Stack:** FastAPI, SQLAlchemy async engine, Pydantic v2, Redis via `app.core.cache.RedisCache`, pytest, ruff.

---

### Task 1: DB Pool Timeout 503

**Files:**
- Modify: `app/core/exceptions.py`
- Modify: `app/main.py`
- Test: `tests/test_exceptions.py`

- [ ] **Step 1: Write failing test**

Add a test that registers the app and raises `sqlalchemy.exc.TimeoutError` from a temporary endpoint, then asserts status 503, code `SERVICE_BUSY`, message `系统繁忙，请稍后再试`, and `Retry-After: 2`.

- [ ] **Step 2: Implement handler**

Add `db_pool_timeout_exception_handler()` in `app/core/exceptions.py` using the existing `_build_error_response()` helper. Register it before the catch-all exception handler in `app/main.py`.

- [ ] **Step 3: Verify**

Run `uv run pytest tests/test_exceptions.py -q` and `uv run ruff check app/core/exceptions.py app/main.py tests/test_exceptions.py`.

### Task 2: Hot List Response Cache

**Files:**
- Modify: `app/routers/persona.py`
- Modify: `app/routers/product.py`
- Test: `tests/test_hot_list_cache.py`

- [ ] **Step 1: Write failing tests**

Add unit tests that patch `RedisCache.get` to return a hit and assert `PersonaService.list_personas` / `ProductService.list_products` are not called. Add miss tests that assert the service is called and `RedisCache.set` stores JSON-mode data.

- [ ] **Step 2: Implement cache helpers**

Use deterministic keys including user id and query parameters:
`user:{id}:category:{category}:page:{page}:page_size:{page_size}:include_critical:{bool}:owner_scope:{scope}:keyword:{keyword}` for personas, and `user:{id}:cursor:{cursor}:limit:{limit}` for products. Validate cached dicts back into `PersonaPageResponse` / `ProductListResponse`.

- [ ] **Step 3: Product write invalidation**

After successful `create_product()` and `reanalyze_product()`, call `RedisCache(prefix="products").delete_pattern(f"user:{current_user.id}:*")`.

- [ ] **Step 4: Verify**

Run `uv run pytest tests/test_hot_list_cache.py -q` and `uv run ruff check app/routers/persona.py app/routers/product.py tests/test_hot_list_cache.py`.

### Task 3: API Rebuild And Load-Test Readiness

**Files:**
- No source changes expected.

- [ ] **Step 1: Run focused test suite**

Run `uv run pytest tests/test_exceptions.py tests/test_hot_list_cache.py tests/test_production_config.py -q`.

- [ ] **Step 2: Run lint**

Run `uv run ruff check app/core/exceptions.py app/main.py app/routers/persona.py app/routers/product.py tests/test_exceptions.py tests/test_hot_list_cache.py`.

- [ ] **Step 3: Rebuild API for pressure test**

Run `docker compose -f docker-compose.yml -f docker-compose.loadtest-2c2g.yml --profile api up -d --build`.

- [ ] **Step 4: Smoke test**

Call `/health/live`, generate/load tokens if needed, then the user can connect Locust or external API pressure tooling to the API endpoint.
