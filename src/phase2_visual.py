"""
src/phase2_visual.py — Phase 2B: VLM Captioning & Multimodal Fusion Prep
=========================================================================

Pipeline overview
-----------------
Step A │ Zero-Shot Captioning     — each scene frame is sent to Gemini Flash
       │                           (VLM) with a structured prompt that extracts
       │                           text, diagrams, and semantic content
Step B │ Structured Caption Parse — raw VLM response is decomposed into typed
       │                           fields (on_screen_text, diagram_type, actions,
       │                           summary) for richer downstream embedding
Step C │ Multimodal Fusion Prep   — merges VLM captions with ASR transcripts
       │                           from Phase 2A into a single `combined_context`
       │                           field, ready for Phase 3 embedding

Advanced techniques
--------------------
• Zero-Shot Captioning      — no examples provided to the VLM; prompt engineering
                               alone steers it toward RAG-friendly structured output
• Structured JSON Prompting — VLM is asked to return strict JSON, eliminating
                               free-text parsing ambiguity
• Exponential Backoff Retry — rate-limit / transient errors are retried up to
                               MAX_RETRIES times before the scene is skipped
• Resume / Incremental      — scenes that already have a visual_description are
                               skipped, so partial runs are safely restartable
• Batch Size Control        — MAX_CONCURRENT limits parallel API calls to stay
                               inside the Gemini free-tier RPM quota
• Multimodal Fusion         — combined_context = visual caption + audio transcript,
                               the single string that Phase 3 will embed

Terminologies
--------------
ASR  — Automatic Speech Recognition (output from phase2_audio.py)
VLM  — Vision Language Model (Gemini Flash is a VLM)
Zero-Shot Captioning — describing an image without prior training examples
"""

from __future__ import annotations

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

# ── Local utilities ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_dirs, save_metadata, load_metadata, log

# ── Configuration ──────────────────────────────────────────────────────────────

# Resolve paths relative to the repository root (not the current working directory).
REPO_ROOT         = Path(__file__).resolve().parent.parent
DATA_ROOT         = REPO_ROOT / "data"

FRAMES_DIR       = str(DATA_ROOT / "processed" / "frames")
ENRICHED_PATH    = str(DATA_ROOT / "processed" / "metadata" / "enriched_metadata.json")   # from phase2_audio
FINAL_PATH       = str(DATA_ROOT / "processed" / "metadata" / "enriched_metadata.json")   # overwrite in place
RESULTS_PATH     = str(DATA_ROOT / "processed" / "results" / "multimodal_data.json")        # final combined data

# Gemini model — use the correct model name for the API
GEMINI_MODEL     = "gemini-1.5-flash"

# Retry / rate-limit handling
MAX_RETRIES      = 4
RETRY_BASE_DELAY = 2.0   # seconds; doubles on each retry (exponential backoff)

# Throttle between API calls (seconds) — adjust for your quota tier
INTER_CALL_DELAY = 0.5

# Skip frames already captioned (resume support)
SKIP_IF_CAPTIONED = True


# ── Gemini client ──────────────────────────────────────────────────────────────

def _get_gemini_model():
    """Initialise and return the Gemini GenerativeModel."""
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )

    client = genai.Client(api_key=api_key)
    log.info("Using Gemini vision model via google-genai: %s", GEMINI_MODEL)
    return client, GEMINI_MODEL, "new"

    try:
        # Try the newer google.genai package first
        import google.genai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
        client = genai.Client(api_key=api_key)
        
        # Try different model names
        model_names = ["gemini-pro-vision", "gemini-1.5-flash", "gemini-1.5-flash-001", "gemini-1.5-flash-002"]
        
        for model_name in model_names:
            try:
                # For the new API, we return the client and model name
                log.info("🤖  Using Gemini model (new API): %s", model_name)
                return client, model_name, "new"
            except Exception as e:
                log.warning("Failed to load model %s: %s", model_name, e)
                continue
        
        # Fallback to older model
        log.info("🤖  Using fallback Gemini model (new API): gemini-pro")
        return client, "gemini-pro", "new"
        
    except ImportError:
        # Fallback to the deprecated google.generativeai
        raise ImportError("google-genai is required; install dependencies from requirement.txt")
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
        genai.configure(api_key=api_key)
        
        # Try different model names
        model_names = ["gemini-pro-vision", "gemini-1.5-flash", "gemini-1.5-flash-001", "gemini-1.5-flash-002"]
        
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                log.info("🤖  Using Gemini model (old API): %s", model_name)
                return model, model_name, "old"
            except Exception as e:
                log.warning("Failed to load model %s: %s", model_name, e)
                continue
        
        # If all fail, try the older gemini-pro model
        try:
            model = genai.GenerativeModel("gemini-pro")
            log.info("🤖  Using fallback Gemini model (old API): gemini-pro")
            return model, "gemini-pro", "old"
        except Exception as e:
            raise RuntimeError(f"Failed to initialize any Gemini model: {e}")


# ── Step A: Zero-Shot Captioning ──────────────────────────────────────────────

_CAPTION_PROMPT = """
You are a multimodal indexing engine for a video search system.

Analyse the provided video frame and return ONLY a valid JSON object (no markdown fences,
no preamble) with exactly these fields:

{
  "on_screen_text":  "<all readable text visible in the frame, verbatim>",
  "diagram_type":    "<one of: slide | code | diagram | chart | whiteboard | person | scene | other>",
  "visual_actions":  "<brief description of any actions or movements in the frame>",
  "key_concepts":    ["<concept 1>", "<concept 2>"],
  "summary":         "<2-3 sentence dense description optimised for semantic search>"
}

Rules:
- on_screen_text must include ALL visible text, including slide titles, bullet points, code.
- key_concepts must be noun phrases useful as search keywords.
- summary must be self-contained — assume no other context.
- Return ONLY the JSON object. Any extra text will break the pipeline.
""".strip()


def _caption_with_retry(model_info, image, scene_id: str) -> dict[str, Any]:
    """
    Call the Gemini VLM with exponential backoff retry on transient errors.

    Returns a parsed caption dict, or a fallback dict on permanent failure.
    """
    from PIL import Image as PILImage

    delay = RETRY_BASE_DELAY
    model, model_name, api_version = model_info
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if api_version == "new":
                # New API using google.genai
                response = model.models.generate_content(
                    model=model_name,
                    contents=[_CAPTION_PROMPT, image]
                )
                raw_text = response.text.strip()
            else:
                # Old API using google.generativeai
                response = model.generate_content([_CAPTION_PROMPT, image])
                raw_text = response.text.strip()

            # Strip accidental markdown fences (```json ... ```)
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            caption = json.loads(raw_text)
            return caption

        except json.JSONDecodeError as exc:
            log.warning("Scene %s: VLM returned non-JSON (attempt %d): %s", scene_id, attempt, exc)
            # Return a best-effort fallback with the raw text
            if attempt == MAX_RETRIES:
                return {
                    "on_screen_text":  "",
                    "diagram_type":    "other",
                    "visual_actions":  "",
                    "key_concepts":    [],
                    "summary":         raw_text if 'raw_text' in locals() else "",
                    "_parse_error":    True,
                }

        except Exception as exc:  # rate-limit, network error, etc.
            log.warning(
                "Scene %s: API error (attempt %d/%d): %s — retrying in %.1fs",
                scene_id, attempt, MAX_RETRIES, exc, delay,
            )
            if attempt == MAX_RETRIES:
                log.error("Scene %s: all %d retries exhausted — skipping", scene_id, MAX_RETRIES)
                return {
                    "on_screen_text": "",
                    "diagram_type":   "other",
                    "visual_actions": "",
                    "key_concepts":   [],
                    "summary":        "",
                    "_api_error":     str(exc),
                }
            time.sleep(delay)
            delay *= 2   # exponential backoff

    # Should never reach here
    return {}


def caption_frames(scenes: list[dict]) -> list[dict]:
    """
    Step A — Zero-Shot VLM captioning for every non-duplicate scene frame.

    Each scene record is enriched with:
      visual_description  : raw VLM response (structured JSON as dict)
      on_screen_text      : extracted text layer (for keyword search)
      diagram_type        : frame category
      key_concepts        : noun-phrase keywords
      visual_summary      : dense 2-3 sentence description

    Parameters
    ----------
    scenes : List of scene dicts (from enriched_metadata.json or mapping.json).

    Returns
    -------
    Same list with VLM fields added in place.
    """
    from PIL import Image as PILImage

    model_info = _get_gemini_model()
    total = len(scenes)

    log.info("👁️  Starting Zero-Shot VLM captioning with %s (%d scenes)…", model_info[1], total)

    for i, scene in enumerate(scenes, start=1):
        scene_id = scene.get("frame_id", f"scene_{i:03d}")

        # Resume: skip if already captioned
        if SKIP_IF_CAPTIONED and scene.get("visual_summary"):
            log.info("[%d/%d] %s — already captioned, skipping", i, total, scene_id)
            continue

        # Skip dedup-flagged frames (they share content with a previous scene)
        if scene.get("dedup_skipped"):
            log.debug("[%d/%d] %s — dedup-skipped frame, skipping VLM", i, total, scene_id)
            continue

        img_path = os.path.join(FRAMES_DIR, scene_id)
        if not Path(img_path).exists():
            log.warning("[%d/%d] %s — image file not found, skipping", i, total, scene_id)
            continue

        try:
            image = PILImage.open(img_path).convert("RGB")
        except Exception as exc:
            log.error("[%d/%d] %s — cannot open image: %s", i, total, scene_id, exc)
            continue

        caption = _caption_with_retry(model_info, image, scene_id)

        # Flatten VLM output into the scene record
        scene["visual_description"] = caption                        # full structured dict
        scene["on_screen_text"]     = caption.get("on_screen_text", "")
        scene["diagram_type"]       = caption.get("diagram_type",   "other")
        scene["key_concepts"]       = caption.get("key_concepts",   [])
        scene["visual_summary"]     = caption.get("summary",        "")

        log.info(
            "[%d/%d] %s | type=%-12s | concepts=%s",
            i, total, scene_id,
            scene["diagram_type"],
            scene["key_concepts"][:3],
        )

        # Polite throttle to respect API quota
        if i < total:
            time.sleep(INTER_CALL_DELAY)

    return scenes


# ── Step B+C: Multimodal Fusion ────────────────────────────────────────────────

def fuse_modalities(scenes: list[dict]) -> list[dict]:
    """
    Multimodal Fusion — merge visual and audio streams into combined_context.

    combined_context is the single string that Phase 3 will pass to the
    embedding model.  Fusing both modalities allows semantic queries like:
      "slides about vector databases shown while the speaker explains cosine similarity"

    Layout
    ------
    [VISUAL] <visual_summary>
    [TEXT ON SCREEN] <on_screen_text>
    [AUDIO] <scene_transcript>

    Parameters
    ----------
    scenes : Enriched scene dicts with both VLM and ASR fields populated.

    Returns
    -------
    Same list with combined_context field added.
    """
    for scene in scenes:
        parts: list[str] = []

        if scene.get("visual_summary"):
            parts.append(f"[VISUAL] {scene['visual_summary']}")

        if scene.get("on_screen_text"):
            parts.append(f"[TEXT ON SCREEN] {scene['on_screen_text']}")

        if scene.get("scene_transcript"):
            parts.append(f"[AUDIO] {scene['scene_transcript']}")

        scene["combined_context"] = "\n".join(parts) if parts else ""

    fused = sum(1 for s in scenes if s["combined_context"])
    log.info("🔗  Multimodal fusion: %d / %d scenes have combined_context", fused, len(scenes))
    return scenes


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_phase2_visual(enriched_path: str = ENRICHED_PATH) -> list[dict]:
    """
    Full Phase 2B pipeline:
      1. Load enriched_metadata.json (output of phase2_audio.py).
      2. Zero-Shot VLM captioning with retry (Step A).
      3. Multimodal fusion into combined_context (Steps B+C).
      4. Overwrite enriched_metadata.json with final enriched records.

    Returns
    -------
    Fully enriched list of scene dicts.
    """
    ensure_dirs([FRAMES_DIR])

    # Load — either the audio-enriched file or the raw mapping.json
    if Path(enriched_path).exists():
        scenes = load_metadata(enriched_path)
        log.info("📂  Loaded %d scenes from %s", len(scenes), enriched_path)
    else:
        fallback = str(DATA_ROOT / "processed" / "metadata" / "mapping.json")
        log.warning("%s not found — falling back to %s", enriched_path, fallback)
        scenes = load_metadata(fallback)

    # Step A: VLM captioning
    scenes = caption_frames(scenes)

    # Steps B+C: Multimodal fusion
    scenes = fuse_modalities(scenes)

    # Export
    save_metadata(scenes, FINAL_PATH)
    save_metadata(scenes, RESULTS_PATH)  # Also save to results folder
    log.info("🚀  Phase 2B complete")
    log.info("   📄 Enriched metadata: %s", FINAL_PATH)
    log.info("   📁 Results: %s", RESULTS_PATH)
    return scenes


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2B: VLM captioning & multimodal fusion")
    parser.add_argument(
        "--enriched", default=ENRICHED_PATH,
        help="Path to enriched_metadata.json from phase2_audio.py",
    )
    parser.add_argument(
        "--model", default=GEMINI_MODEL,
        help="Gemini model name (default: gemini-1.5-flash-latest)",
    )
    parser.add_argument(
        "--no-skip", action="store_true",
        help="Re-caption all frames even if already captioned",
    )
    args = parser.parse_args()

    GEMINI_MODEL      = args.model        # noqa: F841
    SKIP_IF_CAPTIONED = not args.no_skip  # noqa: F841

    run_phase2_visual(enriched_path=args.enriched)
