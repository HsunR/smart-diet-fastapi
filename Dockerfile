FROM python:3.12-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TIMEOUT=60
ARG PIP_RETRIES=5

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --require-hashes \
    --index-url "$PIP_INDEX_URL" --timeout "$PIP_TIMEOUT" --retries "$PIP_RETRIES" \
    -r requirements.txt

COPY . .

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
