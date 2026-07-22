from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from .hierarchy_retrieval import HierarchyRetriever

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


class HierarchyVideoRAG:
    """Answer questions from canonical atoms/chunks/events with dynamic context expansion."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        self.retriever = HierarchyRetriever(repo_root=self.repo_root)
        self.client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if genai is not None and genai_types is not None and api_key:
            self.client = genai.Client(api_key=api_key)

    def _prompt(self, question: str, contexts: list[dict[str, Any]]) -> str:
        blocks = []
        for index, context in enumerate(contexts, start=1):
            event = context.get("parent_event") or {}
            chunk = context.get("parent_chunk") or {}
            blocks.append(
                "\n".join(
                    [
                        f"[S{index}] {context['timestamp']} - source={context['source_type']}:{context['source_id']}",
                        f"Event: {event.get('title', '')}",
                        f"Chunk: {chunk.get('title', '')}",
                        f"Transcript: {context.get('transcript_text', '')}",
                        f"Nearby: {context.get('nearby_transcript', '')}",
                        f"Frames: {', '.join(context.get('representative_frame_ids') or [])}",
                        f"Clips: {', '.join(path for path in context.get('clip_paths', []) if path)}",
                    ]
                )
            )
        return (
            "You are answering questions about a video using only grounded timeline evidence.\n"
            "Use the supplied contexts. Cite relevant statements with [S1], [S2], etc.\n"
            "If evidence is weak, say what is uncertain.\n\n"
            f"Question: {question}\n\n"
            "Contexts:\n"
            + "\n\n".join(blocks)
        )

    def _fallback_answer(self, question: str, contexts: list[dict[str, Any]]) -> str:
        if not contexts:
            return "I could not find matching timeline evidence for that question."
        first = contexts[0]
        event = first.get("parent_event") or {}
        chunk = first.get("parent_chunk") or {}
        text = first.get("transcript_text") or first.get("nearby_transcript") or first.get("document", "")
        return (
            f"The closest match is around {first['timestamp']}. "
            f"It belongs to the event '{event.get('title', 'Untitled event')}' and chunk "
            f"'{chunk.get('title', 'Untitled chunk')}'. "
            f"The relevant transcript says: {text[:700]} [S1]"
        )

    def _local_grounded_answer(
        self,
        question: str,
        contexts: list[dict[str, Any]],
        reason: str | None = None,
    ) -> str:
        if not contexts:
            return "I could not find matching timeline evidence for that question."
        lines = []
        if reason:
            lines.append(
                "The external answer model was temporarily unavailable, so I used the local retrieved video evidence."
            )
        lines.append(f"Question: {question}")
        for index, context in enumerate(contexts[:3], start=1):
            event = context.get("parent_event") or {}
            chunk = context.get("parent_chunk") or {}
            text = (
                context.get("transcript_text")
                or context.get("nearby_transcript")
                or context.get("document")
                or ""
            )
            lines.append(
                f"[S{index}] Around {context['timestamp']}, event "
                f"'{event.get('title', 'Untitled event')}', chunk "
                f"'{chunk.get('title', 'Untitled chunk')}': {text[:450]}"
            )
        return "\n\n".join(lines)

    def ask(self, question: str, video_id: str, top_k: int = 5) -> dict[str, Any]:
        contexts = self.retriever.query(question, video_id=video_id, top_k=top_k)
        if self.client is None:
            answer = self._fallback_answer(question, contexts)
        else:
            try:
                response = self.client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=self._prompt(question, contexts),
                    config=genai_types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=900,
                    ),
                )
                answer = str(response.text or "").strip() or self._fallback_answer(question, contexts)
            except Exception as exc:
                answer = self._local_grounded_answer(question, contexts, reason=str(exc))
        citations = self._extract_citations(answer, contexts)
        confidence = self._confidence(answer, contexts)
        return {
            "question": question,
            "video_id": video_id,
            "answer": answer,
            "contexts": contexts,
            "scenes": contexts,
            "citations": citations,
            "confidence": confidence,
            "retrieval_mode": "hierarchy_dynamic_context",
        }

    def _extract_citations(self, answer: str, contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cited_indices = sorted(set(int(value) for value in re.findall(r"S(\d+)", answer)))
        if not cited_indices and contexts:
            cited_indices = [1]
        citations = []
        for index in cited_indices:
            context_index = index - 1
            if 0 <= context_index < len(contexts):
                context = contexts[context_index]
                citations.append(
                    {
                        "ref": f"[S{index}]",
                        "timestamp": context["timestamp"],
                        "start_seconds": context["start_seconds"],
                        "start_ms": context["start_ms"],
                        "end_ms": context["end_ms"],
                        "source_type": context["source_type"],
                        "source_id": context["source_id"],
                        "parent_chunk_id": context["parent_chunk_id"],
                        "parent_event_id": context["parent_event_id"],
                        "frame_ids": context.get("representative_frame_ids", []),
                        "clip_paths": context.get("clip_paths", []),
                        "visual_summary": (context.get("transcript_text") or "")[:160],
                    }
                )
        return citations

    def _confidence(self, answer: str, contexts: list[dict[str, Any]]) -> float:
        if not contexts:
            return 0.0
        scores = [float(context.get("score", 0.5)) for context in contexts[:3]]
        retrieval = sum(scores) / len(scores)
        citation_bonus = 0.2 if re.search(r"S\d+", answer) else 0.0
        return round(max(0.0, min(1.0, retrieval * 0.8 + citation_bonus)), 3)
