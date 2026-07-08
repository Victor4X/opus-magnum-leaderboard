"""
Parse Opus Magnum .solution binary files to extract the puzzle ID.

Binary format (from omsp Formats.md):
  INT (4 bytes LE): solution format version (= 7)
  STRING: puzzle file name  (length as 7-bit variable-length int, then UTF-8 bytes)
  STRING: solution name
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


def extract_puzzle_id(data: bytes) -> str:
    """Extract the puzzle ID (e.g. 'P008') from a .solution file's bytes."""
    if len(data) < 5:
        raise ValueError("Solution file too short")
    version = struct.unpack_from("<I", data, 0)[0]
    if version != 7:
        raise ValueError(f"Unexpected solution version: {version}")
    length, idx = _read_varint(data, 4)
    puzzle_id = data[idx : idx + length].decode("utf-8")
    return puzzle_id
