#!/usr/bin/env bash
# Quantum Superbot Setup Script
# This script helps new users set up the development environment using the uv package manager

set -euo pipefail

# Print with colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Quantum Superbot Setup Script${NC}"
echo -e "${BLUE}=======================================${NC}"

# Check if Python 3.12+ is installed
PYTHON_VERSION=$(python3 --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+' || echo "0.0")
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 12 ]]; then
    echo -e "${RED}Error: Python 3.12 or higher is required!${NC}"
    echo -e "${YELLOW}Please install Python 3.12+ and try again.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found Python $PYTHON_VERSION${NC}"

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Installing uv package manager...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add uv to PATH for the current session
    if [[ -d "$HOME/.cargo/bin" ]]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
else
    echo -e "${GREEN}✓ uv package manager is already installed${NC}"
fi

# Create virtual environment if it doesn't exist
if [[ ! -d ".venv" ]]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    uv venv
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment
if [[ "$OSTYPE" == "win32" || "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    echo -e "${YELLOW}Activating virtual environment (Windows)...${NC}"
    source .venv/Scripts/activate
else
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

# Install dependencies using uv
echo -e "${YELLOW}Installing dependencies...${NC}"
uv pip sync pyproject.toml
echo -e "${GREEN}✓ Successfully installed dependencies${NC}"

# Ask if development dependencies should be installed
echo ""
echo -e "${BLUE}Would you like to install development dependencies? (y/n)${NC}"
read -r install_dev

if [[ $install_dev =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Installing development dependencies...${NC}"
    uv pip install -e ".[development]"
    echo -e "${GREEN}✓ Successfully installed development dependencies${NC}"
fi

echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}  Setup completed successfully!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "${YELLOW}To activate the virtual environment, run:${NC}"
if [[ "$OSTYPE" == "win32" || "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    echo -e "${BLUE}    source .venv/Scripts/activate${NC}"
else
    echo -e "${BLUE}    source .venv/bin/activate${NC}"
fi
echo -e "${YELLOW}To start the bot, run:${NC}"
echo -e "${BLUE}    python launcher.py${NC}"
echo "" 