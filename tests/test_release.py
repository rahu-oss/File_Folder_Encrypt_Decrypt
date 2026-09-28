import hashlib
from pathlib import Path

import pytest

from scripts.build_release import validate_tag, version, write_checksum


def test_release_tag_matches_app_version() -> None:
    value = version()
    validate_tag(value, f"refs/tags/v{value}")
    validate_tag(value, "refs/heads/main")
    with pytest.raises(ValueError):
        validate_tag(value, "refs/tags/v999.0.0")


def test_release_checksum(tmp_path: Path) -> None:
    archive = tmp_path / "Vault-test.zip"
    archive.write_bytes(b"test release content")
    checksum = write_checksum(archive)
    assert checksum.read_text() == f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  Vault-test.zip\n"
