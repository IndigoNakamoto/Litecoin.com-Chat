#!/bin/bash
# Copy public suggested questions from cms.lite.space into local Payload Mongo.
# Chat chips fetch localhost:3001 from the browser; a fresh local CMS has none.
# Does not change webhooks or point the frontend at production.

set -euo pipefail

SOURCE_URL="${SOURCE_URL:-https://cms.lite.space}"
MONGO_CONTAINER="${MONGO_CONTAINER:-litecoin-mongodb-dev}"
MONGO_DB="${MONGO_DB:-payload_cms}"

if ! docker ps --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then
  echo "Mongo container $MONGO_CONTAINER is not running."
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl -fsS "$SOURCE_URL/api/suggested-questions?limit=100&sort=order" -o "$tmp"

count="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("docs") or []))' < "$tmp")"
if [ "$count" -eq 0 ]; then
  echo "No suggested questions at $SOURCE_URL"
  exit 1
fi

python3 - "$tmp" "$MONGO_DB" <<'PY' | docker exec -i "$MONGO_CONTAINER" mongosh --quiet
import json, sys
from datetime import datetime, timezone

data = json.load(open(sys.argv[1], encoding="utf-8"))
db_name = sys.argv[2]
docs = []
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
for raw in data.get("docs") or []:
    question = (raw.get("question") or "").strip()
    if not question:
        continue
    docs.append(
        {
            "question": question,
            "order": int(raw.get("order") or 0),
            "isActive": bool(raw.get("isActive", True)),
            "createdAt": now,
            "updatedAt": now,
        }
    )
print("const docs = " + json.dumps(docs) + ";")
print(f'const col = db.getSiblingDB({json.dumps(db_name)}).getCollection("suggested-questions");')
print(
    """
const existing = col.countDocuments();
if (existing > 0) {
  print("suggested-questions already has " + existing + " docs; skip");
} else {
  const res = col.insertMany(docs);
  print("inserted " + Object.keys(res.insertedIds).length);
}
"""
)
PY

echo "Verify: curl -s 'http://localhost:3001/api/suggested-questions?limit=5'"
