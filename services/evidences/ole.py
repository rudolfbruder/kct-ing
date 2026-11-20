"""Read an OLE compound file (the old Office container, [MS-CFB]) with the standard library only.

Word stores many embedded files as OLE files (word/embeddings/oleObject1.bin). This reads the
streams inside one, so no package (olefile) is needed.

    streams = ole_streams(data)            # {"\\x01ole10native": b"...", "package": b"..."}

Names are lower case, nested ones joined with "/". Only reading, and only what is needed:
version 3 and 4 files, normal and mini streams.
"""
from __future__ import annotations

import struct
from typing import Dict, List

SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
END_OF_CHAIN, FREE = 0xFFFFFFFE, 0xFFFFFFFF
NO_STREAM = 0xFFFFFFFF
MAX_SECTORS = 1_000_000     # protects against broken files with endless chains


class OleError(ValueError):
    pass


def is_ole(data: bytes) -> bool:
    return data[:8] == SIGNATURE


def ole_streams(data: bytes) -> Dict[str, bytes]:
    """Every stream of the OLE file, by its path in lower case."""
    if not is_ole(data) or len(data) < 512:
        raise OleError("not an OLE file")
    sector_size = 1 << struct.unpack_from("<H", data, 0x1E)[0]
    mini_size = 1 << struct.unpack_from("<H", data, 0x20)[0]
    first_dir, = struct.unpack_from("<I", data, 0x30)
    cutoff, = struct.unpack_from("<I", data, 0x38)
    first_minifat, = struct.unpack_from("<I", data, 0x3C)
    first_difat, = struct.unpack_from("<I", data, 0x44)
    count_difat, = struct.unpack_from("<I", data, 0x48)

    def sector(number: int) -> bytes:
        start = (number + 1) * sector_size
        if start >= len(data):
            raise OleError("sector outside the file")
        return data[start:start + sector_size]

    # The FAT: its sectors are listed in the header (109) and in DIFAT sectors.
    fat_sectors = [n for n in struct.unpack_from("<109I", data, 0x4C) if n not in (FREE, END_OF_CHAIN)]
    difat, seen = first_difat, 0
    per = sector_size // 4 - 1
    while difat not in (FREE, END_OF_CHAIN) and seen < count_difat:
        values = struct.unpack(f"<{per + 1}I", sector(difat))
        fat_sectors += [n for n in values[:per] if n not in (FREE, END_OF_CHAIN)]
        difat, seen = values[per], seen + 1
    fat: List[int] = []
    for number in fat_sectors:
        fat += struct.unpack(f"<{sector_size // 4}I", sector(number))

    def chain(start: int, table: List[int]) -> List[int]:
        out, current = [], start
        while current not in (END_OF_CHAIN, FREE) and len(out) < MAX_SECTORS:
            if current >= len(table):
                raise OleError("broken sector chain")
            out.append(current)
            current = table[current]
        return out

    def read(start: int) -> bytes:
        return b"".join(sector(n) for n in chain(start, fat))

    directory = read(first_dir)
    entries = []
    for offset in range(0, len(directory) - 127, 128):
        raw = directory[offset:offset + 128]
        length, = struct.unpack_from("<H", raw, 0x40)
        name = raw[:max(0, length - 2)].decode("utf-16-le", errors="replace")
        kind = raw[0x42]
        left, right, child = struct.unpack_from("<III", raw, 0x44)
        start, = struct.unpack_from("<I", raw, 0x74)
        size, = struct.unpack_from("<Q", raw, 0x78)
        if sector_size == 512:
            size &= 0xFFFFFFFF
        entries.append((name, kind, left, right, child, start, size))
    if not entries:
        raise OleError("no directory")

    root = entries[0]
    mini_stream = read(root[5]) if root[5] not in (END_OF_CHAIN, FREE) else b""
    minifat: List[int] = []
    if first_minifat not in (END_OF_CHAIN, FREE):
        raw = read(first_minifat)
        minifat = list(struct.unpack(f"<{len(raw) // 4}I", raw))

    def content(start: int, size: int) -> bytes:
        if size < cutoff:
            return b"".join(mini_stream[n * mini_size:(n + 1) * mini_size] for n in chain(start, minifat))[:size]
        return read(start)[:size]

    streams: Dict[str, bytes] = {}
    visited = set()

    def walk(index: int, prefix: str) -> None:
        stack = [index]
        while stack:
            current = stack.pop()
            if current == NO_STREAM or current >= len(entries) or current in visited:
                continue
            visited.add(current)
            name, kind, left, right, child, start, size = entries[current]
            stack += [left, right]
            path = (prefix + "/" if prefix else "") + name.lower()
            if kind == 2:
                streams[path] = content(start, size)
            elif kind == 1:
                walk(child, path)

    walk(root[4], "")
    return streams
