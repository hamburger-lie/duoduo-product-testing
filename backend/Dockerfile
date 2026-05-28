# ── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/0.7.8/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

# Install dependencies first (layer-cached unless lock file changes)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY . .

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy built app and venv from builder
COPY --from=builder --chown=appuser:appuser /app /app
# Copy uv binary so CMD can use `uv run`
COPY --from=builder --chown=appuser:appuser /root/.local/bin/uv /usr/local/bin/uv

USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
