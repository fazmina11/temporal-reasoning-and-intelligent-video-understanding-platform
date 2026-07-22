from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hierarchy_indexing import (
    BASE_COLLECTIONS,
    COLLECTION_ATOMS_TEXT,
    COLLECTION_CHUNKS_TEXT,
    COLLECTION_CHUNKS_VISUAL,
    COLLECTION_EVENTS,
    _chroma,
    hierarchy_collection_name,
)
from .json_artifacts import read_json
from .media_manifest import load_manifest

DEFAULT_TOP_K = 5


class HierarchyRetrievalError(RuntimeError):
    """Raised when hierarchy retrieval cannot run."""


def _json_meta(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return value
    if value[0] not in "[{":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _format_timestamp(ms: int) -> str:
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class HierarchyRetriever:
    """C12 retriever with dynamic hierarchy context expansion."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        self.client, self.embedding_function = _chroma(self.repo_root)
        self.collections = {
            base_name: self.client.get_collection(
                hierarchy_collection_name(base_name),
                embedding_function=self.embedding_function,
            )
            for base_name in BASE_COLLECTIONS
        }

    def _load_hierarchy(self, video_id: str) -> dict[str, Any]:
        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        atoms = read_json(Path(manifest["artifacts"]["atoms_path"]))["atoms"]
        chunks = read_json(Path(manifest["artifacts"]["semantic_chunks_path"]))["chunks"]
        events = read_json(Path(manifest["artifacts"]["events_path"]))["events"]
        visual = read_json(Path(manifest["artifacts"]["visual_artifacts_path"]))["records"]
        return {
            "manifest": manifest,
            "atoms": atoms,
            "chunks": chunks,
            "events": events,
            "visual": visual,
            "atom_by_id": {atom["atom_id"]: atom for atom in atoms},
            "chunk_by_id": {chunk["chunk_id"]: chunk for chunk in chunks},
            "event_by_id": {event["event_id"]: event for event in events},
            "visual_by_atom": {record["atom_id"]: record for record in visual},
        }

    def _query_collection(
        self,
        collection_name: str,
        query_text: str,
        video_id: str,
        n_results: int,
    ) -> list[dict[str, Any]]:
        collection = self.collections[collection_name]
        result = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where={"video_id": video_id},
            include=["metadatas", "distances", "documents"],
        )
        rows: list[dict[str, Any]] = []
        for doc_id, metadata, distance, document in zip(
            result.get("ids", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
            result.get("documents", [[]])[0],
        ):
            rows.append(
                {
                    "doc_id": doc_id,
                    "collection": collection_name,
                    "metadata": {key: _json_meta(value) for key, value in metadata.items()},
                    "distance": float(distance),
                    "document": document,
                }
            )
        return rows

    def _source_to_atom_ids(self, source_type: str, source_id: str, hierarchy: dict[str, Any]) -> list[str]:
        if source_type == "atom_text":
            return [source_id]
        if source_type in {"semantic_chunk_text", "semantic_chunk_visual"}:
            chunk = hierarchy["chunk_by_id"].get(source_id)
            return list(chunk.get("atom_ids", [])) if chunk else []
        if source_type == "event":
            event = hierarchy["event_by_id"].get(source_id)
            return list(event.get("atom_ids", [])) if event else []
        return []

    def _expand(self, hit: dict[str, Any], hierarchy: dict[str, Any]) -> dict[str, Any]:
        metadata = hit["metadata"]
        source_type = str(metadata["source_type"])
        source_id = str(metadata["source_id"])
        atoms = hierarchy["atoms"]
        atom_by_id = hierarchy["atom_by_id"]
        chunk_by_id = hierarchy["chunk_by_id"]
        event_by_id = hierarchy["event_by_id"]
        visual_by_atom = hierarchy["visual_by_atom"]

        atom_ids = self._source_to_atom_ids(source_type, source_id, hierarchy)
        seed_atom_id = atom_ids[0] if atom_ids else ""
        seed_index = next(
            (index for index, atom in enumerate(atoms) if atom["atom_id"] == seed_atom_id),
            -1,
        )
        neighbor_atom_ids: list[str] = []
        if seed_index >= 0:
            for index in [seed_index - 1, seed_index, seed_index + 1]:
                if 0 <= index < len(atoms):
                    neighbor_atom_ids.append(atoms[index]["atom_id"])

        parent_chunk_id = str(metadata.get("parent_chunk_id") or "")
        parent_event_id = str(metadata.get("parent_event_id") or "")
        if not parent_chunk_id and seed_atom_id:
            parent_chunk_id = atom_by_id.get(seed_atom_id, {}).get("semantic_chunk_id", "")
        if not parent_event_id and parent_chunk_id:
            parent_event_id = chunk_by_id.get(parent_chunk_id, {}).get("parent_event_id", "")

        nearby_atoms = [atom_by_id[atom_id] for atom_id in neighbor_atom_ids if atom_id in atom_by_id]
        parent_chunk = chunk_by_id.get(parent_chunk_id)
        parent_event = event_by_id.get(parent_event_id)
        visual_records = [
            visual_by_atom[atom_id]
            for atom_id in neighbor_atom_ids
            if atom_id in visual_by_atom
        ]
        start_ms = int(metadata["start_ms"])
        end_ms = int(metadata["end_ms"])
        return {
            "doc_id": hit["doc_id"],
            "collection": hit["collection"],
            "source_type": source_type,
            "source_id": source_id,
            "video_id": metadata["video_id"],
            "start_ms": start_ms,
            "end_ms": end_ms,
            "start_seconds": start_ms / 1000,
            "end_seconds": end_ms / 1000,
            "timestamp": _format_timestamp(start_ms),
            "distance": round(hit["distance"], 4),
            "score": round(1.0 - min(1.0, hit["distance"]), 4),
            "parent_chunk_id": parent_chunk_id,
            "parent_event_id": parent_event_id,
            "atom_ids": atom_ids,
            "neighbor_atom_ids": neighbor_atom_ids,
            "transcript_text": (
                parent_chunk.get("transcript_text", "")
                if parent_chunk
                else " ".join(atom.get("transcript_text", "") for atom in nearby_atoms)
            ),
            "nearby_transcript": " ".join(
                atom.get("transcript_text", "") for atom in nearby_atoms if atom.get("transcript_text")
            ),
            "parent_chunk": parent_chunk,
            "parent_event": parent_event,
            "visual_evidence": visual_records,
            "representative_frame_ids": (
                parent_chunk.get("representative_frame_ids", [])
                if parent_chunk
                else []
            ),
            "clip_paths": [
                record.get("clip", {}).get("clip_path_relative", "")
                for record in visual_records
                if record.get("clip")
            ],
            "document": hit["document"],
        }

    def query(self, query_text: str, video_id: str, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
        hierarchy = self._load_hierarchy(video_id)
        hits: list[dict[str, Any]] = []
        for collection_name in [
            COLLECTION_CHUNKS_TEXT,
            COLLECTION_ATOMS_TEXT,
            COLLECTION_CHUNKS_VISUAL,
            COLLECTION_EVENTS,
        ]:
            hits.extend(
                self._query_collection(
                    collection_name,
                    query_text,
                    video_id,
                    n_results=max(top_k * 2, 6),
                )
            )
        best_by_source: dict[tuple[str, str], dict[str, Any]] = {}
        for hit in hits:
            metadata = hit["metadata"]
            key = (str(metadata["source_type"]), str(metadata["source_id"]))
            if key not in best_by_source or hit["distance"] < best_by_source[key]["distance"]:
                best_by_source[key] = hit
        ranked = sorted(best_by_source.values(), key=lambda item: item["distance"])
        return [self._expand(hit, hierarchy) for hit in ranked[:top_k]]

    def query_by_timestamp(self, video_id: str, seconds: float, radius: float = 45.0) -> list[dict[str, Any]]:
        hierarchy = self._load_hierarchy(video_id)
        center_ms = int(seconds * 1000)
        radius_ms = int(radius * 1000)
        chunks = [
            chunk
            for chunk in hierarchy["chunks"]
            if chunk["start_ms"] <= center_ms + radius_ms and chunk["end_ms"] >= center_ms - radius_ms
        ]
        results = []
        for chunk in chunks:
            hit = {
                "doc_id": f"{video_id}__chunk__{chunk['chunk_id']}",
                "collection": COLLECTION_CHUNKS_TEXT,
                "metadata": {
                    "video_id": video_id,
                    "source_type": "semantic_chunk_text",
                    "source_id": chunk["chunk_id"],
                    "start_ms": chunk["start_ms"],
                    "end_ms": chunk["end_ms"],
                    "parent_chunk_id": chunk["chunk_id"],
                    "parent_event_id": chunk.get("parent_event_id", ""),
                },
                "distance": 0.0,
                "document": chunk.get("transcript_text", ""),
            }
            results.append(self._expand(hit, hierarchy))
        return sorted(results, key=lambda item: item["start_ms"])
