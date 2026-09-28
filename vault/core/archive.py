"""Pack portable tar payloads and extract only ordinary files and directories."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tarfile
from typing import BinaryIO, Callable

from .format import CHUNK_SIZE, InvalidVault, VaultError

Check = Callable[[], None]


def safe_parts(name: str) -> tuple[str, ...]:
    """Reject paths dangerous on either Windows or POSIX, regardless of host."""
    path = PurePosixPath(name)
    parts = name.split("/")
    if (not name or path.is_absolute() or PureWindowsPath(name).drive
            or "\\" in name or any(p in ("", ".", "..") for p in parts)):
        raise InvalidVault("The archive contains an unsafe path.")
    for part in parts:
        if (any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved()):
            raise InvalidVault("The archive contains a non-portable filename.")
    return tuple(parts)


class CheckedReader:
    def __init__(self, stream: BinaryIO, check: Check) -> None:
        self.stream, self.check = stream, check

    def read(self, size: int = -1) -> bytes:
        self.check()
        return self.stream.read(size)


def pack(source: Path, stream: BinaryIO, compressed: bool, check: Check) -> None:
    """Do not follow links, junctions, devices, or hardlinks into other data."""
    def add(archive: tarfile.TarFile, path: Path, name: str) -> None:
        check()
        safe_parts(name)
        stat = path.lstat()
        if path.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
            raise VaultError("Links and junctions are not supported. Choose ordinary files or folders.")
        info = archive.gettarinfo(str(path), arcname=name)
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        if info.isdir():
            archive.addfile(info)
            for child in sorted(path.iterdir()):
                add(archive, child, name + "/" + child.name)
        elif info.isfile():
            with path.open("rb") as file:
                archive.addfile(info, CheckedReader(file, check))
        else:
            raise VaultError("Only ordinary files and folders can be locked.")

    with tarfile.open(fileobj=stream, mode="w:gz" if compressed else "w", dereference=True) as archive:
        add(archive, source, source.name)


def extract(stream: BinaryIO, destination: Path, folder: bool, compressed: bool,
            check: Check) -> Path:
    """Extract into a fresh private staging directory, never via tar.extractall."""
    root: str | None = None
    seen: set[str] = set()
    total = 0
    try:
        with tarfile.open(fileobj=stream, mode="r|gz" if compressed else "r|") as archive:
            for member in archive:
                check()
                parts = safe_parts(member.name.rstrip("/") if member.isdir() else member.name)
                if root is None:
                    root = parts[0]
                    if len(parts) != 1 or member.isdir() != folder:
                        raise InvalidVault("The archive type does not match its header.")
                if parts[0] != root or (not folder and seen):
                    raise InvalidVault("The archive has multiple roots.")
                normalized = "/".join(parts).casefold()
                if normalized in seen or not (member.isdir() or member.isfile()):
                    raise InvalidVault("The archive contains a duplicate, link, or special file.")
                seen.add(normalized)
                total += member.size
                # A generous fixed ceiling bounds malicious compressed archive expansion.
                if len(seen) > 1_000_000 or total > 1024**4:
                    raise InvalidVault("The archive exceeds the supported extraction limits.")
                target = destination.joinpath(*parts)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise InvalidVault("The archive contains an escaping path.")
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise InvalidVault("The archive is incomplete.")
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as output:
                        while True:
                            check()
                            chunk = source.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
        if root is None:
            raise InvalidVault("The archive is empty.")
        return destination / root
    except (tarfile.TarError, EOFError, ValueError) as exc:
        raise InvalidVault("The archive is damaged.") from exc
