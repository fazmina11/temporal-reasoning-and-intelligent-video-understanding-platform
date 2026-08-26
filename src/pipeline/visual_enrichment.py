"""
src/pipeline/visual_enrichment.py — VLM Captioning for Extracted Frames
=======================================================================

Sends representative frames from visual_artifacts.json to a VLM
(Vision Language Model) for structured visual analysis.

Uses the multi-provider client (providers.py) with automatic fallback:
  1. Groq  (qwen/qwen3.6-27b)     — 14,400 req/day, primary
  2. Gemini (gemini-2.5-flash)      — 1,500 req/day, fallback

Each atom record is enriched with:
  - visual_summary  : dense 2-3 sentence description for semantic search
  - on_screen_text  : all readable text visible in the frame
  - diagram_type    : frame category (slide, code, chart, person, scene, etc.)
  - key_concepts    : noun-phrase keywords for search

Techniques used:
  - Zero-Shot Captioning via VLM
  - Structured JSON Prompting for deterministic parsing
  - Multi-provider fallback (Groq → Gemini)
  - Resume support: skips records that already have visual_summary
  - Incremental saves: progress survives interruption
"""

from __future__ import annotations

import json
import base64
import time
import logging
from pathlib import Path
from typing import Any

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now
from .providers import call_vlm, get_provider_status

logger = logging.getLogger("visual_enrichment")

# ── Configuration ──────────────────────────────────────────────────────────────

INTER_CALL_DELAY = 0.3  # seconds between VLM calls (polite throttle)
SKIP_IF_ENRICHED = True


# ── VLM Caption Prompt ────────────────────────────────────────────────────────

_CAPTION_PROMPT = """
You are a multimodal indexing engine for a video search system.

Analyse the provided video frame and return ONLY a valid JSON object (no markdown fences,
no preamble, no <think> tags) with exactly these fields:

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
- Do NOT use <think> tags or any reasoning tokens.
""".strip()


# ── Caption with Retry ────────────────────────────────────────────────────────

def _caption_with_retry(image_b64: str, record_id: str) -> dict[str, Any]:
    """
    Call the VLM with retry via the multi-provider client.
    Returns a parsed caption dict, or a fallback dict on failure.
    """
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    for attempt in range(1, MAX_RETRIES + 1):
        caption = call_vlm(
            image_b64=image_b64,
            prompt=_CAPTION_PROMPT,
            max_tokens=500,
            temperature=0.3,
        )
        if caption is not None and isinstance(caption, dict):
            # Validate it has the expected fields
            required = ["summary", "diagram_type"]
            if any(k in caption for k in required):
                logger.info("Record %s: enriched (attempt %d)", record_id, attempt)
                return caption
            else:
                logger.warning(
                    "Record %s: VLM returned incomplete JSON (attempt %d): %s",
                    record_id, attempt, list(caption.keys()),
                )
        else:
            logger.warning(
                "Record %s: VLM returned None (attempt %d/%d)",
                record_id, attempt, MAX_RETRIES,
            )

        if attempt < MAX_RETRIES:
            logger.info("  Waiting %.1fs before retry...", RETRY_DELAY)
            time.sleep(RETRY_DELAY * attempt)

    # All retries failed
    logger.error("Record %s: all retries exhausted", record_id)
    return {
        "on_screen_text": "",
        "diagram_type": "other",
        "visual_actions": "",
        "key_concepts": [],
        "summary": "",
        "_api_error": "all_retries_exhausted",
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
    Enrich visual artifact records with VLM captions.

    Uses multi-provider client with automatic fallback (Groq → Gemini).

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

    enriched_count = 0
    skipped_count = 0
    error_count = 0
    total = len(records)

    # Check provider status
    status = get_provider_status()
    logger.info("Provider status: %s", {k: {"exhausted": v.get("quota_exhausted"), "keys_available": v.get("available_keys", v.get("requests_today"))} for k, v in status.items()})

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

        # Load and encode image to base64
        try:
            with open(frame_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as exc:
            logger.error("[%d/%d] %s — cannot read image: %s", i, total, record_id, exc)
            error_count += 1
            continue

        # Call VLM via multi-provider client
        caption = _caption_with_retry(image_b64, record_id)

        if not caption:
            error_count += 1
            continue

        if caption.get("_api_error"):
            error_count += 1
            record["visual_enrichment_error"] = caption["_api_error"]
            # Still store partial data
            record["visual_summary"] = caption.get("summary", "")
            record["on_screen_text"] = caption.get("on_screen_text", "")
            record["diagram_type"] = caption.get("diagram_type", "other")
            record["key_concepts"] = caption.get("key_concepts", [])
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
                "providers": get_provider_status(),
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
        "providers": get_provider_status(),
        "completed_at": utc_now(),
    }
    write_json_atomic(visual_artifacts_path, visual_payload)

    # Also update manifest with enrichment metadata
    manifest.setdefault("artifact_metadata", {})[
        "visual_enrichment"
    ] = {
        "enriched_count": enriched_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "total_records": total,
        "providers": get_provider_status(),
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
