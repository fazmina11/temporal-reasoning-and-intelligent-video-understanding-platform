from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .atomic_spans import ATOM_SCHEMA_VERSION
from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now, validate_manifest_timeline

SEMANTIC_CHUNK_SCHEMA_VERSION = "semantic-chunks-v1"
SEMANTIC_CHUNK_VALIDATION_SCHEMA_VERSION = "semantic-chunk-validation-v1"


class SemanticChunkError(RuntimeError):
    """Raised when semantic chunks cannot be built or validated."""


@dataclass(frozen=True)
class SemanticChunkConfig:
    minimum_chunk_duration_ms: int = 12_000
    target_chunk_duration_ms: int = 35_000
    maximum_chunk_duration_ms: int = 60_000
    split_on_scene_cut: bool = True
    split_on_visual_difference: bool = True
    split_on_pause: bool = True
    split_on_forced_boundary: bool = True

    def validate(self) -> None:
        values = (
            self.minimum_chunk_duration_ms,
            self.target_chunk_duration_ms,
            self.maximum_chunk_duration_ms,
        )
        if any(not isinstance(value, int) or value <= 0 for value in values):
            raise SemanticChunkError("Semantic chunk durations must be positive integers.")
        if not (
            self.minimum_chunk_duration_ms
            <= self.target_chunk_duration_ms
            <= self.maximum_chunk_duration_ms
        ):
            raise SemanticChunkError(
                "Semantic chunk durations must satisfy minimum <= target <= maximum."
            )


def _load_atoms(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(Path(manifest["artifacts"]["atoms_path"]))
    if not isinstance(payload, dict) or payload.get("schema_version") != ATOM_SCHEMA_VERSION:
        raise SemanticChunkError("Atomic span artifact has an unsupported schema.")
    if payload.get("video_id") != manifest["video_id"]:
        raise SemanticChunkError("Atom video_id does not match manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise SemanticChunkError("Atom source hash does not match manifest.")
    if not isinstance(payload.get("atoms"), list):
        raise SemanticChunkError("Atomic span artifact has no atom list.")
    return payload


def _clean_summary_text(text: str, max_words: int = 12) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", text)
    if not words:
        return "Visual or silent segment"
    return " ".join(words[:max_words])


def _split_reasons_between_atoms(
    previous_atom: dict[str, Any],
    current_atom: dict[str, Any],
    current_chunk_start_ms: int,
    config: SemanticChunkConfig,
) -> list[str]:
    reasons: list[str] = []
    previous_end_reasons = set(previous_atom.get("boundary_end_reasons") or [])
    current_duration = current_atom["end_ms"] - current_chunk_start_ms
    if current_duration > config.maximum_chunk_duration_ms:
        reasons.append("maximum_chunk_duration")
    if current_duration >= config.target_chunk_duration_ms:
        if config.split_on_scene_cut and "scene_cut" in previous_end_reasons:
            reasons.append("scene_cut")
        if config.split_on_visual_difference and "visual_difference" in previous_end_reasons:
            reasons.append("visual_difference")
        if config.split_on_pause and "pause" in previous_end_reasons:
            reasons.append("pause")
        if config.split_on_forced_boundary and previous_atom.get("end_boundary_forced"):
            reasons.append("forced_atomic_boundary")
    return reasons


def _make_chunk(
    *,
    video_id: str,
    index: int,
    atoms: list[dict[str, Any]],
    split_reason: list[str],
) -> dict[str, Any]:
    transcript_text = " ".join(
        atom.get("transcript_text", "").strip()
        for atom in atoms
        if atom.get("transcript_text")
    ).strip()
    representative_frame_ids: list[str] = []
    for atom in atoms:
        for frame_id in atom.get("representative_frame_ids") or []:
            if frame_id not in representative_frame_ids:
                representative_frame_ids.append(frame_id)
    speaker_ids = sorted(
        {
            speaker_id
            for atom in atoms
            for speaker_id in (atom.get("speaker_ids") or [])
        }
    )
    confidence_values = [
        float(atom["asr_confidence"])
        for atom in atoms
        if isinstance(atom.get("asr_confidence"), (int, float))
    ]
    return {
        "video_id": video_id,
        "chunk_id": f"chunk_{index:06d}",
        "atom_ids": [atom["atom_id"] for atom in atoms],
        "start_ms": atoms[0]["start_ms"],
        "end_ms": atoms[-1]["end_ms"],
        "duration_ms": atoms[-1]["end_ms"] - atoms[0]["start_ms"],
        "title": _clean_summary_text(transcript_text),
        "summary_text": _clean_summary_text(transcript_text, max_words=36),
        "transcript_text": transcript_text,
        "speaker_ids": speaker_ids,
        "representative_frame_ids": representative_frame_ids[:12],
        "split_reason_from_previous": split_reason,
        "asr_confidence": (
            round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else None
        ),
    }


def build_semantic_chunks(
    *,
    repo_root: Path,
    video_id: str,
    config: SemanticChunkConfig | None = None,
) -> dict[str, Any]:
    """Run Phase C8 and build coherent semantic chunks from canonical atoms."""
    config = config or SemanticChunkConfig()
    config.validate()
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    atom_payload = _load_atoms(manifest)
    atoms = atom_payload["atoms"]
    if not atoms:
        raise SemanticChunkError("Cannot build semantic chunks without atoms.")

    chunks: list[dict[str, Any]] = []
    current_atoms: list[dict[str, Any]] = [atoms[0]]
    pending_split_reason: list[str] = ["timeline_start"]
    for previous_atom, current_atom in zip(atoms, atoms[1:]):
        split_reasons = _split_reasons_between_atoms(
            previous_atom,
            current_atom,
            current_atoms[0]["start_ms"],
            config,
        )
        current_duration = previous_atom["end_ms"] - current_atoms[0]["start_ms"]
        if split_reasons and current_duration >= config.minimum_chunk_duration_ms:
            chunks.append(
                _make_chunk(
                    video_id=video_id,
                    index=len(chunks) + 1,
                    atoms=current_atoms,
                    split_reason=pending_split_reason,
                )
            )
            current_atoms = [current_atom]
            pending_split_reason = split_reasons
        else:
            current_atoms.append(current_atom)

    chunks.append(
        _make_chunk(
            video_id=video_id,
            index=len(chunks) + 1,
            atoms=current_atoms,
            split_reason=pending_split_reason,
        )
    )

    atom_to_chunk = {
        atom_id: chunk["chunk_id"]
        for chunk in chunks
        for atom_id in chunk["atom_ids"]
    }
    for atom in atoms:
        atom["semantic_chunk_id"] = atom_to_chunk.get(atom["atom_id"])

    payload = {
        "schema_version": SEMANTIC_CHUNK_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": manifest["duration_ms"],
        "config": asdict(config),
        "atom_schema_version": atom_payload["schema_version"],
        "atom_count": len(atoms),
        "chunk_count": len(chunks),
        "chunks": chunks,
        "quality_metrics": {
            "minimum_chunk_duration_ms": min(chunk["duration_ms"] for chunk in chunks),
            "maximum_chunk_duration_ms": max(chunk["duration_ms"] for chunk in chunks),
            "average_chunk_duration_ms": round(
                sum(chunk["duration_ms"] for chunk in chunks) / len(chunks),
                2,
            ),
        },
        "created_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["semantic_chunks_path"]), payload)
    atom_payload["semantic_chunk_attachment"] = {
        "schema_version": SEMANTIC_CHUNK_SCHEMA_VERSION,
        "semantic_chunks_path": manifest["artifacts"]["semantic_chunks_path"],
        "chunk_count": len(chunks),
        "completed_at": utc_now(),
    }
    atom_payload["updated_at"] = utc_now()
    write_json_atomic(Path(manifest["artifacts"]["atoms_path"]), atom_payload)
    return payload


def _issue(code: str, message: str, chunk_id: str | None = None) -> dict[str, Any]:
    issue = {"code": code, "message": message}
    if chunk_id is not None:
        issue["chunk_id"] = chunk_id
    return issue


def validate_semantic_chunks(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Run Phase C9 and validate atom-to-chunk hierarchy."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    atom_payload = _load_atoms(manifest)
    atoms = atom_payload["atoms"]
    chunks_path = Path(manifest["artifacts"]["semantic_chunks_path"])
    if not chunks_path.is_file():
        raise SemanticChunkError(f"Semantic chunk artifact is missing: {chunks_path}")
    payload = read_json(chunks_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("chunks"), list):
        raise SemanticChunkError("Semantic chunk artifact has an invalid structure.")

    chunks = payload["chunks"]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    atom_lookup = {atom["atom_id"]: atom for atom in atoms}
    assigned_atom_ids: list[str] = []
    previous_end_ms: int | None = None

    if payload.get("schema_version") != SEMANTIC_CHUNK_SCHEMA_VERSION:
        errors.append(_issue("schema_version", "Unsupported semantic chunk schema."))
    if payload.get("video_id") != video_id:
        errors.append(_issue("video_id", "Chunk video_id does not match."))
    if payload.get("source_sha256") != manifest["source_sha256"]:
        errors.append(_issue("source_sha256", "Source hash does not match manifest."))
    if payload.get("duration_ms") != manifest["duration_ms"]:
        errors.append(_issue("duration_ms", "Chunk duration does not match manifest."))

    for index, chunk in enumerate(chunks):
        chunk_id = chunk.get("chunk_id")
        expected_chunk_id = f"chunk_{index + 1:06d}"
        if chunk_id != expected_chunk_id:
            errors.append(_issue("chunk_order", f"Expected {expected_chunk_id}.", str(chunk_id)))
        atom_ids = chunk.get("atom_ids")
        if not isinstance(atom_ids, list) or not atom_ids:
            errors.append(_issue("empty_chunk", "Chunk must reference at least one atom.", chunk_id))
            continue
        invalid_atom_ids = [atom_id for atom_id in atom_ids if atom_id not in atom_lookup]
        if invalid_atom_ids:
            errors.append(
                _issue(
                    "invalid_atom_reference",
                    f"Chunk references invalid atoms: {invalid_atom_ids}",
                    chunk_id,
                )
            )
            continue
        chunk_atoms = [atom_lookup[atom_id] for atom_id in atom_ids]
        if chunk.get("start_ms") != chunk_atoms[0]["start_ms"]:
            errors.append(_issue("chunk_start", "Chunk start must equal first atom start.", chunk_id))
        if chunk.get("end_ms") != chunk_atoms[-1]["end_ms"]:
            errors.append(_issue("chunk_end", "Chunk end must equal last atom end.", chunk_id))
        if chunk.get("duration_ms") != chunk.get("end_ms") - chunk.get("start_ms"):
            errors.append(_issue("chunk_duration", "Chunk duration is inconsistent.", chunk_id))
        for left, right in zip(chunk_atoms, chunk_atoms[1:]):
            if left["end_ms"] != right["start_ms"]:
                errors.append(_issue("non_contiguous_atoms", "Chunk atoms are not contiguous.", chunk_id))
        if previous_end_ms is not None:
            if chunk.get("start_ms") != previous_end_ms:
                errors.append(_issue("chunk_interval_conflict", "Chunk intervals conflict.", chunk_id))
        previous_end_ms = chunk.get("end_ms")
        assigned_atom_ids.extend(atom_ids)

    atom_id_set = set(atom_lookup)
    assigned_set = set(assigned_atom_ids)
    duplicate_assignments = sorted(
        {atom_id for atom_id in assigned_atom_ids if assigned_atom_ids.count(atom_id) > 1}
    )
    missing_atom_ids = sorted(atom_id_set - assigned_set)
    if duplicate_assignments:
        errors.append(
            _issue("duplicate_atom_assignment", f"Atoms assigned more than once: {duplicate_assignments}")
        )
    if missing_atom_ids:
        errors.append(_issue("missing_atom_assignment", f"Atoms missing from chunks: {missing_atom_ids}"))
    if chunks and chunks[0].get("start_ms") != 0:
        errors.append(_issue("timeline_start", "First chunk must start at 0 ms."))
    if chunks and chunks[-1].get("end_ms") != manifest["duration_ms"]:
        errors.append(_issue("timeline_end", "Last chunk must end at video duration."))
    if not chunks:
        errors.append(_issue("empty_chunks", "Semantic chunk list must not be empty."))

    report = {
        "schema_version": SEMANTIC_CHUNK_VALIDATION_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": manifest["duration_ms"],
        "semantic_chunks_path": str(chunks_path),
        "valid": len(errors) == 0,
        "checks": {
            "all_chunks_reference_valid_atoms": not any(
                issue["code"] == "invalid_atom_reference" for issue in errors
            ),
            "every_atom_belongs_to_one_chunk": not missing_atom_ids and not duplicate_assignments,
            "chunk_boundaries_match_atoms": not any(
                issue["code"] in {"chunk_start", "chunk_end", "chunk_duration"}
                for issue in errors
            ),
            "chunk_intervals_do_not_conflict": not any(
                issue["code"] == "chunk_interval_conflict" for issue in errors
            ),
            "timeline_is_exactly_covered": not any(
                issue["code"] in {"timeline_start", "timeline_end"}
                for issue in errors
            ),
        },
        "metrics": {
            "atom_count": len(atoms),
            "chunk_count": len(chunks),
            "assigned_atom_count": len(assigned_set),
            "missing_atom_count": len(missing_atom_ids),
            "duplicate_assignment_count": len(duplicate_assignments),
        },
        "errors": errors,
        "warnings": warnings,
        "validated_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["chunk_validation_path"]), report)

    manifest.setdefault("artifact_metadata", {})["semantic_chunk_validation"] = {
        "schema_version": report["schema_version"],
        "semantic_chunks_path": str(chunks_path),
        "chunk_validation_path": manifest["artifacts"]["chunk_validation_path"],
        "validation_passed": report["valid"],
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return report


def run_semantic_chunking(
    *,
    repo_root: Path,
    video_id: str,
    config: SemanticChunkConfig | None = None,
) -> dict[str, Any]:
    chunks = build_semantic_chunks(repo_root=repo_root, video_id=video_id, config=config)
    report = validate_semantic_chunks(repo_root=repo_root, video_id=video_id)
    if not report["valid"]:
        raise SemanticChunkError(
            f"Semantic chunk validation failed with {len(report['errors'])} error(s)."
        )
    return {"chunks": chunks, "validation": report}
