#!/bin/bash
# Helper script to shutdown production services gracefully
# This script uses docker-compose.prod.yml and docker-compose.override.yml

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

# Check if docker-compose.prod.yml exists
PROD_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.prod.yml"
if [ ! -f "$PROD_COMPOSE_FILE" ]; then
  echo "❌ Error: docker-compose.prod.yml file not found!"
  echo ""
  echo "This file should exist in the project root."
  exit 1
fi

# Check if docker-compose.override.yml exists (use if available)
OVERRIDE_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.override.yml"
if [ -f "$OVERRIDE_COMPOSE_FILE" ]; then
  COMPOSE_FILES="-f docker-compose.prod.yml -f docker-compose.override.yml"
else
  COMPOSE_FILES="-f docker-compose.prod.yml"
fi

# Change to project root
cd "$PROJECT_ROOT"

# For shutdown operations, docker-compose needs to parse the entire config file
# If GRAFANA_ADMIN_PASSWORD is not set, provide a temporary dummy value
# This only affects parsing - no services will start during shutdown
if [ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
  export GRAFANA_ADMIN_PASSWORD="dummy-for-shutdown-only"
fi

# Parse command line arguments
REMOVE_VOLUMES=false
REMOVE_IMAGES=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -v|--volumes)
      REMOVE_VOLUMES=true
      shift
      ;;
    --images)
      REMOVE_IMAGES=true
      shift
      ;;
    --force|-f)
      FORCE=true
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Shutdown production services gracefully."
      echo ""
      echo "Options:"
      echo "  -v, --volumes    Remove volumes when shutting down"
      echo "  --images         Remove images when shutting down"
      echo "  -f, --force      Force shutdown without confirmation"
      echo "  -h, --help       Show this help message"
      echo ""
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1"
      echo "   Use -h or --help for usage information"
      exit 1
      ;;
  esac
done

# Check for running production containers
echo "🔍 Checking for running production containers..."
RUNNING_CONTAINERS=$($DOCKER_COMPOSE $COMPOSE_FILES ps --services --filter "status=running" 2>/dev/null || true)

if [ -z "$RUNNING_CONTAINERS" ]; then
  echo "ℹ️  No running production containers found."
  
  # Check if there are any stopped containers
  STOPPED_CONTAINERS=$($DOCKER_COMPOSE $COMPOSE_FILES ps --services --filter "status=stopped" 2>/dev/null || true)
  if [ -n "$STOPPED_CONTAINERS" ]; then
    echo "   However, there are stopped containers that can be removed."
    if [ "$FORCE" = false ]; then
      echo ""
      read -p "Remove stopped containers? (y/N) " -n 1 -r
      echo
      if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted."
        exit 0
      fi
    fi
  else
    echo "✅ All production services are already stopped."
    exit 0
  fi
else
  echo "📦 Found running production containers:"
  echo "$RUNNING_CONTAINERS" | sed 's/^/   - /'
  echo ""
  
  if [ "$FORCE" = false ]; then
    read -p "Shutdown these services? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "❌ Aborted."
      exit 0
    fi
  fi
fi

# Build docker-compose down command (include profile-only services)
DOWN_CMD="$DOCKER_COMPOSE $COMPOSE_FILES --profile monitoring --profile litecoin-integration --profile local-rag down"

if [ "$REMOVE_VOLUMES" = true ]; then
  echo "⚠️  Warning: Volumes will be removed!"
  if [ "$FORCE" = false ]; then
    read -p "This will delete all data in volumes. Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "❌ Aborted."
      exit 0
    fi
  fi
  DOWN_CMD="$DOWN_CMD -v"
fi

if [ "$REMOVE_IMAGES" = true ]; then
  DOWN_CMD="$DOWN_CMD --rmi all"
fi

echo ""
echo "🛑 Shutting down production services..."
echo ""

# Execute shutdown command
$DOWN_CMD

echo ""
echo "✅ Production services have been shutdown successfully!"

if [ "$REMOVE_VOLUMES" = true ]; then
  echo "   (Volumes have been removed)"
fi

if [ "$REMOVE_IMAGES" = true ]; then
  echo "   (Images have been removed)"
fi

echo ""

