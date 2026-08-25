"""
src/pipeline/visual_enrichment.py — VLM Captioning for Extracted Frames
=======================================================================

Sends representative frames from the new pipeline's visual_artifacts.json
to Gemini VLM (Vision Language Model) for structured visual analysis.

Each atom record is enriched with:
  - visual_summary  : dense 2-3 sentence description for semantic search
  - on_screen_text  : all readable text visible in the frame
  - diagram_type    : frame category (slide, code, chart, person, scene, etc.)
  - key_concepts    : noun-phrase keywords for search

The enriched data is saved back into visual_artifacts.json so downstream
retrievers (local_visual, chroma_dense) can use real visual descriptions
instead of generic placeholders.

Techniques used:
  - Zero-Shot Captioning via Gemini VLM
  - Structured JSON Prompting for deterministic parsing
  - Exponential Backoff Retry on transient API errors
  - Resume support: skips records that already have visual_summary
  - Batch Throttle: respects Gemini free-tier RPM quota
"""

from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from repo root so GEMINI_API_KEY is available
_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_REPO_ROOT_ENV)

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now

logger = logging.getLogger("visual_enrichment")

# ── Configuration ──────────────────────────────────────────────────────────────

# Models in priority order — when one is quota-exhausted, we try the next
_GEMINI_MODELS = [
    os.getenv("GEMINI_MODEL_VLM", "gemini-2.5-flash"),
    os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
    "gemini-flash-latest",
    "gemini-3.5-flash",
]
GEMINI_MODEL = _GEMINI_MODELS[0]
MAX_RETRIES = 5
RETRY_BASE_DELAY = 3.0
INTER_CALL_DELAY = 0.3
SKIP_IF_ENRICHED = True


# ── Gemini Client ──────────────────────────────────────────────────────────────

def _get_gemini_client():
    """Initialise and return the Gemini client."""
    try:
        from google import genai
    except ImportError:
        raise ImportError(
            "google-genai is required for visual enrichment. "
            "Install with: pip install google-genai"
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )

    client = genai.Client(api_key=api_key)
    logger.info("Using Gemini VLM: %s", GEMINI_MODEL)
    return client


# ── VLM Caption Prompt ────────────────────────────────────────────────────────

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


# ── Caption with Retry (model fallback + server-respectful backoff) ──────────

import re as _re

# Global: tracks which models are quota-exhausted for this session
_quota_exhausted_models: set[str] = set()


def _parse_retry_delay(exc: Exception) -> float:
    """Extract the server-suggested retry delay from a 429 error message."""
    try:
        err_str = str(exc)
        match = _re.search(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", err_str)
        if match:
            return max(1.0, float(match.group(1)))
    except Exception:
        pass
    return 0.0


def _is_quota_error(exc: Exception) -> bool:
    """Check if the error is a 429 RESOURCE_EXHAUSTED quota error."""
    return "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc)


def _caption_with_retry(client, image, record_id: str) -> dict[str, Any]:
    """
    Call the Gemini VLM with:
    - Server-respectful retry delays (honors retryDelay from 429 response)
    - Model fallback: if one model is quota-exhausted, try the next one
    - Exponential backoff for transient errors
    
    Returns a parsed caption dict, or a fallback dict on permanent failure.
    """
    # Build list of models to try: non-exhausted ones first
    models_to_try = [m for m in _GEMINI_MODELS if m not in _quota_exhausted_models]
    if not models_to_try:
        models_to_try = _GEMINI_MODELS  # try all if all exhausted

    for model_name in models_to_try:
        delay = RETRY_BASE_DELAY
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[_CAPTION_PROMPT, image],
                )
                raw_text = (response.text or "").strip()

                # Strip accidental markdown fences
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("```")[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:]
                    raw_text = raw_text.strip()

                caption = json.loads(raw_text)
                logger.info(
                    "Record %s: enriched with model %s",
                    record_id, model_name,
                )
                return caption

            except json.JSONDecodeError as exc:
                logger.warning(
                    "Record %s: VLM returned non-JSON (attempt %d, model %s): %s",
                    record_id, attempt, model_name, exc,
                )
                if attempt == MAX_RETRIES:
                    return {
                        "on_screen_text": "",
                        "diagram_type": "other",
                        "visual_actions": "",
                        "key_concepts": [],
                        "summary": raw_text if 'raw_text' in dir() else "",
                        "_parse_error": True,
                    }

            except Exception as exc:
                # Check for quota exhaustion — mark model and try next one
                if _is_quota_error(exc):
                    _quota_exhausted_models.add(model_name)
                    server_delay = _parse_retry_delay(exc)
                    logger.warning(
                        "Record %s: model %s quota exhausted (attempt %d/%d). "
                        "Server retry delay: %.1fs. Trying next model.",
                        record_id, model_name, attempt, MAX_RETRIES, server_delay,
                    )
                    break  # Break inner loop to try next model
                
                logger.warning(
                    "Record %s: API error (attempt %d/%d, model %s): %s",
                    record_id, attempt, MAX_RETRIES, model_name, exc,
                )
                if attempt == MAX_RETRIES:
                    continue  # Try next model
                # Respect server delay if available, otherwise exponential backoff
                server_delay = _parse_retry_delay(exc)
                wait = max(delay, server_delay) if server_delay > 0 else delay
                logger.info("  Waiting %.1fs before retry...", wait)
                time.sleep(wait)
                delay *= 2

    # All models exhausted
    logger.error(
        "Record %s: all models and retries exhausted — skipping",
        record_id,
    )
    return {
        "on_screen_text": "",
        "diagram_type": "other",
        "visual_actions": "",
        "key_concepts": [],
        "summary": "",
        "_api_error": "all_models_quota_exhausted",
    }


# ── Best Frame Selection ──────────────────────────────────────────────────────

def _best_frame_for_enrichment(record: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the single best frame from a record's references for VLM captioning."""
    refs = record.get("frame_references", [])
    if not refs:
        return None

    # Priority: highest_visual_change > best_ocr_readable > middle > start
    priority_roles = ["highest_visual_change", "best_ocr_readable", "middle", "start"]
    for role in priority_roles:
        for ref in refs:
            if role in str(ref.get("role", "")):
                return ref

    # Fallback: first frame
    return refs[0]


# ── Main Enrichment ───────────────────────────────────────────────────────────

def run_visual_enrichment(
    *,
    repo_root: Path,
    video_id: str,
) -> dict[str, Any]:
    """
    Enrich visual artifact records with Gemini VLM captions.

    For each atom's visual artifacts, this function:
    1. Picks the best representative frame
    2. Sends it to Gemini VLM for structured visual analysis
    3. Populates visual_summary, on_screen_text, diagram_type, key_concepts
    4. Saves enriched records back to visual_artifacts.json

    Parameters
    ----------
    repo_root : Path
        The repository root directory.
    video_id : str
        The video identifier.

    Returns
    -------
    dict with enrichment statistics (enriched_count, skipped_count, error_count)
    """
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)

    visual_artifacts_path = Path(manifest["artifacts"].get("visual_artifacts_path", ""))
    if not visual_artifacts_path.is_file():
        logger.warning("No visual_artifacts.json found for %s — skipping enrichment", video_id)
        return {"enriched_count": 0, "skipped_count": 0, "error_count": 0, "status": "no_artifacts"}

    # Load visual artifacts
    visual_payload = read_json(visual_artifacts_path)
    records = visual_payload.get("records", [])
    if not records:
        logger.info("No visual records for %s — nothing to enrich", video_id)
        return {"enriched_count": 0, "skipped_count": 0, "error_count": 0, "status": "empty"}

    # Initialize Gemini client
    client = _get_gemini_client()

    enriched_count = 0
    skipped_count = 0
    error_count = 0
    total = len(records)

    logger.info(
        "👁️  Starting VLM visual enrichment for %s (%d records)...",
        video_id, total,
    )

    for i, record in enumerate(records, start=1):
        record_id = f"{record.get('atom_id', f'record_{i}')}-{record.get('start_ms', 0)}"

        # Resume: skip if already enriched or permanently failed
        if SKIP_IF_ENRICHED and (record.get("visual_summary") or record.get("visual_enrichment_error")):
            logger.info("[%d/%d] %s — already enriched/failed, skipping", i, total, record_id)
            skipped_count += 1
            continue

        # Pick best frame
        frame_ref = _best_frame_for_enrichment(record)
        if not frame_ref:
            logger.warning("[%d/%d] %s — no frame references, skipping", i, total, record_id)
            skipped_count += 1
            continue

        # Resolve frame image path
        frame_path = repo_root / frame_ref.get("path_relative", "")
        if not frame_path.is_file():
            # Try alternative path resolution
            frame_path = repo_root / "data" / "processed" / "frames" / video_id / f"{frame_ref['frame_id']}.jpg"
            if not frame_path.is_file():
                logger.warning(
                    "[%d/%d] %s — frame image not found at %s, skipping",
                    i, total, record_id, frame_path,
                )
                skipped_count += 1
                continue

        # Load image
        try:
            from PIL import Image as PILImage
            image = PILImage.open(frame_path).convert("RGB")
        except Exception as exc:
            logger.error("[%d/%d] %s — cannot open image: %s", i, total, record_id, exc)
            error_count += 1
            continue

        # Call Gemini VLM
        caption = _caption_with_retry(client, image, record_id)

        if not caption:
            error_count += 1
            continue

        if caption.get("_parse_error") or caption.get("_api_error"):
            error_count += 1
            # Still store what we got (best-effort)
            record["visual_summary"] = caption.get("summary", "")
            record["on_screen_text"] = caption.get("on_screen_text", "")
            record["diagram_type"] = caption.get("diagram_type", "other")
            record["key_concepts"] = caption.get("key_concepts", [])
            record["visual_enrichment_error"] = (
                caption.get("_parse_error") and "parse_error" or "api_error"
            )
            # If all models are quota-exhausted, save immediately and stop
            if caption.get("_api_error") == "all_models_quota_exhausted":
                logger.warning("All models quota-exhausted at record %d — saving progress and stopping", i)
                visual_payload["records"] = records
                visual_payload["enrichment"] = {
                    "enriched_count": enriched_count,
                    "skipped_count": skipped_count,
                    "error_count": error_count,
                    "total_records": total,
                    "model": GEMINI_MODEL,
                    "quota_exhausted": True,
                    "completed_at": utc_now(),
                }
                write_json_atomic(visual_artifacts_path, visual_payload)
                return {
                    "enriched_count": enriched_count,
                    "skipped_count": skipped_count,
                    "error_count": error_count,
                    "total_records": total,
                    "status": "quota_exhausted",
                    "completed_up_to": i,
                }
        else:
            # Successful enrichment
            record["visual_summary"] = caption.get("summary", "")
            record["on_screen_text"] = caption.get("on_screen_text", "")
            record["diagram_type"] = caption.get("diagram_type", "other")
            record["key_concepts"] = caption.get("key_concepts", [])
            record["visual_actions"] = caption.get("visual_actions", "")
            record["visual_description"] = caption  # Full structured dict
            enriched_count += 1

        logger.info(
            "[%d/%d] %s | type=%-12s | concepts=%s",
            i, total, record_id,
            record.get("diagram_type", "other"),
            record.get("key_concepts", [])[:3],
        )

        # Incremental save after every record so progress survives interruption
        if i < total:
            visual_payload["records"] = records
            visual_payload["enrichment"] = {
                "enriched_count": enriched_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
                "total_records": total,
                "model": GEMINI_MODEL,
                "in_progress": True,
                "last_record_index": i,
            }
            write_json_atomic(visual_artifacts_path, visual_payload)

        # Polite throttle
        if i < total:
            time.sleep(INTER_CALL_DELAY)

    # Final save of enriched records
    visual_payload["records"] = records
    visual_payload["enrichment"] = {
        "enriched_count": enriched_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "total_records": total,
        "model": GEMINI_MODEL,
        "completed_at": utc_now(),
    }
    write_json_atomic(visual_artifacts_path, visual_payload)

    # Also update manifest with enrichment metadata
    manifest.setdefault("artifact_metadata", {})["visual_enrichment"] = {
        "enriched_count": enriched_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "total_records": total,
        "model": GEMINI_MODEL,
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)

    logger.info(
        "✅ Visual enrichment complete for %s: "
        "%d enriched, %d skipped, %d errors",
        video_id, enriched_count, skipped_count, error_count,
    )

    return {
        "enriched_count": enriched_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "total_records": total,
        "status": "completed",
    }
