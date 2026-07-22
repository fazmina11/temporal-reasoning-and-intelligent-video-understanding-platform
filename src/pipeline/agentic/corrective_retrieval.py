from __future__ import annotations

from typing import Any

from .contracts import RetrievalPlan, RetrievalStep


def create_corrective_plan(
    *,
    original_plan: RetrievalPlan,
    query_understanding: dict[str, Any],
    answerability: dict[str, Any],
    attempt: int,
) -> RetrievalPlan:
    """Create a bounded retry plan without inventing new facts."""
    if attempt >= original_plan.max_corrective_attempts:
        return original_plan

    query = query_understanding.get("standalone_query") or query_understanding.get("raw_query") or ""
    missing_modalities = set(query_understanding.get("required_modalities") or [])
    existing = {(step.retriever, step.query.lower()) for step in original_plan.retrieval_steps}
    steps = list(original_plan.retrieval_steps)

    expanded_queries = _safe_query_expansions(query, query_understanding)
    for expanded in expanded_queries:
        for retriever, weight in [
            ("sparse_text", 1.25),
            ("chunk_dense", 1.15),
            ("event_dense", 1.1),
            ("transcript_dense", 1.0),
        ]:
            key = (retriever, expanded.lower())
            if key not in existing:
                steps.append(
                    RetrievalStep(
                        retriever=retriever,
                        level="semantic_chunk" if retriever != "transcript_dense" else "atomic_span",
                        query=expanded,
                        top_k=25,
                        weight=weight,
                    )
                )
                existing.add(key)

    if "visual" in missing_modalities and ("local_visual", query.lower()) not in existing:
        steps.append(RetrievalStep(retriever="local_visual", level="atomic_span", query=query, top_k=25, weight=1.2))
    if "visual" in missing_modalities and ("visual_dense", query.lower()) not in existing:
        steps.append(RetrievalStep(retriever="visual_dense", level="semantic_chunk", query=query, top_k=30, weight=1.3))
    for modality, retriever, level in [
        ("ocr", "ocr_sparse", "frame"),
        ("speaker", "speaker", "speaker_turn"),
        ("audio", "audio_event", "audio_event"),
    ]:
        if modality in missing_modalities and (retriever, query.lower()) not in existing:
            steps.append(RetrievalStep(retriever=retriever, level=level, query=query, top_k=25, weight=1.3))

    policy = original_plan.context_policy
    policy.max_previous_atoms = min(20, policy.max_previous_atoms + 2)
    policy.max_next_atoms = min(20, policy.max_next_atoms + 2)
    policy.max_context_ms = min(300_000, policy.max_context_ms + 60_000)

    return RetrievalPlan(
        strategy=f"{original_plan.strategy}_corrective_{attempt + 1}",
        retrieval_steps=steps[:8],
        context_policy=policy,
        requires_reranking=True,
        requires_temporal_reasoning=True,
        max_corrective_attempts=original_plan.max_corrective_attempts,
        answer_mode=original_plan.answer_mode,
    )


def should_retry(answerability: dict[str, Any], attempt: int, max_attempts: int) -> bool:
    return (
        answerability.get("decision") == "corrective_retrieval"
        and attempt < max_attempts
    )


def _safe_query_expansions(query: str, query_understanding: dict[str, Any]) -> list[str]:
    expansions = [query]
    entities = [str(entity) for entity in query_understanding.get("entities") or []]
    if entities:
        expansions.append(" ".join(entities))
    visual_hints = [str(item) for item in query_understanding.get("objects") or []]
    if visual_hints:
        expansions.append(" ".join([query, *visual_hints]))
    if "comparison" in set(query_understanding.get("query_types") or []) and len(entities) >= 2:
        expansions.append(f"{entities[0]} compared with {entities[1]}")
    deduped = []
    for item in expansions:
        text = " ".join(item.split())
        if text and text.lower() not in {seen.lower() for seen in deduped}:
            deduped.append(text)
    return deduped[:3]
