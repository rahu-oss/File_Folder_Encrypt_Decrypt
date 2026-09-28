from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from vault.core.crypto import decrypt
from vault.core.format import Header, FOLDER, inspect_header
from .widgets import ScrollFrame, Step, button, checkbox, entry

if TYPE_CHECKING:
    from .app import VaultApp


class UnlockTab(ScrollFrame):
    def __init__(self, parent: tk.Widget, app: VaultApp) -> None:
        super().__init__(parent)
        self.app = app
        self.header: Header | None = None
        self.source = tk.StringVar()
        self.password = tk.StringVar()
        self.key = tk.StringVar()
        self.output = tk.StringVar()
        self.show = tk.BooleanVar()
        ttk.Label(self.body, text="Unlock your files", style="Title.TLabel").pack(anchor="w", padx=18, pady=(14, 0))
        ttk.Label(self.body, text="Decrypt a vault using the secrets you chose when locking it.").pack(anchor="w", padx=18, pady=(2, 8))
        first = Step(self.body, 1, "Choose a vault")
        self.steps = [first]
        button(first, "Choose .vault File", self.choose_source, "Select the protected file you want to unlock.").pack(anchor="w")
        ttk.Label(first, textvariable=self.source, wraplength=570).pack(anchor="w", pady=5)
        self.preview = ttk.Label(first, text="Choose a vault to see its details.", wraplength=570)
        self.preview.pack(anchor="w")
        second = Step(self.body, 2, "Enter your passphrase")
        self.steps.append(second)
        self.password_entry = entry(second, self.password, "Enter the original passphrase exactly, including spaces.", show="•")
        self.password_entry.pack(fill="x")
        checkbox(second, "Show passphrase", self.show, "Show or hide your passphrase.", self.toggle_show).pack(anchor="w", pady=5)
        third = Step(self.body, 3, "Choose the key file, if required")
        self.steps.append(third)
        self.choose_key_button = button(third, "Choose Key File", self.choose_key, "Choose the exact key file used when this vault was locked.")
        self.choose_key_button.pack(anchor="w")
        ttk.Label(third, textvariable=self.key, wraplength=570).pack(anchor="w", pady=5)
        self.key_hint = ttk.Label(third, text="Select a vault first.")
        self.key_hint.pack(anchor="w")
        fourth = Step(self.body, 4, "Choose an output folder")
        self.steps.append(fourth)
        entry(fourth, self.output, "Restored items keep their original names inside this folder.").pack(fill="x")
        button(fourth, "Choose Output Folder", self.choose_output, "Choose where the unlocked file or folder should appear.").pack(anchor="w", pady=5)
        ttk.Label(fourth, text="Tip: choose an empty folder for your first test unlock.", wraplength=570).pack(anchor="w")
        self.submit = button(self.body, "Unlock Now", self.start, "Check the entire vault and restore its contents.", style="Action.TButton")
        self.submit.pack(fill="x", padx=18, pady=(14, 20))
        for variable in (self.password, self.key, self.output):
            variable.trace_add("write", lambda *_: self.validate())
        self.validate()

    def toggle_show(self) -> None:
        self.password_entry.configure(show="" if self.show.get() else "•")

    def clear_secrets(self) -> None:
        self.password.set("")
        self.show.set(False)
        self.toggle_show()

    def choose_source(self) -> None:
        value = filedialog.askopenfilename(parent=self, title="Choose a vault", filetypes=[("Vault files", "*.vault"), ("All files", "*")])
        if value:
            self.set_source(value)

    def set_source(self, value: str) -> None:
        self.source.set(value)
        self.header = None
        self.key.set("")
        try:
            self.header = inspect_header(value)
            self.preview.configure(text=f"Created with key file: {'Yes' if self.header.keyfile else 'No'}  •  Type: {'Folder' if self.header.payload == FOLDER else 'File'}\nDetails are verified when you unlock.")
            self.output.set(str(Path(value).parent))
        except Exception as exc:
            # Never expose raw parser errors or paths from exceptions in the GUI.
            self.preview.configure(text="This file could not be read as a supported Vault file.")
            self.app.log_error(exc)
        self.validate()

    def choose_key(self) -> None:
        value = filedialog.askopenfilename(parent=self, title="Choose the original key file")
        if value:
            self.key.set(value)

    def choose_output(self) -> None:
        value = filedialog.askdirectory(parent=self, title="Choose an output folder")
        if value:
            self.output.set(value)

    def validate(self) -> bool:
        selected = self.header is not None
        password = bool(self.password.get())
        needs_key = selected and self.header.keyfile
        key = not needs_key or self.app.valid_key(self.key.get())
        output = bool(self.output.get()) and Path(self.output.get()).is_dir()
        self.choose_key_button.configure(state="normal" if needs_key and not self.app.busy else "disabled")
        self.key_hint.configure(text="Required: choose the original 32-byte key file." if needs_key else "No key file needed." if selected else "Select a vault first.")
        for step, state in zip(self.steps, (selected, password, selected and key, output)):
            step.complete(state)
        ready = selected and password and key and output and not self.app.busy
        self.submit.configure(state="normal" if ready else "disabled")
        self.app.set_hint(self, "Choose a .vault file to begin" if not selected else "Enter your passphrase" if not password else "Choose the original key file" if not key else "Choose an output folder" if not output else "Ready — select Unlock Now")
        return ready

    def start(self) -> None:
        if not self.validate():
            return
        source, output, password = self.source.get(), self.output.get(), self.password.get()
        key = self.key.get() if self.header and self.header.keyfile else None
        self.app.run_operation("unlock", lambda cancel, progress: decrypt(source, output, password, keyfile=key,
                               cancel=cancel, progress=progress, overwrite=False,
                               confirm_overwrite=self.app.confirm_overwrite))
