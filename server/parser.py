"""
Parse Opus Magnum .solution and .puzzle binary files.

Solution binary format (from omsp Formats.md):
  INT (4 bytes LE): solution format version (= 7)
  STRING: puzzle file name  (length as 7-bit variable-length int, then UTF-8 bytes)
  STRING: solution name
  ...

Puzzle binary format:
  INT (4 bytes LE): puzzle format version (= 3)
  STRING: puzzle name  (human-readable, e.g. "Stabilized Water")
  ...
"""

import struct


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a C# BinaryReader-style 7-bit encoded int. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, offset


def _read_string(data: bytes, offset: int) -> tuple[str, int]:
    length, offset = _read_varint(data, offset)
    return data[offset : offset + length].decode("utf-8"), offset + length


def extract_puzzle_id(data: bytes) -> str:
    """Extract the puzzle ID (e.g. 'P008') from a .solution file's bytes."""
    if len(data) < 5:
        raise ValueError("Solution file too short")
    version = struct.unpack_from("<I", data, 0)[0]
    if version != 7:
        raise ValueError(f"Unexpected solution version: {version}")
    puzzle_id, _ = _read_string(data, 4)
    return puzzle_id


def extract_puzzle_name(data: bytes) -> str:
    """Extract the human-readable name (e.g. 'Stabilized Water') from a .puzzle file's bytes."""
    if len(data) < 5:
        raise ValueError("Puzzle file too short")
    name, _ = _read_string(data, 4)
    return name


def extract_metrics(data: bytes) -> dict | None:
    """Return the solution's self-reported {cost, cycles, area, instructions}.

    These come straight from the solution header and are NOT verified by omsim;
    used as a fallback for custom puzzles that have no .puzzle file to simulate.
    Returns None if the solution is not marked solved (no metrics recorded).
    """
    if len(data) < 5:
        raise ValueError("Solution file too short")
    version = struct.unpack_from("<I", data, 0)[0]
    if version != 7:
        raise ValueError(f"Unexpected solution version: {version}")
    _, offset = _read_string(data, 4)       # puzzle id
    _, offset = _read_string(data, offset)  # solution name
    (solved,) = struct.unpack_from("<I", data, offset)
    offset += 4
    if not solved:
        return None
    # Eight uint32s: marker 0, cycles, marker 1, cost, marker 2, area, marker 3, instructions.
    _, cycles, _, cost, _, area, _, instructions = struct.unpack_from("<8I", data, offset)
    return {"cost": cost, "cycles": cycles, "area": area, "instructions": instructions}
