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

            -- Pareto-optimal submissions per player per puzzle.
            -- A row is excluded when another submission from the same player is
            -- better-or-equal in every metric and either strictly better in at
            -- least one (dominated) or identical but earlier (a duplicate, e.g.
            -- from uploading the same solution twice). The latter keeps exactly
            -- one representative of each identical score tuple.
            DROP VIEW IF EXISTS best_scores;
            DROP VIEW IF EXISTS category_best;
            DROP VIEW IF EXISTS pareto_scores;
            CREATE VIEW pareto_scores AS
            SELECT
                s1.id, s1.puzzle_id, s1.nickname,
                s1.cost, s1.cycles, s1.area, s1.instructions,
                s1.cost + s1.cycles + s1.area AS score,
                s1.submitted_at
            FROM submissions s1
            WHERE NOT EXISTS (
                SELECT 1 FROM submissions s2
                WHERE s2.puzzle_id = s1.puzzle_id
                  AND s2.nickname  = s1.nickname
                  AND s2.id       != s1.id
                  AND s2.cost         <= s1.cost
                  AND s2.cycles       <= s1.cycles
                  AND s2.area         <= s1.area
                  AND s2.instructions <= s1.instructions
                  AND (   s2.cost         < s1.cost
                       OR s2.cycles       < s1.cycles
                       OR s2.area         < s1.area
                       OR s2.instructions < s1.instructions
                       OR s2.id < s1.id)
            );

            -- Category champions per player per puzzle: a submission is shown
            -- only when it holds that player's personal best (minimum) in at
            -- least one category — score, cost, cycles, area or instructions.
            -- Built on pareto_scores so it can never resurface a dominated row.
            -- Interior pareto trade-offs (best in no single category) are hidden.
            CREATE VIEW category_best AS
            SELECT p.id, p.puzzle_id, p.nickname,
                   p.cost, p.cycles, p.area, p.instructions, p.score,
                   p.submitted_at
            FROM pareto_scores p
            WHERE p.score        = (SELECT MIN(q.score)        FROM pareto_scores q WHERE q.puzzle_id = p.puzzle_id AND q.nickname = p.nickname)
               OR p.cost         = (SELECT MIN(q.cost)         FROM pareto_scores q WHERE q.puzzle_id = p.puzzle_id AND q.nickname = p.nickname)
               OR p.cycles       = (SELECT MIN(q.cycles)       FROM pareto_scores q WHERE q.puzzle_id = p.puzzle_id AND q.nickname = p.nickname)
               OR p.area         = (SELECT MIN(q.area)         FROM pareto_scores q WHERE q.puzzle_id = p.puzzle_id AND q.nickname = p.nickname)
               OR p.instructions = (SELECT MIN(q.instructions) FROM pareto_scores q WHERE q.puzzle_id = p.puzzle_id AND q.nickname = p.nickname);
        """)


def is_superseded(puzzle_id: str, nickname: str, scores: dict) -> bool:
    """Return True if the new scores add nothing for this player: some existing
    submission is better-or-equal in every metric. That covers both a strictly
    dominating submission and an exact duplicate (e.g. the same solution uploaded
    twice), so neither gets stored again."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT 1 FROM submissions
               WHERE puzzle_id = ? AND nickname = ?
                 AND cost         <= ? AND cycles       <= ?
                 AND area         <= ? AND instructions <= ?
               LIMIT 1""",
            (
                puzzle_id, nickname,
                scores["cost"], scores["cycles"], scores["area"], scores["instructions"],
            ),
        ).fetchone()
    return row is not None


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
            """SELECT puzzle_id, nickname, cost, cycles, area, instructions, score
               FROM category_best ORDER BY puzzle_id, score"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_puzzle_leaderboard(puzzle_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT puzzle_id, nickname, cost, cycles, area, instructions, score
               FROM category_best WHERE puzzle_id = ? ORDER BY score""",
            (puzzle_id,),
        ).fetchall()
    return [dict(r) for r in rows]
