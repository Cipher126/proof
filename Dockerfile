FROM node:24-alpine AS dashboard-build
WORKDIR /ui
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
COPY --from=dashboard-build /ui/dist ./dashboard/dist
COPY alembic.ini ./
COPY migrations ./migrations
ENV PROOF_DASHBOARD_DIR=/app/dashboard/dist
ENV PROOF_ENVIRONMENT=sandbox

USER 65532:65532
EXPOSE 8000
CMD [".venv/bin/uvicorn", "proof.main:app", "--host", "0.0.0.0", "--port", "8000"]
