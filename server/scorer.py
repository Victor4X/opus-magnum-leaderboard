"""
Run omsim to score a .solution file.
Returns dict with keys: cost, cycles, area, instructions (all int or None).
"""

import resource
import subprocess
import os
import tempfile
from pathlib import Path

from parser import extract_metrics

OMSIM_PATH = os.path.join(os.path.dirname(__file__), "..", "omsim", "omsim")
# Resolved once so the traversal check below compares against a canonical base.
PUZZLE_DIR = Path(__file__).resolve().parent / "puzzles"

# omsim is C code processing untrusted input; bound its resource use so a
# malicious solution can only crash its own subprocess, not exhaust the host.
CPU_LIMIT_SECONDS = 30
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB address space


def _sandbox():
    resource.setrlimit(
        resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS + 1)
    )
    resource.setrlimit(
        resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES)
    )


def _puzzle_file(puzzle_id: str) -> Path | None:
    """Resolve the .puzzle path for an untrusted puzzle id.

    The id is embedded in an uploaded file, so confine the result to PUZZLE_DIR:
    resolve the candidate and verify it stays inside the directory, rejecting
    traversal (`../`, absolute paths, ...). Returns None when the id is clean
    but has no puzzle file on disk (a custom puzzle).
    """
    candidate = (PUZZLE_DIR / f"{puzzle_id}.puzzle").resolve()
    if not candidate.is_relative_to(PUZZLE_DIR):
        raise FileNotFoundError(f"Invalid puzzle id {puzzle_id!r}")
    return candidate if candidate.is_file() else None


def score_solution(puzzle_id: str, solution_bytes: bytes) -> dict:
    puzzle_file = _puzzle_file(puzzle_id)
    if puzzle_file is None:
        # Custom puzzles have no .puzzle file, so omsim can't simulate them.
        # Fall back to the metrics the solution reports about itself — these are
        # NOT verified by the simulator, but enough to list it on the board.
        metrics = extract_metrics(solution_bytes)
        if metrics is None:
            raise RuntimeError("solution is not marked solved")
        return metrics

    with tempfile.NamedTemporaryFile(suffix=".solution", delete=False) as f:
        f.write(solution_bytes)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                OMSIM_PATH,
                "--puzzle-file", str(puzzle_file),
                "--metric", "cost",
                "--metric", "cycles",
                "--metric", "area",
                "--metric", "instructions",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            preexec_fn=_sandbox,
        )
    finally:
        os.unlink(tmp_path)

    if result.returncode != 0:
        raise RuntimeError(f"omsim failed: {result.stderr.strip()}")

    return _parse_output(result.stdout)


def _parse_output(output: str) -> dict:
    """Parse omsim key: value output lines."""
    scores = {"cost": None, "cycles": None, "area": None, "instructions": None}
    for line in output.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            if key in scores:
                try:
                    scores[key] = int(val.strip())
                except ValueError:
                    pass
    return scores
