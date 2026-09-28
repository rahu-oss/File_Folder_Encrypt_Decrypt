from __future__ import annotations

import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from vault.core.crypto import create_keyfile, encrypt
from vault.core.passphrase import strength
from .widgets import ScrollFrame, Step, button, checkbox, entry, Tooltip

if TYPE_CHECKING:
    from .app import VaultApp


class LockTab(ScrollFrame):
    def __init__(self, parent: tk.Widget, app: VaultApp) -> None:
        super().__init__(parent)
        self.app = app
        self.source = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm = tk.StringVar()
        self.output = tk.StringVar()
        self.key = tk.StringVar()
        self.use_key = tk.BooleanVar()
        self.show = tk.BooleanVar()
        self.compress = tk.BooleanVar(value=True)
        self.erase = tk.BooleanVar()
        ttk.Label(self.body, text="Lock your files", style="Title.TLabel").pack(anchor="w", padx=18, pady=(14, 0))
        ttk.Label(self.body, text="Encrypt a protected copy. Follow the four steps below.").pack(anchor="w", padx=18, pady=(2, 8))
        self.steps = [Step(self.body, 1, "Choose what to protect")]
        first = self.steps[0]
        row = ttk.Frame(first)
        row.pack(fill="x")
        button(row, "Choose File", self.choose_file, "Select one file to lock.").pack(side="left", padx=(0, 8))
        button(row, "Choose Folder", self.choose_folder, "Lock a folder and everything inside it.").pack(side="left")
        self.path_label = ttk.Label(first, textvariable=self.source, wraplength=570)
        self.path_label.pack(anchor="w", pady=(6, 0))
        self.size_label = ttk.Label(first, text="No file or folder selected")
        self.size_label.pack(anchor="w")
        try:
            from tkinterdnd2 import DND_FILES
            self.path_label.drop_target_register(DND_FILES)
            self.path_label.dnd_bind("<<Drop>>", self.drop)
            Tooltip(self.path_label, "Drop one file or folder here, or use the Choose buttons.")
        except (ImportError, AttributeError, tk.TclError):
            Tooltip(self.path_label, "Your selected file or folder. Use the Choose buttons to select it.")

        second = Step(self.body, 2, "Create a passphrase")
        self.steps.append(second)
        ttk.Label(second, text="Passphrase").pack(anchor="w")
        self.password_entry = entry(second, self.password, "Use four or more random words. This secret cannot be reset.", show="•")
        self.password_entry.pack(fill="x")
        ttk.Label(second, text="Confirm passphrase").pack(anchor="w", pady=(5, 0))
        self.confirm_entry = entry(second, self.confirm, "Type the same passphrase again.", show="•")
        self.confirm_entry.pack(fill="x")
        checkbox(second, "Show passphrase", self.show, "Show or hide both passphrase fields.", self.toggle_show).pack(anchor="w", pady=4)
        self.meter = ttk.Progressbar(second, maximum=3, length=160)
        self.meter.pack(anchor="w")
        Tooltip(self.meter, "Length and variety guidance; this is not a guarantee of strength.")
        self.tip = ttk.Label(second, wraplength=570)
        self.tip.pack(anchor="w", pady=(4, 0))
        self.validation = ttk.Label(second, foreground="#b03636")
        self.validation.pack(anchor="w")

        third = Step(self.body, 3, "Add a key file (optional)")
        self.steps.append(third)
        checkbox(third, "Also require a key file", self.use_key, "Require both the passphrase and this exact key file to unlock.", self.validate).pack(anchor="w")
        row = ttk.Frame(third)
        row.pack(fill="x", pady=5)
        self.new_key = button(row, "Create new key file", self.make_key, "Save a fresh 32-byte random key. Keep a separate backup.")
        self.new_key.pack(side="left", padx=(0, 8))
        self.choose_key_button = button(row, "Choose existing key file", self.choose_key, "Select an existing 32-byte Vault key file.")
        self.choose_key_button.pack(side="left")
        ttk.Label(third, textvariable=self.key, wraplength=570).pack(anchor="w")
        ttk.Label(third, text="If you lose this key file, your data cannot be recovered.", foreground="#b03636", wraplength=570).pack(anchor="w", pady=(3, 0))

        fourth = Step(self.body, 4, "Choose where to save")
        self.steps.append(fourth)
        entry(fourth, self.output, "Choose the full filename for the new .vault copy.").pack(fill="x")
        button(fourth, "Save As…", self.choose_output, "Choose a filename and folder for your locked copy.").pack(anchor="w", pady=5)
        self.compress_control = checkbox(fourth, "Compress folder", self.compress, "Reduce folder size before encryption. Preparation may take longer.")
        self.compress_control.pack(anchor="w")
        checkbox(fourth, "Securely delete original afterward", self.erase, "Best effort only. A separate confirmation after locking is required; SSDs and backups can retain data.").pack(anchor="w", pady=5)
        self.submit = button(self.body, "Lock Now", self.start, "Create the protected .vault copy.", style="Action.TButton")
        self.submit.pack(fill="x", padx=18, pady=(10, 20))
        for variable in (self.source, self.password, self.confirm, self.output, self.key):
            variable.trace_add("write", lambda *_: self.validate())
        self.validate()

    def toggle_show(self) -> None:
        for control in (self.password_entry, self.confirm_entry):
            control.configure(show="" if self.show.get() else "•")

    def clear_secrets(self) -> None:
        self.password.set("")
        self.confirm.set("")
        self.show.set(False)
        self.toggle_show()

    def choose_file(self) -> None:
        value = filedialog.askopenfilename(parent=self, title="Choose a file to protect")
        if value:
            self.set_source(value)

    def choose_folder(self) -> None:
        value = filedialog.askdirectory(parent=self, title="Choose a folder to protect")
        if value:
            self.set_source(value)

    def drop(self, event: tk.Event) -> None:
        if self.app.busy:
            return
        paths = self.tk.splitlist(event.data)
        if len(paths) == 1:
            self.set_source(paths[0])
        else:
            messagebox.showinfo("Choose one item", "Choose one file or folder at a time.", parent=self)

    def set_source(self, value: str) -> None:
        self.source.set(value)
        self.output.set(value.rstrip("/\\") + ".vault")
        self.size_label.configure(text="Calculating size…")

        def measure() -> None:
            try:
                path = Path(value)
                size = path.stat().st_size if path.is_file() else 0
                if path.is_dir():
                    for directory, dirs, files in os.walk(path, followlinks=False):
                        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()
                                   and not getattr((Path(directory) / d).lstat(), "st_file_attributes", 0) & 0x400]
                        for name in files:
                            item = Path(directory) / name
                            if not item.is_symlink():
                                size += item.stat().st_size
                label = f"{size:,} bytes  •  {'Folder' if path.is_dir() else 'File'}"
            except OSError:
                label = "Size unavailable — check that you can read this item."
            self.app.events.put(("size", (value, label)))
        threading.Thread(target=measure, daemon=True).start()

    def choose_key(self) -> None:
        value = filedialog.askopenfilename(parent=self, title="Choose your key file")
        if value:
            self.key.set(value)

    def make_key(self) -> None:
        value = filedialog.asksaveasfilename(parent=self, title="Save a new key file", defaultextension=".key", initialfile="vault.key")
        if value:
            # Never replace a key file that might be required by another vault.
            try:
                create_keyfile(value)
                self.key.set(value)
            except FileExistsError:
                messagebox.showerror("Keep your existing key safe", "Choose a new filename. Replacing a key file can make older vaults impossible to unlock.", parent=self)
            except OSError:
                self.app.report_error(OSError("key creation failed"))

    def choose_output(self) -> None:
        value = filedialog.asksaveasfilename(parent=self, title="Save your locked copy", defaultextension=".vault", initialfile=Path(self.output.get()).name or "protected.vault")
        if value:
            self.output.set(value)

    def validate(self) -> bool:
        source = Path(self.source.get())
        selected = bool(self.source.get()) and source.exists() and not source.is_symlink()
        same = bool(self.password.get()) and self.password.get() == self.confirm.get()
        key_ok = not self.use_key.get() or self.app.valid_key(self.key.get())
        output = Path(self.output.get())
        saved = bool(self.output.get()) and output.parent.is_dir() and not output.is_dir()
        if selected and saved:
            saved = output.resolve() != source.resolve() and not (source.is_dir() and output.resolve().is_relative_to(source.resolve()))
        result = strength(self.password.get())
        self.meter.configure(value=result.score if self.password.get() else 0)
        self.tip.configure(text=f"{result.label}: {result.tip}" if self.password.get() else "Use 4+ random words. Keep this passphrase safe.")
        self.validation.configure(text="Passphrases don't match" if self.confirm.get() and not same else "Warning: fewer than 12 characters" if 0 < len(self.password.get()) < 12 else "")
        for step, state in zip(self.steps, (selected, same, key_ok, saved)):
            step.complete(state)
        key_state = "normal" if self.use_key.get() and not self.app.busy else "disabled"
        self.new_key.configure(state=key_state)
        self.choose_key_button.configure(state=key_state)
        self.compress_control.configure(state="normal" if selected and source.is_dir() and not self.app.busy else "disabled")
        ready = selected and same and key_ok and saved and not self.app.busy
        self.submit.configure(state="normal" if ready else "disabled")
        next_step = ("Choose a file or folder to begin" if not selected else "Create and confirm your passphrase" if not same
                     else "Choose a 32-byte key file" if not key_ok else "Choose a save location outside your original" if not saved else "Ready — select Lock Now")
        self.app.set_hint(self, next_step)
        return ready

    def start(self) -> None:
        if not self.validate():
            return
        if len(self.password.get()) < 12 and not messagebox.askyesno("Use a longer passphrase?", "This passphrase has fewer than 12 characters and may be easy to guess. Continue anyway?", parent=self):
            return
        overwrite = False
        if Path(self.output.get()).exists():
            overwrite = messagebox.askyesno("Replace existing file?", "The output file already exists. Replace it with this new vault?", parent=self)
            if not overwrite:
                return
        source, output, password = self.source.get(), self.output.get(), self.password.get()
        key = self.key.get() if self.use_key.get() else None
        compress, erase = self.compress.get(), self.erase.get()
        self.app.run_operation("lock", lambda cancel, progress: encrypt(source, output, password, keyfile=key,
                               compress=compress, overwrite=overwrite, cancel=cancel, progress=progress),
                               original=Path(source) if erase else None)
