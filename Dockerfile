# ======================================================================
# Stage 1: Build & Python Dependencies
# ======================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /install

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ======================================================================
# Stage 2: Final Production Runtime Image
# ======================================================================
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PAPERPLANE_ENV=production \
    PAPERPLANE_DATA_DIR=/data \
    PAPERPLANE_REQUIRE_AUTH=false \
    PAPERPLANE_WORKERS=4 \
    PAPERPLANE_HOST=0.0.0.0 \
    PAPERPLANE_PORT=8501

WORKDIR /app

# Install system utilities for LibreOffice, OCR, repair, and headless conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    tesseract-ocr \
    tesseract-ocr-eng \
    qpdf \
    ghostscript \
    chromium \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Create non-root user and prepare data directory
RUN useradd -m -u 1001 -s /bin/bash paperplane && \
    mkdir -p /data && \
    chown -R paperplane:paperplane /app /data

USER paperplane
VOLUME ["/data"]
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/api/health')" || exit 1

CMD ["python", "app.py"]
