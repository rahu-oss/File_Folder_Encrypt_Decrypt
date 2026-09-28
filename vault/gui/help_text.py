HELP_TEXT = """QUICK START

1. Lock: choose a file or folder, create and confirm a passphrase, then choose where to save your .vault file.
2. Unlock: choose the .vault file, enter the same passphrase and key file (if used), then choose an output folder.
3. Test your unlocked copy before deleting anything. Keep backups of your vault and keep the key file separately.

HOW IT WORKS

Locking makes an encrypted copy. AES-256-GCM protects the contents and detects changes. Your passphrase is processed with Argon2id (or PBKDF2 if Argon2 is unavailable). Each vault gets fresh random settings. The original name is inside the encrypted contents, though the suggested .vault filename still includes that name: rename the vault if you want to hide it.

An optional key file adds a second secret. You need BOTH the passphrase and that exact key file to unlock. Creating a new key file cannot replace a lost one. Header previews are unverified until unlocking succeeds.

TIPS FOR A GOOD PASSPHRASE

Use 4 or more random, unrelated words. Longer is better. Avoid quotations, names, birthdays, and reused passwords. Save it in a trusted password manager. The strength meter measures length and variety, not whether your words are actually random. Short passphrases are allowed after a warning.

WHAT IF I FORGET MY PASSPHRASE OR LOSE MY KEY FILE?

The data cannot be recovered. There is no reset, back door, or recovery service. Back up the key file somewhere separate and safe.

SAFETY CHECKLIST

• Test unlocking before deleting your original.
• Back up the vault file and key file separately.
• Keep your computer and backups protected. An unlocked or infected computer can expose your data.
• Do not edit source files while locking them.
• Restoring a folder requires a destination where its name does not already exist. Vault never merges or replaces existing folders.
• Existing files are replaced only after you confirm. Use a different output folder if unsure.
• Compression applies to folders and can save space, but preparation takes time.
• Cancel stops work at the next safe point. Key derivation may take a moment to finish.

DELETING ORIGINALS

The optional “Securely delete original afterward” feature overwrites ordinary files once before removing them. It is best effort only. SSDs, flash drives, snapshots, cloud sync, journals, backups, and wear leveling can retain copies. Full-disk encryption is a better foundation. Deletion cannot be undone. Test an unlocked copy before using this feature.

LIMITATIONS

Vault handles ordinary files and folders, including empty ones. Links, junctions, devices, and non-portable filenames are rejected. Files larger than available temporary disk space cannot be processed. Temporary plaintext is stored privately during packing and unlocking and removed after normal completion, failure, or cancellation; crashes can leave temporary data. File permissions of restored files are private where supported; original ownership, ACLs, and extended attributes are not preserved. Windows permissions depend on your account and folder ACLs.

The vault header reveals the file/folder type, key-file use, compression setting, and approximate content size. Python cannot guarantee erasure of secrets from memory. Vault is not independently security-audited.
"""
