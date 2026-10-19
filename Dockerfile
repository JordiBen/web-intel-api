FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-heb \
      tesseract-ocr-ara tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY engines ./engines
# OMP_THREAD_LIMIT=1: Tesseract's OpenMP threads busy-wait and are 2-3x slower on a throttled 0.1-CPU instance
ENV PORT=8000 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
