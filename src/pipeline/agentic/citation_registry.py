from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..json_artifacts import read_json
from ..media_manifest import load_manifest

REGISTRY_SCHEMA_VERSION = "phase-n-evidence-registry-v1"
AUDIO_PADDING_MS = 500

SOURCE_ALIASES = {
    "atom": "atomic_span",
    "atomic_span": "atomic_span",
    "semantic_chunk": "semantic_chunk",
    "visual_chunk": "visual_evidence",
    "event": "event",
    "ocr": "ocr_track",
    "speaker_turn": "speaker_turn",
    "audio_event": "audio_event",
}


def evidence_registry_path(repo_root: Path, video_id: str) -> Path:
    return repo_root / "data" / "processed" / "evidence_registry" / f"{video_id}.jsonl"


def build_evidence_registry(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Create the canonical source registry used for citations."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    artifacts = manifest.get("artifacts") or {}
    pipeline_version = str(manifest.get("pipeline_version") or "")
    records: list[dict[str, Any]] = []

    records.extend(_records_from_atoms(repo_root, video_id, artifacts, pipeline_version))
    records.extend(_records_from_chunks(repo_root, video_id, artifacts, pipeline_version))
    records.extend(_records_from_events(repo_root, video_id, artifacts, pipeline_version))
    records.extend(_records_from_visual(repo_root, video_id, artifacts, pipeline_version))
    records.extend(_records_from_ocr(repo_root, video_id, artifacts, pipeline_version))
    records.extend(_records_from_speakers(repo_root, video_id, artifacts, pipeline_version))
    records.extend(_records_from_audio(repo_root, video_id, artifacts, pipeline_version, int(manifest.get("duration_ms") or 0)))

    for index, record in enumerate(records, start=1):
        record.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
        record.setdefault("evidence_id", f"E_{record['canonical_source_type'].upper()}_{index:06d}")

    path = evidence_registry_path(repo_root, video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "video_id": video_id,
        "registry_path": str(path),
        "record_count": len(records),
        "source_type_counts": _source_type_counts(records),
    }


def load_evidence_registry(*, repo_root: Path, video_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    path = evidence_registry_path(repo_root, video_id)
    if not path.is_file():
        build_evidence_registry(repo_root=repo_root, video_id=video_id)
    registry: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.is_file():
        return registry
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        source_type = _canonical_source_type(record.get("source_type") or record.get("canonical_source_type"))
        registry[(source_type, str(record.get("source_id")))] = record
    return registry


def canonicalize_citation_evidence(
    *,
    repo_root: Path,
    video_id: str,
    item: dict[str, Any],
    citation_id: str,
    temporal_context: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    """Map retrieved evidence to canonical intervals and registry IDs."""
    registry = load_evidence_registry(repo_root=repo_root, video_id=video_id)
    source_type = _canonical_source_type(item.get("source_type"))
    source_id = str(item.get("source_id") or "")
    record = registry.get((source_type, source_id)) or _fallback_record(video_id, item, source_type, source_id)
    duration_ms = _duration_ms(repo_root, video_id)
    anchor = _select_anchor(record, item, temporal_context, question, registry)
    citation_interval = _citation_interval(record, item, source_type, duration_ms)
    context_window = _context_window(anchor, temporal_context, duration_ms)
    return {
        **item,
        "citation_id": citation_id,
        "evidence_id": record["evidence_id"],
        "canonical_source_type": record["canonical_source_type"],
        "source_type": _public_source_type(record["canonical_source_type"]),
        "source_id": record["source_id"],
        "start_ms": citation_interval["start_ms"],
        "end_ms": citation_interval["end_ms"],
        "evidence_anchor": anchor,
        "answer_context_window": context_window,
        "citation_interval": citation_interval,
        "parent_atom_ids": record.get("parent_atom_ids", []),
        "parent_chunk_id": record.get("parent_chunk_id") or item.get("parent_chunk_id"),
        "parent_event_id": record.get("parent_event_id") or item.get("parent_event_id"),
        "quality_score": record.get("quality_score", item.get("support_score", 0.0)),
        "registry": {
            "schema_version": record.get("schema_version", REGISTRY_SCHEMA_VERSION),
            "artifact_uri": record.get("artifact_uri"),
        },
    }


def validate_citation_objects(citations: list[dict[str, Any]], *, duration_ms: int | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in citations:
        citation_id = str(citation.get("citation_id") or "")
        if not citation_id:
            errors.append({"citation_id": citation_id, "reason": "missing_citation_id"})
        if citation_id in seen:
            errors.append({"citation_id": citation_id, "reason": "duplicate_citation_id"})
        seen.add(citation_id)
        if not citation.get("evidence_id"):
            errors.append({"citation_id": citation_id, "reason": "missing_evidence_id"})
        if not citation.get("source_id"):
            errors.append({"citation_id": citation_id, "reason": "missing_source_id"})
        start = citation.get("start_ms")
        end = citation.get("end_ms")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            errors.append({"citation_id": citation_id, "reason": "invalid_citation_interval"})
        if duration_ms is not None and isinstance(end, int) and end > duration_ms:
            errors.append({"citation_id": citation_id, "reason": "citation_exceeds_video_duration"})
        for interval_name in ("evidence_anchor", "answer_context_window", "citation_interval"):
            interval = citation.get(interval_name)
            if not _valid_interval(interval, duration_ms):
                errors.append({"citation_id": citation_id, "reason": f"invalid_{interval_name}"})
    return {"valid": not errors, "error_count": len(errors), "errors": errors}


def citation_source_compatible(sentence: str, citation: dict[str, Any]) -> bool:
    claim_type = infer_claim_type(sentence)
    source_type = citation.get("canonical_source_type") or _canonical_source_type(citation.get("source_type"))
    return source_type in COMPATIBILITY[claim_type]


def infer_claim_type(sentence: str) -> str:
    lowered = sentence.lower()
    if re.search(r"\b(slide|screen|written|text|caption|title|heading|ocr|read)\b", lowered):
        return "visible_text"
    if re.search(r"\b(who said|which speaker|speaker id|speaker identity|whose voice)\b", lowered):
        return "speaker_identity"
    if re.search(r"\b(sound|audio|music|silence|pause|noise|heard)\b", lowered):
        return "acoustic_event"
    if re.search(r"\b(draw|shown|displayed|graph|diagram|chart|image|frame|clip|visual)\b", lowered):
        return "visual_action"
    if re.search(r"\b(summary|overall|chapter|section|event)\b", lowered):
        return "broad_summary"
    return "spoken_statement"


COMPATIBILITY = {
    "spoken_statement": {"atomic_span", "semantic_chunk", "speaker_turn", "event"},
    "visible_text": {"ocr_track", "visual_evidence"},
    "speaker_identity": {"speaker_turn", "atomic_span", "semantic_chunk"},
    "acoustic_event": {"audio_event"},
    "broad_summary": {"event", "semantic_chunk"},
    "visual_action": {"visual_evidence", "ocr_track", "semantic_chunk"},
}


def _records_from_atoms(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "atoms_path", "atoms")
    return [
        _record(
            prefix="TXT",
            video_id=video_id,
            source_type="atomic_span",
            source_id=item["atom_id"],
            start_ms=item["start_ms"],
            end_ms=item["end_ms"],
            parent_atom_ids=[item["atom_id"]],
            parent_chunk_id=item.get("semantic_chunk_id"),
            parent_event_id=item.get("parent_event_id"),
            artifact_uri=str(path),
            pipeline_version=pipeline_version,
            text=item.get("transcript_text", ""),
        )
        for item in _items(path, "atoms")
        if item.get("atom_id")
    ]


def _records_from_chunks(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "semantic_chunks_path", "semantic_chunks")
    return [
        _record(
            prefix="CHK",
            video_id=video_id,
            source_type="semantic_chunk",
            source_id=item["chunk_id"],
            start_ms=item["start_ms"],
            end_ms=item["end_ms"],
            parent_atom_ids=item.get("atom_ids", []),
            parent_chunk_id=item["chunk_id"],
            parent_event_id=item.get("parent_event_id"),
            artifact_uri=str(path),
            pipeline_version=pipeline_version,
            text=" ".join(str(item.get(key, "")) for key in ("title", "summary_text", "transcript_text")),
        )
        for item in _items(path, "chunks")
        if item.get("chunk_id")
    ]


def _records_from_events(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "events_path", "events")
    return [
        _record(
            prefix="EVT",
            video_id=video_id,
            source_type="event",
            source_id=item["event_id"],
            start_ms=item["start_ms"],
            end_ms=item["end_ms"],
            parent_atom_ids=item.get("atom_ids", []),
            parent_chunk_id=None,
            parent_event_id=item["event_id"],
            artifact_uri=str(path),
            pipeline_version=pipeline_version,
            text=" ".join(str(item.get(key, "")) for key in ("title", "summary_text", "summary", "transcript_text")),
        )
        for item in _items(path, "events")
        if item.get("event_id")
    ]


def _records_from_visual(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "visual_artifacts_path", "visual_artifacts")
    records = []
    for item in _items(path, "records"):
        source_id = item.get("visual_id") or item.get("atom_id")
        if not source_id:
            continue
        records.append(
            _record(
                prefix="VIS",
                video_id=video_id,
                source_type="visual_evidence",
                source_id=source_id,
                start_ms=int(item.get("start_ms") or 0),
                end_ms=max(int(item.get("end_ms") or 0), int(item.get("start_ms") or 0) + 1),
                parent_atom_ids=[item["atom_id"]] if item.get("atom_id") else [],
                parent_chunk_id=item.get("parent_chunk_id"),
                parent_event_id=item.get("parent_event_id"),
                artifact_uri=str(path),
                pipeline_version=pipeline_version,
                quality_score=float(item.get("quality_score", 0.7) or 0.7),
            )
        )
    return records


def _records_from_ocr(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "ocr_path", "ocr")
    return [
        _record(
            prefix="OCR",
            video_id=video_id,
            source_type="ocr_track",
            source_id=item["ocr_id"],
            start_ms=item["start_ms"],
            end_ms=max(item["start_ms"] + 1, item["end_ms"]),
            parent_atom_ids=item.get("parent_atom_ids", []),
            parent_chunk_id=item.get("parent_chunk_id"),
            parent_event_id=item.get("parent_event_id"),
            artifact_uri=str(path),
            pipeline_version=pipeline_version,
            quality_score=float(item.get("mean_confidence", item.get("quality_score", 0.0)) or 0.0),
            text=item.get("text", ""),
        )
        for item in _items(path, "records")
        if item.get("ocr_id")
    ]


def _records_from_speakers(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "speakers_path", "speakers")
    return [
        _record(
            prefix="SPK",
            video_id=video_id,
            source_type="speaker_turn",
            source_id=item["turn_id"],
            start_ms=item["start_ms"],
            end_ms=item["end_ms"],
            parent_atom_ids=item.get("parent_atom_ids", []),
            parent_chunk_id=item.get("parent_chunk_id"),
            parent_event_id=item.get("parent_event_id"),
            artifact_uri=str(path),
            pipeline_version=pipeline_version,
            quality_score=float(item.get("confidence", item.get("quality_score", 0.7)) or 0.7),
            text=item.get("text", ""),
        )
        for item in _items(path, "turns")
        if item.get("turn_id")
    ]


def _records_from_audio(repo_root: Path, video_id: str, artifacts: dict[str, Any], pipeline_version: str, duration_ms: int) -> list[dict[str, Any]]:
    path = _path(repo_root, video_id, artifacts, "audio_events_path", "audio_events")
    records = []
    for item in _items(path, "events"):
        if not item.get("audio_event_id"):
            continue
        start_ms = max(0, int(item["start_ms"]) - AUDIO_PADDING_MS)
        end_ms = min(duration_ms or int(item["end_ms"]) + AUDIO_PADDING_MS, int(item["end_ms"]) + AUDIO_PADDING_MS)
        records.append(
            _record(
                prefix="AUD",
                video_id=video_id,
                source_type="audio_event",
                source_id=item["audio_event_id"],
                start_ms=start_ms,
                end_ms=max(start_ms + 1, end_ms),
                parent_atom_ids=item.get("parent_atom_ids", []),
                parent_chunk_id=item.get("parent_chunk_id"),
                parent_event_id=item.get("parent_event_id"),
                artifact_uri=str(path),
                pipeline_version=pipeline_version,
                quality_score=float(item.get("confidence", item.get("quality_score", 0.0)) or 0.0),
                text=str(item.get("label", "")),
            )
        )
    return records


def _record(
    *,
    prefix: str,
    video_id: str,
    source_type: str,
    source_id: str,
    start_ms: int,
    end_ms: int,
    parent_atom_ids: list[str],
    parent_chunk_id: str | None,
    parent_event_id: str | None,
    artifact_uri: str,
    pipeline_version: str,
    quality_score: float = 0.8,
    text: str = "",
) -> dict[str, Any]:
    canonical = _canonical_source_type(source_type)
    return {
        "evidence_id": f"E_{prefix}_{_numeric_suffix(source_id)}",
        "video_id": video_id,
        "source_type": source_type,
        "canonical_source_type": canonical,
        "source_id": str(source_id),
        "start_ms": int(start_ms),
        "end_ms": max(int(start_ms) + 1, int(end_ms)),
        "parent_atom_ids": parent_atom_ids,
        "parent_chunk_id": parent_chunk_id,
        "parent_event_id": parent_event_id,
        "artifact_uri": artifact_uri,
        "pipeline_version": pipeline_version,
        "quality_score": max(0.0, min(1.0, float(quality_score or 0.0))),
        "text_excerpt": " ".join(str(text).split())[:600],
    }


def _fallback_record(video_id: str, item: dict[str, Any], source_type: str, source_id: str) -> dict[str, Any]:
    return _record(
        prefix="DYN",
        video_id=video_id,
        source_type=source_type,
        source_id=source_id or str(item.get("candidate_id", "unknown")),
        start_ms=int(item.get("start_ms", 0)),
        end_ms=int(item.get("end_ms", 1)),
        parent_atom_ids=item.get("parent_atom_ids", []),
        parent_chunk_id=item.get("parent_chunk_id"),
        parent_event_id=item.get("parent_event_id"),
        artifact_uri="dynamic_verified_candidate",
        pipeline_version=str((item.get("versions") or {}).get("pipeline", "")),
        quality_score=float(item.get("support_score", 0.5) or 0.5),
        text=str(item.get("text") or item.get("transcript") or item.get("visual_summary") or ""),
    )


def _select_anchor(
    record: dict[str, Any],
    item: dict[str, Any],
    temporal_context: dict[str, Any],
    question: str,
    registry: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, int | float | str]:
    source_type = record["canonical_source_type"]
    if source_type in {"atomic_span", "ocr_track", "speaker_turn", "audio_event", "visual_evidence"}:
        return _interval_with_score(record["start_ms"], record["end_ms"], 0.9, "source_interval")
    parent_atom_ids = set(record.get("parent_atom_ids") or [])
    expanded_atoms = temporal_context.get("expanded_atoms") or []
    terms = _terms(question)
    best_atom = None
    best_score = -1.0
    for atom in expanded_atoms:
        if parent_atom_ids and atom.get("atom_id") not in parent_atom_ids:
            continue
        text = str(atom.get("transcript_text", "")).lower()
        overlap = sum(1 for term in terms if term in text) / max(1, len(terms))
        score = overlap + (0.08 if atom.get("atom_id") in parent_atom_ids else 0.0)
        if score > best_score:
            best_atom = atom
            best_score = score
    if best_atom:
        return _interval_with_score(best_atom["start_ms"], best_atom["end_ms"], min(1.0, 0.45 + best_score), "best_parent_atom")
    primary = temporal_context.get("primary_moment") or {}
    if primary.get("source_id") == item.get("source_id") and _valid_interval(primary):
        return _interval_with_score(primary["start_ms"], primary["end_ms"], 0.72, "primary_moment")
    return _interval_with_score(record["start_ms"], record["end_ms"], 0.55, "source_start")


def _citation_interval(record: dict[str, Any], item: dict[str, Any], source_type: str, duration_ms: int) -> dict[str, int]:
    start, end = int(record["start_ms"]), int(record["end_ms"])
    if source_type == "audio_event":
        start = max(0, start - AUDIO_PADDING_MS)
        end = min(duration_ms or end + AUDIO_PADDING_MS, end + AUDIO_PADDING_MS)
    if source_type == "visual_evidence":
        start = max(0, start)
        end = min(duration_ms or end, max(start + 1, end))
    return {"start_ms": start, "end_ms": max(start + 1, end)}


def _context_window(anchor: dict[str, Any], temporal_context: dict[str, Any], duration_ms: int) -> dict[str, int]:
    atoms = temporal_context.get("expanded_atoms") or []
    if atoms:
        start = min(int(atom["start_ms"]) for atom in atoms)
        end = max(int(atom["end_ms"]) for atom in atoms)
    else:
        start = int(anchor["start_ms"]) - 30_000
        end = int(anchor["end_ms"]) + 30_000
    return {"start_ms": max(0, start), "end_ms": min(duration_ms or end, max(start + 1, end))}


def _path(repo_root: Path, video_id: str, artifacts: dict[str, Any], key: str, folder: str) -> Path:
    configured = artifacts.get(key)
    return Path(str(configured)) if configured else repo_root / "data" / "processed" / folder / f"{video_id}.json"


def _items(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = read_json(path)
    return [item for item in payload.get(key, []) if isinstance(item, dict)]


def _duration_ms(repo_root: Path, video_id: str) -> int:
    try:
        return int(load_manifest(repo_root=repo_root, video_id=video_id).get("duration_ms") or 0)
    except Exception:
        return 0


def _canonical_source_type(value: Any) -> str:
    raw = getattr(value, "value", value)
    normalized = str(raw or "").strip().lower()
    return SOURCE_ALIASES.get(normalized, normalized or "unknown")


def _public_source_type(canonical: str) -> str:
    mapping = {
        "atomic_span": "atom",
        "visual_evidence": "visual_chunk",
        "ocr_track": "ocr",
    }
    return mapping.get(canonical, canonical)


def _numeric_suffix(source_id: str) -> str:
    digits = re.findall(r"\d+", str(source_id))
    if digits:
        return f"{int(digits[-1]):06d}"
    return re.sub(r"[^A-Za-z0-9]+", "_", str(source_id)).strip("_")[:24] or "unknown"


def _source_type_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = record["canonical_source_type"]
        counts[key] = counts.get(key, 0) + 1
    return counts


def _interval_with_score(start_ms: int, end_ms: int, score: float, reason: str) -> dict[str, int | float | str]:
    return {"start_ms": int(start_ms), "end_ms": max(int(start_ms) + 1, int(end_ms)), "score": round(score, 6), "reason": reason}


def _valid_interval(value: Any, duration_ms: int | None = None) -> bool:
    if not isinstance(value, dict):
        return False
    start, end = value.get("start_ms"), value.get("end_ms")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        return False
    return duration_ms is None or end <= duration_ms


def _terms(text: str) -> set[str]:
    stop = {"what", "where", "when", "why", "how", "does", "did", "the", "and", "from", "that", "this", "with", "about", "tell"}
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text) if term.lower() not in stop}
