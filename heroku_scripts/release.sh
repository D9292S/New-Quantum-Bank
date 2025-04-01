#!/bin/bash
# Heroku release phase script to configure the application after deployment

echo "Starting release phase configuration..."

# Install uv if not already present
if ! command -v uv &> /dev/null; then
  echo "Installing uv package manager..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install dependencies using uv
echo "Installing dependencies using uv..."
uv pip install -e ".[production]"

# Run the post-deployment script
python heroku_scripts/post_deploy.py

# Apply any configuration changes it recommended
if [ -f heroku_release_config.txt ]; then
  echo "Applying recommended configuration changes..."
  while read -r cmd; do
    echo "Executing: $cmd"
    eval "$cmd"
  done < heroku_release_config.txt
  rm heroku_release_config.txt
fi

# Set up MongoDB indexes if needed
echo "Checking MongoDB indexes..."
python -c "
from optimizations.mongodb_improvements import optimize_indexes
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def setup_indexes():
    mongo_uri = os.environ.get('MONGO_URI')
    if not mongo_uri:
        print('MongoDB URI not found in environment variables')
        return
    
    client = AsyncIOMotorClient(mongo_uri)
    db_name = mongo_uri.split('/')[-1].split('?')[0] or 'quantum_bank'
    db = client[db_name]
    
    print(f'Setting up indexes for {db_name} database...')
    await optimize_indexes(db)
    print('Indexes setup complete')

asyncio.run(setup_indexes())
"

echo "Release phase configuration completed" 