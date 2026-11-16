# Codebase Architecture & File Map

Quick navigation map for codebase structure and module responsibilities.

---

## 1. Directory Tree

```text
py_AI_voice_dubbing/
├── py_ai_voice_dubbing.py          # App entry point (launches modules.gui.create_app())
├── AGENTS.md                       # Core system directives and developer rules
├── ARCHITECTURE.md                 # This navigation map
│
└── modules/
    ├── config.py                   # Hardware/thread limits, device setup, paths, voice rankings
    ├── audio_utils.py              # FFmpeg processing, silence trim, resampling, VRAM, voice catalog
    ├── subtitles.py                # SRT/VTT/ASS parsing, dialogue text extraction, sentence tokenizer
    ├── diarization.py              # Speaker segmentation, F0 pitch/gender analysis, voice matching
    ├── mixer.py                    # Audio mixer, Foley/SFX passthrough, ducking, video muxing
    ├── multi_file_narration.py     # Backward-compatible re-exporter for tab2_multi_file
    │
    ├── tts/                        # TTS ENGINES
    │   ├── __init__.py             # DynamicDubbingEngine + sample preview player
    │   ├── supertonic_engine.py    # Local ONNX Supertonic TTS (voices M1-M5, F1-F5)
    │   ├── edge_engine.py          # Microsoft Edge TTS online neural voices
    │   └── xtts_engine.py          # Local Coqui XTTS v2 voice cloning
    │
    └── gui/                        # PROCEDURAL TKINTER GUI
        ├── __init__.py             # create_app() - root window, theme, tabs & status bar assembly
        ├── status_log_panel.py     # Bottom shared panel (progress bar, status, VRAM, log box)
        ├── tab1_video_dubbing.py   # Tab 1: Video dubbing studio, diarization & dialogue tables, batch dub
        ├── tab2_narration_host.py  # Tab 2 Host: Radio switcher (Single Text vs Multi-File)
        ├── tab2_single_text.py     # Tab 2A: Single text/SRT narration & multi-voice sentence synthesis
        └── tab2_multi_file.py      # Tab 2B: Multi-file dubbing (.txt/.srt) with row override priority
```

---

## 2. Module Responsibilities Quick Lookup

| Task / Feature | File Location | Responsibility |
| :--- | :--- | :--- |
| **App Launch** | `py_ai_voice_dubbing.py` | Bootstraps GUI via `create_app().mainloop()`. |
| **Config & Voices** | `modules/config.py` | `SUPERTONIC_MALE_RANKED`, catalogs, thread-spin fixes, paths. |
| **Audio Operations** | `modules/audio_utils.py` | `convert_to_mp3_160k`, `trim_audio_silence`, voice list scanner. |
| **Subtitles & Text** | `modules/subtitles.py` | Clean dialogue extractor (`extract_clean_text_from_srt`), sentence tokenizer. |
| **Diarization** | `modules/diarization.py` | Speaker clustering, F0 pitch profiling, character assignments. |
| **Audio Mixing** | `modules/mixer.py` | BGM/Foley passthrough, anti-collision timeline alignment, video muxing. |
| **TTS Models** | `modules/tts/` | Engine loaders and synthesis logic for Supertonic, Edge, and XTTS. |
| **Main Window** | `modules/gui/__init__.py` | Creates root, registers cross-tab voice listeners, starts log queue. |
| **Status & Logs** | `modules/gui/status_log_panel.py` | Shared progress bar, VRAM indicator, scrolling log console. |
| **Tab 1: Video Dubbing** | `modules/gui/tab1_video_dubbing.py` | Full video dubbing UI and background processing tasks. |
| **Tab 2: Mode Switcher** | `modules/gui/tab2_narration_host.py`| Radiobox toggle between Single and Multi modes without state loss. |
| **Tab 2A: Single Text** | `modules/gui/tab2_single_text.py` | Single text/SRT input, phrase assignment table, MP3 generation. |
| **Tab 2B: Multi-File Dub** | `modules/gui/tab2_multi_file.py` | Folder file scanner (.txt/.srt), checkboxes, row overrides, auto-save. |
