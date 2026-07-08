import sqlite3
import os

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "leaderboard.db"),
)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS submissions (
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

            CREATE VIEW IF NOT EXISTS best_scores AS
            SELECT puzzle_id, nickname,
                MIN(cost) as cost,
                MIN(cycles) as cycles,
                MIN(area) as area,
                MIN(instructions) as instructions,
                MIN(cost) + MIN(cycles) + MIN(area) as score
            FROM submissions
            GROUP BY puzzle_id, nickname;
        """)


def insert_submission(puzzle_id: str, nickname: str, cost, cycles, area, instructions, blob: bytes):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO submissions (puzzle_id, nickname, cost, cycles, area, instructions, solution_blob)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (puzzle_id, nickname, cost, cycles, area, instructions, blob),
        )


def get_leaderboard() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT puzzle_id, nickname, cost, cycles, area, instructions, score FROM best_scores ORDER BY puzzle_id, score"
        ).fetchall()
    return [dict(r) for r in rows]


def get_puzzle_leaderboard(puzzle_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT puzzle_id, nickname, cost, cycles, area, instructions, score FROM best_scores WHERE puzzle_id = ? ORDER BY score",
            (puzzle_id,),
        ).fetchall()
    return [dict(r) for r in rows]
