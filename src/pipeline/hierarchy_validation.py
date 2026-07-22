from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic_spans import validate_atomic_spans
from .frame_extraction import validate_frame_index
from .hierarchy_indexing import (
    BASE_COLLECTIONS,
    _chroma,
    hierarchy_collection_name,
)
from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now, validate_manifest_timeline
from .semantic_chunks import validate_semantic_chunks

HIERARCHY_VALIDATION_SCHEMA_VERSION = "hierarchy-validation-v1"


class HierarchyValidationError(RuntimeError):
    """Raised when the full base hierarchy cannot be validated."""


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def validate_full_hierarchy(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Validate atoms, frames, chunks, events, and hierarchy Chroma collections."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)

    atom_report = validate_atomic_spans(repo_root=repo_root, video_id=video_id)
    frame_report = validate_frame_index(repo_root=repo_root, video_id=video_id)
    chunk_report = validate_semantic_chunks(repo_root=repo_root, video_id=video_id)

    atoms_payload = read_json(Path(manifest["artifacts"]["atoms_path"]))
    chunks_payload = read_json(Path(manifest["artifacts"]["semantic_chunks_path"]))
    events_payload = read_json(Path(manifest["artifacts"]["events_path"]))
    visual_payload = read_json(Path(manifest["artifacts"]["visual_artifacts_path"]))

    atoms = atoms_payload.get("atoms", [])
    chunks = chunks_payload.get("chunks", [])
    events = events_payload.get("events", [])
    visual_records = visual_payload.get("records", [])
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not atom_report["valid"]:
        errors.append(_issue("atom_validation", "Atomic span validation failed."))
    if not frame_report["valid"]:
        errors.append(_issue("frame_validation", "Frame validation failed."))
    if not chunk_report["valid"]:
        errors.append(_issue("chunk_validation", "Semantic chunk validation failed."))

    atom_ids = {atom["atom_id"] for atom in atoms}
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    event_ids = {event["event_id"] for event in events}

    if sum(bool(atom.get("semantic_chunk_id")) for atom in atoms) != len(atoms):
        errors.append(_issue("atom_chunk_attachment", "Not every atom has semantic_chunk_id."))
    if sum(bool(atom.get("visual_evidence")) for atom in atoms) != len(atoms):
        errors.append(_issue("atom_visual_attachment", "Not every atom has visual evidence."))
    if len(visual_records) != len(atoms):
        errors.append(_issue("visual_record_count", "Visual records do not match atom count."))
    if sum(bool(record.get("clip")) for record in visual_records) != len(atoms):
        warnings.append(_issue("clip_record_count", "Not every atom has a generated clip."))

    chunk_parent_ids = [chunk.get("parent_event_id") for chunk in chunks]
    if any(parent_id not in event_ids for parent_id in chunk_parent_ids):
        errors.append(_issue("chunk_event_attachment", "A chunk references an invalid parent event."))
    if len(chunk_parent_ids) != len(chunks) or any(not parent_id for parent_id in chunk_parent_ids):
        errors.append(_issue("chunk_event_attachment", "Not every chunk has parent_event_id."))

    event_chunk_refs = [chunk_id for event in events for chunk_id in event.get("chunk_ids", [])]
    if set(event_chunk_refs) != chunk_ids:
        errors.append(_issue("event_chunk_coverage", "Events do not cover exactly all chunks."))
    duplicate_event_chunk_refs = {
        chunk_id for chunk_id in event_chunk_refs if event_chunk_refs.count(chunk_id) > 1
    }
    if duplicate_event_chunk_refs:
        errors.append(_issue("event_chunk_duplicates", "A chunk belongs to more than one event."))

    event_atom_refs = {atom_id for event in events for atom_id in event.get("atom_ids", [])}
    if event_atom_refs != atom_ids:
        errors.append(_issue("event_atom_coverage", "Events do not cover exactly all atoms."))
    if events:
        if events[0].get("start_ms") != 0:
            errors.append(_issue("event_timeline_start", "First event must start at 0 ms."))
        if events[-1].get("end_ms") != manifest["duration_ms"]:
            errors.append(_issue("event_timeline_end", "Last event must reach video duration."))
        for previous, current in zip(events, events[1:]):
            if previous.get("end_ms") != current.get("start_ms"):
                errors.append(_issue("event_interval_conflict", "Event intervals are not contiguous."))
                break
    else:
        errors.append(_issue("events_empty", "Events artifact is empty."))

    chroma_counts: dict[str, int | None] = {}
    hierarchy_index = manifest.get("artifact_metadata", {}).get("hierarchy_index", {})
    expected_counts = hierarchy_index.get("collections", {})
    try:
        client, embedding_function = _chroma(repo_root)
        for base_name in BASE_COLLECTIONS:
            collection_name = hierarchy_collection_name(base_name)
            chroma_counts[collection_name] = client.get_collection(
                collection_name,
                embedding_function=embedding_function,
            ).count()
            expected_count = expected_counts.get(base_name)
            if expected_count is not None and chroma_counts[collection_name] < expected_count:
                errors.append(
                    _issue(
                        "chroma_count",
                        f"{collection_name} has fewer records than expected.",
                    )
                )
    except Exception as exc:
        errors.append(_issue("chroma_access", f"Could not inspect Chroma collections: {exc}"))

    report = {
        "schema_version": HIERARCHY_VALIDATION_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": manifest["duration_ms"],
        "valid": len(errors) == 0,
        "checks": {
            "atoms_valid": atom_report["valid"],
            "frames_valid": frame_report["valid"],
            "semantic_chunks_valid": chunk_report["valid"],
            "all_atoms_have_chunks": sum(bool(atom.get("semantic_chunk_id")) for atom in atoms) == len(atoms),
            "all_atoms_have_visual_evidence": sum(bool(atom.get("visual_evidence")) for atom in atoms) == len(atoms),
            "all_chunks_have_parent_events": all(bool(chunk.get("parent_event_id")) for chunk in chunks),
            "events_cover_all_chunks_once": set(event_chunk_refs) == chunk_ids and not duplicate_event_chunk_refs,
            "events_cover_all_atoms": event_atom_refs == atom_ids,
            "event_timeline_is_contiguous": not any(
                issue["code"].startswith("event_") for issue in errors
            ),
            "chroma_collections_available": not any(
                issue["code"] == "chroma_access" for issue in errors
            ),
        },
        "metrics": {
            "atom_count": len(atoms),
            "atoms_with_transcript": sum(bool(atom.get("transcript_text")) for atom in atoms),
            "atoms_with_visual_evidence": sum(bool(atom.get("visual_evidence")) for atom in atoms),
            "semantic_chunk_count": len(chunks),
            "chunks_with_parent_event": sum(bool(chunk.get("parent_event_id")) for chunk in chunks),
            "event_count": len(events),
            "visual_record_count": len(visual_records),
            "clip_record_count": sum(bool(record.get("clip")) for record in visual_records),
            "chroma_counts": chroma_counts,
        },
        "errors": errors,
        "warnings": warnings,
        "validated_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["hierarchy_validation_path"]), report)
    manifest.setdefault("artifact_metadata", {})["hierarchy_validation"] = {
        "schema_version": report["schema_version"],
        "validation_passed": report["valid"],
        "hierarchy_validation_path": manifest["artifacts"]["hierarchy_validation_path"],
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate the full video hierarchy base.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    report = validate_full_hierarchy(repo_root=Path(args.repo_root), video_id=args.video_id)
    status = "passed" if report["valid"] else "failed"
    print(f"Hierarchy validation {status}: {report['metrics']}")


if __name__ == "__main__":
    main()
