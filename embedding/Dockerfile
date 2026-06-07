FROM python:3.13-slim

WORKDIR /app

# FastEmbed needs ONNX runtime — pre-install system deps
RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8080

# Model cache directory — mount a PV here to persist model across restarts
ENV FASTEMBED_CACHE_DIR=/app/model_cache

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
