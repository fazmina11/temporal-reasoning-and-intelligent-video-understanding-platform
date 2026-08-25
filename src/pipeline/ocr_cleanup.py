"""
src/pipeline/ocr_cleanup.py — LLM-Based OCR Noise Cleanup
==========================================================

Tesseract OCR on compressed video frames produces noisy, garbled text.
This module uses an LLM (Groq via providers.py) to:

1. Read noisy OCR tracks
2. Identify which text is garbage vs real content
3. Reconstruct the likely original text from context
4. Mark cleaned vs noise-only tracks

Example noisy input:
  "2 4 ee rs ~ a ig f s* fr Intended S OF an intend treatment"
Expected cleaned output:
  "Intended for different treatment scenarios"

Each OCR record gets:
  - cleaned_text: the LLM-reconstructed text (or empty if pure noise)
  - ocr_quality: "good" | "cleaned" | "noise"
  - original_text: preserved for audit trail
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now
from .providers import call_llm

logger = logging.getLogger("ocr_cleanup")


# ── Cleanup Prompt ────────────────────────────────────────────────────────────

_CLEANUP_PROMPT = """You are an OCR text cleanup engine. You receive noisy OCR output extracted from video frames using Tesseract.

Your task:
1. Identify which parts of the text are real, readable content
2. Fix garbled characters, misspellings, and OCR artifacts
3. If the text is pure noise (garbage characters, no readable words), return empty string

Rules:
- Preserve the original meaning and structure
- Fix obvious OCR errors (e.g., "fr" → "for", "Intended S" → "Intended")
- Remove noise characters (backslashes, tildes, random letters)
- If the text contains fragments of real sentences, reconstruct them
- If the text is completely garbled with no readable content, return ""

Return ONLY a JSON object:
{"cleaned_text": "<the cleaned text>", "quality": "good|cleaned|noise"}

Where:
- "good" = text was mostly correct, minimal fixes needed
- "cleaned" = text was noisy but had recoverable content
- "noise" = text was pure garbage, no recoverable content
""".strip()


def _batch_cleanup_prompt(texts: list[dict[str, Any]]) -> str:
    """Build a batch cleanup prompt for multiple OCR records."""
    lines = ["Clean up the following OCR outputs. For each, return the cleaned text.\n"]
    for i, item in enumerate(texts):
        lines.append(f"OCR_{i}: \"{item['text']}\"")
    lines.append("")
    lines.append("Return a JSON array with one object per OCR entry:")
    lines.append('[{"index": 0, "cleaned_text": "...", "quality": "good|cleaned|noise"}, ...]')
    lines.append("Return ONLY the JSON array.")
    return "\n".join(lines)


# ── Classification ───────────────────────────────────────────────────────────

def _classify_ocr_text(text: str) -> str:
    """Fast local classification without LLM (saves API calls)."""
    if not text or len(text.strip()) < 2:
        return "noise"

    # Count readable characters vs noise
    readable = sum(1 for c in text if c.isalpha() or c.isdigit() or c in " .,-:;!?%$#@")
    noise = sum(1 for c in text if c in "\\|/{}[]()~`^*+=<>{}")

    if noise > readable:
        return "noise"

    # Check for common OCR words that indicate real content
    real_words = ["the", "and", "for", "are", "but", "not", "you", "all", "can",
                  "was", "one", "our", "out", "has", "had", "its", "may", "use",
                  "battery", "samsung", "galaxy", "watch", "health", "heart",
                  "score", "sleep", "risk", "detection", "intended", "scenarios",
                  "incorporated", "trademark", "subsidiaries", "technologies"]
    text_lower = text.lower()
    found_words = sum(1 for w in real_words if w in text_lower)

    if found_words >= 2:
        return "good"
    elif found_words >= 1:
        return "cleaned"
    elif len(text) > 15 and readable / max(len(text), 1) > 0.5:
        return "cleaned"

    return "noise"


# ── Main Cleanup ──────────────────────────────────────────────────────────────

def run_ocr_cleanup(
    *,
    repo_root: Path,
    video_id: str,
) -> dict[str, Any]:
    """
    Clean up noisy OCR text using LLM (Groq) with local fast-path for obvious cases.

    Parameters
    ----------
    repo_root : Path
        The repository root directory.
    video_id : str
        The video identifier.

    Returns
    -------
    dict with cleanup statistics
    """
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)

    ocr_path = Path(manifest["artifacts"].get("ocr_path", ""))
    if not ocr_path.is_file():
        logger.warning("No OCR artifact found for %s — skipping cleanup", video_id)
        return {"cleaned_count": 0, "noise_count": 0, "total": 0, "status": "no_ocr"}

    # Load OCR records
    ocr_payload = read_json(ocr_path)
    records = ocr_payload.get("records", [])
    if not records:
        logger.info("No OCR records for %s — nothing to clean", video_id)
        return {"cleaned_count": 0, "noise_count": 0, "total": 0, "status": "empty"}

    total = len(records)
    noise_count = 0
    cleaned_count = 0
    good_count = 0
    llm_cleaned_count = 0

    # Phase 1: Local fast-path classification (no API calls)
    needs_llm: list[dict[str, Any]] = []

    for record in records:
        text = record.get("text", "")
        quality = _classify_ocr_text(text)

        if quality == "noise":
            record["ocr_quality"] = "noise"
            record["cleaned_text"] = ""
            record["original_text"] = text
            noise_count += 1
        elif quality == "good":
            record["ocr_quality"] = "good"
            record["cleaned_text"] = text  # Good as-is
            record["original_text"] = text
            good_count += 1
        else:
            # Needs LLM cleanup
            needs_llm.append(record)

    logger.info(
        "OCR cleanup phase 1: %d good, %d noise, %d need LLM cleanup",
        good_count, noise_count, len(needs_llm),
    )

    # Phase 2: LLM cleanup for ambiguous records (batched)
    if needs_llm:
        BATCH_SIZE = 10
        for batch_start in range(0, len(needs_llm), BATCH_SIZE):
            batch = needs_llm[batch_start:batch_start + BATCH_SIZE]
            prompt = _batch_cleanup_prompt(batch)

            result_text = call_llm(
                prompt=prompt,
                system="You are an OCR text cleanup engine. Return only valid JSON.",
                max_tokens=2000,
                temperature=0.1,
            )

            if result_text:
                # Parse the response
                cleaned = _parse_batch_response(result_text, len(batch))
                for j, record in enumerate(batch):
                    if j < len(cleaned) and cleaned[j]:
                        record["cleaned_text"] = cleaned[j].get("cleaned_text", "")
                        record["ocr_quality"] = cleaned[j].get("quality", "cleaned")
                        record["original_text"] = record.get("text", "")
                        if record["ocr_quality"] == "noise":
                            noise_count += 1
                        else:
                            cleaned_count += 1
                            llm_cleaned_count += 1
                    else:
                        # LLM failed for this batch item — mark as cleaned
                        record["cleaned_text"] = record.get("text", "")
                        record["ocr_quality"] = "cleaned"
                        record["original_text"] = record.get("text", "")
                        cleaned_count += 1
            else:
                # LLM unavailable — keep original text
                for record in batch:
                    record["cleaned_text"] = record.get("text", "")
                    record["ocr_quality"] = "cleaned"
                    record["original_text"] = record.get("text", "")
                    cleaned_count += 1

    # Save cleaned OCR records
    ocr_payload["records"] = records
    ocr_payload["cleanup"] = {
        "good_count": good_count,
        "cleaned_count": cleaned_count,
        "noise_count": noise_count,
        "llm_cleaned_count": llm_cleaned_count,
        "total": total,
        "completed_at": utc_now(),
    }
    write_json_atomic(ocr_path, ocr_payload)

    # Update manifest
    manifest.setdefault("artifact_metadata", {})["ocr_cleanup"] = {
        "good_count": good_count,
        "cleaned_count": cleaned_count,
        "noise_count": noise_count,
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)

    logger.info(
        "✅ OCR cleanup complete for %s: "
        "%d good, %d cleaned (LLM: %d), %d noise",
        video_id, good_count, cleaned_count, llm_cleaned_count, noise_count,
    )

    return {
        "good_count": good_count,
        "cleaned_count": cleaned_count,
        "noise_count": noise_count,
        "llm_cleaned_count": llm_cleaned_count,
        "total": total,
        "status": "completed",
    }


def _parse_batch_response(text: str, expected_count: int) -> list[dict[str, Any] | None]:
    """Parse the LLM batch cleanup response."""
    import re

    # Strip thinking tags
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # Strip markdown fences
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)

    try:
        result = json.loads(text.strip())
        if isinstance(result, list):
            return result[:expected_count]
    except json.JSONDecodeError:
        # Try to find JSON array in the response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result[:expected_count]
            except json.JSONDecodeError:
                pass

    return [None] * expected_count
