#!/bin/bash
# Helper script to run production builds locally for verification
# This script uses docker-compose.prod-local.yml which loads .env.prod-local

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

# Check if .env.prod-local exists
ENV_PROD_LOCAL_FILE="$PROJECT_ROOT/.env.prod-local"
if [ ! -f "$ENV_PROD_LOCAL_FILE" ]; then
    echo "❌ Error: .env.prod-local file not found!"
    echo ""
    echo "Please create .env.prod-local in the project root."
    echo ""
    echo "You can copy from the template:"
    echo "  cp .env.example .env.prod-local"
    echo ""
    echo "Then update the values as needed. See docs/setup/ENVIRONMENT_VARIABLES.md for details."
    exit 1
fi

# Check if docker-compose.prod-local.yml exists
PROD_LOCAL_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.prod-local.yml"
if [ ! -f "$PROD_LOCAL_COMPOSE_FILE" ]; then
    echo "❌ Error: docker-compose.prod-local.yml file not found!"
    echo ""
    echo "This file should exist in the project root."
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Check for existing containers for THIS compose project only (ignore other repos' litecoin-* names)
echo "🔍 Checking for existing containers..."
EXISTING_CONTAINERS=$($DOCKER_COMPOSE -f docker-compose.prod-local.yml ps -a --format "{{.Name}}" 2>/dev/null | grep -v '^[[:space:]]*$' || true)
if [ -n "$EXISTING_CONTAINERS" ]; then
    echo "⚠️  Warning: This compose project already has containers (may conflict on ports or names):"
    echo "$EXISTING_CONTAINERS" | sed 's/^/   - /'
    echo ""
    echo "💡 Tip: Stop this stack first with:"
    echo "   $DOCKER_COMPOSE -f docker-compose.prod-local.yml down"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted. Please stop existing containers first."
        exit 1
    fi
fi

# Export variables from .env.prod-local for build args
echo "📦 Loading environment variables from .env.prod-local..."
echo "🚀 Starting local production build verification..."
echo ""

# Export variables (handle comments and empty lines)
# Use a safer method that handles values with spaces and special characters
set -a  # Automatically export all variables
source <(grep -v '^#' "$ENV_PROD_LOCAL_FILE" | grep -v '^$' | sed 's/^/export /')
set +a  # Stop automatically exporting

# Verify critical variables are set
if [ -z "$MONGO_URI" ]; then
  echo "⚠️  Warning: MONGO_URI is not set in .env.prod-local"
  echo "   Setting default: mongodb://mongodb:27017"
  echo "   This uses the Docker service name 'mongodb' for container-to-container communication"
  export MONGO_URI="mongodb://mongodb:27017"
fi

if [ -z "$DATABASE_URI" ]; then
  echo "⚠️  Warning: DATABASE_URI is not set in .env.prod-local"
  echo "   Setting default: mongodb://mongodb:27017/payload_cms"
  echo "   This uses the Docker service name 'mongodb' for Payload CMS"
  export DATABASE_URI="mongodb://mongodb:27017/payload_cms"
fi

if [ -z "$NEXT_PUBLIC_PAYLOAD_URL" ]; then
  echo "⚠️  Warning: NEXT_PUBLIC_PAYLOAD_URL is not set in .env.prod-local"
  echo "   Frontend will use default localhost URL"
fi

# Verify critical Payload CMS auth variables
if [ -z "$PAYLOAD_PUBLIC_SERVER_URL" ]; then
  echo "⚠️  Warning: PAYLOAD_PUBLIC_SERVER_URL is not set in .env.prod-local"
  echo "   Payload CMS will default to http://localhost:3001"
  echo "   This should be correct for local production builds, but verify auth works correctly"
elif [ "$PAYLOAD_PUBLIC_SERVER_URL" != "http://localhost:3001" ]; then
  echo "⚠️  Warning: PAYLOAD_PUBLIC_SERVER_URL is set to: $PAYLOAD_PUBLIC_SERVER_URL"
  echo "   For local production builds, this should typically be http://localhost:3001"
  echo "   Using a different URL may cause authentication issues"
fi

# Run docker-compose with production-local file
# Pass build args explicitly from .env.prod-local for frontend build
# The exported variables will be available to docker-compose for build args
#
# Note: Production-local builds always use --no-cache to ensure clean, reproducible builds
# that match production. This prevents issues from stale build cache and ensures
# all dependencies are freshly installed.
if [ -n "$NEXT_PUBLIC_BACKEND_URL" ] && [ -n "$NEXT_PUBLIC_PAYLOAD_URL" ]; then
  echo "🔧 Using build args from .env.prod-local:"
  echo "   NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL"
  echo "   NEXT_PUBLIC_PAYLOAD_URL=$NEXT_PUBLIC_PAYLOAD_URL"
  echo ""
  echo "🔨 Building all services with --no-cache (clean build)..."
  # Build all services with --no-cache, passing explicit build args for frontend
  # Note: "$@" is intentionally excluded from build command to ensure --no-cache cannot be overridden
  $DOCKER_COMPOSE -f docker-compose.prod-local.yml build --no-cache \
    --build-arg NEXT_PUBLIC_BACKEND_URL="$NEXT_PUBLIC_BACKEND_URL" \
    --build-arg NEXT_PUBLIC_PAYLOAD_URL="$NEXT_PUBLIC_PAYLOAD_URL"
  $DOCKER_COMPOSE -f docker-compose.prod-local.yml up "$@"
else
  echo "⚠️  Warning: NEXT_PUBLIC_* variables not set, using defaults from docker-compose.prod-local.yml"
  echo "🔨 Building all services with --no-cache (clean build)..."
  # Build all services with --no-cache
  # Note: "$@" is intentionally excluded from build command to ensure --no-cache cannot be overridden
  $DOCKER_COMPOSE -f docker-compose.prod-local.yml build --no-cache
  $DOCKER_COMPOSE -f docker-compose.prod-local.yml up "$@"
fi

