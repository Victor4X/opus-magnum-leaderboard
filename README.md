# Opus Magnum Leaderboard

A self-hosted leaderboard for a friend group playing [Opus Magnum](https://store.steampowered.com/app/558990/Opus_Magnum/).

Each player runs a small desktop client that watches their local save directory. Whenever a solution file changes, it's automatically uploaded to a shared server, scored, and shown on the leaderboard.

## How it works

```
[Rust client]  watches your save folder
     |
     |  uploads .solution files over HTTP
     v
[Python server]  scores them with omsim
     |
     v
[Web UI]  shows best scores per puzzle per player
```

## Quick start

**Server** (run this on a machine your friends can reach):
```bash
cd server
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```
Then open `http://your-server:8000` in a browser.

**Client** (each player runs this on their own machine):
```bash
cd client
cargo run --release
```
Enter the server URL and your nickname, and the client handles the rest. Your solution directory is detected automatically.

## Requirements

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Rust toolchain (`cargo`)
- omsim built: `cd omsim && make`

## Credits

Solutions are scored by [omsim](https://github.com/ianh/omsim).

The `.solution`/`.puzzle` binary parser is adapted from
[omsp](https://github.com/F43nd1r/omsp) by F43nd1r, licensed under Apache-2.0.

[Opus Magnum](https://store.steampowered.com/app/558990/Opus_Magnum/) is a game
by [Zachtronics](https://www.zachtronics.com/). This project is an unofficial,
fan-made tool and is not affiliated with Zachtronics.
