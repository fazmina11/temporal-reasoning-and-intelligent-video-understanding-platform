from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .contracts import RetrievalPlan, RetrievalStep
from .query_understanding import is_episodic_memory_query
from .retrievers.base import RetrieverAdapter
from .retrievers.chroma_dense import COLLECTION_BY_RETRIEVER, ChromaDenseRetriever
from .retrievers.exact_timeline import ExactTimelineRetriever
from .retrievers.local_modalities import AudioEventRetriever, OCRRetriever, SpeakerRetriever
from .retrievers.local_sparse import LocalSparseRetriever
from .retrievers.local_visual import LocalVisualRetriever, PlaceholderModalityRetriever

LOGGER = logging.getLogger(__name__)


class RetrievalOrchestrator:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._adapters: dict[str, RetrieverAdapter] = {}

    def execute(
        self,
        *,
        video_id: str,
        plan: RetrievalPlan,
        query_understanding: dict[str, Any],
    ) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        warnings: list[str] = []

        raw_query = (
            query_understanding.get("raw_query")
            or query_understanding.get("standalone_query")
            or ""
        )
        is_episodic = query_understanding.get("is_episodic_memory")
        if is_episodic is None:
            is_episodic = is_episodic_memory_query(raw_query)

        # Automatic MemoryRetriever invocation for episodic memory queries before standard retrieval
        if is_episodic:
            try:
                from ..memory_recovery.memory_retriever import retrieve_memory

                evidence_store = self._load_evidence_store(video_id)
                memory_result = retrieve_memory(
                    query=raw_query,
                    evidence_store=evidence_store,
                    video_id=video_id,
                )
                for mem_cand in memory_result.candidate_moments:
                    candidates.append({
                        "source_id": mem_cand.candidate_id,
                        "source_type": mem_cand.modality,
                        "video_id": mem_cand.video_id,
                        "text": mem_cand.text_content,
                        "start_ms": mem_cand.start_ms,
                        "end_ms": mem_cand.end_ms,
                        "score": mem_cand.score,
                        "confidence": min(1.0, mem_cand.score / 12.0),
                        "retriever": "memory_retriever",
                        "matched_features": mem_cand.matched_features,
                        "metadata": mem_cand.metadata,
                    })
                attempts.append({
                    "retriever": "memory_retriever",
                    "level": "memory_recovery",
                    "candidate_count": len(memory_result.candidate_moments),
                    "confidence": memory_result.confidence,
                })
            except Exception as exc:
                LOGGER.exception("MemoryRetriever execution failed for query: %s", raw_query)
                attempts.append({
                    "retriever": "memory_retriever",
                    "level": "memory_recovery",
                    "candidate_count": 0,
                    "error": str(exc),
                })
                warnings.append(f"memory_retriever failed: {exc}")

        # Execute standard retrieval steps
        for step in plan.retrieval_steps:
            adapter = self._adapter_for(step)
            try:
                rows = adapter.retrieve(
                    video_id=video_id,
                    step=step,
                    query_understanding=query_understanding,
                )
                candidates.extend(rows)
                attempts.append({
                    "retriever": step.retriever,
                    "level": step.level,
                    "top_k": step.top_k,
                    "weight": step.weight,
                    "candidate_count": len(rows),
                })
                if not rows and step.retriever in {
                    "ocr_sparse",
                    "speaker",
                    "audio_event",
                    "entity_world",
                    "clip_action",
                }:
                    warnings.append(
                        f"{step.retriever} returned no matching evidence or its artifact is unavailable"
                    )
            except Exception as exc:
                attempts.append({
                    "retriever": step.retriever,
                    "level": step.level,
                    "top_k": step.top_k,
                    "weight": step.weight,
                    "candidate_count": 0,
                    "error": str(exc),
                })
                warnings.append(f"{step.retriever} failed: {exc}")

        return {"candidates": candidates, "attempts": attempts, "warnings": warnings}

    def _load_evidence_store(self, video_id: str) -> dict[str, list[dict[str, Any]]]:
        from ..json_artifacts import read_json

        evidence_store: dict[str, list[dict[str, Any]]] = {
            "ocr": [],
            "semantic_chunks": [],
            "events": [],
            "frames": [],
            "clips": [],
        }
        manifest_path = (
            self.repo_root / "data" / "processed" / "manifests" / f"{video_id}.json"
        )
        if not manifest_path.exists():
            return evidence_store

        try:
            manifest = read_json(manifest_path)
            artifacts = manifest.get("artifacts", {})

            for key, store_key in (
                ("ocr_path", "ocr"),
                ("semantic_chunks_path", "semantic_chunks"),
                ("events_path", "events"),
                ("frame_index_path", "frames"),
                ("atoms_path", "clips"),
            ):
                if key in artifacts:
                    art_path = Path(artifacts[key])
                    if not art_path.is_absolute():
                        art_path = self.repo_root / art_path
                    if art_path.is_file():
                        payload = read_json(art_path)
                        items = (
                            payload.get("records")
                            or payload.get("ocr_records")
                            or payload.get("chunks")
                            or payload.get("events")
                            or payload.get("frames")
                            or payload.get("atoms")
                            or []
                        )
                        evidence_store[store_key] = items
        except Exception as exc:
            LOGGER.warning("Failed loading evidence store for %s: %s", video_id, exc)

        return evidence_store

    def _adapter_for(self, step: RetrievalStep) -> RetrieverAdapter:
        if step.retriever in self._adapters:
            return self._adapters[step.retriever]
        if step.retriever == "exact_timeline":
            adapter = ExactTimelineRetriever(self.repo_root)
        elif step.retriever in COLLECTION_BY_RETRIEVER:
            adapter = ChromaDenseRetriever(self.repo_root)
        elif step.retriever == "local_visual":
            adapter = LocalVisualRetriever(self.repo_root)
        elif step.retriever == "sparse_text":
            adapter = LocalSparseRetriever(self.repo_root)
        elif step.retriever == "ocr_sparse":
            adapter = OCRRetriever(self.repo_root)
        elif step.retriever == "speaker":
            adapter = SpeakerRetriever(self.repo_root)
        elif step.retriever == "audio_event":
            adapter = AudioEventRetriever(self.repo_root)
        else:
            adapter = PlaceholderModalityRetriever(self.repo_root)
        self._adapters[step.retriever] = adapter
        return adapter
