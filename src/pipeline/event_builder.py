from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now, validate_manifest_timeline
from .semantic_chunks import SEMANTIC_CHUNK_SCHEMA_VERSION, validate_semantic_chunks

EVENT_SCHEMA_VERSION = "events-v1"


class EventBuilderError(RuntimeError):
    """Raised when events cannot be built from semantic chunks."""


@dataclass(frozen=True)
class EventConfig:
    target_event_duration_ms: int = 90_000
    maximum_event_duration_ms: int = 150_000

    def validate(self) -> None:
        if self.target_event_duration_ms <= 0 or self.maximum_event_duration_ms <= 0:
            raise EventBuilderError("Event duration settings must be positive.")
        if self.target_event_duration_ms > self.maximum_event_duration_ms:
            raise EventBuilderError("target_event_duration_ms must be <= maximum_event_duration_ms.")


def _clean_title(text: str, max_words: int = 14) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", text)
    return " ".join(words[:max_words]) if words else "Visual or silent event"


def _load_chunks(manifest: dict[str, Any]) -> dict[str, Any]:
    path = Path(manifest["artifacts"]["semantic_chunks_path"])
    if not path.is_file():
        raise EventBuilderError(f"Semantic chunk artifact is missing: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != SEMANTIC_CHUNK_SCHEMA_VERSION:
        raise EventBuilderError("Semantic chunk artifact has an unsupported schema.")
    if payload.get("video_id") != manifest["video_id"]:
        raise EventBuilderError("Semantic chunk video_id does not match manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise EventBuilderError("Semantic chunk source hash does not match manifest.")
    return payload


def _make_event(video_id: str, index: int, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    transcript_text = " ".join(
        chunk.get("transcript_text", "").strip()
        for chunk in chunks
        if chunk.get("transcript_text")
    ).strip()
    atom_ids = [atom_id for chunk in chunks for atom_id in chunk.get("atom_ids", [])]
    frame_ids: list[str] = []
    for chunk in chunks:
        for frame_id in chunk.get("representative_frame_ids", []):
            if frame_id not in frame_ids:
                frame_ids.append(frame_id)
    confidence_values = [
        float(chunk["asr_confidence"])
        for chunk in chunks
        if isinstance(chunk.get("asr_confidence"), (int, float))
    ]
    return {
        "video_id": video_id,
        "event_id": f"event_{index:06d}",
        "chunk_ids": [chunk["chunk_id"] for chunk in chunks],
        "atom_ids": atom_ids,
        "start_ms": chunks[0]["start_ms"],
        "end_ms": chunks[-1]["end_ms"],
        "duration_ms": chunks[-1]["end_ms"] - chunks[0]["start_ms"],
        "title": _clean_title(transcript_text),
        "summary_text": _clean_title(transcript_text, max_words=42),
        "transcript_text": transcript_text,
        "representative_frame_ids": frame_ids[:20],
        "asr_confidence": (
            round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else None
        ),
    }


def build_events(
    *,
    repo_root: Path,
    video_id: str,
    config: EventConfig | None = None,
) -> dict[str, Any]:
    """Run C10 and group semantic chunks into explanation/activity events."""
    config = config or EventConfig()
    config.validate()
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    chunk_report = validate_semantic_chunks(repo_root=repo_root, video_id=video_id)
    if not chunk_report["valid"]:
        raise EventBuilderError("Semantic chunks must validate before event building.")
    chunk_payload = _load_chunks(manifest)
    chunks = chunk_payload["chunks"]
    if not chunks:
        raise EventBuilderError("Cannot build events without semantic chunks.")

    events: list[dict[str, Any]] = []
    current_chunks: list[dict[str, Any]] = [chunks[0]]
    for chunk in chunks[1:]:
        candidate_duration = chunk["end_ms"] - current_chunks[0]["start_ms"]
        should_split = candidate_duration > config.maximum_event_duration_ms
        if not should_split and candidate_duration >= config.target_event_duration_ms:
            reasons = set(chunk.get("split_reason_from_previous") or [])
            should_split = bool(reasons & {"scene_cut", "pause", "maximum_chunk_duration"})
        if should_split:
            events.append(_make_event(video_id, len(events) + 1, current_chunks))
            current_chunks = [chunk]
        else:
            current_chunks.append(chunk)
    events.append(_make_event(video_id, len(events) + 1, current_chunks))

    chunk_to_event = {
        chunk_id: event["event_id"]
        for event in events
        for chunk_id in event["chunk_ids"]
    }
    for chunk in chunks:
        chunk["parent_event_id"] = chunk_to_event[chunk["chunk_id"]]
    chunk_payload["event_attachment"] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "events_path": manifest["artifacts"]["events_path"],
        "event_count": len(events),
        "completed_at": utc_now(),
    }
    chunk_payload["updated_at"] = utc_now()
    write_json_atomic(Path(manifest["artifacts"]["semantic_chunks_path"]), chunk_payload)

    payload = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": manifest["duration_ms"],
        "config": asdict(config),
        "semantic_chunks_path": manifest["artifacts"]["semantic_chunks_path"],
        "chunk_count": len(chunks),
        "event_count": len(events),
        "events": events,
        "quality_metrics": {
            "minimum_event_duration_ms": min(event["duration_ms"] for event in events),
            "maximum_event_duration_ms": max(event["duration_ms"] for event in events),
            "average_event_duration_ms": round(
                sum(event["duration_ms"] for event in events) / len(events),
                2,
            ),
        },
        "created_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["events_path"]), payload)

    manifest.setdefault("artifact_metadata", {})["events"] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "events_path": manifest["artifacts"]["events_path"],
        "event_count": len(events),
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return payload
