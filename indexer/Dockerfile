FROM python:3.14-slim

RUN apt-get update && apt-get install -y git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --no-interaction

COPY main.py .

# Default: knowledge files cloned into /tmp/data by the K8s Job command
ENV DATA_DIR=/data/knowledge

CMD ["poetry", "run", "python", "main.py"]
