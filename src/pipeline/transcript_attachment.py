from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic_spans import ATOM_SCHEMA_VERSION, validate_atomic_spans
from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now, validate_manifest_timeline

TRANSCRIPT_ATTACHMENT_SCHEMA_VERSION = "transcript-attachment-v1"


class TranscriptAttachmentError(RuntimeError):
    """Raised when transcript evidence cannot be attached to atoms."""


def _seconds_to_ms(value: float | int) -> int:
    return max(0, int(float(value) * 1000 + 0.5))


def _load_transcript(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise TranscriptAttachmentError(f"Transcript artifact is missing: {path}")
    payload = read_json(path)
    if isinstance(payload, list):
        segments = payload
    elif isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        segments = payload["segments"]
    else:
        raise TranscriptAttachmentError(
            "Transcript must be a segment list or an object containing 'segments'."
        )
    return [segment for segment in segments if isinstance(segment, dict)]


def _load_atoms(manifest: dict[str, Any]) -> dict[str, Any]:
    atoms_path = Path(manifest["artifacts"]["atoms_path"])
    if not atoms_path.is_file():
        raise TranscriptAttachmentError(f"Atomic span artifact is missing: {atoms_path}")
    payload = read_json(atoms_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != ATOM_SCHEMA_VERSION:
        raise TranscriptAttachmentError("Atomic span artifact has an unsupported schema.")
    if payload.get("video_id") != manifest["video_id"]:
        raise TranscriptAttachmentError("Atom video_id does not match manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise TranscriptAttachmentError("Atom source hash does not match manifest.")
    return payload


def _overlaps(start_ms: int, end_ms: int, atom: dict[str, Any]) -> bool:
    return start_ms < atom["end_ms"] and end_ms > atom["start_ms"]


def _normalize_text(words: list[dict[str, Any]], fallback_segments: list[dict[str, Any]]) -> str:
    if words:
        return " ".join(str(word["text"]).strip() for word in words).strip()
    return " ".join(str(segment.get("text") or "").strip() for segment in fallback_segments).strip()


def attach_transcript_to_atoms(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Run Phase C6 and update atoms with transcript text, word IDs, and segment IDs."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    atom_payload = _load_atoms(manifest)
    atoms = atom_payload["atoms"]
    segments = _load_transcript(Path(manifest["artifacts"]["transcript_path"]))

    segment_records: list[dict[str, Any]] = []
    word_records: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(segments, start=1):
        try:
            segment_start_ms = _seconds_to_ms(segment["start"])
            segment_end_ms = _seconds_to_ms(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if segment_end_ms <= segment_start_ms:
            continue
        segment_id = f"segment_{segment_index:06d}"
        speaker_id = segment.get("speaker_id") or segment.get("speaker")
        segment_records.append(
            {
                "segment_id": segment_id,
                "start_ms": segment_start_ms,
                "end_ms": segment_end_ms,
                "text": str(segment.get("text") or "").strip(),
                "speaker_id": speaker_id,
                "avg_logprob": segment.get("avg_logprob"),
                "no_speech_prob": segment.get("no_speech_prob"),
            }
        )
        words = segment.get("words")
        if not isinstance(words, list):
            continue
        for word_index, word in enumerate(words, start=1):
            if not isinstance(word, dict):
                continue
            try:
                word_start_ms = _seconds_to_ms(word["start"])
                word_end_ms = _seconds_to_ms(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if word_end_ms <= word_start_ms:
                continue
            word_records.append(
                {
                    "word_id": f"word_{segment_index:06d}_{word_index:06d}",
                    "segment_id": segment_id,
                    "start_ms": word_start_ms,
                    "end_ms": word_end_ms,
                    "text": str(word.get("word") or "").strip(),
                    "probability": word.get("prob"),
                    "speaker_id": speaker_id,
                }
            )

    attached_atom_count = 0
    total_word_refs = 0
    total_segment_refs = 0
    confidence_values: list[float] = []
    for atom in atoms:
        atom_words = [
            word for word in word_records if _overlaps(word["start_ms"], word["end_ms"], atom)
        ]
        atom_segments = [
            segment
            for segment in segment_records
            if _overlaps(segment["start_ms"], segment["end_ms"], atom)
        ]
        speaker_ids = sorted(
            {
                str(value)
                for value in [
                    *[word.get("speaker_id") for word in atom_words],
                    *[segment.get("speaker_id") for segment in atom_segments],
                ]
                if value
            }
        )
        word_probabilities = [
            float(word["probability"])
            for word in atom_words
            if isinstance(word.get("probability"), (int, float))
        ]
        segment_confidences = [
            max(0.0, min(1.0, 1.0 + float(segment["avg_logprob"])))
            for segment in atom_segments
            if isinstance(segment.get("avg_logprob"), (int, float))
        ]
        confidence_pool = word_probabilities or segment_confidences
        asr_confidence = (
            round(sum(confidence_pool) / len(confidence_pool), 4)
            if confidence_pool
            else None
        )
        if asr_confidence is not None:
            confidence_values.append(asr_confidence)
        transcript_text = _normalize_text(atom_words, atom_segments)
        word_ids = [word["word_id"] for word in atom_words]
        segment_ids = sorted({segment["segment_id"] for segment in atom_segments})
        atom["transcript_text"] = transcript_text
        atom["word_ids"] = word_ids
        atom["transcript_word_ids"] = word_ids
        atom["segment_ids"] = segment_ids
        atom["speaker_ids"] = speaker_ids
        atom["asr_confidence"] = asr_confidence
        atom["transcript_attachment"] = {
            "schema_version": TRANSCRIPT_ATTACHMENT_SCHEMA_VERSION,
            "word_count": len(word_ids),
            "segment_count": len(segment_ids),
            "has_text": bool(transcript_text),
        }
        if transcript_text:
            attached_atom_count += 1
        total_word_refs += len(word_ids)
        total_segment_refs += len(segment_ids)

    atom_payload["transcript_attachment"] = {
        "schema_version": TRANSCRIPT_ATTACHMENT_SCHEMA_VERSION,
        "transcript_path": manifest["artifacts"]["transcript_path"],
        "segment_count": len(segment_records),
        "word_count": len(word_records),
        "attached_atom_count": attached_atom_count,
        "empty_atom_count": len(atoms) - attached_atom_count,
        "word_reference_count": total_word_refs,
        "segment_reference_count": total_segment_refs,
        "average_asr_confidence": (
            round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else None
        ),
        "completed_at": utc_now(),
    }
    atom_payload["updated_at"] = utc_now()
    write_json_atomic(Path(manifest["artifacts"]["atoms_path"]), atom_payload)
    validation = validate_atomic_spans(repo_root=repo_root, video_id=video_id)
    if not validation["valid"]:
        raise TranscriptAttachmentError("Atom validation failed after transcript attachment.")

    manifest.setdefault("artifact_metadata", {})["transcript_attachment"] = atom_payload[
        "transcript_attachment"
    ]
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return atom_payload
