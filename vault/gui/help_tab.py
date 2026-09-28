import tkinter as tk
from tkinter import ttk

from .help_text import HELP_TEXT
from .widgets import Tooltip


class HelpTab(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, padding=16)
        text = tk.Text(self, wrap="word", padx=20, pady=18, font=("TkDefaultFont", 11),
                       relief="flat", background="white", foreground="#203149", spacing3=6)
        scrollbar = ttk.Scrollbar(self, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")
        Tooltip(text, "Read the guide. You can select and copy text, but cannot edit it.")
        Tooltip(scrollbar, "Scroll the help guide.")
