from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import RetrievalPlan, RetrievalStep
from .retrievers.base import RetrieverAdapter
from .retrievers.chroma_dense import ChromaDenseRetriever, COLLECTION_BY_RETRIEVER
from .retrievers.exact_timeline import ExactTimelineRetriever
from .retrievers.local_sparse import LocalSparseRetriever
from .retrievers.local_modalities import AudioEventRetriever, OCRRetriever, SpeakerRetriever
from .retrievers.local_visual import LocalVisualRetriever, PlaceholderModalityRetriever


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
        for step in plan.retrieval_steps:
            adapter = self._adapter_for(step)
            try:
                rows = adapter.retrieve(video_id=video_id, step=step, query_understanding=query_understanding)
                candidates.extend(rows)
                attempts.append(
                    {
                        "retriever": step.retriever,
                        "level": step.level,
                        "top_k": step.top_k,
                        "weight": step.weight,
                        "candidate_count": len(rows),
                    }
                )
                if not rows and step.retriever in {"ocr_sparse", "speaker", "audio_event", "entity_world", "clip_action"}:
                    warnings.append(f"{step.retriever} returned no matching evidence or its artifact is unavailable")
            except Exception as exc:
                attempts.append(
                    {
                        "retriever": step.retriever,
                        "level": step.level,
                        "top_k": step.top_k,
                        "weight": step.weight,
                        "candidate_count": 0,
                        "error": str(exc),
                    }
                )
                warnings.append(f"{step.retriever} failed: {exc}")
        return {"candidates": candidates, "attempts": attempts, "warnings": warnings}

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
