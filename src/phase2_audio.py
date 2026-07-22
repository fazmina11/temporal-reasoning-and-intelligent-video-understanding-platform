"""
src/phase2_audio.py — Phase 2A: ASR Transcription & Temporal Alignment
========================================================================

Pipeline overview
-----------------
Step A │ Full-video ASR          — Faster-Whisper transcribes the entire audio track
       │                           with word-level timestamps (VAD-filtered)
Step B │ Scene-level Alignment   — each Whisper segment is mapped to the correct
       │                           scene window from mapping.json via temporal overlap
Step C │ Transcript Export       — produces two artefacts:
       │   • transcript.json     — flat list of all ASR segments (raw)
       │   • enriched_metadata.json (audio pass) — mapping.json rows enriched with
       │                           scene_transcript, avg_confidence, word_count

Advanced techniques
--------------------
• VAD (Voice Activity Detection)  — Whisper's built-in VAD filter suppresses
                                    silence/music segments before decoding, cutting
                                    hallucinations and runtime
• Word-level Timestamps           — enable fine-grained temporal alignment without
                                    a second forced-alignment pass
• Confidence Filtering            — segments below MIN_AVG_LOG_PROB are flagged
                                    as low-confidence rather than silently included
• Resume / Incremental Processing — if transcript.json already exists the ASR step
                                    is skipped, avoiding redundant GPU/CPU work
• Device Auto-detection           — falls back gracefully: CUDA → CPU
"""

from __future__ import annotations

import json
import os
import sys
import logging
from pathlib import Path
from typing import Any

# Audio extraction
try:
    from moviepy import VideoFileClip
    AUDIO_EXTRACTION_AVAILABLE = True
except ImportError:
    AUDIO_EXTRACTION_AVAILABLE = False

# ── Local utilities ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_dirs, save_metadata, load_metadata, log

# ── Configuration ──────────────────────────────────────────────────────────────

# Resolve paths relative to the repository root (not the current working directory).
REPO_ROOT         = Path(__file__).resolve().parent.parent
DATA_ROOT         = REPO_ROOT / "data"

VIDEO_PATH        = str(DATA_ROOT / "input_videos" / "demo_video.mp4")
MAPPING_PATH      = str(DATA_ROOT / "processed" / "metadata" / "mapping.json")
TRANSCRIPT_PATH   = str(DATA_ROOT / "processed" / "metadata" / "transcript.json")
ENRICHED_PATH     = str(DATA_ROOT / "processed" / "metadata" / "enriched_metadata.json")
AUDIO_SEGMENTS_DIR = str(DATA_ROOT / "processed" / "audio")
RESULTS_DIR       = str(DATA_ROOT / "processed" / "results")

# ASR model — tiny/base for speed, small/medium/large for accuracy
MODEL_SIZE        = "base"

# Compute — auto-detects CUDA; falls back to CPU
COMPUTE_TYPE      = "float16"   # "float16" on GPU, "int8" on CPU (set below)
BEAM_SIZE         = 5

# VAD (Voice Activity Detection) — suppress non-speech before decoding
ENABLE_VAD        = True
VAD_FILTER_PARAMS = {
    "min_silence_duration_ms": 500,   # merge gaps shorter than 500 ms
    "speech_pad_ms":           400,   # keep 400 ms padding around speech
}

# Word-level timestamps
WORD_TIMESTAMPS   = True

# Confidence — segments with avg_logprob below this are flagged low-confidence
MIN_AVG_LOG_PROB  = -1.0   # log-probability; 0.0 = perfect, < -1.0 = noisy

# Language — None = auto-detect; set e.g. "en" to skip language detection
LANGUAGE          = None


# ── Device selection ───────────────────────────────────────────────────────────

def _select_device() -> tuple[str, str]:
    """Return (device, compute_type) based on available hardware."""
    try:
        import torch
        if torch.cuda.is_available():
            log.info("🖥️  CUDA detected — using GPU with float16")
            return "cuda", "float16"
    except ImportError:
        pass
    log.info("🖥️  No CUDA — using CPU with int8")
    return "cpu", "int8"


# ── Audio Extraction ─────────────────────────────────────────────────────────────

def extract_audio_segments(
    video_path: str, 
    scenes: list[dict], 
    output_dir: str = AUDIO_SEGMENTS_DIR
) -> list[dict]:
    """
    Extract audio segments for each scene from the video.
    
    Parameters
    ----------
    video_path : Path to the source video file
    scenes     : List of scene metadata dicts with start_seconds and end_seconds
    output_dir : Directory to save .wav audio segments
    
    Returns
    -------
    Updated scenes list with audio_file field added
    """
    if not AUDIO_EXTRACTION_AVAILABLE:
        log.warning("⚠️  moviepy not available - skipping audio extraction")
        log.info("Install with: pip install moviepy")
        return scenes
    
    ensure_dirs([output_dir])
    
    try:
        video = VideoFileClip(video_path)
        log.info("🎬  Extracting audio segments for %d scenes...", len(scenes))
        
        for i, scene in enumerate(scenes):
            start_time = scene["start_seconds"]
            end_time = scene["end_seconds"]
            
            # Extract video segment first, then get audio
            video_segment = video.subclipped(start_time, end_time)
            audio_segment = video_segment.audio
            
            # Save as WAV file
            audio_filename = f"scene_{i + 1:03d}_audio.wav"
            audio_path = os.path.join(output_dir, audio_filename)
            
            audio_segment.write_audiofile(audio_path)
            scene["audio_file"] = audio_filename
            
            log.debug("🎵  Extracted audio: %s (%.2fs → %.2fs)", 
                     audio_filename, start_time, end_time)
        
        video.close()
        log.info("✅  Audio extraction complete - %d segments saved to %s", 
                 len(scenes), output_dir)
        
    except Exception as exc:
        log.error("❌  Audio extraction failed: %s", exc)
        # Add empty audio_file field to maintain consistency
        for scene in scenes:
            scene["audio_file"] = None
    
    return scenes


# ── Step A: Full-video ASR ─────────────────────────────────────────────────────

def transcribe_video(
    video_path: str,
    force: bool = False,
    transcript_path: str | None = None,
) -> list[dict]:
    """
    ASR (Automatic Speech Recognition) via Faster-Whisper.

    Produces a flat list of segments, each containing:
      start, end, text, avg_logprob, no_speech_prob, words (optional)

    Resume logic: if transcript.json already exists and force=False,
    loads and returns the cached result instead of re-running ASR.

    Parameters
    ----------
    video_path : Path to the source video/audio file.
    force      : If True, re-run ASR even if transcript.json exists.

    Returns
    -------
    List of segment dicts.
    """
    # ── Resume check ─────────────────────────────────────────────────────
    output_path = Path(transcript_path or TRANSCRIPT_PATH)
    if not force and output_path.exists():
        log.info("⏩  transcript.json found — skipping ASR (use force=True to rerun)")
        with output_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    from faster_whisper import WhisperModel

    device, compute_type = _select_device()

    log.info("🎙️  Loading Whisper model: %s  [%s / %s]", MODEL_SIZE, device, compute_type)
    model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute_type)

    transcribe_kwargs: dict[str, Any] = {
        "beam_size":        BEAM_SIZE,
        "word_timestamps":  WORD_TIMESTAMPS,
        "vad_filter":       ENABLE_VAD,
        "vad_parameters":   VAD_FILTER_PARAMS if ENABLE_VAD else {},
    }
    if LANGUAGE:
        transcribe_kwargs["language"] = LANGUAGE

    log.info("🎙️  Transcribing: %s  (VAD=%s, word_ts=%s)", video_path, ENABLE_VAD, WORD_TIMESTAMPS)
    segments_iter, info = model.transcribe(video_path, **transcribe_kwargs)

    log.info(
        "🌐  Detected language: %s  (probability=%.2f)",
        info.language, info.language_probability,
    )

    segments: list[dict] = []
    for seg in segments_iter:
        record: dict[str, Any] = {
            "start":          round(seg.start, 3),
            "end":            round(seg.end,   3),
            "text":           seg.text.strip(),
            "avg_logprob":    round(seg.avg_logprob,    4),
            "no_speech_prob": round(seg.no_speech_prob, 4),
            "low_confidence": seg.avg_logprob < MIN_AVG_LOG_PROB,
        }
        # Word-level timestamps (if enabled)
        if WORD_TIMESTAMPS and seg.words:
            record["words"] = [
                {
                    "word":  w.word,
                    "start": round(w.start, 3),
                    "end":   round(w.end,   3),
                    "prob":  round(w.probability, 4),
                }
                for w in seg.words
            ]
        segments.append(record)
        log.debug("[%.2f → %.2f]  %s", seg.start, seg.end, seg.text.strip())

    ensure_dirs([str(output_path.parent)])
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(segments, fh, indent=4, ensure_ascii=False)

    log.info("ASR complete: %d segments -> %s", len(segments), output_path)
    return segments


# ── Step B: Scene-level Temporal Alignment ────────────────────────────────────

def _overlap_seconds(
    seg_start: float, seg_end: float,
    scene_start: float, scene_end: float,
) -> float:
    """Return the overlap in seconds between a segment and a scene window."""
    return max(0.0, min(seg_end, scene_end) - max(seg_start, scene_start))


def align_to_scenes(
    scenes: list[dict],
    segments: list[dict],
) -> list[dict]:
    """
    Scene-level Alignment — map ASR segments → scene windows.

    Each ASR segment is assigned to the scene whose time window has the
    greatest overlap with that segment (rather than a simple "falls inside"
    check, which misses segments that straddle a scene boundary).

    Enriches each scene record with:
      scene_transcript  : concatenated text of all aligned segments
      word_count        : total word count for the scene
      avg_confidence    : mean avg_logprob across aligned segments
      has_low_conf_seg  : True if any segment was flagged low-confidence
      aligned_segments  : full list of aligned segment dicts

    Parameters
    ----------
    scenes   : List of scene metadata dicts (from mapping.json).
    segments : List of ASR segment dicts (from transcribe_video).

    Returns
    -------
    Enriched copy of scenes (original list is not mutated).
    """
    import copy
    enriched = copy.deepcopy(scenes)

    # Initialise audio fields on every scene
    for scene in enriched:
        scene.setdefault("scene_transcript",  "")
        scene.setdefault("word_count",         0)
        scene.setdefault("avg_confidence",     None)
        scene.setdefault("has_low_conf_seg",   False)
        scene.setdefault("aligned_segments",   [])

    for seg in segments:
        # Skip near-silent segments
        if seg.get("no_speech_prob", 0) > 0.8:
            continue

        best_scene_idx = None
        best_overlap   = 0.0

        for idx, scene in enumerate(enriched):
            ov = _overlap_seconds(
                seg["start"], seg["end"],
                scene["start_seconds"], scene["end_seconds"],
            )
            if ov > best_overlap:
                best_overlap   = ov
                best_scene_idx = idx

        if best_scene_idx is not None and best_overlap > 0:
            enriched[best_scene_idx]["aligned_segments"].append(seg)

    # Aggregate per-scene audio fields
    for scene in enriched:
        aligned = scene["aligned_segments"]
        if aligned:
            scene["scene_transcript"] = " ".join(s["text"] for s in aligned)
            scene["word_count"]       = sum(len(s["text"].split()) for s in aligned)
            scene["avg_confidence"]   = round(
                sum(s["avg_logprob"] for s in aligned) / len(aligned), 4
            )
            scene["has_low_conf_seg"] = any(s.get("low_confidence") for s in aligned)

    return enriched


# ── Step C: Export ─────────────────────────────────────────────────────────────

def run_phase2_audio(
    video_path: str = VIDEO_PATH,
    force_asr: bool = False,
) -> list[dict]:
    """
    Full Phase 2A pipeline:
      1. ASR transcription with VAD + word timestamps (Step A).
      2. Temporal alignment to scene windows (Step B).
      3. Export enriched_metadata.json (Step C).

    Returns
    -------
    List of enriched scene metadata dicts.
    """
    # Ensure paths are resolved relative to the repository root
    video_path = str((REPO_ROOT / video_path) if not Path(video_path).is_absolute() else Path(video_path))
    if not Path(video_path).exists():
        raise FileNotFoundError(
            f"Video file not found: {video_path}\n"
            f"Expected to find the video at the path above.\n"
            f"Tip: run this script from the repo root or pass --video with an absolute path."
        )
    ensure_dirs([
        AUDIO_SEGMENTS_DIR,
        RESULTS_DIR,
        str(Path(TRANSCRIPT_PATH).parent),
    ])

    # ── Step A ────────────────────────────────────────────────────────────
    segments = transcribe_video(video_path, force=force_asr)

    # ── Step B ────────────────────────────────────────────────────────────
    log.info("🔗  Aligning %d ASR segments to scene windows…", len(segments))
    scenes   = load_metadata(MAPPING_PATH)
    enriched = align_to_scenes(scenes, segments)

    aligned_count = sum(1 for s in enriched if s["scene_transcript"])
    log.info(
        "📊  Alignment complete — %d / %d scenes have transcript coverage",
        aligned_count, len(enriched),
    )

    # ── Step C: Audio Extraction ───────────────────────────────────────────
    enriched = extract_audio_segments(video_path, enriched)

    # ── Step D: Save Results ───────────────────────────────────────────────
    # Save to both locations
    save_metadata(enriched, ENRICHED_PATH)
    results_path = os.path.join(RESULTS_DIR, "multimodal_data.json")
    save_metadata(enriched, results_path)
    
    log.info("🚀  Phase 2A complete")
    log.info("   📄 Enriched metadata: %s", ENRICHED_PATH)
    log.info("   📁 Results: %s", results_path)
    return enriched


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2A: ASR transcription & alignment")
    parser.add_argument("--video",     default=VIDEO_PATH, help="Input video path")
    parser.add_argument("--model",     default=MODEL_SIZE, help="Whisper model size")
    parser.add_argument("--language",  default=None,       help="Force language (e.g. 'en')")
    parser.add_argument("--force-asr", action="store_true", help="Re-run ASR even if cached")
    args = parser.parse_args()

    MODEL_SIZE = args.model       # noqa: F841
    LANGUAGE   = args.language    # noqa: F841

    run_phase2_audio(video_path=args.video, force_asr=args.force_asr)
