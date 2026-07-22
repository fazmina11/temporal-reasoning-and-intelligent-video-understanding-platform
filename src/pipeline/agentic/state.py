from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import AnswerMode, Outcome


@dataclass
class AgenticRAGState:
    trace_id: str
    request_id: str
    video_id: str
    raw_query: str
    answer_mode: AnswerMode = AnswerMode.STRICT_VIDEO

    conversation_context: list[dict[str, Any]] = field(default_factory=list)
    resolved_query: dict[str, Any] | None = None
    query_understanding: dict[str, Any] | None = None
    scope_decision: dict[str, Any] | None = None
    retrieval_plan: dict[str, Any] | None = None

    raw_candidates: list[dict[str, Any]] = field(default_factory=list)
    fused_candidates: list[dict[str, Any]] = field(default_factory=list)
    reranked_candidates: list[dict[str, Any]] = field(default_factory=list)
    verified_evidence: list[dict[str, Any]] = field(default_factory=list)

    corrective_attempt: int = 0
    answerability: dict[str, Any] | None = None
    temporal_context: dict[str, Any] | None = None
    evidence_packet: dict[str, Any] | None = None

    draft_answer: dict[str, Any] | None = None
    claim_verification: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None

    outcome: Outcome | None = None
    response: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
