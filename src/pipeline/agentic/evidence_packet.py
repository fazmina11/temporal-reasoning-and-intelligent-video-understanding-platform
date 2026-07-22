from __future__ import annotations

from typing import Any


def build_evidence_packet(
    *,
    request: dict[str, Any],
    outcome_candidate: str,
    verified_evidence: list[dict[str, Any]],
    temporal_context: dict[str, Any],
    answerability: dict[str, Any],
) -> dict[str, Any]:
    ordered_evidence = _order_evidence(verified_evidence, temporal_context)
    citations = []
    evidence_items = []
    for index, item in enumerate(ordered_evidence[:8], start=1):
        citation_id = f"S{index}"
        citations.append(
            {
                "citation_id": citation_id,
                "source_type": item["source_type"],
                "source_id": item["source_id"],
                "video_id": item["video_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "parent_chunk_id": item.get("parent_chunk_id"),
                "parent_event_id": item.get("parent_event_id"),
            }
        )
        evidence_items.append(
            {
                "citation_id": citation_id,
                "source_type": item["source_type"],
                "source_id": item["source_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "text": _clip_text(item.get("transcript") or item.get("text") or ""),
                "visual_summary": item.get("visual_summary") or "",
                "media_refs": _safe_media_refs(item.get("media_refs") or {}),
                "support_score": item.get("support_score", 0.0),
            }
        )
    return {
        "question": request["query"],
        "video_id": request["video_id"],
        "answer_mode": request.get("answer_mode", "strict_video"),
        "outcome_candidate": outcome_candidate,
        "answerability": answerability,
        "citations": citations,
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
            "state_limitations": outcome_candidate != "answer",
        },
    }


def _clip_text(text: str, limit: int = 900) -> str:
    text = " ".join(str(text).split())
    return text[:limit]


def _order_evidence(verified_evidence: list[dict[str, Any]], temporal_context: dict[str, Any]) -> list[dict[str, Any]]:
    primary = temporal_context.get("primary_moment") or {}
    primary_key = (primary.get("source_type"), primary.get("source_id"))

    def key(item: dict[str, Any]) -> tuple[int, float, int]:
        is_primary = (item.get("source_type"), item.get("source_id")) == primary_key
        return (
            0 if is_primary else 1,
            -float(item.get("support_score", item.get("rerank_score", 0.0)) or 0.0),
            int(item.get("start_ms", 0)),
        )

    return sorted(verified_evidence, key=key)


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
