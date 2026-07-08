"""
Run omsim to score a .solution file.
Returns dict with keys: cost, cycles, area, instructions (all int or None).
"""

import re
import resource
import subprocess
import os
import tempfile

OMSIM_PATH = os.path.join(os.path.dirname(__file__), "..", "omsim", "omsim")
PUZZLE_DIR = os.path.join(os.path.dirname(__file__), "puzzles")

# Puzzle IDs come from untrusted uploaded files and are used to build a file
# path, so restrict them to the known shape (e.g. "P008", "P030b") to prevent
# directory traversal.
PUZZLE_ID_RE = re.compile(r"P\d{3,4}[a-z]?")

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


def score_solution(puzzle_id: str, solution_bytes: bytes) -> dict:
    if not PUZZLE_ID_RE.fullmatch(puzzle_id):
        raise FileNotFoundError(f"No puzzle file for {puzzle_id!r}")
    puzzle_file = os.path.join(PUZZLE_DIR, f"{puzzle_id}.puzzle")
    if not os.path.exists(puzzle_file):
        raise FileNotFoundError(f"No puzzle file for {puzzle_id!r}")

    with tempfile.NamedTemporaryFile(suffix=".solution", delete=False) as f:
        f.write(solution_bytes)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                OMSIM_PATH,
                "--puzzle-file", puzzle_file,
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
