#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build -t om-leaderboard "$SCRIPT_DIR"

echo "Saving image to om-leaderboard.tar.gz..."
docker save om-leaderboard | gzip > "${SCRIPT_DIR}/om-leaderboard.tar.gz"

echo "Done: om-leaderboard.tar.gz"
