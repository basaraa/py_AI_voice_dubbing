"""
Local AI Video Dubbing & Localization Studio - Modular GUI Package
------------------------------------------------------------------
Pure procedural assembly of the application UI:
- Window setup, geometry, minsize, and dark ttk styles
- Notebook container (Tab 1 and Tab 2)
- Tab 1: Video Dubbing Studio (modules.gui.tab1_video_dubbing)
- Tab 2: Narration Host (modules.gui.tab2_narration_host with Single & Multi-File)
- Shared Status Bar & Log Console (modules.gui.status_log_panel)
"""

import tkinter as tk
from tkinter import ttk

from modules.gui.status_log_panel import create_status_log_panel
from modules.gui.tab1_video_dubbing import create_tab1_video_dubbing
from modules.gui.tab2_narration_host import create_tab2_narration_host


def create_app():
    root = tk.Tk()
    root.title("Local AI Video Dubbing & Localization Studio")
    root.geometry("1440x960")
    root.minsize(960, 680)

    # Dark / Accent Styles
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except Exception:
        pass
    style.configure("Treeview", rowheight=23)
    style.configure("TButton", padding=3)
    style.configure("Accent.TButton", font=('Segoe UI', 9, 'bold'))

    # Notebook Container
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=(3, 2))

    # Shared Status & Log footer
    status_log = create_status_log_panel(root, notebook)
    log_fn = status_log["log"]
    prog_var = status_log["prog_var"]
    status_lbl = status_log["status_lbl"]
    vram_lbl = status_log["vram_lbl"]

    # Voice update synchronization between tabs
    voice_listeners = []
    def notify_voice_listeners():
        for fn in voice_listeners:
            try:
                fn()
            except Exception:
                pass

    # Mount Tab 1: Video Dubbing Studio
    tab1_ctrl = create_tab1_video_dubbing(
        notebook,
        root=root,
        log_cb=log_fn,
        prog_var=prog_var,
        on_voice_added=notify_voice_listeners
    )
    voice_listeners.append(tab1_ctrl["update_voices"])

    # Mount Tab 2: Narration Host (hosts Single Text and Multi-File Dubbing)
    tab2_ctrl = create_tab2_narration_host(
        notebook,
        root=root,
        log_cb=log_fn,
        prog_var=prog_var,
        status_lbl=status_lbl,
        vram_lbl=vram_lbl,
        on_voice_added=notify_voice_listeners
    )
    voice_listeners.append(tab2_ctrl["update_voices"])

    # Start polling log queue
    root.after(120, status_log["process_logs"])

    return root
