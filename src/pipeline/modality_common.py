from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_artifacts import read_json


def load_transcript_segments(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rows = payload.get("segments", [])
        return [item for item in rows if isinstance(item, dict)]
    return []


def normalized_segment(segment: dict[str, Any], index: int) -> dict[str, Any] | None:
    start = segment.get("start_ms")
    end = segment.get("end_ms")
    if start is None:
        start = round(float(segment.get("start", 0.0)) * 1000)
    if end is None:
        end = round(float(segment.get("end", 0.0)) * 1000)
    start_ms, end_ms = int(start), int(end)
    if end_ms <= start_ms:
        return None
    return {
        **segment,
        "segment_id": segment.get("segment_id") or f"segment_{index:06d}",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "text": " ".join(str(segment.get("text", "")).split()),
    }


def hierarchy_maps(manifest: dict[str, Any]) -> dict[str, Any]:
    artifacts = manifest.get("artifacts", {})
    atoms_payload = read_json(Path(artifacts["atoms_path"]))
    chunks_payload = read_json(Path(artifacts["semantic_chunks_path"]))
    events_path = Path(artifacts.get("events_path", ""))
    events_payload = read_json(events_path) if events_path.is_file() else {"events": []}

    atoms = atoms_payload.get("atoms", [])
    chunks = chunks_payload.get("chunks", [])
    events = events_payload.get("events", [])
    atom_by_id = {row["atom_id"]: row for row in atoms}
    chunk_by_id = {row["chunk_id"]: row for row in chunks}
    event_by_id = {row["event_id"]: row for row in events}
    return {
        "atoms": atoms,
        "chunks": chunks,
        "events": events,
        "atom_by_id": atom_by_id,
        "chunk_by_id": chunk_by_id,
        "event_by_id": event_by_id,
    }


def timeline_parents(timestamp_ms: int, maps: dict[str, Any]) -> dict[str, str | None]:
    atom = next(
        (
            row
            for row in maps["atoms"]
            if int(row["start_ms"]) <= timestamp_ms < int(row["end_ms"])
        ),
        None,
    )
    chunk_id = atom.get("semantic_chunk_id") if atom else None
    chunk = maps["chunk_by_id"].get(chunk_id) if chunk_id else None
    return {
        "atom_id": atom.get("atom_id") if atom else None,
        "parent_chunk_id": chunk_id,
        "parent_event_id": chunk.get("parent_event_id") if chunk else None,
    }


def timeline_parent_ids(start_ms: int, end_ms: int, maps: dict[str, Any]) -> dict[str, Any]:
    """Return all hierarchy parents touched by a modality interval."""
    atoms = [
        row
        for row in maps["atoms"]
        if overlap_ms(int(row["start_ms"]), int(row["end_ms"]), int(start_ms), int(end_ms)) > 0
    ]
    atom_ids = [row["atom_id"] for row in atoms]
    chunk_ids = sorted({row.get("semantic_chunk_id") for row in atoms if row.get("semantic_chunk_id")})
    event_ids = sorted({
        maps["chunk_by_id"].get(chunk_id, {}).get("parent_event_id")
        for chunk_id in chunk_ids
        if maps["chunk_by_id"].get(chunk_id, {}).get("parent_event_id")
    })
    midpoint = (int(start_ms) + int(end_ms)) // 2
    primary = timeline_parents(midpoint, maps)
    return {
        **primary,
        "parent_atom_ids": atom_ids,
        "parent_chunk_ids": chunk_ids,
        "parent_event_ids": event_ids,
    }


def overlap_ms(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))
