"""Memory candidate generator for vague episodic memory recovery.

Searches across OCR, transcript, semantic chunks, events, frames, and clips using
weighted feature scoring without calling embeddings or LLMs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import CandidateMemory, FeatureType, MemoryFeature, MemoryQuery
from .memory_parser import parse_memory_query

# Feature Scoring Weights
WEIGHTS = {
    "text_clue": 3.5,
    "color": 3.0,
    "object": 2.5,
    "action": 2.0,
    "visual_clue": 2.0,
    "spatial_clue": 1.5,
    "temporal_clue": 1.5,
}

MODALITY_SOURCE_MAP = {
    "ocr": "ocr",
    "ocr_records": "ocr",
    "transcript": "transcript",
    "transcripts": "transcript",
    "semantic_chunks": "semantic_chunk",
    "chunks": "semantic_chunk",
    "events": "event",
    "frames": "frame",
    "frame_index": "frame",
    "clips": "clip",
    "atoms": "clip",
}


def _extract_text_content(item: dict[str, Any]) -> str:
    """Extract concatenated text representation from an evidence item."""
    text_parts: list[str] = []
    for key in ("ocr_text", "transcript", "caption", "description", "visual_summary", "title", "text"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            text_parts.append(val.strip())
    return " ".join(text_parts)


def score_evidence_item(
    item: dict[str, Any],
    query: MemoryQuery,
    modality: str,
) -> tuple[float, list[str]]:
    """Calculate weighted matching score for a single evidence item against query features."""
    score = 0.0
    matched_features: list[str] = []

    text_content = _extract_text_content(item).lower()
    item_tags = [str(t).lower() for t in (item.get("tags") or item.get("labels") or [])]
    item_colors = [str(c).lower() for c in (item.get("colors") or [])]
    item_objects = [str(o).lower() for o in (item.get("objects") or [])]

    # 1. Colors (Weight 3.0)
    for color in query.colors:
        if color in item_colors or re.search(r"\b" + re.escape(color) + r"\b", text_content):
            score += WEIGHTS["color"]
            matched_features.append(f"color:{color}")

    # 2. Objects (Weight 2.5)
    for obj in query.objects:
        singular_obj = obj.rstrip("s")
        if (
            obj in item_objects
            or singular_obj in item_objects
            or any(obj in tag for tag in item_tags)
            or re.search(r"\b" + re.escape(singular_obj) + r"\w*\b", text_content)
        ):
            score += WEIGHTS["object"]
            matched_features.append(f"object:{obj}")

    # 3. Text Clues (Weight 3.5)
    for text_clue in query.text_clues:
        clue_lower = text_clue.lower()
        if clue_lower in text_content or any(clue_lower in tag for tag in item_tags):
            score += WEIGHTS["text_clue"]
            matched_features.append(f"text_clue:{text_clue}")

    # 4. Actions (Weight 2.0)
    for action in query.actions:
        if action in text_content or any(action in tag for tag in item_tags):
            score += WEIGHTS["action"]
            matched_features.append(f"action:{action}")

    # 5. Visual Clues (Weight 2.0)
    for visual_clue in query.visual_clues:
        if visual_clue in text_content or any(visual_clue in tag for tag in item_tags):
            score += WEIGHTS["visual_clue"]
            matched_features.append(f"visual_clue:{visual_clue}")

    # 6. Spatial Clues (Weight 1.5)
    for spatial_clue in query.spatial_clues:
        if spatial_clue in text_content or any(spatial_clue in tag for tag in item_tags):
            score += WEIGHTS["spatial_clue"]
            matched_features.append(f"spatial_clue:{spatial_clue}")

    # 7. Temporal Clues (Weight 1.5)
    for temporal_clue in query.temporal_clues:
        if temporal_clue in text_content or any(temporal_clue in tag for tag in item_tags):
            score += WEIGHTS["temporal_clue"]
            matched_features.append(f"temporal_clue:{temporal_clue}")

    # Modality affinity bonuses
    if modality == "ocr" and any(f.startswith("text_clue:") for f in matched_features):
        score += 1.0
    if modality == "frame" and any(f.startswith("color:") or f.startswith("object:") for f in matched_features):
        score += 1.0

    return round(score, 3), matched_features


def generate_candidates(
    memory_query: MemoryQuery | str,
    retrieval_context: Mapping[str, Sequence[dict[str, Any]]] | None = None,
    *,
    video_id: str = "default_video",
    min_score: float = 0.1,
    top_k: int | None = None,
) -> list[CandidateMemory]:
    """Generate ranked CandidateMemory moments across available retrieval sources."""
    if isinstance(memory_query, str):
        parsed_query = parse_memory_query(memory_query)
    elif isinstance(memory_query, MemoryQuery):
        parsed_query = memory_query
    else:
        raise TypeError("memory_query must be a string or MemoryQuery instance")

    if not retrieval_context:
        return []

    candidates: list[CandidateMemory] = []

    for raw_modality, items in retrieval_context.items():
        source_type = MODALITY_SOURCE_MAP.get(raw_modality.lower(), raw_modality.lower())
        if not items:
            continue

        for idx, item in enumerate(items):
            item_id = str(
                item.get("id")
                or item.get("source_id")
                or item.get("candidate_id")
                or item.get("ocr_id")
                or item.get("frame_id")
                or item.get("chunk_id")
                or item.get("event_id")
                or item.get("atom_id")
                or f"{source_type}_{idx + 1}"
            )

            score, matched_features = score_evidence_item(item, parsed_query, source_type)
            if score < min_score:
                continue

            ts_start = item.get("start_ms") or item.get("timestamp_ms") or item.get("start_seconds")
            ts_end = item.get("end_ms") or item.get("end_seconds") or ts_start

            candidate = CandidateMemory(
                source_type=source_type,
                source_id=item_id,
                timestamp_start=ts_start,
                timestamp_end=ts_end,
                matched_features=matched_features,
                score=score,
                evidence=item,
                video_id=video_id,
            )
            candidates.append(candidate)

    # Sort candidates by score descending, tie-breaking by source_id
    candidates.sort(key=lambda c: (-c.score, c.source_id))

    if top_k is not None and top_k > 0:
        return candidates[:top_k]

    return candidates


# Alias for backward compatibility with memory_retriever.py and existing tests
def generate_memory_candidates(
    memory_query: MemoryQuery | str,
    evidence_store: Mapping[str, Sequence[dict[str, Any]]] | None = None,
    *,
    video_id: str = "default_video",
    min_score: float = 0.1,
    top_k: int | None = None,
) -> list[CandidateMemory]:
    """Alias delegating to generate_candidates for backward compatibility."""
    return generate_candidates(
        memory_query=memory_query,
        retrieval_context=evidence_store,
        video_id=video_id,
        min_score=min_score,
        top_k=top_k,
    )
