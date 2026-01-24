# Use a lightweight Python image
FROM python:3.10-slim

# 1. Install system dependencies (FFmpeg is required for yt-dlp to make MP3s)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy requirements and install them
COPY Requirements.txt .
RUN pip install --no-cache-dir -r Requirements.txt

# 4. Copy your Python code into the container
COPY . .

# 5. Tell Docker how to run your app
# Note: Render provides the PORT environment variable automatically
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]