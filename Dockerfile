# Python 3.10 base image
FROM python:3.10-slim

# Install ffmpeg (for yt-dlp to handle media)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy all source code, including static and downloads folders
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose FastAPI port
EXPOSE 8000

# Start the app with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
