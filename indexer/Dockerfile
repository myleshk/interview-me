FROM python:3.13-slim

RUN apt-get update && apt-get install -y git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main --no-interaction

COPY main.py .

# Default: knowledge files are mounted at /data/knowledge
ENV DATA_DIR=/data/knowledge

CMD ["poetry", "run", "python", "main.py"]
