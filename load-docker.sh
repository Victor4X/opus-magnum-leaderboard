#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="${SCRIPT_DIR}/om-leaderboard.tar.gz"

if [ ! -f "$ARCHIVE" ]; then
  echo "Error: $ARCHIVE not found. Run build-docker.sh first." >&2
  exit 1
fi

echo "Loading om-leaderboard.tar.gz..."
docker load < "$ARCHIVE"
echo "Done. Run ./start-docker.sh to start the server."
