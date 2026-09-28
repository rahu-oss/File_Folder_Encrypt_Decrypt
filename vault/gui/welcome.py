from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .widgets import button, checkbox

SLIDES = [
    ("Your files, protected", "Vault creates a locked copy of a file or folder.\nYour original stays where it is.\n\nStart with the Lock tab and follow the four steps."),
    ("Two ways to keep a secret", "Choose a long, memorable passphrase of random words.\nYou can also require a separate key file.\n\nKeep both safe: lost secrets mean lost data."),
    ("Try an unlock first", "Unlock your new vault into another folder to test it.\nBack up the vault and key file separately.\n\nThe Help tab is always here when you need it."),
]


def should_show(config: Path) -> bool:
    try:
        return not json.loads(config.read_text(encoding="utf-8")).get("hide_welcome", False)
    except (OSError, ValueError, AttributeError):
        return True


def show_welcome(root: tk.Tk, config: Path) -> None:
    window = tk.Toplevel(root)
    window.title("Welcome to Vault")
    window.transient(root)
    window.resizable(False, False)
    body = ttk.Frame(window, padding=26)
    body.pack(fill="both", expand=True)
    title = ttk.Label(body, font=("TkDefaultFont", 18, "bold"))
    title.pack(anchor="w", pady=(0, 16))
    detail = ttk.Label(body, wraplength=460, justify="left")
    detail.pack(anchor="w", pady=(0, 20))
    count = ttk.Label(body)
    count.pack(anchor="w")
    hidden = tk.BooleanVar(value=False)
    checkbox(body, "Don't show again", hidden, "You can reopen this tutorial from the Help menu.").pack(anchor="w", pady=12)
    controls = ttk.Frame(body)
    controls.pack(fill="x")
    index = 0

    def close() -> None:
        try:
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps({"hide_welcome": hidden.get()}), encoding="utf-8")
        except OSError:
            pass  # On read-only accounts the tutorial simply appears next time.
        window.destroy()

    def render() -> None:
        title.configure(text=SLIDES[index][0])
        detail.configure(text=SLIDES[index][1])
        count.configure(text=f"{index + 1} of 3")
        previous.configure(state="normal" if index else "disabled")
        following.configure(text="Get started" if index == 2 else "Next →")

    def move(delta: int) -> None:
        nonlocal index
        if index == 2 and delta == 1:
            close()
            return
        index += delta
        render()

    previous = button(controls, "← Back", lambda: move(-1), "Return to the previous slide.")
    previous.pack(side="left")
    following = button(controls, "Next →", lambda: move(1), "Continue the tutorial.")
    following.pack(side="right")
    window.protocol("WM_DELETE_WINDOW", close)
    render()
    following.focus_set()
    window.grab_set()
