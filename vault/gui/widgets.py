"""Accessible reusable guided-form widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget, self.text = widget, text
        self.window: tk.Toplevel | None = None
        self.timer: str | None = None
        widget.bind("<Enter>", self.schedule, add=True)
        widget.bind("<Leave>", self.hide, add=True)
        widget.bind("<FocusIn>", self.schedule, add=True)
        widget.bind("<FocusOut>", self.hide, add=True)
        widget.bind("<ButtonPress>", self.hide, add=True)
        widget.bind("<Destroy>", self.hide, add=True)

    def schedule(self, event: tk.Event | None = None) -> None:
        self.hide()
        self.timer = self.widget.after(650, self.show)

    def show(self) -> None:
        self.timer = None
        if not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.geometry(f"+{self.widget.winfo_rootx()+12}+{self.widget.winfo_rooty()+self.widget.winfo_height()+5}")
        ttk.Label(self.window, text=self.text, padding=10, wraplength=360,
                  background="#fff6d6", foreground="#222222").pack()

    def hide(self, event: tk.Event | None = None) -> None:
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.window:
            self.window.destroy()
            self.window = None


def button(parent: tk.Widget, text: str, command: Callable, tip: str, **kwargs: object) -> ttk.Button:
    control = ttk.Button(parent, text=text, command=command, **kwargs)
    Tooltip(control, tip)
    return control


def entry(parent: tk.Widget, variable: tk.StringVar, tip: str, **kwargs: object) -> ttk.Entry:
    control = ttk.Entry(parent, textvariable=variable, **kwargs)
    Tooltip(control, tip)
    return control


def checkbox(parent: tk.Widget, text: str, variable: tk.BooleanVar, tip: str,
             command: Callable | None = None) -> ttk.Checkbutton:
    control = ttk.Checkbutton(parent, text=text, variable=variable, command=command)
    Tooltip(control, tip)
    return control


class Step(ttk.LabelFrame):
    def __init__(self, parent: tk.Widget, number: int, title: str) -> None:
        super().__init__(parent, text=f"{number}. {title}", padding=(12, 7))
        self.pack(fill="x", padx=16, pady=5)
        self.indicator = ttk.Label(self, text="○ To do", foreground="#637185")
        self.indicator.pack(anchor="e")

    def complete(self, complete: bool, optional: bool = False) -> None:
        self.indicator.configure(text="✓ Ready" if complete else ("Optional" if optional else "○ To do"),
                                 foreground="#187044" if complete else "#637185")


class ScrollFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#f4f6fa")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        Tooltip(bar, "Scroll through the steps.")
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add=True)
        self.bind_all("<Button-4>", self._wheel, add=True)
        self.bind_all("<Button-5>", self._wheel, add=True)
        self.bind_all("<FocusIn>", self._focus, add=True)

    def _belongs(self, widget: tk.Widget) -> bool:
        return str(widget).startswith(str(self.body) + ".")

    def _wheel(self, event: tk.Event) -> None:
        if self.winfo_ismapped() and (self._belongs(event.widget) or event.widget == self.canvas):
            amount = -1 if getattr(event, "num", 0) == 4 else 1 if getattr(event, "num", 0) == 5 else (-1 if event.delta > 0 else 1)
            self.canvas.yview_scroll(amount * 3, "units")

    def _focus(self, event: tk.Event) -> None:
        if self.winfo_ismapped() and self._belongs(event.widget):
            self.update_idletasks()
            y = event.widget.winfo_rooty() - self.body.winfo_rooty()
            top = self.canvas.canvasy(0)
            if y < top or y + event.widget.winfo_height() > top + self.canvas.winfo_height():
                self.canvas.yview_moveto(max(0, y - 30) / max(1, self.body.winfo_height()))
