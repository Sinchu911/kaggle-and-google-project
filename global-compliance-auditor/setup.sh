#!/bin/bash
# Global Compliance Auditor setup script

echo "Initializing environment..."

# Create Python virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate virtual environment and install requirements
source .venv/bin/activate
pip install -r requirements.txt
pip install google-agents-cli

echo "Setup complete!"
