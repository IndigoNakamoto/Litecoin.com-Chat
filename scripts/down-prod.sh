#!/bin/bash
# Shutdown production: docker-compose.prod.yml (+ override if present).
# Stops core stack, monitoring (Prometheus/Grafana), chat_tunnel, local-rag profile containers, and native embedding server if used.

set -e

# Detect Docker Compose command (v2 uses 'docker compose', v1 uses 'docker-compose')
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ Error: Docker Compose not found!"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Change to project root
cd "$PROJECT_ROOT"

# Check if docker-compose.prod.yml exists
PROD_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.prod.yml"
if [ ! -f "$PROD_COMPOSE_FILE" ]; then
  echo "❌ Error: docker-compose.prod.yml file not found!"
  exit 1
fi

# Check if docker-compose.override.yml exists (use if available)
OVERRIDE_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.override.yml"
if [ -f "$OVERRIDE_COMPOSE_FILE" ]; then
  COMPOSE_FILES="-f docker-compose.prod.yml -f docker-compose.override.yml"
else
  COMPOSE_FILES="-f docker-compose.prod.yml"
fi

echo "🛑 Shutting down production services..."
echo ""

# =============================================================================
# Stop Native Embedding Server (if running)
# =============================================================================
if [ -f "$PROJECT_ROOT/.infinity.pid" ]; then
    PID=$(cat "$PROJECT_ROOT/.infinity.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🍎 Stopping native embedding server (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 2
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null || true
        fi
        echo "   ✓ Native embedding server stopped"
    fi
    rm -f "$PROJECT_ROOT/.infinity.pid"
fi

# Also check for any stray embedding server processes
STRAY_PIDS=$(pgrep -f "embeddings_server.py" 2>/dev/null || true)
if [ -n "$STRAY_PIDS" ]; then
    echo "   Cleaning up stray embedding server processes..."
    echo "$STRAY_PIDS" | xargs kill 2>/dev/null || true
fi

# For shutdown operations, docker-compose needs to parse the entire config file
# If GRAFANA_ADMIN_PASSWORD is not set, provide a temporary dummy value
# This only affects parsing - no services will start during shutdown
if [ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
  export GRAFANA_ADMIN_PASSWORD="dummy-for-shutdown-only"
  echo "⚠️  Note: GRAFANA_ADMIN_PASSWORD not set, using temporary value for shutdown parsing"
  echo ""
fi

# Shutdown entire production project, including profile-only services:
#   monitoring (Prometheus, Grafana), litecoin-integration (chat_tunnel), local-rag (Ollama, redis_stack, infinity)
# One compose down avoids leaving the network up because monitoring/tunnel containers still hold it.
echo "   Stopping core stack + monitoring + chat tunnel + local RAG profiles..."
$DOCKER_COMPOSE $COMPOSE_FILES \
  --profile monitoring \
  --profile litecoin-integration \
  --profile local-rag \
  down "$@"

echo ""
echo "🧹 Cleaning up dangling images from previous builds..."
docker image prune -f > /dev/null 2>&1
echo "   ✓ Cleaned up dangling images"
echo ""

echo "✅ All services shutdown complete!"
echo "   (Core stack + monitoring + chat tunnel + local RAG, if any were running)"
echo ""
echo "💡 Tip: To free up more disk space, run:"
echo "   docker system prune -a        # Remove all unused images, containers, networks"
echo "   docker builder prune -a       # Remove build cache"

