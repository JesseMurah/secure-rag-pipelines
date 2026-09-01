#!/usr/bin/env bash
# One-time OpenFGA setup: store, model, tuples.
#
# Requires: docker running the openfga container, and the fga CLI
#   brew install openfga/tap/fga
#
# Run from the repo root:  bash fga/bootstrap.sh

set -euo pipefail

FGA_API_URL="${FGA_API_URL:-http://localhost:8080}"
export FGA_API_URL

echo "→ checking OpenFGA at $FGA_API_URL"
curl -sf "$FGA_API_URL/healthz" >/dev/null || {
  echo "OpenFGA is not responding. Start it with:"
  echo "  docker start openfga   # or, first time:"
  echo "  docker run -d --name openfga -p 8080:8080 -p 8081:8081 -p 3000:3000 openfga/openfga run"
  exit 1
}

echo "→ creating store"
STORE_ID=$(fga store create --name "secure-rag-pipelines" | python3 -c 'import json,sys; print(json.load(sys.stdin)["store"]["id"])')

echo "→ writing authorization model from fga/model.fga"
MODEL_ID=$(fga model write --store-id="$STORE_ID" --file fga/model.fga | python3 -c 'import json,sys; print(json.load(sys.stdin)["authorization_model_id"])')

echo "→ writing relationship tuples from fga/tuples.yaml"
fga tuple write --store-id="$STORE_ID" --model-id="$MODEL_ID" --file fga/tuples.yaml >/dev/null

cat <<EOF

Done. Paste these into .env:

FGA_API_URL=$FGA_API_URL
FGA_STORE_ID=$STORE_ID
FGA_MODEL_ID=$MODEL_ID

EOF
