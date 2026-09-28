"""AES-256-GCM records, password derivation, and atomic publication."""
from __future__ import annotations

import os
from pathlib import Path
import struct
import tempfile
from threading import Event
from typing import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    from argon2.low_level import Type, hash_secret_raw
except ImportError:
    hash_secret_raw = None

from . import archive
from .format import (ARGON2ID, PBKDF2, FILE, FOLDER, CHUNK_SIZE, RECORD,
                     Header, InvalidVault, VaultError, Cancelled, read_header, chunk_nonce)

Progress = Callable[[float, str], None]


def _check(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("Operation cancelled. Your original is unchanged.")


def _key(header: Header, passphrase: str, keyfile: Path | str | None) -> bytes:
    if not passphrase:
        raise VaultError("Enter a passphrase.")
    extra = b""
    if header.keyfile:
        if keyfile is None:
            raise VaultError("This vault also requires its key file.")
        with open(keyfile, "rb") as stream:
            extra = stream.read(33)
        if len(extra) != 32:
            raise VaultError("Choose a Vault key file containing exactly 32 bytes.")
    elif keyfile is not None:
        raise VaultError("This vault does not use a key file.")
    secret = passphrase.encode("utf-8")
    if header.kdf == ARGON2ID:
        if hash_secret_raw is None:
            raise VaultError("This vault needs Argon2 support. Install argon2-cffi or use the full Vault app.")
        key = hash_secret_raw(secret, header.salt, header.work, header.memory,
                              header.lanes, 32, Type.ID)
    else:
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                        salt=header.salt, iterations=header.work).derive(secret)
    if header.keyfile:
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=header.salt,
                   info=b"VAULT1/keyfile/AES-256-GCM").derive(key + extra)
    return key


def _publish(staged: Path, target: Path, overwrite: bool) -> None:
    if target.is_symlink() or target.is_dir():
        raise FileExistsError("Choose a new name; existing folders and links cannot be replaced.")
    if overwrite:
        os.replace(staged, target)
    elif staged.is_file():
        # Atomic no-clobber publication, including a destination created mid-operation.
        os.link(staged, target)
        staged.unlink()
    else:
        if target.exists():
            raise FileExistsError("An output with this name already exists.")
        # rename is atomic on the same filesystem; the source is a complete directory.
        os.rename(staged, target)


def create_keyfile(path: Path | str, *, overwrite: bool = False) -> Path:
    target = Path(path).absolute()
    fd, name = tempfile.mkstemp(prefix=".vault-key-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(os.urandom(32))
            stream.flush()
            os.fsync(stream.fileno())
        _publish(temporary, target, overwrite)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def encrypt(source: Path | str, destination: Path | str, passphrase: str, *,
            keyfile: Path | str | None = None, compress: bool = False,
            overwrite: bool = False, cancel: Event | None = None,
            progress: Progress | None = None, kdf: str = "auto") -> Path:
    source, target = Path(source).absolute(), Path(destination).absolute()
    notify = progress or (lambda percent, message: None)
    check = lambda: _check(cancel)
    if source.is_symlink() or not source.exists():
        raise VaultError("Choose an existing ordinary file or folder.")
    if target.resolve() == source.resolve() or (source.is_dir() and target.resolve().is_relative_to(source.resolve())):
        raise VaultError("Save the vault outside the original folder and use a different filename.")
    if keyfile and (source.resolve() == Path(keyfile).resolve() or target.resolve() == Path(keyfile).resolve()
                    or (source.is_dir() and Path(keyfile).resolve().is_relative_to(source.resolve()))):
        raise VaultError("Keep your key file separate from the folder and output you are locking.")
    if target.exists() and not overwrite:
        raise FileExistsError("The output already exists.")
    if kdf not in ("auto", "argon2id", "pbkdf2"):
        raise ValueError("Unknown KDF")
    use_argon = kdf == "argon2id" or (kdf == "auto" and hash_secret_raw is not None)
    header = Header(ARGON2ID if use_argon else PBKDF2, keyfile is not None,
                    FOLDER if source.is_dir() else FILE, bool(compress and source.is_dir()),
                    3 if use_argon else 600_000, 65536 if use_argon else 0,
                    4 if use_argon else 0, os.urandom(16), os.urandom(12))
    check()
    notify(0, "Preparing your encryption key…")
    cipher = AESGCM(_key(header, passphrase, keyfile))
    check()
    raw = header.encode()
    # Private staging is cleaned on every normal failure or cancellation.
    with tempfile.TemporaryDirectory(prefix=".vault-lock-", dir=target.parent) as work:
        staged = Path(work) / "locked"
        with tempfile.TemporaryFile(dir=work) as payload:
            notify(0, "Preparing files…")
            archive.pack(source, payload, header.compressed, check)
            size = payload.tell()
            payload.seek(0)
            with staged.open("xb") as output:
                os.chmod(staged, 0o600)
                output.write(raw)
                counter = 0
                while True:
                    check()
                    chunk = payload.read(CHUNK_SIZE)
                    # An explicit empty final record authenticates completion, even at boundaries.
                    final = int(not chunk)
                    record = RECORD.pack(len(chunk), final)
                    aad = raw + struct.pack(">Q", counter) + record
                    output.write(record)
                    output.write(cipher.encrypt(chunk_nonce(header.nonce, counter), chunk, aad))
                    notify(min(99, payload.tell() / max(size, 1) * 99), "Locking your files…")
                    counter += 1
                    if final:
                        break
                output.flush()
                os.fsync(output.fileno())
        check()
        _publish(staged, target, overwrite)
    notify(100, "Locked successfully.")
    return target


def decrypt(source: Path | str, output_directory: Path | str, passphrase: str, *,
            keyfile: Path | str | None = None, overwrite: bool = False,
            cancel: Event | None = None, progress: Progress | None = None,
            confirm_overwrite: Callable[[Path], bool] | None = None) -> Path:
    source, destination = Path(source).absolute(), Path(output_directory).absolute()
    notify = progress or (lambda percent, message: None)
    check = lambda: _check(cancel)
    if not destination.is_dir():
        raise VaultError("Choose an existing output folder.")
    check()
    with source.open("rb") as input_file, tempfile.TemporaryDirectory(prefix=".vault-unlock-", dir=destination) as work:
        header, raw = read_header(input_file)
        notify(0, "Preparing your decryption key…")
        cipher = AESGCM(_key(header, passphrase, keyfile))
        size = os.fstat(input_file.fileno()).st_size
        with tempfile.TemporaryFile(dir=work) as payload:
            counter = 0
            try:
                while True:
                    check()
                    record = input_file.read(RECORD.size)
                    if len(record) != RECORD.size:
                        raise InvalidVault("The vault is truncated.")
                    length, final = RECORD.unpack(record)
                    if length > CHUNK_SIZE or final not in (0, 1) or (final and length) or (not final and not length):
                        raise InvalidVault("The vault contains an invalid record.")
                    encrypted = input_file.read(length + 16)
                    if len(encrypted) != length + 16:
                        raise InvalidVault("The vault is truncated.")
                    aad = raw + struct.pack(">Q", counter) + record
                    chunk = cipher.decrypt(chunk_nonce(header.nonce, counter), encrypted, aad)
                    payload.write(chunk)
                    counter += 1
                    notify(min(90, input_file.tell() / max(size, 1) * 90), "Checking and unlocking…")
                    if final:
                        if input_file.read(1):
                            raise InvalidVault("The vault has unexpected trailing data.")
                        break
            except InvalidTag as exc:
                raise InvalidVault("Wrong passphrase or key file, or the file was changed.") from exc
            check()
            payload.seek(0)
            notify(95, "Restoring your files…")
            staged = archive.extract(payload, Path(work), header.payload == FOLDER, header.compressed, check)
        target = destination / staged.name
        if target.resolve() == source.resolve() or (keyfile and target.resolve() == Path(keyfile).resolve()):
            raise VaultError("Choose another output folder to protect your vault and key file.")
        if target.exists() and not overwrite and target.is_file() and not target.is_symlink() and confirm_overwrite:
            overwrite = confirm_overwrite(target)
        check()
        _publish(staged, target, overwrite)
    notify(100, "Unlocked successfully.")
    return target
