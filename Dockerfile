FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package installation
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy requirements first for better caching
COPY requirements.txt pyproject.toml ./
COPY .env.example ./.env

# Install dependencies
RUN . ~/.cargo/env && uv pip install -r requirements.txt

# Copy the rest of the code
COPY . .

# Create volume for logs
VOLUME /app/logs

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PERFORMANCE_MODE=medium

# Set the entrypoint
ENTRYPOINT ["python", "launcher.py"]

# Default command
CMD ["--log-level", "normal"] 