FROM python:3.13-slim

RUN apt-get update && apt-get install -y git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Default: knowledge files are mounted at /data/knowledge
ENV DATA_DIR=/data/knowledge

CMD ["python", "main.py"]
