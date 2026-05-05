FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    libpq-dev gcc g++ libglib2.0-0 libsm6 libxext6 libxrender-dev \
    libgl1-mesa-glx libgomp1 tesseract-ocr tesseract-ocr-hin tesseract-ocr-guj \
    tesseract-ocr-tam tesseract-ocr-tel tesseract-ocr-ben tesseract-ocr-mar \
    curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
