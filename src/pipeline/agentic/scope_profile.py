from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from ..json_artifacts import read_json, write_json_atomic
from ..media_manifest import load_manifest, save_manifest, utc_now

SCHEMA_VERSION = "phase-n-scope-profile-v1"
SCOPE_EMBEDDING_VERSION = "lexical-scope-v1"


def scope_profile_path(repo_root: Path, video_id: str) -> Path:
    return repo_root / "data" / "processed" / "scope_profiles" / f"{video_id}.json"


def build_video_scope_profile(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Build a compact, deterministic profile used by the scope firewall."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    artifacts = manifest.setdefault("artifacts", {})

    events = _load_items(_artifact_path(repo_root, video_id, artifacts, "events_path", "events"), "events")
    chunks = _load_items(_artifact_path(repo_root, video_id, artifacts, "semantic_chunks_path", "semantic_chunks"), "chunks")
    atoms = _load_items(_artifact_path(repo_root, video_id, artifacts, "atoms_path", "atoms"), "atoms")
    ocr_records = _load_items(_artifact_path(repo_root, video_id, artifacts, "ocr_path", "ocr"), "records")
    speaker_turns = _load_items(_artifact_path(repo_root, video_id, artifacts, "speakers_path", "speakers"), "turns")
    audio_events = _load_items(_artifact_path(repo_root, video_id, artifacts, "audio_events_path", "audio_events"), "events")

    event_summaries = _summaries(events)
    chunk_titles = [str(item.get("title", "")).strip() for item in chunks if str(item.get("title", "")).strip()]
    ocr_vocabulary = _top_terms(" ".join(str(item.get("text", "")) for item in ocr_records), limit=40)
    searchable_text = " ".join(
        [
            str(manifest.get("source_filename") or manifest.get("original_filename") or ""),
            *event_summaries,
            *chunk_titles,
            *(_item_text(item) for item in chunks[:80]),
            *(_item_text(item) for item in atoms[:120]),
            " ".join(ocr_vocabulary),
        ]
    )
    topic_keywords = _top_terms(searchable_text, limit=60)
    top_entities = _top_entities(searchable_text, topic_keywords)

    profile = {
        "schema_version": SCHEMA_VERSION,
        "video_id": video_id,
        "title": _title(manifest),
        "language": manifest.get("language") or "unknown",
        "duration_ms": int(manifest.get("duration_ms") or 0),
        "chapter_titles": chunk_titles[:20],
        "event_summaries": event_summaries[:50],
        "top_entities": top_entities[:50],
        "speakers": sorted({
            str(turn.get("speaker_id"))
            for turn in speaker_turns
            if turn.get("speaker_id")
        }),
        "ocr_vocabulary": ocr_vocabulary,
        "audio_event_types": sorted({
            str(event.get("label") or event.get("event_type"))
            for event in audio_events
            if event.get("label") or event.get("event_type")
        }),
        "topic_keywords": topic_keywords,
        "scope_summary": _scope_summary(manifest, event_summaries, chunk_titles),
        "scope_embedding_version": SCOPE_EMBEDDING_VERSION,
        "artifact_counts": {
            "events": len(events),
            "semantic_chunks": len(chunks),
            "atoms": len(atoms),
            "ocr_records": len(ocr_records),
            "speaker_turns": len(speaker_turns),
            "audio_events": len(audio_events),
        },
        "created_at": utc_now(),
    }

    path = scope_profile_path(repo_root, video_id)
    write_json_atomic(path, profile)
    artifacts["scope_profile_path"] = str(path)
    manifest.setdefault("artifact_metadata", {})["scope_profile"] = {
        "schema_version": SCHEMA_VERSION,
        "path": str(path),
        "scope_embedding_version": SCOPE_EMBEDDING_VERSION,
        "created_at": profile["created_at"],
    }
    manifest["updated_at"] = utc_now()
    try:
        save_manifest(repo_root=repo_root, manifest=manifest)
    except Exception:
        # Some unit and imported legacy manifests are intentionally minimal.
        # The scope profile remains valid even if the manifest cannot be rewritten.
        pass
    return profile


def load_or_build_scope_profile(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    path = Path(
        manifest.get("artifacts", {}).get("scope_profile_path")
        or scope_profile_path(repo_root, video_id)
    )
    if path.is_file():
        return read_json(path)
    return build_video_scope_profile(repo_root=repo_root, video_id=video_id)


def _load_items(path_value: Any, key: str) -> list[dict[str, Any]]:
    if not path_value:
        return []
    path = Path(str(path_value))
    if not path.is_file():
        return []
    payload = read_json(path)
    items = payload.get(key, []) if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _artifact_path(repo_root: Path, video_id: str, artifacts: dict[str, Any], key: str, folder: str) -> Path:
    configured = artifacts.get(key)
    if configured:
        return Path(str(configured))
    return repo_root / "data" / "processed" / folder / f"{video_id}.json"


def _summaries(items: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in items:
        text = " ".join(
            str(item.get(key, "")).strip()
            for key in ("title", "summary", "summary_text", "transcript_text")
            if str(item.get(key, "")).strip()
        )
        if text:
            values.append(text)
    return values


def _item_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key, ""))
        for key in ("title", "summary", "summary_text", "transcript_text", "text")
        if item.get(key)
    )


def _title(manifest: dict[str, Any]) -> str:
    raw = str(manifest.get("source_filename") or manifest.get("original_filename") or manifest.get("video_id") or "")
    stem = Path(raw).stem if raw else str(manifest.get("video_id") or "")
    return re.sub(r"[_-]+", " ", stem).strip() or str(manifest.get("video_id"))


def _scope_summary(manifest: dict[str, Any], event_summaries: list[str], chunk_titles: list[str]) -> str:
    if event_summaries:
        return " ".join(event_summaries[:3])[:700]
    if chunk_titles:
        return f"This video covers: {', '.join(chunk_titles[:6])}."
    return f"Video titled {_title(manifest)}."


def _top_entities(text: str, keywords: list[str]) -> list[str]:
    acronyms = re.findall(r"\b[A-Z]{2,}\b", text)
    capitalized = re.findall(r"\b[A-Z][A-Za-z0-9]{2,}(?:\s+[A-Z][A-Za-z0-9]{2,})?\b", text)
    values = Counter(acronyms + capitalized)
    for keyword in keywords[:20]:
        if keyword.isupper() or len(keyword) <= 4:
            values[keyword.upper() if keyword.isupper() else keyword] += 1
    return [item for item, _ in values.most_common()]


def _top_terms(text: str, *, limit: int) -> list[str]:
    counts = Counter(_terms(text))
    return [term for term, _ in counts.most_common(limit)]


def _terms(text: str) -> list[str]:
    stop = {
        "what", "where", "when", "which", "does", "with", "that", "this", "from",
        "there", "their", "about", "would", "could", "should", "video", "speaker",
        "lecturer", "presenter", "explains", "explain", "shown", "said", "says",
        "into", "then", "than", "have", "will", "your", "they", "them", "using",
    }
    return [
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_+-]{2,}", text)
        if term.lower() not in stop
    ]
