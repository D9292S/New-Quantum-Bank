#####################
# BUILDER STAGE
#####################
FROM python:3.12-slim as builder

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY pyproject.toml .
COPY .uv.toml .
COPY LICENSE .
COPY README.md .

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Install dependencies using uv
RUN pip install uv && \
    uv pip install ".[high-performance]" --system

#####################
# FINAL STAGE
#####################
FROM python:3.12-slim

LABEL maintainer="Quantum Bank Team" \
      description="A Discord economy bot with advanced banking features"

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create logs directory with appropriate permissions
RUN mkdir -p /app/logs && \
    chmod -R 755 /app/logs

# Create a non-root user to run the bot
RUN adduser --disabled-password --gecos "" quantum && \
    chown -R quantum:quantum /app

# Switch to non-root user
USER quantum

# Set Python to run in unbuffered mode
ENV PYTHONUNBUFFERED=1

# Set up healthcheck
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests, os; requests.get('http://localhost:' + os.environ.get('PORT', '8080') + '/health') if 'PORT' in os.environ else exit(0)" || exit 1

# Use an entrypoint script for more flexibility
ENTRYPOINT ["python", "launcher.py"]

# Default command line arguments
CMD []
