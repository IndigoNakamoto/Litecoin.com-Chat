#!/bin/bash
# Non-interactive preflight. Fail closed with a missing-key list.
# Usage: ./scripts/preflight.sh [dev|prod-local|prod]

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

TARGET="${1:-dev}"
MISSING=()

if docker compose version &>/dev/null; then
  DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null; then
  DOCKER_COMPOSE="docker-compose"
else
  echo "ERROR: Docker Compose not found"
  exit 1
fi

need_file() {
  local path="$1"
  if [ ! -f "$PROJECT_ROOT/$path" ]; then
    MISSING+=("$path")
  fi
}

need_var_in_file() {
  local file="$1"
  local var="$2"
  if [ ! -f "$PROJECT_ROOT/$file" ]; then
    return
  fi
  if ! grep -qE "^${var}=.+" "$PROJECT_ROOT/$file"; then
    MISSING+=("${file}:${var}")
  fi
}

case "$TARGET" in
  dev)
    need_file ".env.docker.dev"
    need_file "backend/.env"
    need_file "payload_cms/.env"
    need_var_in_file "backend/.env" "WEBHOOK_SECRET"
    need_var_in_file "backend/.env" "ADMIN_TOKEN"
    need_var_in_file "payload_cms/.env" "PAYLOAD_SECRET"
    COMPOSE_FILES="-f docker-compose.dev.yml"
    ;;
  prod-local)
    need_file ".env.prod-local"
    need_file "backend/.env"
    need_file "payload_cms/.env"
    COMPOSE_FILES="-f docker-compose.prod-local.yml"
    ;;
  prod)
    need_file ".env.docker.prod"
    need_file ".env.secrets"
    need_file "backend/.env"
    need_file "payload_cms/.env"
    need_file "docker-compose.override.yml"
    need_var_in_file ".env.docker.prod" "GRAFANA_ADMIN_PASSWORD"
    need_var_in_file ".env.docker.prod" "CLOUDFLARE_CHAT_TUNNEL_TOKEN"
    COMPOSE_FILES="-f docker-compose.prod.yml"
    [ -f docker-compose.override.yml ] && COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.override.yml"
    ;;
  *)
    echo "Usage: $0 [dev|prod-local|prod]"
    exit 1
    ;;
esac

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "Preflight failed. Missing:"
  for item in "${MISSING[@]}"; do
    echo "  - $item"
  done
  echo "See docs/setup/ENVIRONMENT_VARIABLES.md"
  exit 1
fi

echo "Rendering compose config ($TARGET)..."
$DOCKER_COMPOSE $COMPOSE_FILES config >/dev/null
echo "Preflight OK for $TARGET"
