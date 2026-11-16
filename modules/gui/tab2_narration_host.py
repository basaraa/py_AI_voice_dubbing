"""
Tab 2 Host: Narration Mode Switcher & Host Container
---------------------------------------------------
Procedural component managing Tab 2:
- Radiobutton switcher: Single Text Narration vs Multi-File Dubbing
- Hosts Tab 2A (Single Text) and Tab 2B (Multi-File Dubbing)
- 100% in-memory state preservation when switching back and forth
"""

import tkinter as tk
from tkinter import ttk

from modules.gui.tab2_single_text import create_tab2_single_text
from modules.gui.tab2_multi_file import create_tab2_multi_file


def create_tab2_narration_host(parent_notebook, root, log_cb=print, prog_var=None, status_lbl=None, vram_lbl=None, on_voice_added=None):
    """
    Creates and manages the Tab 2 host container with the mode switcher.
    """
    tab_narration = ttk.Frame(parent_notebook)
    parent_notebook.add(tab_narration, text=" 🎙️ 2. Text Narration & Multi-Voice Speech ")

    # Mode selector header
    tab2_mode_f = ttk.LabelFrame(tab_narration, text=" Narration Mode / Režim prednesu ", padding=5)
    tab2_mode_f.pack(fill="x", padx=10, pady=(4, 2))

    tab2_mode_var = tk.StringVar(value="single")

    tab2_single_container = ttk.Frame(tab_narration)
    tab2_multi_container = ttk.Frame(tab_narration)

    def on_tab2_mode_changed():
        m = tab2_mode_var.get()
        if m == "single":
            tab2_multi_container.pack_forget()
            tab2_single_container.pack(fill="both", expand=True)
        else:
            tab2_single_container.pack_forget()
            tab2_multi_container.pack(fill="both", expand=True)

    ttk.Radiobutton(
        tab2_mode_f,
        text="🎙️ Single Text / Subtitle Narration (Pôvodný režim prednesu)",
        variable=tab2_mode_var,
        value="single",
        command=on_tab2_mode_changed
    ).pack(side="left", padx=15)

    ttk.Radiobutton(
        tab2_mode_f,
        text="📁 Multi-File Dubbing (.txt / .srt dávkový dabing)",
        variable=tab2_mode_var,
        value="multi",
        command=on_tab2_mode_changed
    ).pack(side="left", padx=15)

    # Initialize child sub-tabs
    single_ctrl = create_tab2_single_text(
        tab2_single_container,
        root=root,
        log_cb=log_cb,
        prog_var=prog_var,
        on_voice_added=on_voice_added
    )

    multi_ctrl = create_tab2_multi_file(
        tab2_multi_container,
        root=root,
        log_cb=log_cb,
        prog_var=prog_var,
        status_lbl=status_lbl,
        vram_lbl=vram_lbl
    )

    # Pack single mode by default
    tab2_single_container.pack(fill="both", expand=True)

    def update_all_tab2_voices():
        if "update_voices" in single_ctrl:
            single_ctrl["update_voices"]()
        if "update_voices" in multi_ctrl:
            multi_ctrl["update_voices"]()

    return {
        "tab_frame": tab_narration,
        "single_ctrl": single_ctrl,
        "multi_ctrl": multi_ctrl,
        "update_voices": update_all_tab2_voices
    }
