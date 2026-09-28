# SAT-SA Lens backend - offline by construction.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # The ML stack must never reach the network at runtime.
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    SATSA_DATA_DIR=/data \
    SATSA_DB_PATH=/data/satsa.duckdb \
    SATSA_MODEL_DIR=/app/models/all-MiniLM-L6-v2

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Optional heavy ML extras. Build with --build-arg WITH_ML=1 on a networked
# machine if you want the transformer model instead of the lexical fallback.
ARG WITH_ML=0
COPY backend/requirements-ml.txt /app/backend/requirements-ml.txt
RUN if [ "$WITH_ML" = "1" ]; then pip install --no-cache-dir -r /app/backend/requirements-ml.txt; fi

COPY backend/app /app/backend/app
COPY backend/pytest.ini /app/backend/pytest.ini
COPY backend/tests /app/backend/tests
COPY generator /app/generator
COPY models /app/models
COPY CLAUDE.md /app/CLAUDE.md

ENV PYTHONPATH=/app/backend:/app
WORKDIR /app/backend

RUN mkdir -p /data && useradd -m -u 10001 satsa && chown -R satsa /data /app
USER satsa

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=10 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
