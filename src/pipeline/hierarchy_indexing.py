from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import chromadb
from chromadb.utils import embedding_functions

from .event_builder import build_events
from .json_artifacts import read_json
from .media_manifest import load_manifest, save_manifest, utc_now, validate_manifest_timeline

CHROMA_PATH_NAME = "chroma_db"
EMBED_MODEL = os.getenv("HIERARCHY_EMBED_MODEL", "BAAI/bge-base-en-v1.5")
UPSERT_BATCH_SIZE = 64

COLLECTION_ATOMS_TEXT = "video_atoms_text"
COLLECTION_CHUNKS_TEXT = "video_chunks_text"
COLLECTION_CHUNKS_VISUAL = "video_chunks_visual"
COLLECTION_EVENTS = "video_events"
BASE_COLLECTIONS = (
    COLLECTION_ATOMS_TEXT,
    COLLECTION_CHUNKS_TEXT,
    COLLECTION_CHUNKS_VISUAL,
    COLLECTION_EVENTS,
)


def embedding_model_slug(model_name: str = EMBED_MODEL) -> str:
    return (
        model_name.lower()
        .replace("/", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def hierarchy_collection_name(base_name: str, model_name: str = EMBED_MODEL) -> str:
    return f"{base_name}__{embedding_model_slug(model_name)}"


COLLECTIONS = tuple(hierarchy_collection_name(name) for name in BASE_COLLECTIONS)


class HierarchyIndexingError(RuntimeError):
    """Raised when hierarchy artifacts cannot be indexed."""


def _safe_meta(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def _chroma(repo_root: Path) -> tuple[chromadb.PersistentClient, Any]:
    path = repo_root / CHROMA_PATH_NAME
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client, ef


def _collection(client: chromadb.PersistentClient, ef: Any, name: str):
    return client.get_or_create_collection(
        name=name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _document_for_atom(atom: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            f"Atom {atom['atom_id']} from {atom['start_ms']} ms to {atom['end_ms']} ms.",
            atom.get("transcript_text", ""),
            f"Boundary reasons: {', '.join(atom.get('boundary_end_reasons') or [])}.",
            f"Frames: {', '.join(atom.get('representative_frame_ids') or [])}.",
        ]
        if part.strip()
    )


def _document_for_chunk(chunk: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            chunk.get("title", ""),
            chunk.get("summary_text", ""),
            chunk.get("transcript_text", ""),
            f"Atoms: {', '.join(chunk.get('atom_ids') or [])}.",
        ]
        if part.strip()
    )


def _document_for_chunk_visual(chunk: dict[str, Any], visual_by_atom: dict[str, dict[str, Any]]) -> str:
    visual_lines: list[str] = []
    frame_ids: list[str] = []
    clip_paths: list[str] = []
    for atom_id in chunk.get("atom_ids", []):
        record = visual_by_atom.get(atom_id)
        if not record:
            continue
        for frame in record.get("frame_references", []):
            frame_ids.append(frame.get("frame_id", ""))
            visual_lines.append(
                f"{frame.get('role')} frame {frame.get('frame_id')} at {frame.get('timestamp_ms')} ms"
            )
        clip = record.get("clip")
        if clip:
            clip_paths.append(clip.get("clip_path_relative", ""))
    return "\n".join(
        [
            chunk.get("title", ""),
            f"Visual evidence frames: {', '.join(frame_id for frame_id in frame_ids if frame_id)}.",
            f"Clip paths: {', '.join(path for path in clip_paths if path)}.",
            *visual_lines,
        ]
    )


def _document_for_event(event: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            event.get("title", ""),
            event.get("summary_text", ""),
            event.get("transcript_text", ""),
            f"Chunks: {', '.join(event.get('chunk_ids') or [])}.",
        ]
        if part.strip()
    )


def _base_metadata(
    *,
    manifest: dict[str, Any],
    source_type: str,
    source_id: str,
    start_ms: int,
    end_ms: int,
    parent_chunk_id: str | None = None,
    parent_event_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str | int | float | bool]:
    metadata = {
        "video_id": manifest["video_id"],
        "pipeline_version": manifest["pipeline_version"],
        "source_type": source_type,
        "source_id": source_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "start_seconds": round(start_ms / 1000, 3),
        "end_seconds": round(end_ms / 1000, 3),
        "parent_chunk_id": parent_chunk_id or "",
        "parent_event_id": parent_event_id or "",
        "source_sha256": manifest["source_sha256"],
    }
    if extra:
        metadata.update({key: _safe_meta(value) for key, value in extra.items()})
    return metadata


def _upsert(collection: Any, ids: list[str], docs: list[str], metadatas: list[dict[str, Any]]) -> None:
    for start in range(0, len(ids), UPSERT_BATCH_SIZE):
        end = min(start + UPSERT_BATCH_SIZE, len(ids))
        collection.upsert(
            ids=ids[start:end],
            documents=docs[start:end],
            metadatas=metadatas[start:end],
        )


def index_hierarchy(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Run C11 and index canonical atoms, chunks, visual chunks, and events."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    build_events(repo_root=repo_root, video_id=video_id)
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)

    atoms_payload = read_json(Path(manifest["artifacts"]["atoms_path"]))
    chunks_payload = read_json(Path(manifest["artifacts"]["semantic_chunks_path"]))
    visual_payload = read_json(Path(manifest["artifacts"]["visual_artifacts_path"]))
    events_payload = read_json(Path(manifest["artifacts"]["events_path"]))

    atoms = atoms_payload.get("atoms", [])
    chunks = chunks_payload.get("chunks", [])
    events = events_payload.get("events", [])
    visual_by_atom = {
        record["atom_id"]: record for record in visual_payload.get("records", [])
    }
    chunk_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}

    client, ef = _chroma(repo_root)
    collections = {
        base_name: _collection(client, ef, hierarchy_collection_name(base_name))
        for base_name in BASE_COLLECTIONS
    }

    atom_ids: list[str] = []
    atom_docs: list[str] = []
    atom_metas: list[dict[str, Any]] = []
    for atom in atoms:
        chunk_id = atom.get("semantic_chunk_id") or ""
        parent_event_id = chunk_by_id.get(chunk_id, {}).get("parent_event_id", "")
        atom_ids.append(f"{video_id}__atom__{atom['atom_id']}")
        atom_docs.append(_document_for_atom(atom))
        atom_metas.append(
            _base_metadata(
                manifest=manifest,
                source_type="atom_text",
                source_id=atom["atom_id"],
                start_ms=atom["start_ms"],
                end_ms=atom["end_ms"],
                parent_chunk_id=chunk_id,
                parent_event_id=parent_event_id,
                extra={
                    "word_ids": atom.get("word_ids", []),
                    "segment_ids": atom.get("segment_ids", []),
                    "representative_frame_ids": atom.get("representative_frame_ids", []),
                    "clip_path": (atom.get("visual_evidence", {}).get("clip") or {}).get("clip_path_relative", ""),
                },
            )
        )

    chunk_ids: list[str] = []
    chunk_docs: list[str] = []
    chunk_metas: list[dict[str, Any]] = []
    chunk_visual_ids: list[str] = []
    chunk_visual_docs: list[str] = []
    chunk_visual_metas: list[dict[str, Any]] = []
    for chunk in chunks:
        parent_event_id = chunk.get("parent_event_id", "")
        chunk_ids.append(f"{video_id}__chunk__{chunk['chunk_id']}")
        chunk_docs.append(_document_for_chunk(chunk))
        chunk_metas.append(
            _base_metadata(
                manifest=manifest,
                source_type="semantic_chunk_text",
                source_id=chunk["chunk_id"],
                start_ms=chunk["start_ms"],
                end_ms=chunk["end_ms"],
                parent_chunk_id=chunk["chunk_id"],
                parent_event_id=parent_event_id,
                extra={
                    "atom_ids": chunk.get("atom_ids", []),
                    "title": chunk.get("title", ""),
                    "representative_frame_ids": chunk.get("representative_frame_ids", []),
                },
            )
        )
        chunk_visual_ids.append(f"{video_id}__chunk_visual__{chunk['chunk_id']}")
        chunk_visual_docs.append(_document_for_chunk_visual(chunk, visual_by_atom))
        chunk_visual_metas.append(
            _base_metadata(
                manifest=manifest,
                source_type="semantic_chunk_visual",
                source_id=chunk["chunk_id"],
                start_ms=chunk["start_ms"],
                end_ms=chunk["end_ms"],
                parent_chunk_id=chunk["chunk_id"],
                parent_event_id=parent_event_id,
                extra={
                    "atom_ids": chunk.get("atom_ids", []),
                    "representative_frame_ids": chunk.get("representative_frame_ids", []),
                },
            )
        )

    event_ids: list[str] = []
    event_docs: list[str] = []
    event_metas: list[dict[str, Any]] = []
    for event in events:
        event_ids.append(f"{video_id}__event__{event['event_id']}")
        event_docs.append(_document_for_event(event))
        event_metas.append(
            _base_metadata(
                manifest=manifest,
                source_type="event",
                source_id=event["event_id"],
                start_ms=event["start_ms"],
                end_ms=event["end_ms"],
                parent_chunk_id="",
                parent_event_id=event["event_id"],
                extra={
                    "chunk_ids": event.get("chunk_ids", []),
                    "atom_ids": event.get("atom_ids", []),
                    "title": event.get("title", ""),
                    "representative_frame_ids": event.get("representative_frame_ids", []),
                },
            )
        )

    _upsert(collections[COLLECTION_ATOMS_TEXT], atom_ids, atom_docs, atom_metas)
    _upsert(collections[COLLECTION_CHUNKS_TEXT], chunk_ids, chunk_docs, chunk_metas)
    _upsert(collections[COLLECTION_CHUNKS_VISUAL], chunk_visual_ids, chunk_visual_docs, chunk_visual_metas)
    _upsert(collections[COLLECTION_EVENTS], event_ids, event_docs, event_metas)

    result = {
        "schema_version": "hierarchy-index-v1",
        "video_id": video_id,
        "collections": {
            COLLECTION_ATOMS_TEXT: len(atom_ids),
            COLLECTION_CHUNKS_TEXT: len(chunk_ids),
            COLLECTION_CHUNKS_VISUAL: len(chunk_visual_ids),
            COLLECTION_EVENTS: len(event_ids),
        },
        "chroma_path": str(repo_root / CHROMA_PATH_NAME),
        "embedding_model": EMBED_MODEL,
        "completed_at": utc_now(),
    }
    manifest.setdefault("artifact_metadata", {})["hierarchy_index"] = result
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Index hierarchy artifacts into ChromaDB.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    result = index_hierarchy(repo_root=Path(args.repo_root), video_id=args.video_id)
    print(f"C11 complete: {result['collections']}")


if __name__ == "__main__":
    main()
