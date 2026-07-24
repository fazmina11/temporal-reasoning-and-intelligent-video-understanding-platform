from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .citation_registry import canonicalize_citation_evidence, validate_citation_objects


def build_evidence_packet(
    *,
    request: dict[str, Any],
    outcome_candidate: str,
    verified_evidence: list[dict[str, Any]],
    temporal_context: dict[str, Any],
    answerability: dict[str, Any],
    repo_root: Path | None = None,
    query_understanding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered_evidence = _order_evidence(
        verified_evidence,
        temporal_context,
        query_understanding or {},
    )
    citations = []
    evidence_items = []
    for index, item in enumerate(ordered_evidence[:8], start=1):
        citation_id = f"S{index}"
        canonical = (
            canonicalize_citation_evidence(
                repo_root=repo_root,
                video_id=request["video_id"],
                item=item,
                citation_id=citation_id,
                temporal_context=temporal_context,
                question=(query_understanding or {}).get("standalone_query") or request["query"],
            )
            if repo_root is not None
            else {**item, "citation_id": citation_id, "evidence_id": f"E_DYNAMIC_{index:06d}", "canonical_source_type": item["source_type"], "evidence_anchor": {"start_ms": item["start_ms"], "end_ms": item["end_ms"], "score": 0.5, "reason": "legacy"}, "answer_context_window": {"start_ms": item["start_ms"], "end_ms": item["end_ms"]}, "citation_interval": {"start_ms": item["start_ms"], "end_ms": item["end_ms"]}}
        )
        citations.append(
            {
                "citation_id": citation_id,
                "evidence_id": canonical["evidence_id"],
                "source_type": canonical["source_type"],
                "canonical_source_type": canonical["canonical_source_type"],
                "source_id": canonical["source_id"],
                "video_id": canonical["video_id"],
                "start_ms": canonical["start_ms"],
                "end_ms": canonical["end_ms"],
                "evidence_anchor": canonical["evidence_anchor"],
                "answer_context_window": canonical["answer_context_window"],
                "citation_interval": canonical["citation_interval"],
                "source_interval": canonical.get("source_interval", canonical["citation_interval"]),
                "parent_atom_ids": canonical.get("parent_atom_ids", []),
                "parent_chunk_id": canonical.get("parent_chunk_id"),
                "parent_event_id": canonical.get("parent_event_id"),
                "quality_score": canonical.get("quality_score"),
            }
        )
        evidence_items.append(
            {
                "citation_id": citation_id,
                "evidence_id": canonical["evidence_id"],
                "source_type": canonical["source_type"],
                "canonical_source_type": canonical["canonical_source_type"],
                "source_id": canonical["source_id"],
                "start_ms": canonical["start_ms"],
                "end_ms": canonical["end_ms"],
                "evidence_anchor": canonical["evidence_anchor"],
                "answer_context_window": canonical["answer_context_window"],
                "citation_interval": canonical["citation_interval"],
                "source_interval": canonical.get("source_interval", canonical["citation_interval"]),
                "text": _clean_evidence_text(
                    canonical.get("text") or canonical.get("transcript") or ""
                ),
                "visual_summary": canonical.get("visual_summary") or "",
                "media_refs": _safe_media_refs(canonical.get("media_refs") or {}),
                "support_score": canonical.get("support_score", 0.0),
                "quality_score": canonical.get("quality_score"),
            }
        )
    citation_validation = validate_citation_objects(citations)
    return {
        "question": request["query"],
        "video_id": request["video_id"],
        "answer_mode": request.get("answer_mode", "strict_video"),
        "outcome_candidate": outcome_candidate,
        "answerability": answerability,
        "citations": citations,
        "citation_validation": citation_validation,
        "verified_evidence": evidence_items,
        "temporal_context": {
            "primary_moment": temporal_context.get("primary_moment"),
            "supporting_moments": temporal_context.get("supporting_moments", [])[:5],
            "timeline_summary": temporal_context.get("timeline_summary", ""),
            "before_after": temporal_context.get("before_after", {}),
            "repeated_concepts": temporal_context.get("repeated_concepts", []),
            "conflicts": temporal_context.get("conflicts", []),
        },
        "visual_references": [
            {
                "citation_id": item["citation_id"],
                "media_refs": item["media_refs"],
                "visual_summary": item["visual_summary"],
            }
            for item in evidence_items
            if item["visual_summary"] or item["media_refs"].get("frames")
        ],
        "missing_evidence_notes": _missing_notes(answerability, temporal_context),
        "allowed_answer_style": {
            "direct": True,
            "must_cite": bool(citations),
            "must_include_timestamp": bool(citations),
            "no_filesystem_paths": True,
            "citations_from_registry_only": repo_root is not None,
            "state_limitations": outcome_candidate != "answer",
        },
    }


def _clip_text(text: str, limit: int = 900) -> str:
    text = " ".join(str(text).split())
    return text[:limit]


def _clean_evidence_text(text: str, limit: int = 900) -> str:
    value = str(text).strip()
    if re.match(r"^Atom\s+\S+\s+from\s+\d+\s+ms\s+to\s+\d+\s+ms\.", value):
        value = value.split("\n", 1)[1] if "\n" in value else value
    value = re.split(r"\n(?:Boundary reasons|Frames):", value, maxsplit=1)[0]
    return _clip_text(value, limit)


def _order_evidence(
    verified_evidence: list[dict[str, Any]],
    temporal_context: dict[str, Any],
    query_understanding: dict[str, Any],
) -> list[dict[str, Any]]:
    primary = temporal_context.get("primary_moment") or {}
    primary_key = (primary.get("source_type"), primary.get("source_id"))
    query_types = set(query_understanding.get("query_types") or [])
    if "ocr_or_slide_text" in query_types:
        source_priority = {"ocr": 0, "atom": 1, "semantic_chunk": 2, "visual_chunk": 3, "event": 4}
    elif "visual_memory" in query_types:
        source_priority = {
            "ocr": 0,
            "visual_chunk": 0,
            "atom": 0,
            "semantic_chunk": 0,
            "event": 0,
        }
    elif "exact_timestamp" in query_types:
        source_priority = {"atom": 0, "semantic_chunk": 1, "speaker_turn": 2, "event": 3, "ocr": 4, "visual_chunk": 5}
    elif "comparison" in query_types:
        # Comparisons commonly cross an atomic boundary: one atom introduces
        # side A and the next connects side B. Rank the coherent semantic unit
        # first, then let citation canonicalization select its strongest atom.
        source_priority = {
            "semantic_chunk": 0,
            "event": 0,
            "atom": 1,
            "speaker_turn": 2,
            "visual_chunk": 3,
            "ocr": 4,
        }
    else:
        source_priority = {
            "atom": 0,
            "semantic_chunk": 1,
            "speaker_turn": 2,
            "event": 3,
            "visual_chunk": 4,
            "ocr": 5,
        }
    query = str(
        query_understanding.get("standalone_query")
        or query_understanding.get("raw_query")
        or ""
    )
    terms = _ranking_terms(query)
    entity_terms = {
        _stem(token)
        for entity in query_understanding.get("entities") or []
        if str(entity).strip().lower() in {"mcp", "api", "apis", "model context protocol"}
        for token in re.findall(r"[A-Za-z0-9]{3,}", str(entity).lower())
    }
    focused_terms = terms - entity_terms
    if focused_terms:
        terms = focused_terms
    definition_query = bool(
        {"definition", "concept"} & query_types
        or re.match(r"\s*(?:what is|what does|define|meaning of)\b", query, re.I)
    )

    def key(item: dict[str, Any]) -> tuple[int, float, int, float, int, int]:
        is_primary = (item.get("source_type"), item.get("source_id")) == primary_key
        text = _clean_evidence_text(
            item.get("text") or item.get("transcript") or ""
        ).lower()
        if query_types & {"ocr_or_slide_text", "visual_memory"}:
            text = f"{text} {item.get('visual_summary') or ''}".lower()
        overlap = sum(_term_present(term, text) for term in terms) / max(1, len(terms))
        definition_bonus = 0.0
        if definition_query:
            definition_bonus = _definition_relation_bonus(text, terms)
        lexical_score = overlap + definition_bonus
        return (
            source_priority.get(str(item.get("source_type")), 10),
            -lexical_score,
            max(1, int(item.get("end_ms", 0)) - int(item.get("start_ms", 0))),
            -float(item.get("support_score", item.get("rerank_score", 0.0)) or 0.0),
            0 if is_primary else 1,
            int(item.get("start_ms", 0)),
        )

    return sorted(verified_evidence, key=key)


def _ranking_terms(text: str) -> set[str]:
    stop = {
        "what", "where", "when", "why", "how", "does", "did", "the", "and",
        "from", "that", "this", "with", "about", "tell", "lecture", "speaker",
        "video", "appears", "appear", "shown", "show", "visual", "text", "slide",
        "described", "explain", "explanation", "compared", "meant",
    }
    return {
        _stem(term)
        for term in re.findall(r"[A-Za-z0-9]{3,}", text.lower())
        if term not in stop
    }


def _term_present(term: str, text: str) -> bool:
    for token in re.findall(r"[A-Za-z0-9]{3,}", text.lower()):
        stemmed = _stem(token)
        if stemmed == term:
            return True
        if min(len(stemmed), len(term)) >= 5 and (
            stemmed.startswith(term) or term.startswith(stemmed)
        ):
            return True
    return False


def _definition_relation_bonus(text: str, terms: set[str]) -> float:
    for term in terms:
        escaped = re.escape(term)
        if re.search(
            rf"\b{escaped}\w*\b.{{0,35}}\b(?:means|refers to|includes|which includes)\b|"
            rf"\b(?:means|refers to|includes|which includes)\b.{{0,35}}\b{escaped}\w*\b",
            text,
        ):
            return 0.25
    for term in terms:
        escaped = re.escape(term)
        if re.search(
            rf"\b{escaped}\w*\b.{{0,24}}\b(?:is|gives|provides)\b|"
            rf"\b(?:is|gives|provides)\b.{{0,24}}\b{escaped}\w*\b",
            text,
        ):
            return 0.12
    return 0.0


def _stem(term: str) -> str:
    for suffix in ("ization", "ation", "ing", "ed", "es", "s"):
        if len(term) > len(suffix) + 3 and term.endswith(suffix):
            return term[: -len(suffix)]
    return term


def _safe_media_refs(media_refs: dict[str, Any]) -> dict[str, Any]:
    frames = media_refs.get("frames") or media_refs.get("frame_ids") or []
    clips = media_refs.get("clip_paths") or []
    if media_refs.get("clip"):
        clips = [media_refs["clip"]]
    return {
        "frames": [str(frame) for frame in frames if frame],
        "clip_ids": [str(path).replace("\\", "/").split("/")[-1] for path in clips if path],
    }


def _missing_notes(answerability: dict[str, Any], temporal_context: dict[str, Any]) -> list[str]:
    notes = []
    if answerability.get("decision") not in {"answer", "partial_answer"}:
        notes.append(f"answerability is {answerability.get('decision')}")
    if temporal_context.get("conflicts"):
        notes.append("conflicting or distant evidence was detected")
    if not temporal_context.get("primary_moment"):
        notes.append("no primary moment found")
    return notes
