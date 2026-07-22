from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...json_artifacts import read_json
from ...media_manifest import load_manifest
from ..contracts import RetrievalStep, SourceType
from .base import RetrieverAdapter, make_candidate


class LocalVisualRetriever(RetrieverAdapter):
    name = "local_visual"

    def retrieve(
        self,
        *,
        video_id: str,
        step: RetrievalStep,
        query_understanding: dict[str, Any],
    ) -> list[dict[str, Any]]:
        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        visual_path = Path(manifest["artifacts"].get("visual_artifacts_path", ""))
        chunks_path = Path(manifest["artifacts"].get("semantic_chunks_path", ""))
        if not visual_path.exists() or not chunks_path.exists():
            return []

        visual_records = read_json(visual_path).get("records", [])
        chunks = read_json(chunks_path).get("chunks", [])
        chunk_by_atom: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            for atom_id in chunk.get("atom_ids", []):
                chunk_by_atom[atom_id] = chunk

        terms = _terms(step.query) | set(query_understanding.get("objects") or [])
        rows: list[tuple[float, dict[str, Any], dict[str, Any] | None]] = []
        for record in visual_records:
            text = " ".join(
                [
                    str(record.get("atom_id", "")),
                    " ".join(str(frame.get("role", "")) for frame in record.get("frame_references", [])),
                    " ".join(str(frame.get("frame_id", "")) for frame in record.get("frame_references", [])),
                    str((record.get("clip") or {}).get("clip_path_relative", "")),
                ]
            ).lower()
            match_count = sum(1 for term in terms if term.lower() in text)
            if not match_count and terms:
                continue
            score = 0.4 + min(0.6, match_count / max(1, len(terms)))
            rows.append((score, record, chunk_by_atom.get(record.get("atom_id"))))

        rows.sort(key=lambda row: row[0], reverse=True)
        candidates: list[dict[str, Any]] = []
        for rank, (score, record, chunk) in enumerate(rows[: step.top_k], start=1):
            start_ms = int(record.get("start_ms") or (chunk or {}).get("start_ms") or 0)
            end_ms = int(record.get("end_ms") or (chunk or {}).get("end_ms") or start_ms + 1)
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            candidates.append(
                make_candidate(
                    candidate_id=f"cand_local_visual_{rank}",
                    video_id=video_id,
                    source_type=SourceType.VISUAL_CHUNK,
                    source_id=(chunk or {}).get("chunk_id") or record.get("atom_id"),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    parent_chunk_id=(chunk or {}).get("chunk_id"),
                    parent_event_id=(chunk or {}).get("parent_event_id"),
                    text=(chunk or {}).get("transcript_text"),
                    transcript=(chunk or {}).get("transcript_text"),
                    visual_summary=f"{len(record.get('frame_references', []))} representative visual frames attached.",
                    media_refs={
                        "frames": [frame.get("frame_id") for frame in record.get("frame_references", [])],
                        "clip": (record.get("clip") or {}).get("clip_path_relative"),
                    },
                    retriever=step.retriever,
                    rank=rank,
                    raw_score=score,
                    query_variant=step.query,
                    versions={"pipeline": manifest.get("pipeline_version", "")},
                )
            )
        return candidates


class PlaceholderModalityRetriever(RetrieverAdapter):
    """Adapter slot for modalities whose indexes are not built yet."""

    def retrieve(
        self,
        *,
        video_id: str,
        step: RetrievalStep,
        query_understanding: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return []


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text)}
