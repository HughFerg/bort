# YOLOv8 Training Environment for Simpsons Character Detection
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    ultralytics \
    opencv-python-headless \
    kaggle \
    pillow \
    tqdm

# Copy training scripts
COPY prepare_dataset.py .
COPY train.py .
COPY simpsons.yaml .

# Create directories
RUN mkdir -p /app/data /app/runs

# Default command
CMD ["python", "train.py"]
