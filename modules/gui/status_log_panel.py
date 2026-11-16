"""
Status and Log Panel Component
------------------------------
Procedural component for the bottom status bar:
- Progress bar
- Status message & VRAM indicator
- Thread-safe log queue and scrolling log console
"""

import queue
import tkinter as tk
from tkinter import ttk

from modules.audio_utils import get_vram_status


def create_status_log_panel(root, notebook):
    """
    Creates the shared bottom status and log console panel.
    Returns a dictionary of controls and helper functions:
      - frame: ttk.LabelFrame container
      - prog_var: ttk.Progressbar
      - status_lbl: ttk.Label
      - vram_lbl: ttk.Label
      - log_txt: tk.Text
      - log: thread-safe logging function
      - process_logs: function to pump log messages to UI
    """
    bottom_frame = ttk.LabelFrame(root, text=" System Status & Log ", padding=4)
    bottom_frame.pack(before=notebook, side="bottom", fill="x", padx=10, pady=(2, 4))

    prog_var = ttk.Progressbar(bottom_frame, mode="determinate")
    prog_var.pack(fill="x", padx=5, pady=2)

    status_row = ttk.Frame(bottom_frame)
    status_row.pack(fill="x", padx=5)

    status_lbl = ttk.Label(status_row, text="Ready.", font=('Segoe UI', 9))
    status_lbl.pack(side="left")

    vram_lbl = ttk.Label(status_row, text=get_vram_status(), font=('Segoe UI', 8, 'italic'))
    vram_lbl.pack(side="right")

    log_txt = tk.Text(bottom_frame, height=5, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 8))
    log_txt.pack(fill="both", expand=True, padx=5, pady=3)

    log_queue = queue.Queue()

    def log(msg):
        log_queue.put(msg)

    def process_logs():
        while not log_queue.empty():
            msg = log_queue.get_nowait()
            log_txt.insert(tk.END, msg + "\n")
            log_txt.see(tk.END)
            status_lbl.config(text=msg)
            vram_lbl.config(text=get_vram_status())
        root.after(120, process_logs)

    return {
        "frame": bottom_frame,
        "prog_var": prog_var,
        "status_lbl": status_lbl,
        "vram_lbl": vram_lbl,
        "log_txt": log_txt,
        "log": log,
        "process_logs": process_logs
    }
