"""Additional filesystem and failure-path regression coverage."""
from pathlib import Path
import threading

import pytest

from vault.core import create_keyfile, decrypt, encrypt
from vault.core import crypto
from vault.core.erase import erase_original
from vault.core.format import Cancelled, VaultError


def test_existing_folder_never_merged(tmp_path: Path) -> None:
    source = tmp_path / "folder"
    source.mkdir()
    (source / "original").write_text("preserve")
    vault = tmp_path / "copy.vault"
    encrypt(source, vault, "random example passphrase")
    with pytest.raises(FileExistsError):
        decrypt(vault, tmp_path, "random example passphrase", overwrite=True)
    assert (source / "original").read_text() == "preserve"
    assert not list(tmp_path.glob(".vault-*"))


def test_key_kept_outside_source_and_output(tmp_path: Path) -> None:
    source = tmp_path / "folder"
    source.mkdir()
    key = create_keyfile(source / "key")
    with pytest.raises(VaultError):
        encrypt(source, tmp_path / "copy.vault", "password", keyfile=key)
    with pytest.raises(VaultError):
        encrypt(key, tmp_path / "copy.vault", "password", keyfile=key)
    assert key.stat().st_size == 32


def test_missing_argon_does_not_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("argon2")
    source = tmp_path / "file"
    source.write_bytes(b"content")
    vault = tmp_path / "copy.vault"
    encrypt(source, vault, "password", kdf="argon2id")
    output = tmp_path / "out"
    output.mkdir()
    monkeypatch.setattr(crypto, "hash_secret_raw", None)
    with pytest.raises(VaultError, match="Argon2"):
        decrypt(vault, output, "password")
    assert not list(output.iterdir())


def test_bad_key_length(tmp_path: Path) -> None:
    source = tmp_path / "file"
    source.touch()
    key = tmp_path / "key"
    key.write_bytes(b"short")
    with pytest.raises(VaultError, match="32 bytes"):
        encrypt(source, tmp_path / "copy.vault", "password", keyfile=key)
    assert not (tmp_path / "copy.vault").exists()


def test_erase_cancel_preserves_empty_file(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    source.touch()
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(Cancelled):
        erase_original(source, cancelled)
    assert source.exists()


def test_erase_disposable_folder(tmp_path: Path) -> None:
    folder = tmp_path / "disposable"
    folder.mkdir()
    (folder / "file").write_bytes(b"test" * 50_000)
    (folder / "empty").mkdir()
    erase_original(folder)
    assert not folder.exists()


def test_source_symlink_rejected(tmp_path: Path) -> None:
    target = tmp_path / "secret"
    target.write_bytes(b"secret")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is not permitted on this host")
    with pytest.raises(VaultError):
        encrypt(link, tmp_path / "copy.vault", "password")
    with pytest.raises(VaultError):
        erase_original(link)
    assert target.read_bytes() == b"secret"
