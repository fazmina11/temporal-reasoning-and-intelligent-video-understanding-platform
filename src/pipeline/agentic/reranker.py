from __future__ import annotations

import re
from typing import Any


def rerank_candidates(
    *,
    candidates: list[dict[str, Any]],
    query_understanding: dict[str, Any],
) -> dict[str, Any]:
    terms = _terms(query_understanding.get("standalone_query") or query_understanding.get("raw_query") or "")
    entities = {str(entity).lower() for entity in query_understanding.get("entities") or []}
    required_modalities = set(query_understanding.get("required_modalities") or [])
    ranked = []
    for candidate in candidates:
        text = _text(candidate)
        overlap = sum(1 for term in terms if term in text)
        query_relevance = overlap / max(1, len(terms))
        entity_coverage = _entity_coverage(text, entities)
        modality_match = _modality_match(candidate, required_modalities)
        temporal_alignment = 1.0 if query_understanding.get("time_constraints") else 0.72
        answer_likelihood = min(1.0, (0.55 * query_relevance) + (0.25 * entity_coverage) + (0.20 * modality_match))
        rerank_score = (
            float(candidate.get("fused_score", 0.0))
            + (0.18 * query_relevance)
            + (0.08 * entity_coverage)
            + (0.08 * modality_match)
        )
        row = {
            **candidate,
            "query_relevance": round(query_relevance, 6),
            "answer_likelihood": round(answer_likelihood, 6),
            "entity_coverage": round(entity_coverage, 6),
            "temporal_alignment": round(temporal_alignment, 6),
            "modality_match": round(modality_match, 6),
            "rerank_score": round(rerank_score, 6),
            "rerank_term_overlap": overlap,
        }
        ranked.append(row)
    ranked.sort(key=lambda row: row["rerank_score"], reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rerank_rank"] = index
    top_score = float(ranked[0]["rerank_score"]) if ranked else 0.0
    second_score = float(ranked[1]["rerank_score"]) if len(ranked) > 1 else 0.0
    return {
        "candidate_count": len(ranked),
        "top_rerank_score": top_score,
        "retrieval_margin": round(max(0.0, top_score - second_score), 6),
        "candidates": ranked,
    }


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text)}


def _text(candidate: dict[str, Any]) -> str:
    ocr = " ".join(str(item) for item in candidate.get("ocr_text", []) or [])
    return " ".join(
        [str(candidate.get(key, "")) for key in ["text", "transcript", "visual_summary"]]
        + [ocr]
    ).lower()


def _entity_coverage(text: str, entities: set[str]) -> float:
    if not entities:
        return 0.75
    return sum(1 for entity in entities if entity and entity in text) / max(1, len(entities))


def _modality_match(candidate: dict[str, Any], required_modalities: set[str]) -> float:
    if not required_modalities:
        return 1.0
    available = set()
    source_type = str(candidate.get("source_type") or "")
    if candidate.get("text") or candidate.get("transcript"):
        available.add("transcript")
    if candidate.get("visual_summary") or (candidate.get("media_refs") or {}).get("frames"):
        available.add("visual")
    if candidate.get("ocr_text") or source_type == "ocr":
        available.add("ocr")
    if source_type == "speaker_turn" or (candidate.get("media_refs") or {}).get("speaker_id"):
        available.add("speaker")
    if source_type == "audio_event" or (candidate.get("media_refs") or {}).get("audio_event"):
        available.add("audio")
    return len(required_modalities & available) / max(1, len(required_modalities))
