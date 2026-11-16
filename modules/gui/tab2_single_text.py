"""
Tab 2A: Single Text Narration & Multi-Voice Speech Component
------------------------------------------------------------
Procedural component for single text narration in Tab 2.
- Language & default voice selection (Supertonic, Edge, Clone)
- Text editor with automatic sentence parsing and SRT timing cleanup
- Multi-voice phrase assignment with Ctrl/Shift extended selection
- Cached sentence synthesis and MP3 export
"""

import os
import re
import time
import math
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import soundfile as sf
import sounddevice as sd

from modules.config import (
    SCRIPT_DIR, VOICES_DIR, SAMPLE_RATE
)
from modules.audio_utils import (
    run_cmd, get_audio_duration, get_all_available_voices,
    get_or_create_reference_transcription, trim_audio_silence,
    convert_to_mp3_160k, sort_treeview
)
from modules.subtitles import extract_clean_text_from_srt, split_text_into_sentences_list
from modules.tts import DynamicDubbingEngine, play_any_voice_sample


def create_tab2_single_text(parent_frame, root, log_cb=print, prog_var=None, on_voice_added=None):
    """
    Procedurally creates the Single Text Narration UI inside parent_frame.
    """
    narr_state = {
        "cancel_requested": False,
        "last_mp3": ""
    }
    narr_phrases = []
    phrase_tree_sort_state = {"col": None, "reverse": False}
    voice_mapping_tab2 = {}

    # --------------------------------------------------------------------------
    # 1. TOP BAR: Language, Default Voice, Speed, Custom Voice
    # --------------------------------------------------------------------------
    narr_top = ttk.LabelFrame(parent_frame, text=" 1. Language & Default Voice (Supertonic, Edge & Clone) ", padding=8)
    narr_top.pack(fill="x", padx=10, pady=3)

    cfg_bar = ttk.Frame(narr_top)
    cfg_bar.pack(fill="x", pady=2)

    ttk.Label(cfg_bar, text="Language:").pack(side="left", padx=(5, 2))
    narr_lang_combo = ttk.Combobox(
        cfg_bar,
        values=["cs (Czech)", "sk (Slovak)", "ja (Japanese)", "en (English)", "de (German)", "pl (Polish)"],
        width=15,
        state="readonly"
    )
    narr_lang_combo.set("cs (Czech)")
    narr_lang_combo.pack(side="left", padx=2)

    ttk.Label(cfg_bar, text="Default Voice:").pack(side="left", padx=(12, 2))
    voice_combo = ttk.Combobox(cfg_bar, width=40, state="readonly")
    voice_combo.pack(side="left", padx=2)

    ttk.Label(cfg_bar, text="Speed:").pack(side="left", padx=(12, 2))
    speed_combo = ttk.Combobox(cfg_bar, values=["0.85", "0.90", "0.95", "1.0", "1.05", "1.10"], width=5)
    speed_combo.set("1.0")
    speed_combo.pack(side="left", padx=2)

    def update_narr_voices_dropdown(event=None):
        nonlocal voice_mapping_tab2
        cat, vmap = get_all_available_voices(narr_lang_combo.get().split()[0])
        voice_mapping_tab2 = vmap
        voice_combo['values'] = cat
        if cat and not voice_combo.get():
            voice_combo.set(cat[0])
        phrase_voice_combo['values'] = cat
        if cat and not phrase_voice_combo.get():
            phrase_voice_combo.set(cat[0])

    narr_lang_combo.bind(
        "<<ComboboxSelected>>",
        lambda e: [update_narr_voices_dropdown(), parse_and_update_tab2_phrases(force_default=False)]
    )

    btn_voice_row = ttk.Frame(narr_top)
    btn_voice_row.pack(fill="x", pady=(4, 2))

    def play_tab2_voice():
        chosen = voice_combo.get()
        if not chosen:
            messagebox.showwarning("Voice", "Please select a voice from the list.")
            return
        ok, msg = play_any_voice_sample(chosen, target_lang=narr_lang_combo.get().split()[0], log_cb=log_cb)
        if not ok:
            messagebox.showwarning("Upozornenie", msg)

    def add_custom_voice_tab2():
        fn = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav *.mp3 *.flac *.ogg *.m4a")])
        if fn:
            clean_name = os.path.splitext(os.path.basename(fn))[0] + ".wav"
            clean_wav = os.path.join(VOICES_DIR, clean_name)
            cmd = ["ffmpeg", "-y", "-i", fn, "-ar", str(SAMPLE_RATE), "-ac", "1", clean_wav]
            run_cmd(cmd)

            src_txt = os.path.splitext(fn)[0] + ".txt"
            if os.path.exists(src_txt):
                shutil.copy2(src_txt, os.path.splitext(clean_wav)[0] + ".txt")

            update_narr_voices_dropdown()
            if on_voice_added:
                on_voice_added()
            messagebox.showinfo("Success", f"Voice added to ./voices/{clean_name}")

    ttk.Button(btn_voice_row, text="▶ Preview Default Voice", command=play_tab2_voice).pack(side="left", padx=3)
    ttk.Button(btn_voice_row, text="➕ Add Custom Voice (.wav/.mp3)", command=add_custom_voice_tab2).pack(side="left", padx=3)
    ttk.Button(btn_voice_row, text="📁 Open voices/ Folder", command=lambda: os.startfile(VOICES_DIR) if os.name == 'nt' else subprocess.run(['xdg-open', VOICES_DIR])).pack(side="left", padx=3)

    # --------------------------------------------------------------------------
    # 2. MAIN TEXT INPUT
    # --------------------------------------------------------------------------
    narr_cfg = ttk.LabelFrame(parent_frame, text=" 2. Main Text Input ", padding=6)
    narr_cfg.pack(fill="x", padx=10, pady=3)

    def load_narr_file():
        fn = filedialog.askopenfilename(filetypes=[("Text & Subtitle Files", "*.txt *.srt *.vtt"), ("All Files", "*.*")])
        if fn:
            try:
                if fn.lower().endswith((".srt", ".vtt")):
                    content = extract_clean_text_from_srt(fn)
                else:
                    with open(fn, 'r', encoding='utf-8-sig', errors='replace') as f:
                        raw = f.read()
                    if re.search(r'\d+\s*\n\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}', raw) or '-->' in raw:
                        content = extract_clean_text_from_srt(raw)
                    else:
                        content = raw
                narr_text_box.delete("1.0", tk.END)
                narr_text_box.insert("1.0", content)
                parse_and_update_tab2_phrases(force_default=False)
            except Exception as e:
                messagebox.showwarning("Notice", f"Error: {e}")

    def clean_pasted_subtitles():
        current = narr_text_box.get("1.0", tk.END).strip()
        if '-->' in current:
            cleaned = extract_clean_text_from_srt(current)
            narr_text_box.delete("1.0", tk.END)
            narr_text_box.insert("1.0", cleaned)
            parse_and_update_tab2_phrases(force_default=False)
            messagebox.showinfo("Cleaned", "Subtitle timing and line numbers stripped successfully.")
        else:
            messagebox.showinfo("Notice", "No subtitle timestamps ('-->') detected in text.")

    top_txt_bar = ttk.Frame(narr_cfg)
    top_txt_bar.pack(fill="x", pady=2)
    ttk.Label(top_txt_bar, text="Type or paste text below (automatically split into sentences):").pack(side="left")
    btn_bar = ttk.Frame(top_txt_bar)
    btn_bar.pack(side="right")
    ttk.Button(btn_bar, text="🧹 Clean Timings", command=clean_pasted_subtitles).pack(side="left", padx=2)
    ttk.Button(btn_bar, text="📂 Load from File (.txt / .srt)", command=load_narr_file).pack(side="left", padx=2)

    narr_text_box = tk.Text(narr_cfg, height=5, wrap="word", font=("Segoe UI", 10))
    narr_text_box.pack(fill="both", expand=True, padx=4, pady=3)

    default_text = "Azeroth calls! Deep in the forests of Ashenvale, the drums of war thunder across the land! Thrall, Warchief of the Horde, rallies his fiercest champions at the gates of Orgrimmar!"
    narr_text_box.insert("1.0", default_text)

    # --------------------------------------------------------------------------
    # 3. SENTENCE LIST & PHRASE VOICE ASSIGNMENT
    # --------------------------------------------------------------------------
    narr_phrase_frame = ttk.LabelFrame(parent_frame, text=" 3. Multi-Voice Phrase Assignment (Ctrl/Shift selection, sortable columns) ", padding=6)
    narr_phrase_frame.pack(fill="both", expand=True, padx=10, pady=3)

    phrase_toolbar = ttk.Frame(narr_phrase_frame)
    phrase_toolbar.pack(fill="x", pady=(0, 4))

    ttk.Label(phrase_toolbar, text="Voice for selected phrases:").pack(side="left", padx=(2, 4))
    phrase_voice_combo = ttk.Combobox(phrase_toolbar, width=40, state="readonly")
    phrase_voice_combo.pack(side="left", padx=2)

    def parse_and_update_tab2_phrases(force_default=False):
        raw_text = narr_text_box.get("1.0", tk.END).strip()
        if not raw_text:
            narr_phrases.clear()
            for r in phrase_tree.get_children():
                phrase_tree.delete(r)
            return

        sentences = split_text_into_sentences_list(raw_text)
        cur_cat, cur_map = get_all_available_voices(narr_lang_combo.get().split()[0])
        def_label = voice_combo.get()
        if not def_label and cur_cat:
            def_label = cur_cat[0]
        def_info = cur_map.get(def_label, {"type": "supertonic", "voice_id": "M1", "label": def_label})

        old_by_idx = {i: p for i, p in enumerate(narr_phrases)}
        old_by_text = {p["text"].strip(): p for p in narr_phrases}

        new_phrases = []
        for idx, s in enumerate(sentences):
            s_clean = s.strip()
            v_label = def_label
            v_info = def_info

            if not force_default:
                if idx in old_by_idx and old_by_idx[idx]["text"].strip() == s_clean:
                    v_label = old_by_idx[idx]["voice_label"]
                    v_info = old_by_idx[idx]["voice_info"]
                elif s_clean in old_by_text:
                    v_label = old_by_text[s_clean]["voice_label"]
                    v_info = old_by_text[s_clean]["voice_info"]

            new_phrases.append({
                "id": idx + 1,
                "text": s_clean,
                "voice_label": v_label,
                "voice_info": v_info
            })

        narr_phrases.clear()
        narr_phrases.extend(new_phrases)

        for r in phrase_tree.get_children():
            phrase_tree.delete(r)

        for p in narr_phrases:
            phrase_tree.insert("", tk.END, iid=str(p["id"]), values=(p["id"], p["voice_label"], p["text"]))

    def assign_voice_to_selected_phrases():
        sel = phrase_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Select at least one sentence from the table (Ctrl/Shift selection supported).")
            return
        chosen = phrase_voice_combo.get()
        if not chosen:
            messagebox.showinfo("Voice", "Please select a voice from the dropdown list.")
            return

        cur_cat, cur_map = get_all_available_voices(narr_lang_combo.get().split()[0])
        chosen_info = cur_map.get(chosen, {"type": "supertonic", "voice_id": "M1", "label": chosen})

        phrase_dict = {str(p["id"]): p for p in narr_phrases}
        for item_id in sel:
            if str(item_id) in phrase_dict:
                phrase_dict[str(item_id)]["voice_label"] = chosen
                phrase_dict[str(item_id)]["voice_info"] = chosen_info
            phrase_tree.set(item_id, "voice", chosen)

        log_cb(f"[Narration] Voice '{chosen}' assigned to {len(sel)} sentences.")

    def reset_all_phrases_to_default():
        parse_and_update_tab2_phrases(force_default=True)
        log_cb("[Narration] Default voice applied to all sentences.")

    def play_tab2_phrase_voice_preview():
        chosen = phrase_voice_combo.get()
        if not chosen:
            messagebox.showinfo("Voice", "Please select a voice from the dropdown list.")
            return
        ok, msg = play_any_voice_sample(chosen, target_lang=narr_lang_combo.get().split()[0], log_cb=log_cb)
        if not ok:
            messagebox.showwarning("Upozornenie", msg)

    ttk.Button(phrase_toolbar, text="✓ Apply to Selected (Ctrl/Shift)", style="Accent.TButton", command=assign_voice_to_selected_phrases).pack(side="left", padx=4)
    ttk.Button(phrase_toolbar, text="🔄 Parse Sentences", command=lambda: parse_and_update_tab2_phrases(force_default=False)).pack(side="left", padx=3)
    ttk.Button(phrase_toolbar, text="↺ Reset All to Default", command=reset_all_phrases_to_default).pack(side="left", padx=3)
    ttk.Button(phrase_toolbar, text="▶ Preview Voice", command=play_tab2_phrase_voice_preview).pack(side="left", padx=3)
    ttk.Button(phrase_toolbar, text="Select All", command=lambda: phrase_tree.selection_set(phrase_tree.get_children())).pack(side="left", padx=3)

    phrase_columns = ("id", "voice", "text")
    phrase_tree = ttk.Treeview(narr_phrase_frame, columns=phrase_columns, show="headings", height=8, selectmode="extended")
    phrase_tree.heading("id", text="#", command=lambda: sort_treeview(phrase_tree, "id", phrase_tree_sort_state))
    phrase_tree.heading("voice", text="Assigned Voice", command=lambda: sort_treeview(phrase_tree, "voice", phrase_tree_sort_state))
    phrase_tree.heading("text", text="Sentence / Phrase Text", command=lambda: sort_treeview(phrase_tree, "text", phrase_tree_sort_state))

    phrase_tree.column("id", width=45, anchor="center")
    phrase_tree.column("voice", width=260, anchor="w")
    phrase_tree.column("text", width=680, anchor="w")

    phrase_tree.pack(side="left", fill="both", expand=True)
    phrase_scroll = ttk.Scrollbar(narr_phrase_frame, orient="vertical", command=phrase_tree.yview)
    phrase_tree.configure(yscrollcommand=phrase_scroll.set)
    phrase_scroll.pack(side="right", fill="y")

    phrase_tree.bind("<Control-a>", lambda e: phrase_tree.selection_set(phrase_tree.get_children()))
    phrase_tree.bind("<Double-1>", lambda e: assign_voice_to_selected_phrases())

    _typing_timer = None
    def on_narr_text_modified(event=None):
        nonlocal _typing_timer
        if _typing_timer is not None:
            root.after_cancel(_typing_timer)
        _typing_timer = root.after(700, lambda: parse_and_update_tab2_phrases(force_default=False))

    narr_text_box.bind("<KeyRelease>", on_narr_text_modified)

    # --------------------------------------------------------------------------
    # 4. BOTTOM ACTIONS & SPEECH GENERATION WORKER
    # --------------------------------------------------------------------------
    narr_action_f = ttk.Frame(parent_frame)
    narr_action_f.pack(fill="x", padx=10, pady=5)

    narr_gen_btn = ttk.Button(narr_action_f, text="🎙️ Generate Speech (MP3 160 kbps)", style="Accent.TButton")
    narr_gen_btn.pack(side="left", padx=5)

    narr_play_out_btn = ttk.Button(narr_action_f, text="▶ Play Generated MP3", state="disabled")
    narr_play_out_btn.pack(side="left", padx=5)

    narr_save_btn = ttk.Button(narr_action_f, text="💾 Save MP3 As...", state="disabled")
    narr_save_btn.pack(side="left", padx=5)

    narr_cancel_btn = ttk.Button(narr_action_f, text="⏹ Cancel", state="disabled")
    narr_cancel_btn.pack(side="right", padx=5)

    def task_generate_narration():
        try:
            lang_code = narr_lang_combo.get().split()[0].lower()
            speed = speed_combo.get().strip() or "1.0"

            if not narr_phrases:
                parse_and_update_tab2_phrases(force_default=False)

            if not narr_phrases:
                messagebox.showerror("Error", "Input text is empty!")
                return

            narr_gen_btn.config(state="disabled")
            narr_cancel_btn.config(state="normal")
            narr_play_out_btn.config(state="disabled")
            narr_save_btn.config(state="disabled")
            narr_state["cancel_requested"] = False
            if prog_var:
                prog_var.config(value=5)

            log_cb(f"[Narration] Starting multi-voice narration ({len(narr_phrases)} sentences, Language: {lang_code})...")

            temp_narr_dir = os.path.join(SCRIPT_DIR, "output_narration")
            os.makedirs(temp_narr_dir, exist_ok=True)

            tot = len(narr_phrases)
            audio_pieces = []
            OUTPUT_SR = 44100
            silence_sentence = np.zeros(int(OUTPUT_SR * 0.05), dtype=np.float32)

            active_engine_obj = DynamicDubbingEngine(target_lang=lang_code, engine_type="supertonic")

            for idx, item in enumerate(narr_phrases):
                if narr_state["cancel_requested"]:
                    break

                chunk_text = item["text"].strip()
                v_info = item["voice_info"]
                v_type = v_info.get("type", "supertonic")
                v_id = v_info.get("voice_id")
                ref_wav = v_info.get("path") if v_type == "clone" else None

                if ref_wav and os.path.exists(ref_wav):
                    get_or_create_reference_transcription(ref_wav, log_cb=log_cb)

                tmp_piece = os.path.join(temp_narr_dir, f"chunk_{idx:04d}.wav")
                tmp_txt = os.path.join(temp_narr_dir, f"chunk_{idx:04d}.txt")

                voice_sig = f"[{v_type}:{v_id or os.path.basename(ref_wav or '')}:{speed}]"
                expected_cache = f"{voice_sig}\n{chunk_text}".strip()

                cache_valid = False
                if os.path.exists(tmp_piece) and os.path.getsize(tmp_piece) > 1000 and os.path.exists(tmp_txt):
                    try:
                        with open(tmp_txt, "r", encoding="utf-8-sig") as f:
                            if f.read().strip() == expected_cache:
                                cache_valid = True
                    except Exception:
                        cache_valid = False

                if cache_valid:
                    log_cb(f"[Narration] ({idx+1}/{tot}) Using cached chunk ({item['voice_label'][:20]}): '{chunk_text[:35]}...'")
                else:
                    log_cb(f"[Narration] ({idx+1}/{tot}) Synthesizing [{item['voice_label'][:25]}]: '{chunk_text[:35]}...'")
                    active_engine_obj.generate_speech(
                        text=chunk_text,
                        spk_id="Narrator",
                        ref_voice_wav=ref_wav,
                        output_wav_path=tmp_piece,
                        target_duration=None,
                        log_cb=log_cb,
                        explicit_voice=v_id,
                        explicit_engine=v_type
                    )
                    with open(tmp_txt, "w", encoding="utf-8") as f:
                        f.write(expected_cache + "\n")

                if os.path.exists(tmp_piece) and os.path.getsize(tmp_piece) > 1000:
                    data, piece_sr = sf.read(tmp_piece)
                    if len(data.shape) > 1:
                        data = np.mean(data, axis=1)
                    data = trim_audio_silence(data, piece_sr, db_thresh=30)

                    if piece_sr != OUTPUT_SR:
                        import scipy.signal
                        g = math.gcd(int(OUTPUT_SR), int(piece_sr))
                        up = int(OUTPUT_SR) // g
                        down = int(piece_sr) // g
                        data = scipy.signal.resample_poly(data, up, down)

                    audio_pieces.append(data.astype(np.float32))
                    audio_pieces.append(silence_sentence)

                if prog_var:
                    prog_var.config(value=int(10 + (idx + 1) / max(1, tot) * 80))

            active_engine_obj.unload_model()

            if narr_state["cancel_requested"]:
                log_cb("[Narration] Generation was cancelled.")
                return

            if not audio_pieces:
                raise RuntimeError("Nepodarilo sa vytvoriť zvukovú stopu.")

            combined = np.concatenate(audio_pieces)
            max_v = np.max(np.abs(combined))
            if max_v > 0:
                combined = (combined / max_v) * 0.92

            master_wav = os.path.join(temp_narr_dir, "master_narration.wav")
            sf.write(master_wav, combined, OUTPUT_SR)

            ts = time.strftime("%Y%m%d_%H%M%S")
            final_mp3 = os.path.join(temp_narr_dir, f"narration_{lang_code}_{ts}.mp3")
            convert_to_mp3_160k(master_wav, final_mp3)

            narr_state["last_mp3"] = final_mp3
            if prog_var:
                prog_var.config(value=100)
            narr_play_out_btn.config(state="normal")
            narr_save_btn.config(state="normal")

            dur = get_audio_duration(final_mp3)
            log_cb(f"[Done] MP3 audio ready ({dur:.1f} s).")
            messagebox.showinfo("Done", f"Narration successfully generated!\n\nDuration: {dur:.1f} s\nFile: {final_mp3}")

        except Exception as e:
            log_cb(f"[ERROR] {str(e)}")
            messagebox.showerror("Error", f"Error during speech generation:\n{str(e)}")
        finally:
            narr_gen_btn.config(state="normal")
            narr_cancel_btn.config(state="disabled")

    def play_narr_output():
        if narr_state["last_mp3"] and os.path.exists(narr_state["last_mp3"]):
            data, sr = sf.read(narr_state["last_mp3"])
            sd.stop()
            sd.play(data, sr)

    def save_narr_output():
        if not (narr_state["last_mp3"] and os.path.exists(narr_state["last_mp3"])):
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 Audio", "*.mp3"), ("All Files", "*.*")],
            initialfile=os.path.basename(narr_state["last_mp3"])
        )
        if dest:
            shutil.copy2(narr_state["last_mp3"], dest)
            log_cb(f"[Saved] Narration saved to: {dest}")
            messagebox.showinfo("Saved", f"File saved:\n{dest}")

    narr_gen_btn.config(command=lambda: threading.Thread(target=task_generate_narration, daemon=True).start())
    narr_cancel_btn.config(command=lambda: narr_state.update({"cancel_requested": True}))
    narr_play_out_btn.config(command=play_narr_output)
    narr_save_btn.config(command=save_narr_output)

    # Initial setup
    update_narr_voices_dropdown()
    parse_and_update_tab2_phrases(force_default=False)

    return {
        "update_voices": update_narr_voices_dropdown,
        "parse_phrases": parse_and_update_tab2_phrases
    }
