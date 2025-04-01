#!/bin/bash
# Custom buildpack script for Heroku that uses uv instead of pip

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Print uv version
echo "Using uv package manager:"
uv --version

# Install the project with uv
echo "Installing project with uv..."
uv pip install -e "."

# Done
echo "Installation completed with uv" 