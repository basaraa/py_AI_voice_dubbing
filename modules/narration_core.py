"""
Shared Tab 2 Narration Synthesis Core (Procedural)
--------------------------------------------------
Single shared implementation for Tab 2A (Single Text), Tab 2B (Multi-File),
and cli_text_tts.py (CLI). Strictly for text/subtitle-to-MP3 synthesis.
"""

import os
import math
import time
import hashlib
import tempfile
import numpy as np
import soundfile as sf

from modules.config import SCRIPT_DIR
from modules.audio_utils import (
    trim_audio_silence,
    convert_to_mp3_160k,
    get_audio_duration,
    get_or_create_reference_transcription
)
from modules.tts import DynamicDubbingEngine


def synthesize_narration_to_mp3(
    sentence_items,
    lang_code,
    output_mp3_path,
    speed=1.0,
    pause_sec=0.05,
    disable_chunks=True,
    active_engine=None,
    log_cb=print,
    progress_cb=None,
    cancel_check=None,
    log_prefix="[Narration]"
):
    """
    Synthesizes a list of sentence items into a single normalized 160 kbps MP3 file.

    Each item in sentence_items must be a dict with:
        - "text": str
        - "voice_info": dict (keys: type, voice_id, path optional)
        - "voice_label": str (optional, for logging)

    When disable_chunks is True (default/preferred), no persistent chunk_*.wav or
    chunk_*.txt files are generated or kept on disk; each sentence uses an ephemeral
    temp WAV that is deleted immediately after loading into memory.

    Returns (output_mp3_path, duration_sec, cancelled).
    """
    if not sentence_items:
        raise ValueError("No non-empty sentences found to synthesize.")

    output_sr = 44100
    pause_samples = max(0, int(output_sr * max(0.0, float(pause_sec))))
    silence_sentence = np.zeros(pause_samples, dtype=np.float32)
    speed_val = float(speed) if speed else 1.0

    temp_narr_dir = os.path.join(SCRIPT_DIR, "output_narration")
    if not disable_chunks:
        os.makedirs(temp_narr_dir, exist_ok=True)

    owns_engine = active_engine is None
    if owns_engine:
        active_engine = DynamicDubbingEngine(target_lang=lang_code, engine_type="supertonic")

    audio_pieces = []
    tot_s = len(sentence_items)
    cancelled = False

    try:
        for idx, item in enumerate(sentence_items):
            if cancel_check and cancel_check():
                cancelled = True
                break

            chunk_text = (item.get("text") or "").strip()
            if not chunk_text:
                if progress_cb:
                    progress_cb(idx + 1, tot_s)
                continue

            v_info = item.get("voice_info") or {}
            v_type = v_info.get("type", "supertonic")
            v_id = v_info.get("voice_id")
            v_label = item.get("voice_label") or str(v_id or v_type)
            ref_wav = v_info.get("path") if v_type == "clone" else None

            if ref_wav and os.path.exists(ref_wav):
                get_or_create_reference_transcription(ref_wav, log_cb=log_cb)

            if disable_chunks:
                fd, tmp_piece = tempfile.mkstemp(prefix="tts_ephemeral_", suffix=".wav")
                os.close(fd)
                try:
                    log_cb(
                        f"{log_prefix} ({idx + 1}/{tot_s}) Synthesizing [{v_label[:25]}]: '{chunk_text[:35]}...'"
                    )
                    active_engine.generate_speech(
                        text=chunk_text,
                        spk_id="Narrator",
                        ref_voice_wav=ref_wav,
                        output_wav_path=tmp_piece,
                        target_duration=None,
                        log_cb=log_cb,
                        explicit_voice=v_id,
                        explicit_engine=v_type,
                        speed=speed_val
                    )
                    if os.path.exists(tmp_piece) and os.path.getsize(tmp_piece) > 1000:
                        data, piece_sr = sf.read(tmp_piece)
                        audio_pieces.extend(
                            _process_piece_audio(data, piece_sr, output_sr, silence_sentence, pause_samples)
                        )
                finally:
                    if os.path.exists(tmp_piece):
                        try:
                            os.remove(tmp_piece)
                        except OSError:
                            pass
            else:
                voice_sig = f"[{v_type}:{v_id or os.path.basename(ref_wav or '')}:{speed_val}:{lang_code}]"
                cache_content = f"{voice_sig}\n{chunk_text}".strip()
                cache_hash = hashlib.md5(cache_content.encode("utf-8")).hexdigest()[:16]

                tmp_piece = os.path.join(temp_narr_dir, f"chunk_{cache_hash}.wav")
                tmp_txt = os.path.join(temp_narr_dir, f"chunk_{cache_hash}.txt")

                cache_valid = False
                if os.path.exists(tmp_piece) and os.path.getsize(tmp_piece) > 1000 and os.path.exists(tmp_txt):
                    try:
                        with open(tmp_txt, "r", encoding="utf-8-sig") as cf:
                            if cf.read().strip() == cache_content:
                                cache_valid = True
                    except Exception:
                        cache_valid = False

                if cache_valid:
                    log_cb(
                        f"{log_prefix} ({idx + 1}/{tot_s}) Using cached chunk ({v_label[:20]}): '{chunk_text[:35]}...'"
                    )
                else:
                    log_cb(
                        f"{log_prefix} ({idx + 1}/{tot_s}) Synthesizing [{v_label[:25]}]: '{chunk_text[:35]}...'"
                    )
                    active_engine.generate_speech(
                        text=chunk_text,
                        spk_id="Narrator",
                        ref_voice_wav=ref_wav,
                        output_wav_path=tmp_piece,
                        target_duration=None,
                        log_cb=log_cb,
                        explicit_voice=v_id,
                        explicit_engine=v_type,
                        speed=speed_val
                    )
                    try:
                        with open(tmp_txt, "w", encoding="utf-8") as cf:
                            cf.write(cache_content + "\n")
                    except Exception:
                        pass

                if os.path.exists(tmp_piece) and os.path.getsize(tmp_piece) > 1000:
                    data, piece_sr = sf.read(tmp_piece)
                    audio_pieces.extend(
                        _process_piece_audio(data, piece_sr, output_sr, silence_sentence, pause_samples)
                    )

            if progress_cb:
                progress_cb(idx + 1, tot_s)

        if cancelled:
            return None, 0.0, True

        if not audio_pieces:
            raise RuntimeError("Failed to generate any audio chunks.")

        combined = np.concatenate(audio_pieces)
        max_v = np.max(np.abs(combined))
        if max_v > 0:
            combined = (combined / max_v) * 0.92

        fd_m, master_wav = tempfile.mkstemp(prefix="tts_master_", suffix=".wav")
        os.close(fd_m)
        try:
            sf.write(master_wav, combined, output_sr)
            out_parent = os.path.dirname(os.path.abspath(output_mp3_path))
            if out_parent:
                os.makedirs(out_parent, exist_ok=True)
            convert_to_mp3_160k(master_wav, output_mp3_path)
        finally:
            if os.path.exists(master_wav):
                try:
                    os.remove(master_wav)
                except OSError:
                    pass

        dur = get_audio_duration(output_mp3_path)
        return output_mp3_path, dur, False
    finally:
        if owns_engine:
            active_engine.unload_model()


def _process_piece_audio(data, piece_sr, output_sr, silence_sentence, pause_samples):
    """
    Normalizes a synthesized sentence waveform to mono float32, trims silence,
    resamples to output_sr if needed, and appends trailing pause.
    """
    if len(data.shape) > 1:
        data = np.mean(data, axis=1)
    data = trim_audio_silence(data, piece_sr, db_thresh=30)

    if piece_sr != output_sr:
        import scipy.signal
        g = math.gcd(int(output_sr), int(piece_sr))
        up = int(output_sr) // g
        down = int(piece_sr) // g
        data = scipy.signal.resample_poly(data, up, down)

    pieces = [data.astype(np.float32)]
    if pause_samples > 0:
        pieces.append(silence_sentence)
    return pieces
