#!/usr/bin/env bash
set -e

docker run -d \
  --name om-leaderboard \
  -p 8000:8000 \
  -v om-leaderboard-data:/app/server/data \
  --restart unless-stopped \
  om-leaderboard

echo "Leaderboard running at http://localhost:8000"
