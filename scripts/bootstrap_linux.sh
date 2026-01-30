#! /bin/bash
# scripts/bootstrap_linux.sh
# ==============================================================================
# ReDate Bootstrap Script for Linux
# Installs Pixi, Docker, and prepares the local environment.
# ==============================================================================
set -e

echo ">>> [1/5] Checking Pre-requisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Install Pixi if missing
if ! command -v pixi &> /dev/null; then
    echo ">>> Installing Pixi (Package Manager)..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
else
    echo "Pixi is already installed."
fi

echo ">>> [2/5] Setting up Project Dependencies..."
# Use strict lockfile installation if available for reproducibility
if [ -f pixi.lock ]; then
    echo "Installing from lockfile (frozen)..."
    pixi install --frozen
else
    echo "Installing dependencies..."
    pixi install
fi

echo ">>> [3/5] Configuring Environment..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Creating .env from template..."
        cp .env.example .env
        echo "⚠️  WARNING: Created .env file. Please edit it with your actual API Keys before running!"
    else
        echo "⚠️  WARNING: No .env.example found. Creating empty .env."
        touch .env
    fi
else
    echo ".env file exists. Skipping."
fi

# Create data directories
mkdir -p data secrets/certs secrets/ssh

echo ">>> [4/5] Preparing Network Configuration..."
if [ ! -f config/gost-client.yaml ]; then
    echo "Generating default Gost config..."
    mkdir -p config
    # (Optional: Generate a dummy config if needed, usually repo has it)
fi

echo ">>> [5/5] Setup Complete!"
echo ""
echo "To start the local development stack:"
echo "  $ pixi run start"
echo "  OR via Docker:"
echo "  $ docker compose -f deploy/redate-compose.local.yml up --build"
echo ""