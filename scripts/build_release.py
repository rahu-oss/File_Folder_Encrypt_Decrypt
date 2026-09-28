"""Build an OS-native app archive and checksum for GitHub Releases."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    text = (ROOT / "vault" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.MULTILINE)
    if not match:
        raise ValueError("Set a numeric X.Y.Z version in vault/__init__.py before building.")
    return match.group(1)


def validate_tag(app_version: str, ref: str) -> None:
    if ref.startswith("refs/tags/") and ref != f"refs/tags/v{app_version}":
        raise ValueError(f"Release tag must be v{app_version}, matching vault/__init__.py.")


def write_checksum(archive: Path) -> Path:
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    output = archive.with_name(archive.name + ".sha256")
    output.write_text(f"{digest.hexdigest()}  {archive.name}\n", encoding="ascii")
    return output


def main() -> None:
    app_version = version()
    validate_tag(app_version, os.environ.get("GITHUB_REF", ""))
    system = platform.system()
    if system not in ("Windows", "Darwin", "Linux"):
        raise RuntimeError(f"Unsupported build platform: {system}")
    architecture = platform.machine().lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(architecture, architecture)
    label = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[system]
    # Separate output paths leave manually built dist/Vault.exe untouched.
    distribution = ROOT / "dist" / "github"
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--windowed",
               "--name", "Vault", "--distpath", str(distribution),
               "--workpath", str(ROOT / "build" / "github"),
               "--specpath", str(ROOT / "build" / "github-spec"),
               "--collect-all", "argon2", "--collect-all", "_argon2_cffi_bindings"]
    if system == "Darwin":
        command.extend(["--onedir", "--osx-bundle-identifier", "org.vault.desktop"])
    else:
        command.append("--onefile")
    command.append(str(ROOT / "Vault.pyw"))
    subprocess.run(command, cwd=ROOT, check=True)
    output = ROOT / "release-assets"
    output.mkdir(exist_ok=True)
    stem = f"Vault-{app_version}-{label}-{architecture}"
    if system == "Darwin":
        archive = output / f"{stem}.zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(distribution / "Vault.app"), str(archive)], check=True)
    elif system == "Windows":
        archive = output / f"{stem}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(distribution / "Vault.exe", "Vault.exe")
            bundle.write(ROOT / "README.md", "README.md")
    else:
        archive = output / f"{stem}.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(distribution / "Vault", arcname="Vault")
            bundle.add(ROOT / "README.md", arcname="README.md")
    checksum = write_checksum(archive)
    print(f"Created {archive}\nCreated {checksum}")


if __name__ == "__main__":
    main()
