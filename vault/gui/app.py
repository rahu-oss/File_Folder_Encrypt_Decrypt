"""Application shell and queue-based worker coordination. Tk stays on its thread."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import font, messagebox, ttk
import traceback
from typing import Callable

from vault.core.erase import erase_original
from vault.core.format import Cancelled, InvalidVault, VaultError
from .help_tab import HelpTab
from .lock_tab import LockTab
from .unlock_tab import UnlockTab
from .welcome import should_show, show_welcome
from .widgets import button, Tooltip


def data_directory() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Vault"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Vault"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "vault"


class VaultApp:
    def __init__(self, root: tk.Tk, *, config_dir: Path | None = None, tutorial: bool = True) -> None:
        self.root = root
        self.busy = False
        self.closing = False
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.saved_states: list[tuple[ttk.Widget, tuple[str, ...]]] = []
        self.logger = logging.getLogger(f"vault.{id(self)}")
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        config_dir = config_dir or data_directory()
        self.config = config_dir / "settings.json"
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(config_dir / "vault.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(handler)
        except OSError:
            self.logger.addHandler(logging.NullHandler())
        root.title("Vault • Protect your files")
        root.geometry("840x850")
        root.minsize(700, 600)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            font.nametofont(name).configure(size=11)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("TkDefaultFont", 11), background="#f4f6fa", foreground="#203149")
        style.configure("TButton", padding=(12, 7))
        style.configure("TNotebook.Tab", padding=(18, 10))
        style.configure("Title.TLabel", font=("TkDefaultFont", 21, "bold"))
        style.configure("Action.TButton", font=("TkDefaultFont", 12, "bold"), padding=13,
                        background="#215bb4", foreground="white")
        style.map("Action.TButton", background=[("disabled", "#cbd4e3"), ("active", "#174a96")], foreground=[("disabled", "#526176")])
        self.status = tk.StringVar(value="Choose a file to begin")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.lock = LockTab(self.notebook, self)
        self.unlock = UnlockTab(self.notebook, self)
        self.help = HelpTab(self.notebook)
        self.notebook.add(self.lock, text="Lock (Encrypt)")
        self.notebook.add(self.unlock, text="Unlock (Decrypt)")
        self.notebook.add(self.help, text="Help")
        Tooltip(self.notebook, "Choose Lock to protect files, Unlock to restore them, or Help for guidance.")
        footer = ttk.Frame(root, padding=(16, 10))
        footer.pack(fill="x")
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 10))
        Tooltip(self.progress, "Progress for the current operation. Preparation can take a moment.")
        self.cancel_button = button(footer, "Cancel", self.cancel_operation, "Stop the current operation at the next safe point.", state="disabled")
        self.cancel_button.pack(side="right")
        ttk.Label(root, textvariable=self.status, padding=(16, 4, 16, 12), wraplength=660).pack(anchor="w", fill="x")
        menu = tk.Menu(root)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Quick tutorial…", command=lambda: show_welcome(root, self.config))
        help_menu.add_command(label="Help and safety guide", command=lambda: self.notebook.select(self.help))
        menu.add_cascade(label="Help", menu=help_menu)
        root.configure(menu=menu)
        self.notebook.bind("<<NotebookTabChanged>>", self.tab_changed)
        root.bind("<Return>", self.enter)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_id = root.after(80, self.poll)
        self.lock.validate()
        if tutorial and should_show(self.config):
            root.after(200, lambda: show_welcome(root, self.config))

    @staticmethod
    def valid_key(value: str) -> bool:
        try:
            return bool(value) and Path(value).is_file() and Path(value).stat().st_size == 32
        except OSError:
            return False

    def set_hint(self, tab: ttk.Frame, hint: str) -> None:
        if not self.busy and hasattr(self, "notebook") and self.notebook.select() == str(tab):
            self.status.set(hint)

    def tab_changed(self, event: tk.Event | None = None) -> None:
        self.lock.clear_secrets()
        self.unlock.clear_secrets()
        self.lock.validate()
        self.unlock.validate()
        if not self.busy and self.notebook.select() == str(self.help):
            self.status.set("Read the guide, or choose Lock or Unlock to begin")

    def enter(self, event: tk.Event) -> str | None:
        if event.widget.winfo_toplevel() != self.root or isinstance(event.widget, (ttk.Button, ttk.Checkbutton)):
            return None
        if not self.busy:
            active = self.notebook.select()
            if active == str(self.lock):
                self.lock.start()
            elif active == str(self.unlock):
                self.unlock.start()
        return "break"

    def freeze(self, value: bool) -> None:
        if value:
            def visit(widget: tk.Widget) -> None:
                if isinstance(widget, (ttk.Entry, ttk.Button, ttk.Checkbutton)):
                    self.saved_states.append((widget, widget.state()))
                    widget.state(["disabled"])
                for child in widget.winfo_children():
                    visit(child)
            visit(self.lock)
            visit(self.unlock)
        else:
            for widget, states in self.saved_states:
                widget.state(["!disabled"])
                widget.state(states)
            self.saved_states.clear()
        self.cancel_button.configure(state="normal" if value else "disabled")

    def run_operation(self, kind: str, operation: Callable, *, original: Path | None = None) -> None:
        if self.busy:
            return
        self.busy = True
        self.cancel = threading.Event()
        self.freeze(True)
        self.progress.configure(value=0)
        self.status.set("Preparing…")
        last = 0.0

        def progress(percent: float, message: str) -> None:
            nonlocal last
            now = time.monotonic()
            if now - last >= 0.08 or percent in (0, 100):
                self.events.put(("progress", (percent, message)))
                last = now

        def work() -> None:
            try:
                result = operation(self.cancel, progress)
                self.events.put(("done", (kind, result, original)))
            except Exception as exc:
                self.log_error(exc)
                self.events.put(("error", exc))
        threading.Thread(target=work, daemon=False, name="VaultWorker").start()

    def confirm_overwrite(self, path: Path) -> bool:
        """Worker waits while the main Tk thread asks about the authenticated name."""
        answer: list[bool] = []
        ready = threading.Event()
        self.events.put(("overwrite", (path, answer, ready)))
        while not ready.wait(0.1):
            if self.cancel.is_set():
                return False
        return answer[0]

    def cancel_operation(self) -> None:
        self.cancel.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("Cancelling… finishing the current safe step")

    def poll(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "size":
                    source, label = value
                    if self.lock.source.get() == source:
                        self.lock.size_label.configure(text=label)
                elif event == "progress":
                    percent, message = value
                    self.progress.configure(value=percent)
                    if not self.cancel.is_set():
                        self.status.set(message)
                elif event == "overwrite":
                    path, answer, ready = value
                    answer.append(False if self.cancel.is_set() else messagebox.askyesno("Replace existing file?", f"The restored file already exists:\n{path.name}\n\nReplace it?", parent=self.root))
                    ready.set()
                elif event in ("done", "error"):
                    self.busy = False
                    self.freeze(False)
                    self.lock.clear_secrets()
                    self.unlock.clear_secrets()
                    self.lock.validate()
                    self.unlock.validate()
                    if self.closing:
                        self.shutdown()
                        return
                    if event == "error":
                        self.progress.configure(value=0)
                        self.report_error(value)
                    else:
                        kind, result, original = value
                        self.progress.configure(value=100)
                        self.status.set("Finished — choose your next file or open the output folder")
                        self.success(kind, result, original)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(80, self.poll)

    def log_error(self, exc: Exception) -> None:
        # No exception text, paths, source lines, local variables, keys, or passwords.
        frames = traceback.extract_tb(exc.__traceback__)
        trace = " > ".join(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames)
        self.logger.warning("%s at %s", type(exc).__name__, trace or "UI action")

    def report_error(self, exc: Exception) -> None:
        if isinstance(exc, Cancelled):
            self.status.set(str(exc))
            return
        if isinstance(exc, InvalidVault):
            detail = "Wrong passphrase or key file, or the file was changed. Check your secrets and try a backup if needed."
        elif isinstance(exc, FileExistsError):
            detail = "An item with that name already exists. Choose another output folder or filename. Existing folders are never replaced."
        elif isinstance(exc, PermissionError):
            detail = "Vault cannot access this location. Choose a folder you can read and write."
        elif isinstance(exc, VaultError):
            detail = str(exc)
        elif isinstance(exc, OSError):
            detail = "Vault could not read or save a file. Check your permissions, free disk space, and that the drive is connected."
        else:
            detail = "Vault could not finish. Try again with a different output folder. Local diagnostics contain no passphrases or keys."
        self.status.set("Operation stopped — review the message, then try again")
        messagebox.showerror("Couldn't finish", detail, parent=self.root)

    def success(self, kind: str, result: Path, original: Path | None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Vault — success")
        window.transient(self.root)
        body = ttk.Frame(window, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Locked successfully" if kind == "lock" else "Original deleted (best effort)" if kind == "erase" else "Unlocked successfully", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=str(result), wraplength=500).pack(anchor="w", pady=12)
        if kind == "lock":
            ttk.Label(body, text="Test unlocking before deleting your original.", wraplength=500).pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(body)
        row.pack(fill="x")
        button(row, "Open containing folder", lambda: self.open_folder(result if kind == "erase" else result.parent), "Open the output folder in your file manager.").pack(side="left", padx=(0, 8))
        button(row, "Done", window.destroy, "Close this success message.").pack(side="right")
        if original is not None:
            def erase() -> None:
                if messagebox.askyesno("Permanently delete original?", "Have you tested an unlocked copy?\n\nThis permanently overwrites and removes the original. It may NOT securely erase SSDs, flash drives, cloud copies, snapshots, or backups. Cancelling deletion may leave the original partly erased.\n\nDelete the original now?", parent=window, default="no"):
                    window.destroy()
                    self.run_operation("erase", lambda cancel, progress: erase_original(original, cancel))
            button(body, "Delete original…", erase, "Optional, irreversible best-effort deletion. Test unlocking first.").pack(anchor="w", pady=(14, 0))
        window.grab_set()

    def open_folder(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as exc:
            self.log_error(exc)
            self.report_error(exc)

    def close(self) -> None:
        if self.busy:
            if messagebox.askyesno("Cancel and close?", "Cancel the current operation and close after temporary files are cleaned up?", parent=self.root):
                self.closing = True
                self.cancel_operation()
        else:
            self.shutdown()

    def shutdown(self) -> None:
        self.root.after_cancel(self.poll_id)
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
        self.root.destroy()


def main() -> None:
    try:
        from tkinterdnd2 import TkinterDnD
        try:
            root = TkinterDnD.Tk()
        except tk.TclError:
            root = tk.Tk()
    except ImportError:
        root = tk.Tk()
    VaultApp(root)
    root.mainloop()
