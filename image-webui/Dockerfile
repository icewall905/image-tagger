FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including exiftool
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libheif-dev \
    libimage-exiftool-perl \
    gcc \
    libc6-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /tmp/thumbnails

# Expose the port
EXPOSE 8491

# Start the application
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8491"]
