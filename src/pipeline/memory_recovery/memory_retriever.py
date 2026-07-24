"""Memory retriever combining query parser, candidate generator, and ranker into a clean public API.

Performs episodic memory retrieval without LLM text generation or answer synthesis.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import CandidateMemory, MemoryQuery, MemoryRetrievalResult
from .memory_candidate_generator import generate_candidates
from .memory_parser import parse_memory_query
from .memory_ranker import rank_candidates


class MemoryRetriever:
    """Public MemoryRetriever API composing Parser, Candidate Generator, and Ranker."""

    def __init__(
        self,
        retrieval_context: Mapping[str, Sequence[dict[str, Any]]] | None = None,
    ) -> None:
        self.retrieval_context = retrieval_context

    def retrieve_memory(
        self,
        query: str | MemoryQuery,
        retrieval_context: Mapping[str, Sequence[dict[str, Any]]] | None = None,
        *,
        video_id: str = "default_video",
        top_k: int | None = 5,
        min_score: float = 0.1,
    ) -> MemoryRetrievalResult:
        """Retrieve memory moments using instance or injected retrieval_context."""
        context = retrieval_context if retrieval_context is not None else self.retrieval_context
        return retrieve_memory(
            query=query,
            retrieval_context=context,
            video_id=video_id,
            top_k=top_k,
            min_score=min_score,
        )


def retrieve_memory(
    query: str | MemoryQuery,
    retrieval_context: Mapping[str, Sequence[dict[str, Any]]] | None = None,
    *,
    video_id: str = "default_video",
    top_k: int | None = 5,
    min_score: float = 0.1,
    evidence_store: Mapping[str, Sequence[dict[str, Any]]] | None = None,
) -> MemoryRetrievalResult:
    """Retrieve ranked candidate memory moments for a vague episodic memory query.

    Pipeline:
    1. Parse the query using Memory Parser.
    2. Generate candidate memories across retrieval sources.
    3. Rank candidates and normalize scores.
    4. Select the best candidate and aggregate matched features.
    5. Return a MemoryRetrievalResult.
    """
    start_time = time.perf_counter()
    context = retrieval_context if retrieval_context is not None else evidence_store

    # 1. Parse query
    if isinstance(query, str):
        parsed_query = parse_memory_query(query)
    elif isinstance(query, MemoryQuery):
        parsed_query = query
    else:
        # Handle non-string/non-MemoryQuery gracefully without raising unhandled exceptions
        raw_str = str(query)
        parsed_query = parse_memory_query(raw_str)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # 2. Check if is_memory_query is False
    if not parsed_query.is_memory_query:
        return MemoryRetrievalResult(
            original_query=parsed_query.original_query,
            parsed_query=parsed_query,
            candidates=[],
            best_candidate=None,
            confidence=0.0,
            matched_features=[],
            retrieval_time_ms=round(elapsed_ms, 3),
        )

    # 3. Generate candidate memories
    raw_candidates = generate_candidates(
        parsed_query,
        context,
        video_id=video_id,
        min_score=min_score,
        top_k=None,
    )

    # 4. Rank candidates
    ranked_candidates = rank_candidates(
        raw_candidates,
        top_k=top_k,
    )

    # 5. Select best candidate & confidence
    best_candidate = ranked_candidates[0] if ranked_candidates else None
    confidence = round(best_candidate.score, 4) if best_candidate else 0.0

    # Aggregate matched features
    matched_set: set[str] = set()
    matched_features: list[str] = []
    for cand in ranked_candidates:
        for feat in cand.matched_features:
            if feat not in matched_set:
                matched_set.add(feat)
                matched_features.append(feat)

    total_time_ms = (time.perf_counter() - start_time) * 1000.0

    return MemoryRetrievalResult(
        original_query=parsed_query.original_query,
        parsed_query=parsed_query,
        candidates=ranked_candidates,
        best_candidate=best_candidate,
        confidence=confidence,
        matched_features=matched_features,
        retrieval_time_ms=round(total_time_ms, 3),
    )
