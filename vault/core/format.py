"""Bounded binary format. All header bytes are authenticated by every record."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import BinaryIO

MAGIC = b"VAULT1"
VERSION = 1
ARGON2ID, PBKDF2 = 1, 2
FILE, FOLDER = 1, 2
CHUNK_SIZE = 64 * 1024
# magic, version, kdf, key flag, type, compression, work, memory, lanes, salt, nonce
HEADER = struct.Struct(">6sBBBBBIII16s12s")
RECORD = struct.Struct(">IB")  # plaintext length, final flag
MAX_CHUNKS = 2**32


class VaultError(Exception):
    """An error safe to translate into a friendly UI message."""


class InvalidVault(VaultError):
    """Unsupported, malformed, or unauthenticated vault."""


class Cancelled(VaultError):
    """The user cancelled before publication."""


@dataclass(frozen=True)
class Header:
    kdf: int
    keyfile: bool
    payload: int
    compressed: bool
    work: int
    memory: int
    lanes: int
    salt: bytes
    nonce: bytes

    def encode(self) -> bytes:
        return HEADER.pack(MAGIC, VERSION, self.kdf, self.keyfile, self.payload,
                           self.compressed, self.work, self.memory, self.lanes,
                           self.salt, self.nonce)


def read_header(stream: BinaryIO) -> tuple[Header, bytes]:
    raw = stream.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise InvalidVault("The vault header is incomplete.")
    magic, version, kdf, key, payload, comp, work, memory, lanes, salt, nonce = HEADER.unpack(raw)
    if (magic != MAGIC or version != VERSION or key not in (0, 1)
            or payload not in (FILE, FOLDER) or comp not in (0, 1)
            or (payload == FILE and comp)):
        raise InvalidVault("This is not a supported Vault file.")
    # Bound untrusted KDF costs before deriving a key (resource exhaustion defense).
    if kdf == ARGON2ID:
        valid = 1 <= work <= 6 and 8192 <= memory <= 262144 and 1 <= lanes <= 8
    elif kdf == PBKDF2:
        valid = 600_000 <= work <= 2_000_000 and memory == 0 and lanes == 0
    else:
        valid = False
    if not valid:
        raise InvalidVault("The vault uses unsupported key settings.")
    return Header(kdf, bool(key), payload, bool(comp), work, memory, lanes, salt, nonce), raw


def inspect_header(path: Path | str) -> Header:
    """Preview only: these fields are untrusted until a successful unlock."""
    with open(path, "rb") as stream:
        return read_header(stream)[0]


def chunk_nonce(base: bytes, counter: int) -> bytes:
    if not 0 <= counter < MAX_CHUNKS:
        raise InvalidVault("The vault exceeds the supported size.")
    # A bijection for a fixed random base; no nonce repeats within a vault.
    return (int.from_bytes(base, "big") ^ counter).to_bytes(12, "big")
