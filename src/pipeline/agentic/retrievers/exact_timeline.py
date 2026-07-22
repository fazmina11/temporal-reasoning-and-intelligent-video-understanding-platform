from __future__ import annotations

from pathlib import Path
from typing import Any

from ...json_artifacts import read_json
from ...media_manifest import load_manifest
from ..contracts import RetrievalStep, SourceType
from .base import RetrieverAdapter, make_candidate


class ExactTimelineRetriever(RetrieverAdapter):
    name = "exact_timeline"

    def retrieve(
        self,
        *,
        video_id: str,
        step: RetrievalStep,
        query_understanding: dict[str, Any],
    ) -> list[dict[str, Any]]:
        time_constraints = query_understanding.get("time_constraints") or []
        if not time_constraints:
            return []

        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        atoms_payload = read_json(Path(manifest["artifacts"]["atoms_path"]))
        atoms = atoms_payload.get("atoms", [])
        radius_ms = int(step.retriever.split(":")[-1]) if ":" in step.retriever and step.retriever.split(":")[-1].isdigit() else 30_000

        rows: list[dict[str, Any]] = []
        for time_index, time_constraint in enumerate(time_constraints):
            target_ms = int(time_constraint["target_ms"])
            matched = [
                atom
                for atom in atoms
                if atom["start_ms"] <= target_ms + radius_ms and atom["end_ms"] >= target_ms - radius_ms
            ]
            for rank, atom in enumerate(matched[: step.top_k], start=1):
                distance_ms = min(abs(atom["start_ms"] - target_ms), abs(atom["end_ms"] - target_ms))
                raw_score = max(0.0, 1.0 - (distance_ms / max(1, radius_ms)))
                rows.append(
                    make_candidate(
                        candidate_id=f"cand_exact_{time_index}_{rank}",
                        video_id=video_id,
                        source_type=SourceType.ATOM,
                        source_id=atom["atom_id"],
                        start_ms=atom["start_ms"],
                        end_ms=atom["end_ms"],
                        parent_chunk_id=atom.get("semantic_chunk_id"),
                        parent_event_id=atom.get("parent_event_id"),
                        text=atom.get("transcript_text"),
                        transcript=atom.get("transcript_text"),
                        media_refs={
                            "frames": atom.get("representative_frame_ids", []),
                            "clip": (atom.get("visual_evidence", {}).get("clip") or {}).get("clip_path_relative"),
                        },
                        retriever=self.name,
                        rank=rank,
                        raw_score=raw_score,
                        query_variant=step.query,
                        versions={"pipeline": manifest.get("pipeline_version", "")},
                    )
                )
        return rows
