FROM node:24-bookworm-slim@sha256:dc26ae92c9fb15cf6b1d63e20f0944b2efe0f115b20e00be48fb23fceb061c54 AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv
FROM python:3.13.16-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641 AS runtime
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1=12.2.0-14+deb12u1 && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 1000 appuser
WORKDIR /opt/babar
COPY babar-source/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY backend/ ./backend/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY --from=frontend /build/dist ./frontend/dist
ENV PATH="/app/.venv/bin:$PATH" MEMORA_PYTHON=/opt/babar/.venv/bin/python MEMORA_CONFIG=/run/abacus/memory.json HF_HOME=/models HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "abacus.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
