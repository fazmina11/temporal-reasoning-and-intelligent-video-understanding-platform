from __future__ import annotations

from typing import Any

from .contracts import AnswerMode, ContextPolicy, RetrievalPlan, RetrievalStep


MAX_TOP_K = 40


def create_retrieval_plan(
    *,
    query_understanding: dict[str, Any],
    answer_mode: AnswerMode | str = AnswerMode.STRICT_VIDEO,
) -> RetrievalPlan:
    query = query_understanding.get("standalone_query") or query_understanding.get("raw_query") or ""
    query_types = set(query_understanding.get("query_types") or [])
    modalities = set(query_understanding.get("required_modalities") or [])
    steps: list[RetrievalStep] = []

    if "exact_timestamp" in query_types and query_understanding.get("time_constraints"):
        return RetrievalPlan(
            strategy="exact_timeline_lookup",
            retrieval_steps=[
                RetrievalStep(
                    retriever="exact_timeline",
                    level="atomic_span",
                    query=query,
                    top_k=12,
                    weight=2.0,
                )
            ],
            context_policy=ContextPolicy(
                direction="both",
                max_previous_atoms=2,
                max_next_atoms=2,
                include_parent_chunk=True,
                include_parent_event=True,
                max_context_ms=90_000,
            ),
            requires_reranking=False,
            requires_temporal_reasoning=True,
            max_corrective_attempts=0,
            answer_mode=AnswerMode(answer_mode),
        )

    if "ocr_or_slide_text" in query_types or "ocr" in modalities:
        steps.extend(
            [
                RetrievalStep(retriever="ocr_sparse", level="frame", query=query, top_k=30, weight=1.7),
                RetrievalStep(retriever="local_visual", level="atomic_span", query=query, top_k=20, weight=1.0),
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=20, weight=1.0),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=0.9),
            ]
        )
        strategy = "ocr_slide_text_retrieval"
    elif "visual_memory" in query_types or "visual" in modalities:
        steps.extend(
            [
                RetrievalStep(retriever="ocr_sparse", level="frame", query=query, top_k=30, weight=1.6),
                RetrievalStep(retriever="visual_dense", level="semantic_chunk", query=query, top_k=30, weight=1.5),
                RetrievalStep(retriever="local_visual", level="atomic_span", query=query, top_k=20, weight=1.2),
                RetrievalStep(retriever="event_dense", level="event", query=query, top_k=15, weight=1.2),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=1.0),
            ]
        )
        if "action_memory" in query_types:
            steps.append(RetrievalStep(retriever="clip_action", level="clip", query=query, top_k=15, weight=1.1))
        strategy = "visual_causal_memory_recovery" if "cause_effect" in query_types else "visual_memory_recovery"
    elif "audio_memory" in query_types or "audio" in modalities:
        steps.extend(
            [
                RetrievalStep(retriever="audio_event", level="audio_event", query=query, top_k=25, weight=1.6),
                RetrievalStep(retriever="speaker", level="speaker_turn", query=query, top_k=20, weight=1.1),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=0.9),
            ]
        )
        strategy = "audio_memory_recovery"
    elif "speaker_question" in query_types or "speaker" in modalities:
        steps.extend(
            [
                RetrievalStep(retriever="speaker", level="speaker_turn", query=query, top_k=30, weight=1.6),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=1.0),
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=20, weight=0.9),
            ]
        )
        strategy = "speaker_grounded_retrieval"
    elif "comparison" in query_types:
        steps.extend(
            [
                RetrievalStep(retriever="event_dense", level="event", query=query, top_k=20, weight=1.4),
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=30, weight=1.2),
                RetrievalStep(retriever="sparse_text", level="semantic_chunk", query=query, top_k=30, weight=1.0),
            ]
        )
        for entity in (query_understanding.get("entities") or [])[:4]:
            steps.append(RetrievalStep(retriever="transcript_dense", level="atomic_span", query=str(entity), top_k=10, weight=0.8))
        strategy = "comparison_multi_entity"
    elif "exact_quote" in query_types:
        steps.extend(
            [
                RetrievalStep(retriever="sparse_text", level="atomic_span", query=query, top_k=30, weight=1.6),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=1.0),
            ]
        )
        strategy = "exact_quote"
    elif "exact_timestamp" in query_types:
        steps.extend(
            [
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=30, weight=1.5),
                RetrievalStep(retriever="sparse_text", level="atomic_span", query=query, top_k=30, weight=1.3),
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=20, weight=1.0),
            ]
        )
        strategy = "timestamp_moment_search"
    elif query_types & {"summary", "chapter_summary"}:
        steps.extend(
            [
                RetrievalStep(retriever="event_dense", level="event", query=query, top_k=20, weight=1.5),
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=20, weight=1.0),
            ]
        )
        strategy = "event_summary"
    elif query_types & {"definition", "concept", "cause_effect"}:
        steps.extend(
            [
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=30, weight=1.4),
                RetrievalStep(retriever="event_dense", level="event", query=query, top_k=15, weight=1.1),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=1.0),
                RetrievalStep(retriever="sparse_text", level="semantic_chunk", query=query, top_k=20, weight=0.8),
            ]
        )
        strategy = "concept_definition"
    else:
        steps.extend(
            [
                RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query=query, top_k=20, weight=1.2),
                RetrievalStep(retriever="event_dense", level="event", query=query, top_k=10, weight=1.0),
                RetrievalStep(retriever="transcript_dense", level="atomic_span", query=query, top_k=20, weight=0.9),
            ]
        )
        strategy = "broad_safe"

    steps = _bounded_steps(steps)
    return RetrievalPlan(
        strategy=strategy,
        retrieval_steps=steps,
        context_policy=ContextPolicy(
            direction="both",
            max_previous_atoms=3 if query_understanding.get("requires_multi_moment_reasoning") else 1,
            max_next_atoms=4 if query_understanding.get("requires_multi_moment_reasoning") else 1,
            include_parent_chunk=True,
            include_parent_event=True,
            max_context_ms=180_000,
        ),
        requires_reranking=True,
        requires_temporal_reasoning=bool(query_understanding.get("requires_multi_moment_reasoning", True)),
        max_corrective_attempts=2,
        answer_mode=AnswerMode(answer_mode),
    )


def _bounded_steps(steps: list[RetrievalStep]) -> list[RetrievalStep]:
    deduped: list[RetrievalStep] = []
    seen: set[tuple[str, str, str]] = set()
    for step in steps:
        key = (step.retriever, step.level, step.query.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            RetrievalStep(
                retriever=step.retriever,
                level=step.level,
                query=step.query,
                top_k=min(step.top_k, MAX_TOP_K),
                weight=step.weight,
            )
        )
    return deduped[:8]
