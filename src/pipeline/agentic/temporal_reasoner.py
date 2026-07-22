from __future__ import annotations

from pathlib import Path
from typing import Any

from ..json_artifacts import read_json
from ..media_manifest import load_manifest


def build_temporal_context(
    *,
    repo_root: Path,
    video_id: str,
    verified_evidence: list[dict[str, Any]],
    retrieval_plan: dict[str, Any],
    query_understanding: dict[str, Any],
) -> dict[str, Any]:
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    hierarchy = _load_hierarchy(manifest)
    sorted_evidence = sorted(verified_evidence, key=lambda item: (item["start_ms"], -float(item.get("support_score", 0.0))))
    primary = max(
        sorted_evidence,
        key=lambda item: _primary_score(item, query_understanding),
    ) if sorted_evidence else None
    context_policy = retrieval_plan.get("context_policy", {})
    previous_count = int(context_policy.get("max_previous_atoms", 1))
    next_count = int(context_policy.get("max_next_atoms", 1))
    max_context_ms = int(context_policy.get("max_context_ms", 180_000))

    primary_moment = _moment_from_candidate(primary) if primary else None
    anchor_atoms = _atom_ids_for_candidate(primary, hierarchy) if primary else []
    expanded_atoms = _expand_atoms(anchor_atoms, hierarchy["atoms"], previous_count, next_count, max_context_ms)
    parent_chunk = _parent_chunk(primary, hierarchy)
    parent_event = _parent_event(primary, hierarchy, parent_chunk)
    supporting_moments = [
        {
            "source_id": item["source_id"],
            "source_type": item["source_type"],
            "start_ms": item["start_ms"],
            "end_ms": item["end_ms"],
            "support_score": item.get("support_score"),
            "reason": "supporting verified evidence",
        }
        for item in sorted_evidence
        if primary is None or item["candidate_id"] != primary["candidate_id"]
    ][:8]

    conflicts = _conflicts(sorted_evidence)
    repeated = _repeated_concepts(sorted_evidence, query_understanding)
    timeline_summary = _timeline_summary(primary, parent_chunk, parent_event, expanded_atoms)
    return {
        "primary_moment": primary_moment,
        "supporting_moments": supporting_moments,
        "expanded_atom_ids": [atom["atom_id"] for atom in expanded_atoms],
        "expanded_atoms": expanded_atoms,
        "parent_chunk": parent_chunk,
        "parent_event": parent_event,
        "timeline_summary": timeline_summary,
        "requires_multi_moment_answer": bool(query_understanding.get("requires_multi_moment_reasoning")),
        "before_after": _before_after(primary, expanded_atoms),
        "repeated_concepts": repeated,
        "conflicts": conflicts,
        "context_within_video_duration": _within_duration(expanded_atoms, int(manifest["duration_ms"])),
    }


def _load_hierarchy(manifest: dict[str, Any]) -> dict[str, Any]:
    atoms = read_json(Path(manifest["artifacts"]["atoms_path"])).get("atoms", [])
    chunks = read_json(Path(manifest["artifacts"]["semantic_chunks_path"])).get("chunks", [])
    events = read_json(Path(manifest["artifacts"]["events_path"])).get("events", [])
    return {
        "atoms": atoms,
        "chunks": chunks,
        "events": events,
        "atom_by_id": {atom["atom_id"]: atom for atom in atoms},
        "chunk_by_id": {chunk["chunk_id"]: chunk for chunk in chunks},
        "event_by_id": {event["event_id"]: event for event in events},
    }


def _moment_from_candidate(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return {
        "source_id": candidate["source_id"],
        "source_type": candidate["source_type"],
        "start_ms": candidate["start_ms"],
        "end_ms": candidate["end_ms"],
        "parent_chunk_id": candidate.get("parent_chunk_id"),
        "parent_event_id": candidate.get("parent_event_id"),
        "support_score": candidate.get("support_score"),
    }


def _atom_ids_for_candidate(candidate: dict[str, Any] | None, hierarchy: dict[str, Any]) -> list[str]:
    if not candidate:
        return []
    if candidate["source_type"] == "atom":
        return [candidate["source_id"]]
    if candidate["source_type"] in {"semantic_chunk", "visual_chunk"}:
        chunk = hierarchy["chunk_by_id"].get(candidate["source_id"]) or hierarchy["chunk_by_id"].get(candidate.get("parent_chunk_id"))
        return list(chunk.get("atom_ids", [])) if chunk else []
    if candidate["source_type"] == "event":
        event = hierarchy["event_by_id"].get(candidate["source_id"]) or hierarchy["event_by_id"].get(candidate.get("parent_event_id"))
        return list(event.get("atom_ids", [])) if event else []
    parent_chunk = hierarchy["chunk_by_id"].get(candidate.get("parent_chunk_id"))
    if parent_chunk:
        return list(parent_chunk.get("atom_ids", []))
    return []


def _expand_atoms(atom_ids: list[str], atoms: list[dict[str, Any]], previous: int, next_: int, max_context_ms: int) -> list[dict[str, Any]]:
    if not atom_ids:
        return []
    indices = [idx for idx, atom in enumerate(atoms) if atom["atom_id"] in set(atom_ids)]
    if not indices:
        return []
    start_index = max(0, min(indices) - previous)
    end_index = min(len(atoms) - 1, max(indices) + next_)
    selected = atoms[start_index : end_index + 1]
    while selected and selected[-1]["end_ms"] - selected[0]["start_ms"] > max_context_ms:
        if len(selected) <= len(atom_ids):
            break
        if selected[0]["atom_id"] not in atom_ids:
            selected = selected[1:]
        elif selected[-1]["atom_id"] not in atom_ids:
            selected = selected[:-1]
        else:
            break
    return selected


def _parent_chunk(candidate: dict[str, Any] | None, hierarchy: dict[str, Any]) -> dict[str, Any] | None:
    if not candidate:
        return None
    return hierarchy["chunk_by_id"].get(candidate.get("parent_chunk_id")) or hierarchy["chunk_by_id"].get(candidate.get("source_id"))


def _parent_event(candidate: dict[str, Any] | None, hierarchy: dict[str, Any], parent_chunk: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return (
        hierarchy["event_by_id"].get(candidate.get("parent_event_id"))
        or hierarchy["event_by_id"].get(candidate.get("source_id"))
        or hierarchy["event_by_id"].get((parent_chunk or {}).get("parent_event_id"))
    )


def _before_after(primary: dict[str, Any] | None, atoms: list[dict[str, Any]]) -> dict[str, Any]:
    if not primary:
        return {"before": [], "after": []}
    return {
        "before": [atom["atom_id"] for atom in atoms if atom["end_ms"] <= primary["start_ms"]],
        "after": [atom["atom_id"] for atom in atoms if atom["start_ms"] >= primary["end_ms"]],
    }


def _conflicts(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(evidence) < 2:
        return []
    top = evidence[:5]
    span = max(item["end_ms"] for item in top) - min(item["start_ms"] for item in top)
    if span > 240_000:
        return [{"type": "distant_evidence", "message": "Top evidence spans distant timeline moments."}]
    return []


def _repeated_concepts(evidence: list[dict[str, Any]], query_understanding: dict[str, Any]) -> list[dict[str, Any]]:
    if "repeated_concept" not in set(query_understanding.get("query_types") or []):
        return []
    by_event: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        event_id = item.get("parent_event_id") or "unknown"
        by_event.setdefault(event_id, []).append(item)
    return [
        {"parent_event_id": event_id, "count": len(items), "start_ms": min(item["start_ms"] for item in items)}
        for event_id, items in by_event.items()
        if len(items) > 1
    ]


def _timeline_summary(primary: dict[str, Any] | None, chunk: dict[str, Any] | None, event: dict[str, Any] | None, atoms: list[dict[str, Any]]) -> str:
    if not primary:
        return "No verified primary timeline moment was found."
    title = (event or {}).get("title") or (chunk or {}).get("title") or primary["source_id"]
    transcript = " ".join(atom.get("transcript_text", "") for atom in atoms if atom.get("transcript_text"))
    return f"Primary moment is {primary['start_ms']} ms to {primary['end_ms']} ms in '{title}'. Context transcript: {transcript[:700]}"


def _within_duration(atoms: list[dict[str, Any]], duration_ms: int) -> bool:
    return all(0 <= atom["start_ms"] < atom["end_ms"] <= duration_ms for atom in atoms)


def _primary_score(item: dict[str, Any], query_understanding: dict[str, Any]) -> float:
    score = float(item.get("support_score", item.get("rerank_score", 0.0)) or 0.0)
    source_type = item.get("source_type")
    if source_type == "semantic_chunk":
        score += 0.1
    elif source_type == "event":
        score += 0.08
    elif source_type == "atom":
        score -= 0.03
    text = f"{item.get('text', '')} {item.get('transcript', '')}".lower()
    query_types = set(query_understanding.get("query_types") or [])
    if query_types & {"definition", "concept"}:
        if any(phrase in text for phrase in [" is ", "called", "protocol", "means", "refers to"]):
            score += 0.18
        if len(text.split()) > 20:
            score += 0.05
    return score
