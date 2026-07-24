from __future__ import annotations

import re
from typing import Any
from uuid import uuid4


FOLLOW_UP_CUES = {
    "that",
    "this",
    "there",
    "then",
    "after that",
    "before that",
    "it",
    "same",
    "previous",
}

REFERENCE_TERMS = {
    "that",
    "this",
    "it",
    "there",
    "same",
    "previous",
    "after that",
    "before that",
    "that part",
    "the slide",
    "the diagram",
    "the graph",
    "the example",
    "example",
    "key point",
    "important difference",
    "the model",
}


def _first_cited_moment(turns: list[dict[str, Any]]) -> dict[str, Any] | None:
    for turn in reversed(turns):
        citations = turn.get("citations") or []
        for citation in citations:
            if citation.get("source_id") and (
                citation.get("start_ms") is not None or citation.get("start_seconds") is not None
            ):
                start_ms = citation.get("start_ms")
                end_ms = citation.get("end_ms")
                if start_ms is None and citation.get("start_seconds") is not None:
                    start_ms = int(float(citation["start_seconds"]) * 1000)
                if end_ms is None and citation.get("end_seconds") is not None:
                    end_ms = int(float(citation["end_seconds"]) * 1000)
                return {
                    "source_id": citation["source_id"],
                    "source_type": citation.get("source_type", "unknown"),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "parent_event_id": citation.get("parent_event_id"),
                }
    return None


def resolve_conversation_references(
    *,
    raw_query: str,
    conversation_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    query = raw_query.strip()
    context = conversation_context or []
    lowered = query.lower()
    has_follow_up_cue = any(re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in FOLLOW_UP_CUES)
    moment = _first_cited_moment(context) if has_follow_up_cue else None
    unresolved = _unresolved_references(lowered) if has_follow_up_cue and not moment else []

    if not moment:
        needs_clarification = bool(unresolved)
        return {
            "resolution_id": f"res_{uuid4().hex[:12]}",
            "standalone_query": query,
            "resolved_references": {},
            "resolved_entities": [],
            "resolved_time_hints_ms": [],
            "unresolved_references": unresolved,
            "requires_reference": bool(has_follow_up_cue),
            "reference_resolved": False,
            "resolution_confidence": 1.0 if not has_follow_up_cue else 0.25,
            "needs_clarification": needs_clarification,
            "ambiguity_reasons": (
                ["follow-up reference has no prior citation or timeline anchor"]
                if needs_clarification
                else []
            ),
        }

    start_ms = moment.get("start_ms") or 0
    timestamp = _format_ms(start_ms)
    standalone = query
    if "after" in lowered:
        standalone = f"{query} after the previously cited moment near {timestamp}"
    elif "before" in lowered:
        standalone = f"{query} before the previously cited moment near {timestamp}"
    else:
        standalone = f"{query} referring to the previously cited moment near {timestamp}"

    return {
        "resolution_id": f"res_{uuid4().hex[:12]}",
        "standalone_query": standalone,
        "resolved_references": {"previous_moment": moment},
        "resolved_entities": [],
        "resolved_time_hints_ms": [start_ms],
        "unresolved_references": [],
        "requires_reference": True,
        "reference_resolved": True,
        "resolution_confidence": 0.9,
        "needs_clarification": False,
        "ambiguity_reasons": [],
    }


def _format_ms(ms: int) -> str:
    total = max(0, int(ms // 1000))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _unresolved_references(lowered_query: str) -> list[str]:
    unresolved = [
        term
        for term in sorted(REFERENCE_TERMS, key=len, reverse=True)
        if re.search(rf"\b{re.escape(term)}\b", lowered_query)
    ]
    if "this" in unresolved and re.search(r"\bthis\s+(lecture|video|mcp explanation|selected video|question)\b", lowered_query):
        unresolved.remove("this")
    if "the slide" in unresolved and re.search(
        r"\b(?:opening|first|initial|title|intro(?:duction)?)\s+slide\b|\btitle\b.*\bslide\b",
        lowered_query,
    ):
        unresolved.remove("the slide")
    return unresolved[:5]
