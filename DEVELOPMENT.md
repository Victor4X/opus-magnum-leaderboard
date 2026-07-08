# Development Guide

## Repository layout

```
opus-magnum-leaderboard/
├── omsim/                 # simulator (C, already cloned; run make to build)
├── omsp/                  # binary format documentation (Formats.md)
├── zachtronics-leaderboard-bot/   # source of the 263 .puzzle files
├── server/
│   ├── main.py            # FastAPI app, route definitions
│   ├── db.py              # SQLite schema and queries
│   ├── scorer.py          # omsim subprocess wrapper
│   ├── parser.py          # .solution binary parser
│   ├── puzzles/           # 263 .puzzle files (copied from zachtronics-leaderboard-bot)
│   ├── static/index.html  # leaderboard web UI
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
cd server
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

`--reload` restarts the server on file changes, useful during development.

The SQLite database is created automatically at `server/leaderboard.db` on first start.

### Dependencies

Managed by uv (`pyproject.toml`). Add new packages with `uv add <package>`.

| Package | Purpose |
|---|---|
| `fastapi` | HTTP framework |
| `uvicorn` | ASGI server |
| `python-multipart` | multipart form parsing (file uploads) |

### API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/submit` | Upload a `.solution` file. Form fields: `file` (bytes), `nickname` (string). Returns scored metrics as JSON. |
| `GET` | `/api/leaderboard` | All best scores, one row per (puzzle, player). |
| `GET` | `/api/leaderboard/{puzzle_id}` | Best scores for a single puzzle. |
| `GET` | `/` | Serves `static/index.html`. |

### Submission flow

1. `parser.py` reads the binary to get the puzzle ID (e.g. `P008`).
2. `scorer.py` writes the bytes to a temp file, runs `omsim/omsim --puzzle-file puzzles/P008.puzzle --metric cost --metric cycles --metric area --metric instructions /tmp/....solution`, and parses the output.
3. `db.py` inserts the raw submission. The `best_scores` view automatically surfaces the minimum value per metric per (puzzle, player).

### omsim output format

```
cost: 40
cycles: 256
area: 37
instructions: 43
```

One `key: value` pair per line. Incomplete/in-progress solutions cause omsim to exit with a non-zero status and empty output; these are returned as HTTP 422 and logged as errors in the client.

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
    MIN(area) as area, MIN(instructions) as instructions
FROM submissions GROUP BY puzzle_id, nickname;
```

All raw submissions are kept, so historical data is never lost. Best scores are computed on read.

### Puzzle files

The 263 `.puzzle` files live in `server/puzzles/`. They were copied from `zachtronics-leaderboard-bot/src/main/resources/om/puzzle/`. Tutorial puzzles (P001–P006, P044) are not present in that source and aren't tracked by the leaderboard.

If the game adds new puzzles, copy the new `.puzzle` files into `server/puzzles/` and restart the server.

### Web UI

`static/index.html` is a single self-contained file — no build step, no framework. It fetches `/api/leaderboard` on load and re-fetches every 30 seconds. Each puzzle gets its own table. Columns are sortable by clicking the header. The search box filters by puzzle ID. The best value in each column is highlighted in blue.

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
```

On first launch with no config, the solution directory is auto-detected:
- **Linux**: first subdirectory of `~/.local/share/Opus Magnum/`
- **macOS**: first subdirectory of `~/Library/Application Support/Opus Magnum/`
- **Windows**: first subdirectory of `Documents\My Games\Opus Magnum\` (also tries OneDrive)

Changes made in the UI take effect after clicking **Save & Restart Watcher**.

### File watcher

`watcher.rs` uses the `notify` crate (`RecommendedWatcher`, which picks the best backend for the OS — inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows). It watches the solution directory recursively and filters for `*.solution` create/modify events.

A 500ms debounce is applied because Opus Magnum writes solution files in multiple steps. Events are sent through a `tokio::sync::mpsc` channel to the upload worker.

### Uploader

`uploader.rs` sends a `multipart/form-data` POST to `/api/submit` with the raw file bytes and the player's nickname. On failure it retries once before reporting an error to the UI.

### Binary parser

Both `server/parser.py` and `client/src/parser.rs` implement the same logic:

```
bytes 0–3:   u32 LE  — version (always 7)
bytes 4+:    7-bit varint — string byte length  (C# BinaryReader encoding)
             then that many UTF-8 bytes — puzzle ID (e.g. "P008")
```

The 7-bit varint: read bytes one at a time. Low 7 bits are data; bit 7 means another byte follows. This matches C#'s `BinaryReader.ReadString`.

See `omsp/Formats.md` for the full solution and puzzle binary formats.

### Cross-compiling for Windows

From Linux:

```bash
rustup target add x86_64-pc-windows-gnu
sudo apt install gcc-mingw-w64
cargo build --release --target x86_64-pc-windows-gnu
# binary at target/x86_64-pc-windows-gnu/release/om-leaderboard-client.exe
```

---

## Testing end-to-end

```bash
# 1. Build omsim
cd omsim && make

# 2. Start server
cd server && uv run uvicorn main:app --port 8000

# 3. Submit a solution manually
curl -F "file=@~/.local/share/Opus Magnum/<steam-id>/stabilized-water-1.solution" \
     -F "nickname=test" \
     http://localhost:8000/api/submit

# 4. Check leaderboard JSON
curl http://localhost:8000/api/leaderboard

# 5. Open http://localhost:8000 in a browser

# 6. Run client and modify a .solution file to verify auto-upload
cd client && cargo run
```
