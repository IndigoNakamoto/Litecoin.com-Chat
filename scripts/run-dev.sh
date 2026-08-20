#!/bin/bash
# Helper script to run development services with hot reload
# This script uses docker-compose.dev.yml and excludes cloudflare service

set -e

# Detect Docker Compose command (v2 uses 'docker compose', v1 uses 'docker-compose')
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ Error: Docker Compose not found!"
    echo "   Please install Docker Compose (v2: 'docker compose' or v1: 'docker-compose')"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Check if .env.docker.dev exists (optional but recommended)
ENV_DEV_FILE="$PROJECT_ROOT/.env.docker.dev"
if [ ! -f "$ENV_DEV_FILE" ]; then
  echo "⚠️  Warning: .env.docker.dev file not found!"
  echo ""
  echo "Development environment variables will use defaults from docker-compose.dev.yml"
  echo "or environment variables set in your shell."
  echo ""
  echo "To create .env.docker.dev:"
  echo "  cp .env.example .env.docker.dev"
  echo ""
  read -p "Continue anyway? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted. Please create .env.docker.dev first."
    exit 1
  fi
else
  echo "📦 Loading environment variables from .env.docker.dev..."
  # Export variables (handle comments and empty lines)
  set -a  # Automatically export all variables
  source <(grep -v '^#' "$ENV_DEV_FILE" | grep -v '^$' | sed 's/^/export /')
  set +a  # Stop automatically exporting
fi

# Check if docker-compose.dev.yml exists
DEV_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.dev.yml"
if [ ! -f "$DEV_COMPOSE_FILE" ]; then
  echo "❌ Error: docker-compose.dev.yml file not found!"
  echo ""
  echo "This file should exist in the project root."
  exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Check for existing containers for THIS compose project only (ignore other repos' litecoin-* names)
echo "🔍 Checking for existing containers..."
EXISTING_CONTAINERS=$($DOCKER_COMPOSE -f docker-compose.dev.yml ps -a --format "{{.Name}}" 2>/dev/null | grep -v '^[[:space:]]*$' || true)
if [ -n "$EXISTING_CONTAINERS" ]; then
  echo "⚠️  Warning: This compose project already has containers (may conflict on ports or names):"
  echo "$EXISTING_CONTAINERS" | sed 's/^/   - /'
  echo ""
  echo "💡 Tip: Stop this stack first with:"
  echo "   $DOCKER_COMPOSE -f docker-compose.dev.yml down"
  echo ""
  read -p "Continue anyway? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted. Please stop existing containers first."
    exit 1
  fi
fi

# Check if cloudflare/cloudflared service exists and exclude it
ALL_SERVICES=$($DOCKER_COMPOSE -f docker-compose.dev.yml config --services 2>/dev/null || true)
CLOUDFLARE_SERVICE=$(echo "$ALL_SERVICES" | grep -i "cloudflare\|cloudflared" | head -n1 || true)

echo "🚀 Starting development services with hot reload..."
echo "   Hot reload is enabled for:"
echo "   - Backend (Python/uvicorn --reload)"
echo "   - Frontend (Next.js dev mode)"
echo "   - Payload CMS (pnpm dev)"
echo ""

if [ -n "$CLOUDFLARE_SERVICE" ]; then
  echo "ℹ️  Excluding cloudflare service: $CLOUDFLARE_SERVICE"
  echo ""
  # Use --scale to set cloudflare to 0 instances
  $DOCKER_COMPOSE -f docker-compose.dev.yml up "$@" --scale "$CLOUDFLARE_SERVICE=0"
else
  # No cloudflare service found, just start normally
  $DOCKER_COMPOSE -f docker-compose.dev.yml up "$@"
fi

