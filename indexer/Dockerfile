FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Default: knowledge files are mounted at /data/knowledge
ENV DATA_DIR=/data/knowledge

CMD ["python", "main.py"]
