FROM python:3.11-slim

# System deps for OpenCV + PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY backend/ /app/backend/
COPY ml/      /app/ml/
COPY scripts/ /app/scripts/

# Create necessary dirs
RUN mkdir -p /app/logs /app/data /app/models /app/reports

ENV PYTHONPATH=/app
ENV MOCK_MODE=true
ENV DATABASE_URL=sqlite+aiosqlite:///./nepal_traffic.db
ENV LOG_LEVEL=INFO

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
