from __future__ import annotations

import re
from typing import Any


RANK_CONSTANT = 60


def fuse_candidates(
    *,
    candidates: list[dict[str, Any]],
    plan: dict[str, Any],
    query_understanding: dict[str, Any],
) -> dict[str, Any]:
    weights = {
        step["retriever"]: float(step.get("weight", 1.0))
        for step in plan.get("retrieval_steps", [])
    }
    terms = _terms(query_understanding.get("standalone_query") or query_understanding.get("raw_query") or "")
    entities = {str(entity).lower() for entity in query_understanding.get("entities") or []}
    visual_hints = {str(item).lower() for item in query_understanding.get("objects") or []}
    temporal_bonus = 0.03 if query_understanding.get("time_constraints") else 0.0

    fused: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = (candidate["source_type"], candidate["source_id"])
        item = fused.setdefault(
            key,
            {
                **candidate,
                "fused_score": 0.0,
                "merged_candidate_ids": [],
                "retrieval_sources": [],
                "fusion_reasons": [],
            },
        )
        retrieval = candidate.get("retrieval", {})
        retriever = retrieval.get("retriever", "")
        rank = int(retrieval.get("rank", 999))
        weight = weights.get(retriever, 1.0)
        rrf = weight / (RANK_CONSTANT + rank)
        exact_bonus = _exact_bonus(candidate, terms)
        entity_bonus = _entity_bonus(candidate, entities)
        visual_bonus = _visual_bonus(candidate, visual_hints)
        stale_penalty = 0.05 if _stale(candidate) else 0.0
        score = rrf + exact_bonus + entity_bonus + visual_bonus + temporal_bonus - stale_penalty
        item["fused_score"] += score
        item["merged_candidate_ids"].append(candidate["candidate_id"])
        item["retrieval_sources"].append(
            {
                "retriever": retriever,
                "rank": rank,
                "raw_score": retrieval.get("raw_score", 0.0),
                "rrf": round(rrf, 6),
            }
        )
        for reason, bonus in [
            ("exact_term_overlap", exact_bonus),
            ("entity_overlap", entity_bonus),
            ("visual_hint_overlap", visual_bonus),
            ("temporal_hint", temporal_bonus),
            ("stale_pipeline_penalty", -stale_penalty),
        ]:
            if bonus:
                item["fusion_reasons"].append({"reason": reason, "score": round(bonus, 6)})

    ranked = sorted(fused.values(), key=lambda row: row["fused_score"], reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["fusion_rank"] = index
        row["fused_score"] = round(row["fused_score"], 6)
    return {
        "rank_constant": RANK_CONSTANT,
        "input_candidate_count": len(candidates),
        "fused_candidate_count": len(ranked),
        "candidates": ranked,
    }


def _terms(text: str) -> set[str]:
    stop = {"what", "where", "when", "why", "how", "does", "did", "the", "and", "from", "that", "this", "with", "about", "tell"}
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text) if term.lower() not in stop}


def _candidate_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, ""))
        for key in ["text", "transcript", "visual_summary"]
        if candidate.get(key)
    ).lower()


def _exact_bonus(candidate: dict[str, Any], terms: set[str]) -> float:
    if not terms:
        return 0.0
    text = _candidate_text(candidate)
    overlap = sum(1 for term in terms if term in text)
    return min(0.25, 0.04 * overlap)


def _entity_bonus(candidate: dict[str, Any], entities: set[str]) -> float:
    if not entities:
        return 0.0
    text = _candidate_text(candidate)
    overlap = sum(1 for entity in entities if entity and entity in text)
    return min(0.2, 0.05 * overlap)


def _visual_bonus(candidate: dict[str, Any], visual_hints: set[str]) -> float:
    if not visual_hints:
        return 0.0
    text = _candidate_text(candidate)
    overlap = sum(1 for hint in visual_hints if hint in text)
    if candidate.get("source_type") == "visual_chunk":
        overlap += 1
    return min(0.18, 0.04 * overlap)


def _stale(candidate: dict[str, Any]) -> bool:
    pipeline = str((candidate.get("versions") or {}).get("pipeline", ""))
    return bool(pipeline and pipeline.startswith("legacy"))
