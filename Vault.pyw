"""Double-click source launcher for machines with Python and dependencies installed."""
import tkinter as tk
from tkinter import messagebox

if __name__ == "__main__":
    try:
        from vault.gui.app import main
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Vault needs setup", "A required component is missing. Use the packaged Vault app, or ask the person installing Vault to follow README.md.")
        root.destroy()
    else:
        main()
