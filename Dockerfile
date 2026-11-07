FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --no-dev --no-editable

USER 65532:65532
EXPOSE 8000
CMD [".venv/bin/uvicorn", "proof.main:app", "--host", "0.0.0.0", "--port", "8000"]
