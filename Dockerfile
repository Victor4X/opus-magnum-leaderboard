# Stage 1: build omsim
FROM gcc:13 AS omsim-builder
WORKDIR /build
COPY omsim/ .
RUN make

# Stage 2: runtime
FROM python:3.12-slim
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy omsim binary from builder
COPY --from=omsim-builder /build/omsim /app/omsim/omsim

# Install Python dependencies (separate layer for caching)
COPY server/pyproject.toml server/uv.lock /app/server/
RUN cd /app/server && uv sync --frozen --no-dev

# Copy server source
COPY server/ /app/server/

# Persist the database outside the image
VOLUME ["/app/server/data"]

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/server/data/leaderboard.db

EXPOSE 8000

WORKDIR /app/server
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
