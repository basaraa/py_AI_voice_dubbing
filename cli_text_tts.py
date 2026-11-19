"""
CLI Text-to-Speech Generator (Tab 2 Only)
-----------------------------------------
Standalone procedural CLI entry point for Tab 2 text narration & multi-file
.txt/.srt/.vtt speech synthesis. Strictly text-to-speech only (no video dubbing).

Examples:
    python cli_text_tts.py --list-voices --lang cs
    python cli_text_tts.py --text "Ahoj, toto je test." --lang sk --voice M5
    python cli_text_tts.py --input test1.txt test2.txt --lang cs --voice F1 --json
"""

import os
import re
import sys
import json
import time
import argparse

from modules.config import (
    SCRIPT_DIR, SUPERTONIC_MALE_RANKED
)
from modules.audio_utils import get_all_available_voices
from modules.subtitles import extract_clean_text_from_srt, split_text_into_sentences_list
from modules.narration_core import synthesize_narration_to_mp3


ALLOWED_TEXT_EXTENSIONS = (".txt", ".srt", ".vtt")
SUPPORTED_LANGUAGES = ("cs", "sk", "ja", "en", "de", "pl")


def validate_safe_path(target_path, base_dir=SCRIPT_DIR):
    """
    Validates that target_path resolves strictly inside base_dir (path traversal guard).
    """
    real_base = os.path.realpath(base_dir)
    real_target = os.path.realpath(target_path)
    try:
        common = os.path.commonpath([real_base, real_target])
    except ValueError as exc:
        raise ValueError(f"Invalid path '{target_path}': {exc}") from exc
    if common != real_base:
        raise ValueError(
            f"Path '{target_path}' resolves outside the allowed workspace directory '{real_base}'."
        )
    return real_target


def resolve_cli_voice(voice_arg, lang_code):
    """
    Resolves a CLI --voice argument (ID, short name, or full label) to (voice_label, voice_info).
    Defaults to SUPERTONIC_MALE_RANKED[0] (e.g. M5) if voice_arg is omitted.
    """
    catalog, voice_map = get_all_available_voices(lang_code)
    if not catalog:
        raise RuntimeError("No TTS voices are available.")

    query = (voice_arg or "").strip()
    if not query:
        default_id = SUPERTONIC_MALE_RANKED[0] if SUPERTONIC_MALE_RANKED else "M5"
        for label, info in voice_map.items():
            if info.get("type") == "supertonic" and info.get("voice_id") == default_id:
                return label, info
        first_label = catalog[0]
        return first_label, voice_map[first_label]

    # 1. Exact label match
    if query in voice_map:
        return query, voice_map[query]

    q_lower = query.lower()
    q_stem = os.path.splitext(q_lower)[0]

    # 2. Exact voice_id match (e.g., "M5", "cs-CZ-AntoninNeural", "custom_name")
    for label, info in voice_map.items():
        vid = str(info.get("voice_id", "")).lower()
        if vid == q_lower or vid == q_stem:
            return label, info

    # 3. Case-insensitive substring match against label or voice_id
    for label, info in voice_map.items():
        vid = str(info.get("voice_id", "")).lower()
        if q_lower in label.lower() or q_lower in vid:
            return label, info

    raise ValueError(
        f"Voice '{voice_arg}' not found for language '{lang_code}'. "
        f"Run with --list-voices --lang {lang_code} to see available voices."
    )


def extract_sentences_from_input(raw_text=None, file_path=None):
    """
    Extracts clean sentences from either raw text or a .txt/.srt/.vtt file.
    Strictly rejects non-text/video files.
    """
    if file_path is not None:
        safe_path = validate_safe_path(file_path, SCRIPT_DIR)
        if not os.path.isfile(safe_path):
            raise FileNotFoundError(f"Input file not found: {file_path}")

        ext = os.path.splitext(safe_path)[1].lower()
        if ext not in ALLOWED_TEXT_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}' for '{file_path}'. "
                f"This CLI only supports text/subtitle files ({', '.join(ALLOWED_TEXT_EXTENSIONS)}), not video/audio."
            )

        if ext in (".srt", ".vtt"):
            clean_text = extract_clean_text_from_srt(safe_path)
        else:
            with open(safe_path, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()
            if "-->" in content or re.search(
                r"\d+\s*\n\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}",
                content
            ):
                clean_text = extract_clean_text_from_srt(content)
            else:
                clean_text = content
    else:
        content = raw_text or ""
        if "-->" in content or re.search(
            r"\d+\s*\n\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}",
            content
        ):
            clean_text = extract_clean_text_from_srt(content)
        else:
            clean_text = content

    return split_text_into_sentences_list(clean_text)


def build_output_mp3_path(base_name, explicit_output=None):
    """
    Builds the output MP3 path in SCRIPT_DIR with timestamp, or validates an explicit path.
    """
    if explicit_output:
        safe_out = validate_safe_path(explicit_output, SCRIPT_DIR)
        if not safe_out.lower().endswith(".mp3"):
            safe_out += ".mp3"
        parent = os.path.dirname(safe_out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return safe_out

    ts = time.strftime("%Y%m%d_%H%M%S")
    clean_base = re.sub(r"[^\w\-]+", "_", base_name).strip("_") or "narration"
    return os.path.join(SCRIPT_DIR, f"{clean_base}_{ts}.mp3")


def synthesize_sentences_to_mp3(
    sentences,
    lang_code,
    voice_label,
    voice_info,
    speed,
    pause_sec,
    output_mp3_path,
    disable_chunks=True,
    log_cb=print
):
    """
    Synthesizes a list of sentences into a single normalized 160 kbps MP3 file
    via the shared Tab 2 narration core.
    """
    sentence_items = [
        {
            "text": s,
            "voice_label": voice_label,
            "voice_info": voice_info
        }
        for s in sentences if s and s.strip()
    ]
    final_mp3, dur, _ = synthesize_narration_to_mp3(
        sentence_items=sentence_items,
        lang_code=lang_code,
        output_mp3_path=output_mp3_path,
        speed=speed,
        pause_sec=pause_sec,
        disable_chunks=disable_chunks,
        log_cb=log_cb,
        log_prefix="[CLI-TTS]"
    )
    return final_mp3, dur


def print_available_voices(lang_code, as_json=False):
    """
    Prints all available Supertonic, Edge, and custom cloned voices for lang_code.
    """
    catalog, voice_map = get_all_available_voices(lang_code)
    if as_json:
        payload = {
            "lang": lang_code,
            "voices": [
                {
                    "label": label,
                    "type": voice_map[label].get("type"),
                    "voice_id": voice_map[label].get("voice_id")
                }
                for label in catalog
            ]
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"Available voices for language '{lang_code}':")
    for label in catalog:
        info = voice_map[label]
        print(f"  - {info.get('voice_id')}  ({info.get('type')}) -> {label}")


def parse_cli_args(argv=None):
    """
    Parses command-line arguments for Tab 2 text-to-speech CLI.
    """
    parser = argparse.ArgumentParser(
        description="CLI Text-to-Speech Generator (Tab 2 only: text, .txt, .srt, .vtt -> MP3). Video dubbing is not supported."
    )
    parser.add_argument("-t", "--text", type=str, help="Direct text string to synthesize.")
    parser.add_argument(
        "-i", "--input", nargs="+",
        help="One or more .txt, .srt, or .vtt files inside the workspace."
    )
    parser.add_argument(
        "-l", "--lang", type=str, default="cs", choices=SUPPORTED_LANGUAGES,
        help="Target language code (default: cs)."
    )
    parser.add_argument(
        "-v", "--voice", type=str, default="",
        help="Voice ID or label (e.g. M5, F1, cs-CZ-AntoninNeural, or custom clone name). Defaults to M5."
    )
    parser.add_argument(
        "-s", "--speed", type=float, default=1.0,
        help="Speech speed multiplier (default: 1.0)."
    )
    parser.add_argument(
        "--pause", type=float, default=0.05,
        help="Silence pause between sentences in seconds (default: 0.05)."
    )
    parser.add_argument(
        "-o", "--output", type=str, default=None,
        help="Optional output .mp3 path (only for single --text or single --input). Defaults to auto-saved timestamped MP3 in root."
    )
    parser.add_argument(
        "--list-voices", action="store_true",
        help="List available voices for --lang and exit."
    )
    parser.add_argument(
        "--keep-chunks", action="store_true",
        help="Keep persistent chunk_*.wav/txt cache files in output_narration/ (disabled by default)."
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Alias: chunk files are already disabled by default unless --keep-chunks is passed."
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print machine-readable JSON summary to stdout (logs go to stderr)."
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress logs."
    )
    return parser.parse_args(argv)


def main(argv=None):
    """
    Main procedural CLI entry point.
    """
    args = parse_cli_args(argv)
    lang_code = args.lang.lower()

    if args.list_voices:
        print_available_voices(lang_code, as_json=args.json)
        return 0

    if not args.text and not args.input:
        sys.stderr.write("Error: Provide either --text or --input (.txt/.srt/.vtt), or use --list-voices.\n")
        return 2

    if args.text and args.input:
        sys.stderr.write("Error: Provide either --text or --input, not both.\n")
        return 2

    if args.output and args.input and len(args.input) > 1:
        sys.stderr.write("Error: --output cannot be used with multiple --input files.\n")
        return 2

    def log_cb(msg):
        if args.quiet:
            return
        stream = sys.stderr if args.json else sys.stdout
        stream.write(str(msg) + "\n")
        stream.flush()

    try:
        voice_label, voice_info = resolve_cli_voice(args.voice, lang_code)
        results = []

        disable_chunks = (not args.keep_chunks) or args.no_cache

        if args.text:
            sentences = extract_sentences_from_input(raw_text=args.text)
            out_path = build_output_mp3_path(f"narration_{lang_code}", args.output)
            final_mp3, dur = synthesize_sentences_to_mp3(
                sentences=sentences,
                lang_code=lang_code,
                voice_label=voice_label,
                voice_info=voice_info,
                speed=args.speed,
                pause_sec=args.pause,
                output_mp3_path=out_path,
                disable_chunks=disable_chunks,
                log_cb=log_cb
            )
            results.append({
                "source": "inline_text",
                "output": final_mp3,
                "duration_sec": round(dur, 2),
                "sentences": len(sentences)
            })
            log_cb(f"[CLI-TTS] Done ({dur:.1f} s): {final_mp3}")
        else:
            for file_path in args.input:
                sentences = extract_sentences_from_input(file_path=file_path)
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                out_path = build_output_mp3_path(base_name, args.output)
                final_mp3, dur = synthesize_sentences_to_mp3(
                    sentences=sentences,
                    lang_code=lang_code,
                    voice_label=voice_label,
                    voice_info=voice_info,
                    speed=args.speed,
                    pause_sec=args.pause,
                    output_mp3_path=out_path,
                    disable_chunks=disable_chunks,
                    log_cb=log_cb
                )
                results.append({
                    "source": os.path.realpath(file_path),
                    "output": final_mp3,
                    "duration_sec": round(dur, 2),
                    "sentences": len(sentences)
                })
                log_cb(f"[CLI-TTS] Done ({dur:.1f} s): {final_mp3}")

        if args.json:
            print(json.dumps({
                "status": "ok",
                "lang": lang_code,
                "voice": voice_info.get("voice_id"),
                "voice_type": voice_info.get("type"),
                "outputs": results
            }, ensure_ascii=False, indent=2))

        return 0
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            sys.stderr.write(f"[CLI-TTS Error] {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
