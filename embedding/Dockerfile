FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main --no-interaction

COPY main.py .

EXPOSE 8080

# Model cache directory — mount a PV here to persist model across restarts
ENV FASTEMBED_CACHE_DIR=/app/model_cache

CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
