#!/bin/bash
# deploy.sh — One-command VPS deployment for Visocode
# Usage: bash deploy.sh
# Run this on your VPS after cloning the repo.

set -e

echo "=== Visocode VPS Deploy ==="

# ── 1. Check Docker ─────────────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "[1/5] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "      Docker installed. You may need to re-login for group changes."
else
    echo "[1/5] Docker already installed: $(docker --version)"
fi

if ! command -v docker compose &> /dev/null; then
    echo "      Installing Docker Compose plugin..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

# ── 2. Pull Manim image ──────────────────────────────────────────────────────
echo "[2/5] Pulling manimcommunity/manim image (this may take a few minutes)..."
docker pull manimcommunity/manim:stable

# ── 3. Check secrets ─────────────────────────────────────────────────────────
echo "[3/5] Checking secrets..."
if [ ! -f .env ]; then
    echo "      ERROR: .env not found. Copy .env.example and fill in your keys."
    echo "      cp .env.example .env && nano .env"
    exit 1
fi
if [ ! -f client_secrets.json ]; then
    echo "      WARNING: client_secrets.json not found. Google Drive upload will be disabled."
fi
if [ ! -f token.json ]; then
    echo "      WARNING: token.json not found. Run the app locally once first to authorize Google Drive."
fi

# ── 4. Create output directory ───────────────────────────────────────────────
echo "[4/5] Creating manim_output directory..."
mkdir -p manim_output

# ── 5. Build and start ───────────────────────────────────────────────────────
echo "[5/5] Building and starting Visocode..."
docker compose build --no-cache
docker compose up -d

echo ""
echo "=== Done! ==="
echo "Visocode is running at http://$(curl -s ifconfig.me):8501"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # stream logs"
echo "  docker compose down           # stop"
echo "  docker compose restart        # restart after code changes"
