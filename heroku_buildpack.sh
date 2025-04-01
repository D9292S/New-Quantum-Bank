#!/bin/bash
# Custom buildpack script for Heroku that uses uv instead of pip

# Exit on error
set -e

# Install system dependencies
apt-get update
apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3-pip

# Clean up apt cache
rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
python3.12 -m venv /app/.venv
source /app/.venv/bin/activate

# Install UV using pip (more reliable than curl install)
pip install uv

# Install project dependencies using UV
cd /app
uv pip install ".[high-performance]" --system

# Clean up
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Print versions for debugging
echo "Python version:"
python --version
echo "UV version:"
uv --version

# Done
echo "Installation completed with uv" 