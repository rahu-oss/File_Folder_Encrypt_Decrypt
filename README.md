# Vault

A guided desktop app for locking and unlocking files and folders. Python 3.10+, Tkinter/ttk, AES-256-GCM, and optional key files. Everything a regular user needs is inside the app.

**Publishing on GitHub?** Follow [GITHUB.md](GITHUB.md) to upload the repository, run automated desktop builds, and publish downloadable apps through GitHub Releases.

**No recovery:** forgotten passphrases or missing key files mean the data cannot be recovered. Always test unlocking before deleting originals.

## For everyday users

Download the archive for your operating system from this repository's **Releases** section when a release is available. Extract it, then open **Vault.exe** on Windows or **Vault.app** on macOS. No terminal or Python installation is needed for a packaged release. Binaries are attached to releases rather than committed with the source; maintainers can create them with GitHub Actions or [build.md](build.md).

1. **Lock:** choose a file or folder, create and confirm a passphrase, optionally add a key file, and choose where to save. Select **Lock Now**.
2. **Unlock:** choose the `.vault` file, enter your passphrase, supply the original key file if requested, and choose an output folder. Select **Unlock Now**.
3. **Check:** open the restored copy and verify its contents before deleting the original. Back up your vault and key file separately.

Use four or more random, unrelated words. The strength meter offers guidance, not a security guarantee. The app warns about passphrases shorter than 12 characters. Spaces and capitalization matter.

Existing files require explicit confirmation before replacement. Existing folders are never merged or replaced: choose another output folder. Key generation always requires a new filename to avoid destroying a key needed by other vaults.

The welcome tutorial and **Help** tab explain every step. Progress, cancellation, inline validation, keyboard navigation, and tooltips are built in. File and folder sizes are calculated in the background. Folder compression is optional. Drag and drop is optional; the Choose buttons work without it.

## Screenshots

_Screenshot placeholder: Lock tab with four guided steps, strength meter, and key-file warning._

_Screenshot placeholder: Unlock tab showing file/folder type and whether a key file is required._

_Screenshot placeholder: Quick Start and safety checklist in Help._

## Developer installation

Install Python 3.10 or newer with Tk support. Windows and macOS python.org installers normally include Tk. Linux may need the distribution's `python3-tk` package. In this project directory:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m vault
```

On Windows, `py` can replace `python` when using the Python launcher. Once dependencies are installed in the associated Python interpreter, `Vault.pyw` is a double-click launcher. Packaged apps are the preferred distribution for non-technical users.

Optional drag and drop:

```sh
python -m pip install tkinterdnd2
```

Optional CLI (passphrases are prompted privately and never supplied as command-line arguments):

```sh
python -m vault.cli lock document.pdf document.pdf.vault
python -m vault.cli keygen personal.key
python -m vault.cli lock photos photos.vault --key-file personal.key --compress
python -m vault.cli unlock photos.vault restored --key-file personal.key
```

The unlock destination must be an existing directory. `--overwrite` explicitly authorizes file replacement; it does not replace folders. CLI actions call the same core as the GUI.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Core coverage includes empty/boundary/large files, folders, Unicode names, both KDFs, key files, corruption, truncation, record reordering, unsafe archives, cancellation, atomic no-clobber file publication, and strength guidance. GUI tests construct a withdrawn window, check validation, exercise header previews and worker completion, and verify passphrase clearing. They skip only if Tcl/Tk or a display is unavailable. On headless Linux, run `xvfb-run -a python -m pytest` to exercise them.

## Security design and threat model

Vault protects a copied vault file from someone who lacks the passphrase and required key file. It detects ciphertext changes, missing records, reordered records, and trailing data. It does not protect against malware, a hostile administrator, a compromised running account, weak/known passphrases, or an attacker reading unlocked copies.

Cryptographic primitives come from `cryptography`; Argon2id is supplied by `argon2-cffi`. There are no homemade cryptographic primitives. The application-specific container format has not received an independent security audit.

- AES-256-GCM encrypts records of at most 65,536 bytes with 16-byte tags.
- Every encryption uses a fresh 16-byte random salt and 12-byte random nonce base.
- Argon2id uses 64 MiB, 3 iterations, 4 lanes, a 32-byte result, and Argon2 version 19. When unavailable for encryption, PBKDF2-HMAC-SHA256 with 600,000 iterations is recorded instead. Unlocking an Argon2 vault still requires Argon2; it never silently substitutes another KDF.
- A key file contains 32 random bytes. When enabled, HKDF-SHA256 combines the derived passphrase key and those bytes with the salt and a fixed context string.
- Every record authenticates the complete header, its 64-bit index, plaintext length, and final flag as AAD. Record nonces are the random 96-bit base XOR the record index. The 32-bit record-count bound prevents within-vault reuse. An empty authenticated final record is mandatory, with no trailing data allowed.
- The cleartext header contains `VAULT1`, format version, KDF settings, key-file flag, payload type, compression flag, salt, and nonce. Parameter bounds are checked before key derivation to limit untrusted resource use. Header previews are not trusted until authentication succeeds.
- Names and tar metadata are encrypted. The suggested **external** filename includes the original name; choose a neutral name if that matters. File/folder type, key-file use, compression, and approximate size remain visible.
- Tar extraction accepts only ordinary files and directories under a single root. It rejects absolute paths, traversal, links (including internal symlinks), special files, duplicate/case-colliding paths, Windows drive/UNC paths, and non-portable names. Limits are one million entries and 1 TiB of declared expanded data. Disk capacity can be a tighter limit.
- Temporary output is created on the destination filesystem and published only after completion. Ordinary files use an atomic hard link for no-clobber creation or atomic replace after approval. Folder restoration uses same-filesystem rename into a new name. Filesystems without hard-link support may reject non-overwriting publication safely; choose NTFS/APFS/ext4 or another supporting filesystem.

## Limitations and local data

- **Temporary plaintext:** packing and authenticated decryption use private temporary storage. No final plaintext output is published until the whole vault authenticates. Normal failures and cancellation remove staging data; crashes or power loss may leave temporary data. Use full-disk encryption. There is no guaranteed forensic deletion.
- **Original deletion:** the optional action makes one zero overwrite and removes ordinary files, only after a separate irreversible-action confirmation following successful locking. It rejects links and hardlinks. SSD wear leveling, snapshots, journals, cloud synchronization, and backups can preserve copies. Cancelling or failing mid-deletion can leave originals partially erased. The encrypted vault remains intact.
- **Source consistency:** do not edit or replace source files during encryption or deletion. Vault does not take filesystem snapshots and is not designed for hostile simultaneous filesystem changes.
- **Permissions:** key files and restored files request mode `0600`; staging directories request private permissions. On Windows, Unix mode bits do not establish a private ACL: keep data under your private user profile and manage Windows folder permissions. Restored files do not preserve original ownership, ACLs, or extended attributes.
- **Memory:** Python cannot guarantee erasing all passphrase/key copies in memory. Visible passphrase fields are cleared after each operation and on tab changes. Cancellation is checked between chunks and archive reads; key derivation cannot be interrupted mid-call.
- **Platform validation:** code is designed for Windows, macOS, and Linux. Platform-specific packaging and real user workflows should be verified on each target OS before release.
- **Logs:** bounded rotating local logs contain exception class and source function/line locations only, not exception messages, user paths, plaintext, passphrases, or keys. Settings store only the welcome preference. Windows: `%LOCALAPPDATA%\Vault`; macOS: `~/Library/Application Support/Vault`; Linux: `$XDG_STATE_HOME/vault` or `~/.local/state/vault`.

## Project map

```text
vault/
  core/       crypto.py, format.py, archive.py, passphrase.py, erase.py
  gui/        app.py, lock_tab.py, unlock_tab.py, help_tab.py,
              widgets.py, help_text.py, welcome.py
  cli.py      optional wrapper
  __main__.py default GUI launcher
tests/        core and withdrawn-window GUI tests
Vault.pyw     double-click source/packaging entry point
```

Primitive references: [cryptography AESGCM documentation](https://cryptography.io/en/latest/hazmat/primitives/aead/) and [argon2-cffi API](https://argon2-cffi.readthedocs.io/en/25.1.0/api.html).
