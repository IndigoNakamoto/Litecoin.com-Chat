#!/bin/bash
# Helper script to rebuild and restart only the backend service
# This is useful during development when you only need to update backend code

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

# Load environment variables from .env.docker.prod (same as run-prod.sh)
ENV_PROD_FILE="$PROJECT_ROOT/.env.docker.prod"
if [ -f "$ENV_PROD_FILE" ]; then
  echo "📦 Loading environment variables from .env.docker.prod..."
  TEMP_ENV=$(mktemp)
  grep -v '^[[:space:]]*#' "$ENV_PROD_FILE" | grep -v '^[[:space:]]*$' > "$TEMP_ENV"
  set -a
  source "$TEMP_ENV"
  set +a
  rm -f "$TEMP_ENV"
  
  if [ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
    echo "❌ Error: GRAFANA_ADMIN_PASSWORD is not set in .env.docker.prod"
    exit 1
  fi
  echo "   ✓ Environment variables loaded"
fi

# Load secrets from .env.secrets (same as run-prod.sh)
SECRETS_FILE="$PROJECT_ROOT/.env.secrets"
if [ -f "$SECRETS_FILE" ]; then
  echo "🔐 Loading secrets from .env.secrets..."
  TEMP_SECRETS=$(mktemp)
  grep -v '^[[:space:]]*#' "$SECRETS_FILE" | grep -v '^[[:space:]]*$' > "$TEMP_SECRETS"
  set -a
  source "$TEMP_SECRETS"
  set +a
  rm -f "$TEMP_SECRETS"
  
  if [ -z "${MONGO_INITDB_ROOT_USERNAME:-}" ]; then
    export MONGO_INITDB_ROOT_USERNAME="admin"
  fi
  
  # URL-encode function for MongoDB connection strings
  url_encode() {
    local string="$1"
    if command -v python3 &> /dev/null; then
      echo -n "$string" | python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=''))"
    elif command -v python &> /dev/null; then
      echo -n "$string" | python -c "import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=''))"
    else
      echo -n "$string" | sed 's/%/%25/g; s/ /%20/g; s/!/%21/g; s/#/%23/g; s/\$/%24/g; s/&/%26/g; s/'\''/%27/g; s/(/%28/g; s/)/%29/g; s/*/%2A/g; s/+/%2B/g; s/,/%2C/g; s/\//%2F/g; s/:/%3A/g; s/;/%3B/g; s/=/%3D/g; s/?/%3F/g; s/@/%40/g; s/\[/%5B/g; s/\]/%5D/g'
    fi
  }
  
  if [ -n "${MONGO_INITDB_ROOT_USERNAME:-}" ]; then
    export MONGO_INITDB_ROOT_USERNAME_ENCODED=$(url_encode "$MONGO_INITDB_ROOT_USERNAME")
  fi
  if [ -n "${MONGO_INITDB_ROOT_PASSWORD:-}" ]; then
    export MONGO_INITDB_ROOT_PASSWORD_ENCODED=$(url_encode "$MONGO_INITDB_ROOT_PASSWORD")
  fi
  if [ -n "${REDIS_PASSWORD:-}" ]; then
    export REDIS_PASSWORD_ENCODED=$(url_encode "$REDIS_PASSWORD")
  fi
  
  echo "   ✓ Secrets loaded and URL-encoded"
fi

# Change to project root
cd "$PROJECT_ROOT"

# Determine compose files (same logic as run-prod.sh)
OVERRIDE_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.override.yml"
if [ -f "$OVERRIDE_COMPOSE_FILE" ]; then
    COMPOSE_FILES="-f docker-compose.prod.yml -f docker-compose.override.yml"
    echo "✅ Using docker-compose.override.yml"
else
    COMPOSE_FILES="-f docker-compose.prod.yml"
    echo "⚠️  Using docker-compose.prod.yml only (no override file found)"
fi

echo "🔨 Rebuilding backend service..."
echo ""

# Rebuild the backend service (cache by default; NO_CACHE=1 for a clean rebuild)
BUILD_FLAGS=()
if [ "${NO_CACHE:-}" = "1" ] || [ "${NO_CACHE:-}" = "true" ]; then
  BUILD_FLAGS+=(--no-cache)
fi
$DOCKER_COMPOSE $COMPOSE_FILES build "${BUILD_FLAGS[@]}" backend

echo ""
echo "🔄 Restarting backend service..."
echo ""

# Stop and remove the backend container, then start it again
# This ensures the new image is used
$DOCKER_COMPOSE $COMPOSE_FILES up -d --force-recreate backend

echo ""
echo "✅ Backend service rebuilt and restarted!"
echo ""
echo "📋 Checking backend logs (Ctrl+C to exit)..."
echo ""

# Show logs (user can Ctrl+C to exit)
$DOCKER_COMPOSE $COMPOSE_FILES logs -f backend

