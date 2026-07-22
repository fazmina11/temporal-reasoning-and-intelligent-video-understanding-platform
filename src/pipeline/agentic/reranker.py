from __future__ import annotations

import re
from typing import Any


def rerank_candidates(
    *,
    candidates: list[dict[str, Any]],
    query_understanding: dict[str, Any],
) -> dict[str, Any]:
    terms = _terms(query_understanding.get("standalone_query") or query_understanding.get("raw_query") or "")
    ranked = []
    for candidate in candidates:
        text = _text(candidate)
        overlap = sum(1 for term in terms if term in text)
        rerank_score = float(candidate.get("fused_score", 0.0)) + min(0.3, 0.03 * overlap)
        row = {**candidate, "rerank_score": round(rerank_score, 6), "rerank_term_overlap": overlap}
        ranked.append(row)
    ranked.sort(key=lambda row: row["rerank_score"], reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rerank_rank"] = index
    return {"candidate_count": len(ranked), "candidates": ranked}


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text)}


def _text(candidate: dict[str, Any]) -> str:
    return " ".join(str(candidate.get(key, "")) for key in ["text", "transcript", "visual_summary"]).lower()
