# Build a single-click Vault app

Build on each target OS using Python 3.10+ with Tk installed. PyInstaller does not cross-compile Windows executables from macOS or Linux. Distribute the resulting binary to users so they do not need Python or a command line.

## Automated GitHub builds

See [GITHUB.md](GITHUB.md). The **Build desktop apps** workflow builds all three platforms after tests pass. Manual runs provide artifacts; pushing a `vX.Y.Z` tag matching `vault/__init__.py` creates a draft GitHub Release with archives and SHA-256 checksums. Review and publish the draft after testing.

To run the same packaging script locally after installing build dependencies:

```sh
python scripts/build_release.py
```

This writes the native build to `dist/github/` and the distribution archive and checksum to `release-assets/`. It leaves an existing manual `dist/Vault.exe` untouched.

## Prepare and verify

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Confirm GUI tests ran rather than skipped. Linux CI needs a display, e.g. `xvfb-run -a python -m pytest -q`.

## Windows

```sh
python -m PyInstaller --clean --noconfirm --onefile --windowed --name Vault --collect-all argon2 --collect-all _argon2_cffi_bindings Vault.pyw
```

Distribute `dist/Vault.exe`. Double-click it. No console is displayed. Build in a fresh virtual environment; sign the executable for production distribution. Windows may warn about unsigned, unfamiliar binaries.

## macOS

```sh
python -m PyInstaller --clean --noconfirm --onedir --windowed --name Vault --osx-bundle-identifier org.vault.desktop --collect-all argon2 --collect-all _argon2_cffi_bindings Vault.pyw
```

Distribute `dist/Vault.app` as a ZIP or DMG. The app bundle is a single-click application, though internally it is a directory. Sign and notarize for public distribution. Build/test the architectures you intend to support.

## Linux

```sh
python -m PyInstaller --clean --noconfirm --onefile --windowed --name Vault --collect-all argon2 --collect-all _argon2_cffi_bindings Vault.pyw
```

Distribute `dist/Vault` with a desktop launcher or installer. Build on the oldest supported distribution and test Tcl/Tk and shared-library compatibility on target systems.

## Optional drag and drop

Install `tkinterdnd2` in the build environment and add `--collect-all tkinterdnd2` to the command. Verify native TkDnD loading on every platform. Without it, the app falls back to standard Choose buttons.

## Release checks

- Launch by double-click on a clean account without Python installed.
- Verify the welcome slides and the Don't show again preference; reopen via Help.
- Lock/unlock empty, large, Unicode-named files and compressed folders; test key-file vaults.
- Confirm wrong secrets and modified/truncated vaults leave no restored output.
- Confirm overwrite approval, existing-folder refusal, cancellation, and passphrase clearing.
- Test drag and drop if bundled, keyboard traversal, resizing, high DPI, and Open containing folder.
- Test best-effort deletion **only on disposable files**; confirm the warning mentions SSDs and irreversibility.
- Check packaged Argon2 is used and no secrets appear in logs.

No signed release binaries or platform installers are committed to this source repository.
