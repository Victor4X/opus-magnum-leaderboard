# Development Guide

## Repository layout

```
opus-magnum-leaderboard/
├── omsim/                 # simulator (C, git submodule; run make to build)
├── vendor/                # reference repos, gitignored
├── Dockerfile             # multi-stage build: omsim + Python server
├── start.sh               # run server locally (builds omsim if needed)
├── start-docker.sh        # run pre-built Docker image
├── server/
│   ├── main.py            # FastAPI app, route definitions
│   ├── db.py              # SQLite schema and queries
│   ├── scorer.py          # omsim subprocess wrapper
│   ├── parser.py          # .solution and .puzzle binary parser
│   ├── puzzles/           # 263 .puzzle files
│   ├── static/index.html  # leaderboard web UI
│   ├── .env.example       # documents API_KEY env var
│   └── pyproject.toml     # uv-managed dependencies
└── client/
    ├── Cargo.toml
    └── src/
        ├── main.rs        # egui app, UI layout
        ├── config.rs      # settings load/save (~/.config/om-leaderboard/config.toml)
        ├── parser.rs      # .solution binary parser (same logic as server)
        ├── watcher.rs     # notify-based file watcher with 500ms debounce
        └── uploader.rs    # reqwest multipart upload
```

---

## Server

### Setup

```bash
./start.sh
```

Or manually, for development with auto-reload:

```bash
cd server
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The SQLite database is created automatically at `server/leaderboard.db` on first start (or at `$DB_PATH` if that env var is set).

### Dependencies

Managed by uv (`pyproject.toml`). Add new packages with `uv add <package>`.

| Package | Purpose |
|---|---|
| `fastapi` | HTTP framework |
| `uvicorn` | ASGI server |
| `python-multipart` | multipart form parsing (file uploads) |
| `python-dotenv` | loads `server/.env` at startup |

### API key

Uploads can be protected by setting `API_KEY` in `server/.env`:

```bash
cp server/.env.example server/.env
# then edit server/.env and set API_KEY=your-secret
```

If `API_KEY` is empty or the file doesn't exist, the server accepts unauthenticated uploads. When set, `POST /api/submit` requires the header `X-Api-Key: <key>` and returns 401 otherwise.

When running with Docker, pass it as an environment variable instead:

```bash
docker run ... -e API_KEY=your-secret om-leaderboard
```

`server/.env` is gitignored and never committed.

### API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/submit` | Upload a `.solution` file. Form fields: `file` (bytes), `nickname` (string). Header: `X-Api-Key` (if key is configured). Returns scored metrics as JSON. |
| `GET` | `/api/leaderboard` | All best scores, one row per (puzzle, player), ordered by score. |
| `GET` | `/api/leaderboard/{puzzle_id}` | Best scores for a single puzzle. |
| `GET` | `/` | Serves `static/index.html`. |

### Submission flow

1. Check `X-Api-Key` header against `API_KEY` (if configured).
2. `parser.py` reads the binary to get the puzzle ID (e.g. `P008`).
3. `scorer.py` writes the bytes to a temp file, runs omsim, and parses the output.
4. Compare new scores against the player's current per-metric best. If the new submission is worse or equal in **every** metric (cost, cycles, area, instructions), it is rejected with `accepted: false` and not stored. If it improves at least one metric, it is inserted.
5. Return the scores along with `accepted: true/false` and `puzzle_name`.

### Submission acceptance

A submission is accepted if it strictly improves at least one metric. The leaderboard view takes `MIN` per metric independently, so a player can have their best cost come from one submission and their best cycles from another.

### omsim output format

```
cost: 40
cycles: 256
area: 37
instructions: 43
```

One `key: value` pair per line. Incomplete/in-progress solutions cause omsim to exit non-zero; these are returned as HTTP 422 and shown as errors in the client log.

### Database schema

```sql
CREATE TABLE submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    puzzle_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    cost INTEGER,
    cycles INTEGER,
    area INTEGER,
    instructions INTEGER,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    solution_blob BLOB
);

CREATE VIEW best_scores AS
SELECT puzzle_id, nickname,
    MIN(cost) as cost, MIN(cycles) as cycles,
    MIN(area) as area, MIN(instructions) as instructions,
    MIN(cost) + MIN(cycles) + MIN(area) as score
FROM submissions GROUP BY puzzle_id, nickname;
```

All raw submissions are kept so historical data is never lost. Best scores and the composite `score` (cost + cycles + area) are computed on read.

### Puzzle files

The 263 `.puzzle` files live in `server/puzzles/`. Human-readable puzzle names (e.g. "Stabilized Water") are parsed from the binary at startup and included in all API responses. Tutorial puzzles (P001–P006, P044) are not present and aren't tracked.

If the game adds new puzzles, copy the new `.puzzle` files into `server/puzzles/` and restart.

### Web UI

`static/index.html` is a single self-contained file — no build step, no framework. It fetches `/api/leaderboard` on load and re-fetches every 30 seconds. Each puzzle section shows the full name with the ID alongside. Columns are sortable; the default sort is by `score` (cost + cycles + area). The search box filters by puzzle name or ID. The best value in each column is highlighted in blue.

---

## Client

### Setup

```bash
cd client
cargo run           # debug build (faster to compile)
cargo run --release # release build (faster to run)
```

### Config file

Stored at `~/.config/om-leaderboard/config.toml` (Linux) / `%APPDATA%\om-leaderboard\config.toml` (Windows):

```toml
server_url = "http://your-server:8000"
nickname = "YourName"
solution_dir = "/home/you/.local/share/Opus Magnum/<steam-id>"
api_key = ""
```

On first launch with no config, the solution directory is auto-detected:
- **Linux**: first subdirectory of `~/.local/share/Opus Magnum/`
- **macOS**: first subdirectory of `~/Library/Application Support/Opus Magnum/`
- **Windows**: first subdirectory of `Documents\My Games\Opus Magnum\` (also tries OneDrive)

Changes made in the UI take effect after clicking **Save & Restart Watcher**.

### UI overview

- **Settings panel**: server URL, nickname, solution directory, API key (masked), connection status, Save button, Open Leaderboard button.
- **Upload All Solutions**: queues every `.solution` file in the watched directory for upload. Useful on first launch or after playing without the client open.
- **Upload log**: last 20 uploads showing time, puzzle name, and scores. Entries are green on improvement, grey on "no improvement" (submission rejected as not better), red on error.

### File watcher

`watcher.rs` uses the `notify` crate (`RecommendedWatcher` — inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows). It watches the solution directory recursively and filters for `*.solution` create/modify events.

A 500ms debounce is applied because Opus Magnum writes solution files in multiple steps. Events are forwarded through a `tokio::sync::mpsc` channel to the upload worker.

### Uploader

`uploader.rs` sends a `multipart/form-data` POST to `/api/submit` with the raw file bytes, the player's nickname, and the `X-Api-Key` header. On failure it retries once before reporting an error to the UI.

### Binary parser

`server/parser.py` and `client/src/parser.rs` implement the same logic for `.solution` files:

```
bytes 0–3:   u32 LE  — version (always 7)
bytes 4+:    7-bit varint — string byte length  (C# BinaryReader encoding)
             then that many UTF-8 bytes — puzzle ID (e.g. "P008")
```

`parser.py` also reads `.puzzle` files to extract the human-readable name (same encoding, starting after the 4-byte version field).

The 7-bit varint: read bytes one at a time. Low 7 bits are data; bit 7 means another byte follows. See `vendor/omsp/Formats.md` for the full binary format spec.

### CI / distributing binaries

`.github/workflows/build-client.yml` builds the client for Linux (x86_64), Windows (x86_64 MSVC), and macOS (Apple Silicon) on every push to `main`. Artifacts are available under the Actions tab for 90 days. Use `workflow_dispatch` to trigger a build manually.

### Cross-compiling for Windows (locally)

From Linux:

```bash
rustup target add x86_64-pc-windows-gnu
sudo apt install gcc-mingw-w64
cargo build --release --target x86_64-pc-windows-gnu
# binary at target/x86_64-pc-windows-gnu/release/om-leaderboard-client.exe
```

---

## Deployment

### Building the Docker image

```bash
docker build -t om-leaderboard .
```

### Running locally with Docker

```bash
./start-docker.sh
```

This starts the container on port 8000 with a named Docker volume (`om-leaderboard-data`) for database persistence and `--restart unless-stopped` so it survives reboots.

### Deploying to a remote server

**Option A — transfer the image directly** (no registry needed):

```bash
# On your machine
docker build -t om-leaderboard .
docker save om-leaderboard | gzip > om-leaderboard.tar.gz
scp om-leaderboard.tar.gz user@your-server:~

# On the server
docker load < om-leaderboard.tar.gz
./start-docker.sh   # or copy and run the script manually
```

**Option B — push to a registry:**

```bash
docker tag om-leaderboard ghcr.io/youruser/om-leaderboard:latest
docker push ghcr.io/youruser/om-leaderboard:latest

# On the server
docker pull ghcr.io/youruser/om-leaderboard:latest
docker tag ghcr.io/youruser/om-leaderboard:latest om-leaderboard
./start-docker.sh
```

### Database

The database lives in the `om-leaderboard-data` Docker volume. To back it up:

```bash
docker run --rm -v om-leaderboard-data:/data -v $(pwd):/out alpine \
  cp /data/leaderboard.db /out/leaderboard.db.bak
```

To restore, stop the container, copy the file back into the volume, and start it again.

---

## Testing end-to-end

```bash
# 1. Build omsim
cd omsim && make

# 2. Start server (with optional API key)
echo "API_KEY=testkey" > server/.env
./start.sh

# 3. Submit a solution manually
curl -H "X-Api-Key: testkey" \
     -F "file=@~/.local/share/Opus Magnum/<steam-id>/stabilized-water-1.solution" \
     -F "nickname=test" \
     http://localhost:8000/api/submit

# 4. Check leaderboard JSON
curl http://localhost:8000/api/leaderboard

# 5. Open http://localhost:8000 in a browser

# 6. Run client, enter the key in the API key field, modify a .solution file
cd client && cargo run
```
