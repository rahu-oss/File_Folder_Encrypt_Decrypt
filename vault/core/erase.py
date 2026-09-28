"""Explicitly requested best-effort deletion; never a guarantee of sanitization."""
from __future__ import annotations

import os
from pathlib import Path
from threading import Event

from .format import CHUNK_SIZE, Cancelled, VaultError


def erase_original(source: Path, cancel: Event | None = None) -> Path:
    """Refuse links and hardlinked files; cancellation may leave partial erasure."""
    files: list[Path] = []
    directories: list[Path] = []

    def collect(path: Path) -> None:
        if cancel and cancel.is_set():
            raise Cancelled("Deletion cancelled before erasing the next item.")
        stat = path.lstat()
        if path.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
            raise VaultError("Links or junctions cannot be securely deleted.")
        if path.is_dir():
            directories.append(path)
            for child in path.iterdir():
                collect(child)
        elif path.is_file() and stat.st_nlink == 1:
            files.append(path)
        else:
            raise VaultError("Only ordinary files without hardlinks can be securely deleted.")

    collect(source)
    for path in files:
        if cancel and cancel.is_set():
            raise Cancelled("Deletion stopped. Some original data may already have been erased.")
        with path.open("r+b", buffering=0) as stream:
            remaining = os.fstat(stream.fileno()).st_size
            while remaining:
                if cancel and cancel.is_set():
                    raise Cancelled("Deletion stopped. Some original data may already have been erased.")
                length = min(CHUNK_SIZE, remaining)
                stream.write(b"\0" * length)
                remaining -= length
            os.fsync(stream.fileno())
        path.unlink()
    for path in reversed(directories):
        if cancel and cancel.is_set():
            raise Cancelled("Deletion stopped. Some original data may already have been erased.")
        path.rmdir()
    return source.parent
