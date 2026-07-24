from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..media_manifest import load_manifest
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
        for step_index, step in enumerate(plan.retrieval_steps, start=1):
            adapter = self._adapter_for(step)
            readiness = self._retriever_readiness(video_id, step.retriever)
            if not readiness["ready"]:
                warnings.extend(readiness["warnings"])
            try:
                rows = adapter.retrieve(
                    video_id=video_id,
                    step=step,
                    query_understanding=query_understanding,
                )
                rows = self._normalize_candidates(
                    rows=rows,
                    video_id=video_id,
                    step=step,
                    step_index=step_index,
                )
                candidates.extend(rows)
                attempts.append({
                    "retriever": step.retriever,
                    "level": step.level,
                    "top_k": step.top_k,
                    "weight": step.weight,
                    "candidate_count": len(rows),
                    "readiness": readiness,
                    "source_type_counts": _source_type_counts(rows),
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

    def _normalize_candidates(
        self,
        *,
        rows: list[dict[str, Any]],
        video_id: str,
        step: RetrievalStep,
        step_index: int,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int, int]] = set()
        for rank, row in enumerate(rows[: step.top_k], start=1):
            if row.get("video_id") not in {None, "", video_id}:
                continue
            start_ms = _safe_int(row.get("start_ms"))
            end_ms = _safe_int(row.get("end_ms"))
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            source_type = _source_type_value(row.get("source_type"))
            source_id = str(row.get("source_id") or row.get("id") or f"{source_type}_{rank}")
            key = (source_type, source_id, start_ms, end_ms)
            if key in seen:
                continue
            seen.add(key)
            retrieval = dict(row.get("retrieval") or {})
            retrieval.setdefault("retriever", step.retriever)
            retrieval.setdefault("raw_score", float(row.get("score", row.get("confidence", 0.0)) or 0.0))
            retrieval["rank"] = int(retrieval.get("rank") or rank)
            retrieval.setdefault("query_variant", step.query)
            normalized.append(
                {
                    **row,
                    "candidate_id": f"cand_{step_index:02d}_{rank:03d}_{source_id}",
                    "video_id": video_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "retrieval": retrieval,
                }
            )
        return normalized

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

    def _retriever_readiness(self, video_id: str, retriever: str) -> dict[str, Any]:
        try:
            manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        except Exception as exc:
            return {"ready": False, "warnings": [f"manifest unavailable for retrieval readiness: {exc}"]}
        artifacts = manifest.get("artifacts") or {}
        required_paths = {
            "local_visual": ["visual_artifacts_path", "semantic_chunks_path"],
            "ocr_sparse": ["ocr_path"],
            "speaker": ["speakers_path"],
            "audio_event": ["audio_events_path"],
            "sparse_text": ["atoms_path", "semantic_chunks_path", "events_path"],
            "exact_timeline": ["atoms_path"],
        }.get(retriever, [])
        missing = [
            key
            for key in required_paths
            if not artifacts.get(key) or not Path(str(artifacts[key])).is_file()
        ]
        warnings = [f"{retriever} readiness missing artifact: {key}" for key in missing]
        return {"ready": not missing, "missing_artifacts": missing, "warnings": warnings}


def _safe_int(value: Any) -> int:
    try:
        if isinstance(value, bool):
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _source_type_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    text = str(raw or "unknown").strip()
    if text.startswith("SourceType."):
        return text.rsplit(".", 1)[-1].lower()
    return text.lower() or "unknown"


def _source_type_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        source_type = _source_type_value(row.get("source_type"))
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts
