#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build omsim if binary is missing
if [ ! -f "$SCRIPT_DIR/omsim/omsim" ]; then
    echo "Building omsim..."
    make -C "$SCRIPT_DIR/omsim"
fi

cd "$SCRIPT_DIR/server"
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000
