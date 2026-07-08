import os
from fastapi import FastAPI, File, Form, Header, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from db import init_db, insert_submission, is_superseded, get_leaderboard, get_puzzle_leaderboard
from parser import extract_puzzle_id, extract_puzzle_name
from scorer import score_solution

load_dotenv()
API_KEY = os.environ.get("API_KEY", "").strip()

app = FastAPI(title="Opus Magnum Leaderboard")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
PUZZLE_DIR = os.path.join(os.path.dirname(__file__), "puzzles")

# puzzle_id -> human-readable name, loaded once at startup
_puzzle_names: dict[str, str] = {}


@app.on_event("startup")
def startup():
    init_db()
    for fname in os.listdir(PUZZLE_DIR):
        if not fname.endswith(".puzzle"):
            continue
        puzzle_id = fname[:-7]  # strip ".puzzle"
        try:
            data = open(os.path.join(PUZZLE_DIR, fname), "rb").read()
            _puzzle_names[puzzle_id] = extract_puzzle_name(data)
        except Exception:
            pass


def _with_names(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["puzzle_name"] = _puzzle_names.get(row["puzzle_id"], row["puzzle_id"])
    return rows


@app.post("/api/submit")
async def submit(
    file: UploadFile = File(...),
    nickname: str = Form(...),
    x_api_key: str = Header(default=""),
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Invalid or missing API key")

    nickname = nickname.strip()
    if not nickname:
        raise HTTPException(400, "nickname is required")

    data = await file.read()

    try:
        puzzle_id = extract_puzzle_id(data)
    except Exception as e:
        raise HTTPException(400, f"Could not parse solution file: {e}")

    try:
        scores = score_solution(puzzle_id, data)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(422, str(e))

    cost, cycles, area = scores["cost"], scores["cycles"], scores["area"]
    score = (cost + cycles + area) if None not in (cost, cycles, area) else None
    puzzle_name = _puzzle_names.get(puzzle_id, puzzle_id)
    base = {"puzzle_id": puzzle_id, "puzzle_name": puzzle_name, **scores, "score": score}

    if is_superseded(puzzle_id, nickname, scores):
        return {**base, "accepted": False}

    insert_submission(
        puzzle_id,
        nickname,
        scores["cost"],
        scores["cycles"],
        scores["area"],
        scores["instructions"],
        data,
    )
    return {**base, "accepted": True}


@app.get("/api/leaderboard")
def leaderboard():
    return _with_names(get_leaderboard())


@app.get("/api/leaderboard/{puzzle_id}")
def leaderboard_puzzle(puzzle_id: str):
    rows = get_puzzle_leaderboard(puzzle_id)
    if not rows:
        raise HTTPException(404, f"No submissions for {puzzle_id!r}")
    return _with_names(rows)


@app.get("/", response_class=HTMLResponse)
def index():
    path = os.path.join(STATIC_DIR, "index.html")
    with open(path) as f:
        return f.read()
