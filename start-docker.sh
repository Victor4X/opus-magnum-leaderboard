#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/om-leaderboard-data"

# Load API_KEY from server/.env if it exists
API_KEY=""
ENV_FILE="${SCRIPT_DIR}/server/.env"
if [ -f "$ENV_FILE" ]; then
  API_KEY=$(grep -E '^API_KEY=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '[:space:]')
fi

mkdir -p "$DATA_DIR"

# Remove any container left over from a previous run so the --name is free
# (docker run would otherwise fail with "name is already in use").
docker rm -f om-leaderboard >/dev/null 2>&1 || true

docker run -d \
  --name om-leaderboard \
  -p 8000:8000 \
  -v "$DATA_DIR":/app/server/data \
  -e "API_KEY=${API_KEY}" \
  --restart unless-stopped \
  om-leaderboard

echo "Leaderboard running at http://localhost:8000"
echo "Data directory: $DATA_DIR"
