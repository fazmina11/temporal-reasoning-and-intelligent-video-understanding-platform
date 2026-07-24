"""Memory ranker for re-ranking candidate memories.

Re-ranks candidate memories considering matched feature counts, OCR text overlap,
object/color/action overlap, temporal & spatial clue agreement, and retrieval confidence.
Normalizes final scores to 0-1 and attaches human-readable ranking explanations.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .contracts import CandidateMemory


def _time_overlap(
    c1_start: int | float | None,
    c1_end: int | float | None,
    c2_start: int | float | None,
    c2_end: int | float | None,
    window_ms: int = 15_000,
) -> float:
    """Calculate temporal overlap / proximity between two candidate spans."""
    if c1_start is None or c2_start is None:
        return 0.0

    t1_center = c1_start if c1_end is None else (c1_start + c1_end) / 2.0
    t2_center = c2_start if c2_end is None else (c2_start + c2_end) / 2.0
    dist_ms = abs(t1_center - t2_center)

    if dist_ms > window_ms:
        return 0.0

    return math.exp(-dist_ms / (window_ms / 2.0))


def _build_explanation(matched_features: list[str]) -> str:
    """Build human-readable explanation describing why a candidate received its score."""
    if not matched_features:
        return "No specific feature matches"

    lines: list[str] = []
    seen: set[str] = set()

    for feature in matched_features:
        if feature in seen:
            continue
        seen.add(feature)

        if ":" in feature:
            category, val = feature.split(":", 1)
            if category == "object":
                lines.append(f"Matched object: {val}")
            elif category == "color":
                lines.append(f"Matched color: {val}")
            elif category in ("text_clue", "ocr"):
                lines.append(f"Matched OCR: {val}")
            elif category == "action":
                lines.append(f"Matched action: {val}")
            elif category == "temporal_clue":
                lines.append(f"Matched temporal clue: {val}")
            elif category == "spatial_clue":
                lines.append(f"Matched spatial clue: {val}")
            elif category == "visual_clue":
                lines.append(f"Matched visual clue: {val}")
            else:
                lines.append(f"Matched {category}: {val}")
        else:
            lines.append(f"Matched feature: {feature}")

    return "\n".join(lines)


def calculate_rerank_score(
    candidate: CandidateMemory,
    all_candidates: Sequence[CandidateMemory],
    *,
    proximity_window_ms: int = 15_000,
) -> tuple[float, dict[str, float]]:
    """Compute re-ranked raw score and signal breakdown for a single candidate memory."""
    base_score = candidate.score
    matched_feats = candidate.matched_features
    num_features = len(matched_feats)

    feature_count_boost = num_features * 2.0

    # Overlap signals
    feat_categories = {f.split(":")[0] for f in matched_feats if ":" in f}
    ocr_boost = 2.5 if ("text_clue" in feat_categories or candidate.source_type == "ocr") else 0.0
    object_boost = 2.0 if "object" in feat_categories else 0.0
    color_boost = 2.0 if "color" in feat_categories else 0.0
    action_boost = 1.5 if "action" in feat_categories else 0.0
    spatial_boost = 1.5 if "spatial_clue" in feat_categories else 0.0
    temporal_boost = 1.5 if "temporal_clue" in feat_categories else 0.0

    # Retrieval confidence
    raw_conf = candidate.evidence.get("confidence") if isinstance(candidate.evidence, dict) else None
    retrieval_conf_boost = 0.0
    if isinstance(raw_conf, (int, float)) and not isinstance(raw_conf, bool):
        conf_val = float(raw_conf)
        if conf_val > 1.0:
            conf_val /= 100.0
        retrieval_conf_boost = max(0.0, min(1.0, conf_val)) * 1.5

    # Cross-evidence agreement & proximity boost
    proximity_sum = 0.0
    for other in all_candidates:
        if (other.source_id == candidate.source_id) and (other.source_type == candidate.source_type):
            continue
        weight = _time_overlap(
            candidate.timestamp_start,
            candidate.timestamp_end,
            other.timestamp_start,
            other.timestamp_end,
            window_ms=proximity_window_ms,
        )
        if weight > 0:
            proximity_sum += weight * (other.score / max(base_score, 1.0))

    proximity_boost = min(3.0, 0.5 * proximity_sum)

    raw_score = (
        base_score
        + feature_count_boost
        + ocr_boost
        + object_boost
        + color_boost
        + action_boost
        + spatial_boost
        + temporal_boost
        + retrieval_conf_boost
        + proximity_boost
    )

    breakdown = {
        "base_score": base_score,
        "feature_count_boost": feature_count_boost,
        "ocr_boost": ocr_boost,
        "object_boost": object_boost,
        "color_boost": color_boost,
        "action_boost": action_boost,
        "spatial_boost": spatial_boost,
        "temporal_boost": temporal_boost,
        "retrieval_conf_boost": retrieval_conf_boost,
        "proximity_boost": round(proximity_boost, 3),
        "agreement_boost": round(proximity_boost, 3),
        "raw_score": round(raw_score, 3),
    }


    return raw_score, breakdown


def rank_candidates(
    candidates: Sequence[CandidateMemory],
    *,
    top_k: int | None = None,
    proximity_window_ms: int = 15_000,
) -> list[CandidateMemory]:
    """Re-rank candidate memories, normalize confidence scores to 0-1, and attach explanations."""
    if not candidates:
        return []

    scored_items: list[tuple[float, CandidateMemory, str, dict[str, float]]] = []

    for candidate in candidates:
        raw_score, breakdown = calculate_rerank_score(
            candidate, candidates, proximity_window_ms=proximity_window_ms
        )
        explanation = _build_explanation(candidate.matched_features)
        scored_items.append((raw_score, candidate, explanation, breakdown))

    max_raw = max((item[0] for item in scored_items), default=0.0)

    reranked: list[CandidateMemory] = []
    for raw_score, candidate, explanation, breakdown in scored_items:
        if max_raw <= 0:
            norm_score = 0.0
        else:
            # Normalize to 0.0 - 1.0
            scale_ref = max(max_raw, 15.0)
            norm_score = round(min(1.0, max(0.0, raw_score / scale_ref)), 4)


        updated_evidence = dict(candidate.evidence)
        updated_evidence["explanation"] = explanation
        updated_evidence["normalized_score"] = norm_score
        updated_evidence["rerank_breakdown"] = breakdown

        updated_candidate = CandidateMemory(
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            timestamp_start=candidate.timestamp_start,
            timestamp_end=candidate.timestamp_end,
            matched_features=list(candidate.matched_features),
            score=norm_score,
            evidence=updated_evidence,
            video_id=candidate.video_id,
        )
        reranked.append(updated_candidate)

    # Sort by normalized score descending, tie-breaking by source_id
    reranked.sort(key=lambda c: (-c.score, c.source_id))

    if top_k is not None and top_k > 0:
        return reranked[:top_k]

    return reranked


# Alias for backward compatibility with memory_retriever.py and existing tests
def rank_memory_candidates(
    candidates: Sequence[CandidateMemory],
    *,
    top_k: int | None = 5,
    proximity_window_ms: int = 15_000,
) -> list[CandidateMemory]:
    """Alias delegating to rank_candidates for backward compatibility."""
    return rank_candidates(
        candidates,
        top_k=top_k,
        proximity_window_ms=proximity_window_ms,
    )
