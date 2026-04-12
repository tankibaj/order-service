# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder
WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
RUN uv lock && uv sync --frozen --no-dev --no-editable

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime
WORKDIR /app

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
