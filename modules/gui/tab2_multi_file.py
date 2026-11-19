"""
Tab 2B: Multi-File Dubbing & Batch Narration Component (.txt / .srt)
-------------------------------------------------------------------
Procedural component for batch dubbing multiple subtitle/text files in Tab 2.
- Lists target-specific files (.txt, .srt) from script root folder
- Startup auto-scan + Recursive scan checkbox (default unchecked)
- File-level voice assignment with default SUPERTONIC_MALE_RANKED[0] (M5)
- Row-level voice override with priority over file voice
- Extended Shift/Ctrl multi-selection for sentences
- Reset button to revert row overrides back to file default
- Zero-Click auto-save to script root folder with timestamps
"""

import os
import re
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from modules.config import (
    SCRIPT_DIR, SUPERTONIC_MALE_RANKED, SUPERTONIC_VOICE_CATALOG
)
from modules.audio_utils import (
    get_all_available_voices, sort_treeview, get_vram_status
)
from modules.subtitles import extract_clean_text_from_srt, split_text_into_sentences_list
from modules.tts import DynamicDubbingEngine, play_any_voice_sample
from modules.narration_core import synthesize_narration_to_mp3


def get_default_supertonic_voice(catalog, voice_map):
    """
    Finds and returns (label, voice_info) corresponding to the first voice in SUPERTONIC_MALE_RANKED (e.g. M5).
    """
    first_male_id = SUPERTONIC_MALE_RANKED[0] if SUPERTONIC_MALE_RANKED else "M5"
    for label, info in voice_map.items():
        if info.get("type") == "supertonic" and info.get("voice_id") == first_male_id:
            return label, info
    if catalog:
        return catalog[0], voice_map.get(catalog[0], {"type": "supertonic", "voice_id": "M5", "label": catalog[0]})
    lbl = "⚡ [Supertonic] M5 (Male - Cinematic Charismatic)"
    return lbl, {"type": "supertonic", "voice_id": "M5", "label": lbl}


def extract_file_sentences(filepath):
    """
    Extracts clean sentences from .srt or .txt file.
    For .srt files, strips timestamps, cue numbers, and tags.
    """
    try:
        lower_path = filepath.lower()
        if lower_path.endswith((".srt", ".vtt")):
            clean_text = extract_clean_text_from_srt(filepath)
        else:
            with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()
            if "-->" in content or re.search(r'\d+\s*\n\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}', content):
                clean_text = extract_clean_text_from_srt(content)
            else:
                clean_text = content
        return split_text_into_sentences_list(clean_text)
    except Exception:
        return []


def scan_target_files(directory, recursive=False):
    """
    Scans directory for .txt and .srt files.
    """
    results = []
    if not os.path.exists(directory):
        return results

    valid_exts = (".txt", ".srt")
    if recursive:
        for root_dir, _, files in os.walk(directory):
            if any(part.startswith(".") or part in ("output_narration", "speaker_profiles", "__pycache__", "voices") for part in os.path.split(root_dir)):
                continue
            for f in sorted(files):
                if f.lower().endswith(valid_exts):
                    if f.lower() in ("requirements.txt",) or (f.lower().endswith(".txt") and (f.startswith("chunk_") or f.endswith("_cache.txt"))):
                        continue
                    full_p = os.path.join(root_dir, f)
                    results.append(full_p)
    else:
        try:
            for f in sorted(os.listdir(directory)):
                full_p = os.path.join(directory, f)
                if os.path.isfile(full_p) and f.lower().endswith(valid_exts):
                    if f.lower() in ("requirements.txt",) or f.startswith("chunk_") or f.endswith("_cache.txt"):
                        continue
                    results.append(full_p)
        except Exception:
            pass

    return results


def create_tab2_multi_file(parent_frame, root, log_cb=print, prog_var=None, status_lbl=None, vram_lbl=None):
    """
    Procedurally creates and configures the Multi-File Dubbing UI inside parent_frame.
    """
    state = {
        "current_dir": SCRIPT_DIR,
        "files": {},
        "active_file": None,
        "catalog": [],
        "voice_map": {},
        "default_voice_label": "",
        "default_voice_info": {},
        "cancel_requested": False,
        "is_generating": False,
        "sort_files": {"col": None, "reverse": False},
        "sort_rows": {"col": None, "reverse": False}
    }

    # --------------------------------------------------------------------------
    # 1. TOP CONFIGURATION BAR
    # --------------------------------------------------------------------------
    top_frame = ttk.LabelFrame(parent_frame, text=" 1. Multi-File Configuration & Scanner ", padding=6)
    top_frame.pack(fill="x", padx=10, pady=(2, 4))

    cfg_row1 = ttk.Frame(top_frame)
    cfg_row1.pack(fill="x", pady=2)

    ttk.Label(cfg_row1, text="Language:").pack(side="left", padx=(4, 2))
    lang_combo = ttk.Combobox(
        cfg_row1,
        values=["cs (Czech)", "sk (Slovak)", "ja (Japanese)", "en (English)", "de (German)", "pl (Polish)"],
        width=14,
        state="readonly"
    )
    lang_combo.set("cs (Czech)")
    lang_combo.pack(side="left", padx=2)

    ttk.Label(cfg_row1, text="Speed:").pack(side="left", padx=(10, 2))
    speed_combo = ttk.Combobox(cfg_row1, values=["0.85", "0.90", "0.95", "1.0", "1.05", "1.10"], width=5)
    speed_combo.set("1.0")
    speed_combo.pack(side="left", padx=2)

    recursive_var = tk.BooleanVar(value=False)
    rec_chk = ttk.Checkbutton(cfg_row1, text="Recursive Scan", variable=recursive_var)
    rec_chk.pack(side="left", padx=(15, 6))

    dir_var = tk.StringVar(value=state["current_dir"])
    dir_entry = ttk.Entry(cfg_row1, textvariable=dir_var, width=32)
    dir_entry.pack(side="left", fill="x", expand=True, padx=(5, 3))

    def choose_dir():
        d = filedialog.askdirectory(initialdir=state["current_dir"])
        if d:
            state["current_dir"] = os.path.abspath(d)
            dir_var.set(state["current_dir"])
            refresh_file_list()

    ttk.Button(cfg_row1, text="📁 Browse...", command=choose_dir).pack(side="left", padx=2)

    def on_rescan_clicked():
        cur = dir_var.get().strip()
        if os.path.isdir(cur):
            state["current_dir"] = os.path.abspath(cur)
        refresh_file_list()

    ttk.Button(cfg_row1, text="🔄 Rescan Files", command=on_rescan_clicked).pack(side="left", padx=2)

    # --------------------------------------------------------------------------
    # 2. MIDDLE SECTION: PanedWindow (Files Table + Sentence Table)
    # --------------------------------------------------------------------------
    paned = ttk.PanedWindow(parent_frame, orient="vertical")
    paned.pack(fill="both", expand=True, padx=10, pady=2)

    # --- Upper Pane: Files List & File Voice Assignment ---
    files_pane = ttk.LabelFrame(paned, text=" 2. File List (.txt / .srt) - Check to Dub & Assign Voice per File ", padding=5)
    paned.add(files_pane, weight=2)

    files_toolbar = ttk.Frame(files_pane)
    files_toolbar.pack(fill="x", pady=(0, 4))

    ttk.Button(files_toolbar, text="☑ Select All", command=lambda: set_all_files_checked(True)).pack(side="left", padx=2)
    ttk.Button(files_toolbar, text="☐ Deselect All", command=lambda: set_all_files_checked(False)).pack(side="left", padx=2)
    ttk.Button(files_toolbar, text="Toggle Checked (Space)", command=lambda: toggle_selected_files_check()).pack(side="left", padx=2)

    ttk.Separator(files_toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

    ttk.Label(files_toolbar, text="File Voice:").pack(side="left", padx=(2, 2))
    file_voice_combo = ttk.Combobox(files_toolbar, width=34, state="readonly")
    file_voice_combo.pack(side="left", padx=2)

    def preview_file_voice():
        chosen = file_voice_combo.get()
        if not chosen:
            messagebox.showwarning("Voice", "Please select a voice from the dropdown.")
            return
        ok, msg = play_any_voice_sample(chosen, target_lang=lang_combo.get().split()[0], log_cb=log_cb)
        if not ok:
            messagebox.showwarning("Warning", msg)

    ttk.Button(files_toolbar, text="✓ Apply to File(s)", style="Accent.TButton", command=lambda: apply_voice_to_selected_files()).pack(side="left", padx=3)
    ttk.Button(files_toolbar, text="▶ Preview", command=preview_file_voice).pack(side="left", padx=2)

    files_cols = ("check", "relpath", "voice", "sentences", "overridden", "status")
    files_tree = ttk.Treeview(files_pane, columns=files_cols, show="headings", height=5, selectmode="extended")
    files_tree.heading("check", text="Dub?", command=lambda: sort_treeview(files_tree, "check", state["sort_files"]))
    files_tree.heading("relpath", text="File Name / Path", command=lambda: sort_treeview(files_tree, "relpath", state["sort_files"]))
    files_tree.heading("voice", text="Assigned File Voice", command=lambda: sort_treeview(files_tree, "voice", state["sort_files"]))
    files_tree.heading("sentences", text="Lines", command=lambda: sort_treeview(files_tree, "sentences", state["sort_files"]))
    files_tree.heading("overridden", text="Overrides", command=lambda: sort_treeview(files_tree, "overridden", state["sort_files"]))
    files_tree.heading("status", text="Status", command=lambda: sort_treeview(files_tree, "status", state["sort_files"]))

    files_tree.column("check", width=55, anchor="center")
    files_tree.column("relpath", width=340, anchor="w")
    files_tree.column("voice", width=250, anchor="w")
    files_tree.column("sentences", width=65, anchor="center")
    files_tree.column("overridden", width=75, anchor="center")
    files_tree.column("status", width=95, anchor="center")

    files_scroll = ttk.Scrollbar(files_pane, orient="vertical", command=files_tree.yview)
    files_tree.configure(yscrollcommand=files_scroll.set)
    files_tree.pack(side="left", fill="both", expand=True)
    files_scroll.pack(side="right", fill="y")

    # --- Lower Pane: Sentence Table & Line-level Voice Assignment ---
    rows_pane = ttk.LabelFrame(paned, text=" 3. Sentence Voice Assignment (Shift / Ctrl Multi-Select, Overrides File Voice) ", padding=5)
    paned.add(rows_pane, weight=3)

    rows_toolbar = ttk.Frame(rows_pane)
    rows_toolbar.pack(fill="x", pady=(0, 4))

    ttk.Label(rows_toolbar, text="Row Voice:").pack(side="left", padx=(2, 2))
    row_voice_combo = ttk.Combobox(rows_toolbar, width=34, state="readonly")
    row_voice_combo.pack(side="left", padx=2)

    def preview_row_voice():
        chosen = row_voice_combo.get()
        if not chosen:
            messagebox.showwarning("Voice", "Please select a voice from the dropdown.")
            return
        ok, msg = play_any_voice_sample(chosen, target_lang=lang_combo.get().split()[0], log_cb=log_cb)
        if not ok:
            messagebox.showwarning("Warning", msg)

    ttk.Button(rows_toolbar, text="✓ Apply to Selected Rows", style="Accent.TButton", command=lambda: apply_voice_to_selected_rows()).pack(side="left", padx=3)
    ttk.Button(rows_toolbar, text="↺ Reset Selected to File Default", command=lambda: reset_selected_rows()).pack(side="left", padx=3)
    ttk.Button(rows_toolbar, text="↺ Reset All Rows of File", command=lambda: reset_all_rows_of_active_file()).pack(side="left", padx=3)
    ttk.Button(rows_toolbar, text="▶ Preview", command=preview_row_voice).pack(side="left", padx=2)
    ttk.Button(rows_toolbar, text="Select All (Ctrl+A)", command=lambda: rows_tree.selection_set(rows_tree.get_children())).pack(side="left", padx=2)

    rows_cols = ("id", "override", "voice", "text")
    rows_tree = ttk.Treeview(rows_pane, columns=rows_cols, show="headings", height=8, selectmode="extended")
    rows_tree.heading("id", text="#", command=lambda: sort_treeview(rows_tree, "id", state["sort_rows"]))
    rows_tree.heading("override", text="Priority", command=lambda: sort_treeview(rows_tree, "override", state["sort_rows"]))
    rows_tree.heading("voice", text="Assigned Sentence Voice", command=lambda: sort_treeview(rows_tree, "voice", state["sort_rows"]))
    rows_tree.heading("text", text="Sentence / Phrase Content", command=lambda: sort_treeview(rows_tree, "text", state["sort_rows"]))

    rows_tree.column("id", width=45, anchor="center")
    rows_tree.column("override", width=80, anchor="center")
    rows_tree.column("voice", width=250, anchor="w")
    rows_tree.column("text", width=620, anchor="w")

    rows_scroll = ttk.Scrollbar(rows_pane, orient="vertical", command=rows_tree.yview)
    rows_tree.configure(yscrollcommand=rows_scroll.set)
    rows_tree.pack(side="left", fill="both", expand=True)
    rows_scroll.pack(side="right", fill="y")

    # --------------------------------------------------------------------------
    # 3. BOTTOM ACTION BAR: Generation, Cancel, Open Folder
    # --------------------------------------------------------------------------
    action_bar = ttk.Frame(parent_frame)
    action_bar.pack(fill="x", padx=10, pady=5)

    gen_btn = ttk.Button(
        action_bar,
        text="🎙️ Generate Multi-File Dubbing (Zero-Click Auto-Save)",
        style="Accent.TButton",
        command=lambda: start_generation()
    )
    gen_btn.pack(side="left", padx=5)

    disable_chunks_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        action_bar,
        text="Disable Chunk Files",
        variable=disable_chunks_var
    ).pack(side="left", padx=(10, 5))

    cancel_btn = ttk.Button(action_bar, text="⏹ Cancel", state="disabled", command=lambda: request_cancel())
    cancel_btn.pack(side="right", padx=5)

    def open_current_folder():
        target = state["current_dir"]
        if os.path.exists(target):
            if os.name == 'nt':
                os.startfile(target)
            else:
                import subprocess
                subprocess.run(['xdg-open', target])

    ttk.Button(action_bar, text="📁 Open Directory", command=open_current_folder).pack(side="left", padx=5)

    # --------------------------------------------------------------------------
    # 4. VOICE UPDATE LOGIC & INITIAL SELECTION (SUPERTONIC_MALE_RANKED[0])
    # --------------------------------------------------------------------------
    def update_voices_dropdowns(event=None):
        cur_lang = lang_combo.get().split()[0]
        cat, vmap = get_all_available_voices(cur_lang)
        state["catalog"] = cat
        state["voice_map"] = vmap

        def_lbl, def_info = get_default_supertonic_voice(cat, vmap)
        state["default_voice_label"] = def_lbl
        state["default_voice_info"] = def_info

        file_voice_combo["values"] = cat
        if cat and not file_voice_combo.get():
            file_voice_combo.set(def_lbl)

        row_voice_combo["values"] = cat
        if cat and not row_voice_combo.get():
            row_voice_combo.set(def_lbl)

    lang_combo.bind("<<ComboboxSelected>>", lambda e: update_voices_dropdowns())
    update_voices_dropdowns()

    # --------------------------------------------------------------------------
    # 5. FILE LIST MANAGEMENT & PARSING
    # --------------------------------------------------------------------------
    def refresh_file_list():
        update_voices_dropdowns()
        folder = state["current_dir"]
        rec = recursive_var.get()
        found_paths = scan_target_files(folder, recursive=rec)

        new_files = {}
        for fp in found_paths:
            norm_p = os.path.normpath(fp)
            if norm_p in state["files"]:
                new_files[norm_p] = state["files"][norm_p]
            else:
                rel = os.path.relpath(norm_p, folder)
                s_list = extract_file_sentences(norm_p)
                sentences_data = []
                for s_idx, s_text in enumerate(s_list):
                    sentences_data.append({
                        "id": s_idx + 1,
                        "text": s_text,
                        "voice_label": state["default_voice_label"],
                        "voice_info": state["default_voice_info"],
                        "is_overridden": False
                    })
                new_files[norm_p] = {
                    "path": norm_p,
                    "relpath": rel,
                    "enabled": True,
                    "voice_label": state["default_voice_label"],
                    "voice_info": state["default_voice_info"],
                    "status": "Ready",
                    "sentences": sentences_data
                }

        state["files"] = new_files
        render_files_tree()

    def render_files_tree():
        for r in files_tree.get_children():
            files_tree.delete(r)

        for fp, fdata in state["files"].items():
            chk_icon = "☑ Yes" if fdata["enabled"] else "☐ No"
            tot_sents = len(fdata["sentences"])
            overridden_sents = sum(1 for s in fdata["sentences"] if s.get("is_overridden"))
            overridden_str = f"{overridden_sents}" if overridden_sents > 0 else "-"
            files_tree.insert(
                "",
                tk.END,
                iid=fp,
                values=(chk_icon, fdata["relpath"], fdata["voice_label"], tot_sents, overridden_str, fdata["status"])
            )

        if state["files"]:
            sel = files_tree.selection()
            if not sel or sel[0] not in state["files"]:
                first_key = next(iter(state["files"]))
                files_tree.selection_set(first_key)
                load_active_file_sentences(first_key)
        else:
            state["active_file"] = None
            render_rows_tree()

    def load_active_file_sentences(filepath):
        state["active_file"] = filepath
        fdata = state["files"].get(filepath)
        if fdata:
            rows_pane.config(text=f" 3. Sentence Voice Assignment: {fdata['relpath']} ({len(fdata['sentences'])} sentences) ")
        else:
            rows_pane.config(text=" 3. Sentence Voice Assignment (No file selected) ")
        render_rows_tree()

    def render_rows_tree():
        for r in rows_tree.get_children():
            rows_tree.delete(r)

        active = state["active_file"]
        if not active or active not in state["files"]:
            return

        fdata = state["files"][active]
        for s in fdata["sentences"]:
            override_disp = "★ Custom" if s.get("is_overridden") else "-"
            rows_tree.insert(
                "",
                tk.END,
                iid=str(s["id"]),
                values=(s["id"], override_disp, s["voice_label"], s["text"])
            )

    # --------------------------------------------------------------------------
    # 6. CHECKBOX / ENABLE TOGGLE LOGIC FOR FILES
    # --------------------------------------------------------------------------
    def toggle_file_check(filepath):
        if filepath in state["files"]:
            state["files"][filepath]["enabled"] = not state["files"][filepath]["enabled"]
            fdata = state["files"][filepath]
            chk_icon = "☑ Yes" if fdata["enabled"] else "☐ No"
            files_tree.set(filepath, "check", chk_icon)

    def set_all_files_checked(val):
        for fp, fdata in state["files"].items():
            fdata["enabled"] = val
            chk_icon = "☑ Yes" if val else "☐ No"
            if files_tree.exists(fp):
                files_tree.set(fp, "check", chk_icon)

    def toggle_selected_files_check():
        for item in files_tree.selection():
            toggle_file_check(item)

    def on_files_tree_click(event):
        region = files_tree.identify("region", event.x, event.y)
        if region == "heading":
            return
        item = files_tree.identify_row(event.y)
        col = files_tree.identify_column(event.x)
        if item:
            if col == "#1":
                toggle_file_check(item)
            load_active_file_sentences(item)

    files_tree.bind("<ButtonRelease-1>", on_files_tree_click)
    files_tree.bind("<space>", lambda e: toggle_selected_files_check())
    files_tree.bind("<<TreeviewSelect>>", lambda e: on_files_tree_select())

    def on_files_tree_select():
        sel = files_tree.selection()
        if sel:
            load_active_file_sentences(sel[0])

    # --------------------------------------------------------------------------
    # 7. VOICE ASSIGNMENT: FILE-LEVEL WITH OVERRIDE PRIORITY PROTECTION
    # --------------------------------------------------------------------------
    def apply_voice_to_selected_files():
        sel = files_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Select at least one file from the list.")
            return

        chosen = file_voice_combo.get()
        if not chosen:
            messagebox.showinfo("Voice", "Please select a voice from the dropdown list.")
            return

        chosen_info = state["voice_map"].get(
            chosen,
            {"type": "supertonic", "voice_id": "M5", "label": chosen}
        )

        for fp in sel:
            if fp not in state["files"]:
                continue
            fdata = state["files"][fp]
            fdata["voice_label"] = chosen
            fdata["voice_info"] = chosen_info

            # Crucial rule: update ONLY sentences that do NOT have a row-level override!
            for s in fdata["sentences"]:
                if not s.get("is_overridden"):
                    s["voice_label"] = chosen
                    s["voice_info"] = chosen_info

            files_tree.set(fp, "voice", chosen)

        if state["active_file"] in sel:
            render_rows_tree()

        log_cb(f"[Multi-Dub] Applied file voice '{chosen}' to {len(sel)} file(s). (Row-level overrides preserved)")

    # --------------------------------------------------------------------------
    # 8. VOICE ASSIGNMENT: ROW-LEVEL OVERRIDES & RESET BUTTONS
    # --------------------------------------------------------------------------
    def apply_voice_to_selected_rows():
        active = state["active_file"]
        if not active or active not in state["files"]:
            messagebox.showinfo("File", "Please select a file first.")
            return

        sel_rows = rows_tree.selection()
        if not sel_rows:
            messagebox.showinfo("Rows", "Select at least one sentence row (Shift/Ctrl multi-selection supported).")
            return

        chosen = row_voice_combo.get()
        if not chosen:
            messagebox.showinfo("Voice", "Please select a voice from the dropdown list.")
            return

        chosen_info = state["voice_map"].get(
            chosen,
            {"type": "supertonic", "voice_id": "M5", "label": chosen}
        )

        fdata = state["files"][active]
        s_map = {str(s["id"]): s for s in fdata["sentences"]}

        for r_id in sel_rows:
            if r_id in s_map:
                s = s_map[r_id]
                s["voice_label"] = chosen
                s["voice_info"] = chosen_info
                s["is_overridden"] = True
                rows_tree.item(r_id, values=(s["id"], "★ Custom", chosen, s["text"]))

        overridden_sents = sum(1 for s in fdata["sentences"] if s.get("is_overridden"))
        files_tree.set(active, "overridden", f"{overridden_sents}" if overridden_sents > 0 else "-")
        log_cb(f"[Multi-Dub] Assigned row voice '{chosen}' to {len(sel_rows)} sentence(s) in {fdata['relpath']}.")

    def reset_selected_rows():
        active = state["active_file"]
        if not active or active not in state["files"]:
            return

        sel_rows = rows_tree.selection()
        if not sel_rows:
            messagebox.showinfo("Rows", "Select at least one sentence row to reset.")
            return

        fdata = state["files"][active]
        s_map = {str(s["id"]): s for s in fdata["sentences"]}

        for r_id in sel_rows:
            if r_id in s_map:
                s = s_map[r_id]
                s["voice_label"] = fdata["voice_label"]
                s["voice_info"] = fdata["voice_info"]
                s["is_overridden"] = False
                rows_tree.item(r_id, values=(s["id"], "-", fdata["voice_label"], s["text"]))

        overridden_sents = sum(1 for s in fdata["sentences"] if s.get("is_overridden"))
        files_tree.set(active, "overridden", f"{overridden_sents}" if overridden_sents > 0 else "-")
        log_cb(f"[Multi-Dub] Reset {len(sel_rows)} sentence(s) back to file voice ({fdata['voice_label']}).")

    def reset_all_rows_of_active_file():
        active = state["active_file"]
        if not active or active not in state["files"]:
            return

        fdata = state["files"][active]
        for s in fdata["sentences"]:
            s["voice_label"] = fdata["voice_label"]
            s["voice_info"] = fdata["voice_info"]
            s["is_overridden"] = False

        render_rows_tree()
        files_tree.set(active, "overridden", "-")
        log_cb(f"[Multi-Dub] Reset all sentences of '{fdata['relpath']}' back to file default voice.")

    rows_tree.bind("<Control-a>", lambda e: rows_tree.selection_set(rows_tree.get_children()))
    rows_tree.bind("<Double-1>", lambda e: apply_voice_to_selected_rows())

    # --------------------------------------------------------------------------
    # 9. GENERATION LOGIC: MULTI-FILE SYNTHESIS & ZERO-CLICK SAVING
    # --------------------------------------------------------------------------
    def request_cancel():
        state["cancel_requested"] = True
        log_cb("[Multi-Dub] Cancellation requested by user...")

    def start_generation():
        enabled_files = [fdata for fdata in state["files"].values() if fdata["enabled"]]
        if not enabled_files:
            messagebox.showwarning("Notice", "No files selected for dubbing. Please mark [☑ Yes] next to files.")
            return

        gen_btn.config(state="disabled")
        cancel_btn.config(state="normal")
        state["cancel_requested"] = False
        state["is_generating"] = True

        threading.Thread(target=run_generation_task, args=(enabled_files,), daemon=True).start()

    def run_generation_task(files_to_dub):
        lang_code = lang_combo.get().split()[0].lower()
        speed = speed_combo.get().strip() or "1.0"
        disable_chunks = disable_chunks_var.get()

        total_files = len(files_to_dub)
        log_cb(f"[Multi-Dub] Starting multi-file dubbing for {total_files} file(s) (Language: {lang_code}, Speed: {speed})...")

        active_engine = DynamicDubbingEngine(target_lang=lang_code, engine_type="supertonic")

        try:
            for f_idx, fdata in enumerate(files_to_dub):
                if state["cancel_requested"]:
                    break

                fp = fdata["path"]
                rel = fdata["relpath"]
                sentences = fdata["sentences"]

                if not sentences:
                    log_cb(f"[Multi-Dub] Skipping empty file: {rel}")
                    fdata["status"] = "Empty"
                    root.after(0, lambda p=fp: files_tree.set(p, "status", "Empty"))
                    continue

                log_cb(f"[Multi-Dub] [{f_idx+1}/{total_files}] Processing '{rel}' ({len(sentences)} sentences)...")
                fdata["status"] = "Generating..."
                root.after(0, lambda p=fp: files_tree.set(p, "status", "Generating..."))

                base_name = os.path.splitext(os.path.basename(fp))[0]
                ts = time.strftime("%Y%m%d_%H%M%S")
                final_mp3 = os.path.join(SCRIPT_DIR, f"{base_name}_{ts}.mp3")

                def on_file_progress(done_s, tot_s, cur_f=f_idx):
                    overall_pct = int(((cur_f + done_s / max(1, tot_s)) / total_files) * 95)
                    if prog_var:
                        root.after(0, lambda v=overall_pct: prog_var.config(value=v))

                _, dur, cancelled = synthesize_narration_to_mp3(
                    sentence_items=sentences,
                    lang_code=lang_code,
                    output_mp3_path=final_mp3,
                    speed=speed,
                    pause_sec=0.05,
                    disable_chunks=disable_chunks,
                    active_engine=active_engine,
                    log_cb=log_cb,
                    progress_cb=on_file_progress,
                    cancel_check=lambda: state["cancel_requested"],
                    log_prefix="[Multi-Dub]"
                )

                if cancelled:
                    fdata["status"] = "Cancelled"
                    root.after(0, lambda p=fp: files_tree.set(p, "status", "Cancelled"))
                    break

                fdata["status"] = "Done"
                root.after(0, lambda p=fp: files_tree.set(p, "status", "Done"))
                log_cb(f"[Multi-Dub] Auto-saved dubbed MP3 ({dur:.1f} s): {final_mp3}")

            active_engine.unload_model()

            if state["cancel_requested"]:
                log_cb("[Multi-Dub] Generation was cancelled.")
                if prog_var:
                    root.after(0, lambda: prog_var.config(value=0))
            else:
                if prog_var:
                    root.after(0, lambda: prog_var.config(value=100))
                log_cb(f"[Multi-Dub] All selected files successfully dubbed!")
                messagebox.showinfo(
                    "Multi-File Dubbing Done",
                    f"Dubbing completed for {total_files} file(s)!\n\nAll output MP3s were auto-saved to:\n{SCRIPT_DIR}"
                )

        except Exception as e:
            log_cb(f"[Multi-Dub Error] {str(e)}")
            messagebox.showerror("Multi-File Dubbing Error", f"An error occurred during multi-file dubbing:\n{str(e)}")
        finally:
            active_engine.unload_model()
            state["is_generating"] = False
            root.after(0, lambda: gen_btn.config(state="normal"))
            root.after(0, lambda: cancel_btn.config(state="disabled"))

    # Initial automatic scan on startup
    refresh_file_list()

    return {
        "refresh_file_list": refresh_file_list,
        "update_voices": update_voices_dropdowns
    }
