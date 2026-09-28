from __future__ import annotations

import io
import os
from pathlib import Path
import tarfile
import threading

import pytest

from vault.core import create_keyfile, decrypt, encrypt
from vault.core import crypto
from vault.core.archive import extract, safe_parts
from vault.core.format import (ARGON2ID, PBKDF2, CHUNK_SIZE, HEADER, RECORD, Cancelled,
                               Header, InvalidVault, VaultError, inspect_header, chunk_nonce, read_header)
from vault.core.passphrase import strength

PASSWORD = "cobalt lantern river meadow"


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "private.txt"
    source.write_bytes(b"secret contents\x00\xff")
    output = tmp_path / "restored"
    output.mkdir()
    return source, tmp_path / "locked.vault", output


@pytest.mark.parametrize("size", [0, 1, CHUNK_SIZE - 1, CHUNK_SIZE, CHUNK_SIZE + 1, 3 * 1024 * 1024])
def test_roundtrip(paths: tuple[Path, Path, Path], size: int) -> None:
    source, vault, output = paths
    content = os.urandom(size)
    source.write_bytes(content)
    encrypt(source, vault, PASSWORD)
    restored = decrypt(vault, output, PASSWORD)
    assert restored.name == source.name
    assert restored.read_bytes() == content
    assert source.read_bytes() == content
    assert source.name.encode() not in vault.read_bytes()


@pytest.mark.parametrize("compress", [False, True])
def test_folder_roundtrip(paths: tuple[Path, Path, Path], compress: bool) -> None:
    source, vault, output = paths
    source.unlink()
    source.mkdir()
    (source / "empty").mkdir()
    (source / "nested").mkdir()
    (source / "nested" / "世界.txt").write_text("hello 🌍", encoding="utf-8")
    (source / "zero").touch()
    encrypt(source, vault, PASSWORD, compress=compress)
    restored = decrypt(vault, output, PASSWORD)
    assert (restored / "empty").is_dir()
    assert (restored / "nested" / "世界.txt").read_text(encoding="utf-8") == "hello 🌍"
    assert (restored / "zero").read_bytes() == b""


def test_empty_folder(paths: tuple[Path, Path, Path]) -> None:
    source, vault, output = paths
    source.unlink()
    source.mkdir()
    encrypt(source, vault, PASSWORD)
    assert list(decrypt(vault, output, PASSWORD).iterdir()) == []


def test_wrong_passphrase_no_output(paths: tuple[Path, Path, Path]) -> None:
    source, vault, output = paths
    encrypt(source, vault, PASSWORD)
    with pytest.raises(InvalidVault):
        decrypt(vault, output, "incorrect")
    assert list(output.iterdir()) == []


def test_keyfiles(paths: tuple[Path, Path, Path], tmp_path: Path) -> None:
    source, vault, output = paths
    key = create_keyfile(tmp_path / "secret.key")
    wrong = create_keyfile(tmp_path / "other.key")
    assert key.stat().st_size == 32
    assert key.read_bytes() != wrong.read_bytes()
    if os.name != "nt":
        assert key.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        create_keyfile(key)
    encrypt(source, vault, PASSWORD, keyfile=key)
    assert inspect_header(vault).keyfile
    with pytest.raises(VaultError):
        decrypt(vault, output, PASSWORD)
    with pytest.raises(InvalidVault):
        decrypt(vault, output, PASSWORD, keyfile=wrong)
    assert list(output.iterdir()) == []
    assert decrypt(vault, output, PASSWORD, keyfile=key).read_bytes() == source.read_bytes()


@pytest.mark.parametrize("mutation", ["header", "ciphertext", "truncate", "remove-final", "append", "final-flag", "record-length", "swap"])
def test_tampering(paths: tuple[Path, Path, Path], mutation: str) -> None:
    source, vault, output = paths
    source.write_bytes(os.urandom(CHUNK_SIZE * 3))
    encrypt(source, vault, PASSWORD)
    data = bytearray(vault.read_bytes())
    if mutation == "header":
        data[HEADER.size - 15] ^= 1
    elif mutation == "ciphertext":
        data[HEADER.size + RECORD.size + 12] ^= 1
    elif mutation == "truncate":
        del data[-4:]
    elif mutation == "remove-final":
        del data[-(RECORD.size + 16):]
    elif mutation == "append":
        data.extend(b"extra")
    elif mutation == "final-flag":
        data[-17] = 0
    elif mutation == "record-length":
        data[HEADER.size:HEADER.size + 4] = b"\xff" * 4
    else:
        width = CHUNK_SIZE + RECORD.size + 16
        start = HEADER.size
        first, second = data[start:start+width], data[start+width:start+2*width]
        data[start:start+2*width] = second + first
    vault.write_bytes(data)
    with pytest.raises(InvalidVault):
        decrypt(vault, output, PASSWORD)
    assert list(output.iterdir()) == []


def test_randomized_ciphertext(paths: tuple[Path, Path, Path], tmp_path: Path) -> None:
    source, vault, _ = paths
    another = tmp_path / "second.vault"
    encrypt(source, vault, PASSWORD)
    encrypt(source, another, PASSWORD)
    assert vault.read_bytes() != another.read_bytes()
    assert inspect_header(vault).nonce != inspect_header(another).nonce
    assert inspect_header(vault).salt != inspect_header(another).salt


def test_pbkdf_fallback(paths: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    source, vault, output = paths
    monkeypatch.setattr(crypto, "hash_secret_raw", None)
    encrypt(source, vault, PASSWORD)
    assert inspect_header(vault).kdf == PBKDF2
    assert inspect_header(vault).work >= 600_000
    assert decrypt(vault, output, PASSWORD).read_bytes() == source.read_bytes()


def test_argon2(paths: tuple[Path, Path, Path]) -> None:
    pytest.importorskip("argon2")
    source, vault, output = paths
    encrypt(source, vault, PASSWORD, kdf="argon2id")
    assert inspect_header(vault).kdf == ARGON2ID
    decrypt(vault, output, PASSWORD)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "C:/escape", "C:escape", "a\\..\\escape", "//server/share", "a//b", "a/./b", "a/NUL.txt", "a/file:stream", "a/name."])
def test_unsafe_names(name: str) -> None:
    with pytest.raises(InvalidVault):
        safe_parts(name)


@pytest.mark.parametrize("kind", ["traversal", "symlink", "hardlink", "device", "duplicate"])
def test_unsafe_archive(tmp_path: Path, kind: str) -> None:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as tar:
        root = tarfile.TarInfo("folder")
        root.type = tarfile.DIRTYPE
        tar.addfile(root)
        item = tarfile.TarInfo("../escape" if kind == "traversal" else "folder/item")
        if kind in ("symlink", "hardlink"):
            item.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
            item.linkname = "../../escape"
        elif kind == "device":
            item.type = tarfile.CHRTYPE
        tar.addfile(item)
        if kind == "duplicate":
            tar.addfile(item)
    payload.seek(0)
    with pytest.raises(InvalidVault):
        extract(payload, tmp_path, True, False, lambda: None)
    assert not (tmp_path.parent / "escape").exists()


def test_overwrite(paths: tuple[Path, Path, Path]) -> None:
    source, vault, output = paths
    encrypt(source, vault, PASSWORD)
    old = vault.read_bytes()
    with pytest.raises(FileExistsError):
        encrypt(source, vault, PASSWORD)
    assert vault.read_bytes() == old
    target = output / source.name
    target.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        decrypt(vault, output, PASSWORD)
    assert target.read_bytes() == b"keep me"
    with pytest.raises(InvalidVault):
        decrypt(vault, output, "wrong", overwrite=True)
    assert target.read_bytes() == b"keep me"
    calls: list[Path] = []
    decrypt(vault, output, PASSWORD, confirm_overwrite=lambda path: calls.append(path) or True)
    assert calls == [target]
    assert target.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("operation", ["lock", "unlock"])
def test_cancel_cleanup(paths: tuple[Path, Path, Path], operation: str) -> None:
    source, vault, output = paths
    source.write_bytes(os.urandom(CHUNK_SIZE * 4))
    event = threading.Event()
    def progress(percent: float, message: str) -> None:
        if percent > 0:
            event.set()
    if operation == "lock":
        with pytest.raises(Cancelled):
            encrypt(source, vault, PASSWORD, cancel=event, progress=progress)
        assert not vault.exists()
    else:
        encrypt(source, vault, PASSWORD)
        with pytest.raises(Cancelled):
            decrypt(vault, output, PASSWORD, cancel=event, progress=progress)
        assert list(output.iterdir()) == []
    assert not list(source.parent.glob(".vault-*"))


def test_bad_cost_rejected_before_kdf() -> None:
    bad = Header(ARGON2ID, False, 1, False, 2**31, 2**31, 4, b"s"*16, b"n"*12)
    with pytest.raises(InvalidVault):
        read_header(io.BytesIO(bad.encode()))


def test_nonce_uniqueness() -> None:
    base = os.urandom(12)
    assert len({chunk_nonce(base, counter) for counter in range(10_000)}) == 10_000
    with pytest.raises(InvalidVault):
        chunk_nonce(base, 2**32)


@pytest.mark.parametrize("value,label", [("", "Weak"), ("short", "Weak"), ("a"*40, "Weak"), ("twelve_chars!", "Okay"), (PASSWORD, "Strong")])
def test_strength(value: str, label: str) -> None:
    assert strength(value).label == label


def test_unsafe_save_location(paths: tuple[Path, Path, Path]) -> None:
    source, _, _ = paths
    with pytest.raises(VaultError):
        encrypt(source, source, PASSWORD, overwrite=True)
    source.unlink()
    source.mkdir()
    with pytest.raises(VaultError):
        encrypt(source, source / "copy.vault", PASSWORD)


def test_publish_race_preserves_file(paths: tuple[Path, Path, Path]) -> None:
    source, vault, _ = paths
    def progress(percent: float, message: str) -> None:
        if percent > 0 and not vault.exists():
            vault.write_bytes(b"created during encryption")
    with pytest.raises(FileExistsError):
        encrypt(source, vault, PASSWORD, progress=progress)
    assert vault.read_bytes() == b"created during encryption"
