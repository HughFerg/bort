FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements-prod.txt .

# Install Python dependencies (ONNX Runtime for inference, no PyTorch)
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/stats')" || exit 1

# Run the application
CMD ["uvicorn", "search:app", "--host", "0.0.0.0", "--port", "8000"]
