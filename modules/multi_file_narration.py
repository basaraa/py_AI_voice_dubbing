"""
Multi-File Dubbing & Batch Narration Module (.txt / .srt)
---------------------------------------------------------
Backward-compatible wrapper re-exporting from modules.gui.tab2_multi_file.
"""

from modules.gui.tab2_multi_file import (
    get_default_supertonic_voice,
    extract_file_sentences,
    scan_target_files,
    create_tab2_multi_file as init_multi_file_narration_ui,
    create_tab2_multi_file
)

__all__ = [
    "get_default_supertonic_voice",
    "extract_file_sentences",
    "scan_target_files",
    "init_multi_file_narration_ui",
    "create_tab2_multi_file"
]
