#!/bin/bash
# One-shot: pull published articles from cms.lite.space into local RAG.
# Does not point local webhooks at production. Local Payload can stay empty.
# Requires: Mongo on localhost:27017, backend/.env with embedding config,
#           and GOOGLE_API_KEY if you are not using local sentence-transformers.

set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

if [ -f backend/.env ]; then
  set -a
  # shellcheck disable=SC1091
  source backend/.env
  set +a
fi

export PAYLOAD_PUBLIC_SERVER_URL="${PAYLOAD_PUBLIC_SERVER_URL:-https://cms.lite.space}"
export MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
export MONGO_DETAILS="${MONGO_DETAILS:-$MONGO_URI}"

echo "Pulling published articles from $PAYLOAD_PUBLIC_SERVER_URL into $MONGO_URI"
python backend/utils/sync_payload_articles.py
echo "Verify: curl http://localhost:8000/api/v1/sync/health"
echo "Sample: curl \"$PAYLOAD_PUBLIC_SERVER_URL/api/articles?where[status][equals]=published&limit=5\""
