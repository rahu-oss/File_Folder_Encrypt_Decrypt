"""Optional thin CLI. The default entry point remains the GUI."""
from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

from vault.core import create_keyfile, decrypt, encrypt
from vault.core.format import VaultError


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault — optional command-line interface")
    parser.add_argument("action", choices=["lock", "unlock", "keygen"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--compress", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly allow replacing an existing file")
    args = parser.parse_args()
    try:
        if args.action == "keygen":
            result = create_keyfile(args.source)
        else:
            if args.destination is None:
                parser.error("lock and unlock require a destination (unlock takes an existing folder)")
            password = getpass("Passphrase: ")
            if args.action == "lock":
                if password != getpass("Confirm passphrase: "):
                    parser.error("Passphrases don't match")
                result = encrypt(args.source, args.destination, password, keyfile=args.key_file,
                                 compress=args.compress, overwrite=args.overwrite)
            else:
                result = decrypt(args.source, args.destination, password, keyfile=args.key_file, overwrite=args.overwrite)
        print(f"Saved: {result}")
    except (VaultError, OSError) as exc:
        parser.exit(1, f"Couldn't finish: {exc}\n")


if __name__ == "__main__":
    main()
