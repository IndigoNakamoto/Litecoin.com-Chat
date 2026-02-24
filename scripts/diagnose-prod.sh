#!/bin/bash
# Quick diagnostic for production Docker stack (e.g. after reboot or network outage).
# Usage: ./scripts/diagnose-prod.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

if docker compose version &>/dev/null; then
  DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null; then
  DOCKER_COMPOSE="docker-compose"
else
  echo "❌ Docker Compose not found."
  exit 1
fi

COMPOSE_FILES="-f docker-compose.prod.yml"
[ -f docker-compose.override.yml ] && COMPOSE_FILES="-f docker-compose.prod.yml -f docker-compose.override.yml"

echo "🔍 Production stack diagnostic"
echo "================================"
echo ""

echo "1️⃣ Docker & container status"
echo "----------------------------"
if ! docker info &>/dev/null; then
  echo "❌ Docker daemon is not running. Start Docker Desktop (or the Docker service) and try again."
  exit 1
fi
echo "   Docker: OK"
$DOCKER_COMPOSE $COMPOSE_FILES ps -a 2>/dev/null || true
echo ""

echo "2️⃣ Backend container (litecoin-backend)"
echo "----------------------------------------"
if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q '^litecoin-backend$'; then
  STATUS=$(docker inspect -f '{{.State.Status}}' litecoin-backend 2>/dev/null || echo "?")
  HEALTH=$(docker inspect -f '{{.State.Health.Status}}' litecoin-backend 2>/dev/null || echo "no healthcheck")
  echo "   Status: $STATUS | Health: $HEALTH"
  if [ "$STATUS" != "running" ]; then
    echo "   Last 20 log lines:"
    docker logs --tail 20 litecoin-backend 2>&1 | sed 's/^/   /'
  fi
else
  echo "   Container not found. Stack may not be up."
fi
echo ""

echo "3️⃣ Dependencies (MongoDB, Payload CMS)"
echo "---------------------------------------"
for c in litecoin-mongodb litecoin-payload-cms; do
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${c}$"; then
    S=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null)
    H=$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "n/a")
    echo "   $c: status=$S health=$H"
  else
    echo "   $c: not found"
  fi
done
echo ""

echo "4️⃣ Backend recent logs (last 30 lines)"
echo "--------------------------------------"
docker logs --tail 30 litecoin-backend 2>&1 | sed 's/^/   /' || echo "   (could not get logs)"
echo ""

echo "5️⃣ Local connectivity"
echo "----------------------"
if curl -sf --connect-timeout 3 http://localhost:8000/ &>/dev/null; then
  echo "   http://localhost:8000/ → OK"
else
  echo "   http://localhost:8000/ → FAIL (backend not responding locally)"
fi
echo ""

# Check for Infinity embedding connection errors (local RAG not running)
# Only flag actual connection failures, not normal "InfinityEmbeddings initialized" lines
if docker logs --tail 100 litecoin-backend 2>&1 | grep -qE "ConnectError|All connection attempts failed"; then
  echo "⚠️  Infinity embedding errors detected"
  echo "--------------------------------------"
  echo "   Backend is trying to use the local Infinity embedding service (port 7997),"
  echo "   but it is not reachable (e.g. not started after reboot)."
  echo ""
  echo "   Fix one of:"
  echo "   • Disable local embeddings: in .env.docker.prod set USE_INFINITY_EMBEDDINGS=false"
  echo "     (and optionally USE_REDIS_CACHE=false, USE_LOCAL_REWRITER=false), then restart:"
  echo "     docker restart litecoin-backend"
  echo "   • Or start local RAG: ./scripts/run-prod.sh -d --local-rag"
  echo "     (starts embedding server on host and optional Ollama/Redis Stack)"
  echo ""
fi

echo "💡 If backend is unhealthy or not responding:"
echo "   ./scripts/down-prod.sh"
echo "   ./scripts/run-prod.sh -d"
echo "   (Ensure .env.docker.prod and .env.secrets are set; run-prod.sh will prompt for Grafana password if needed)"
echo ""
