# syntax=docker/dockerfile:1.7
FROM python:3.14.7-slim-bookworm@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52 AS build
ARG UV_VERSION=0.11.33
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src
RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"
COPY pyproject.toml uv.lock README.md LICENSE.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14.7-slim-bookworm@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 65532 amra
WORKDIR /app
COPY --from=build --chown=amra:amra /src/.venv ./.venv
COPY --from=build --chown=amra:amra /src/src ./src
USER 65532:65532
CMD ["uvicorn", "amra.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
