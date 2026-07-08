import os
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from db import init_db, insert_submission, get_leaderboard, get_puzzle_leaderboard
from parser import extract_puzzle_id
from scorer import score_solution

app = FastAPI(title="Opus Magnum Leaderboard")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.on_event("startup")
def startup():
    init_db()


@app.post("/api/submit")
async def submit(file: UploadFile = File(...), nickname: str = Form(...)):
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

    insert_submission(
        puzzle_id,
        nickname,
        scores["cost"],
        scores["cycles"],
        scores["area"],
        scores["instructions"],
        data,
    )

    cost, cycles, area = scores["cost"], scores["cycles"], scores["area"]
    score = (cost + cycles + area) if None not in (cost, cycles, area) else None
    return {"puzzle_id": puzzle_id, **scores, "score": score}


@app.get("/api/leaderboard")
def leaderboard():
    return get_leaderboard()


@app.get("/api/leaderboard/{puzzle_id}")
def leaderboard_puzzle(puzzle_id: str):
    rows = get_puzzle_leaderboard(puzzle_id)
    if not rows:
        raise HTTPException(404, f"No submissions for {puzzle_id!r}")
    return rows


@app.get("/", response_class=HTMLResponse)
def index():
    path = os.path.join(STATIC_DIR, "index.html")
    with open(path) as f:
        return f.read()
