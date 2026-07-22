from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class AnswerMode(str, Enum):
    STRICT_VIDEO = "strict_video"
    HYBRID_ASSISTANT = "hybrid_assistant"
    CLARIFY_WHEN_AMBIGUOUS = "clarify_when_ambiguous"


class Outcome(str, Enum):
    GROUNDED_ANSWER = "grounded_answer"
    PARTIAL_ANSWER = "partial_answer"
    VIDEO_EVIDENCE_NOT_FOUND = "video_evidence_not_found"
    UNRELATED_TO_VIDEO = "unrelated_to_video"
    AMBIGUOUS_QUERY = "ambiguous_query"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    PROCESSING_INCOMPLETE = "processing_incomplete"
    SYSTEM_ERROR = "system_error"


class SourceType(str, Enum):
    ATOM = "atom"
    SEMANTIC_CHUNK = "semantic_chunk"
    VISUAL_CHUNK = "visual_chunk"
    EVENT = "event"
    OCR = "ocr"
    SPEAKER_TURN = "speaker_turn"
    AUDIO_EVENT = "audio_event"
    GENERAL_KNOWLEDGE = "general_knowledge"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class AskRequest(BaseModel):
    video_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    answer_mode: AnswerMode = AnswerMode.STRICT_VIDEO
    conversation_context: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:16]}")

    @validator("video_id", "query", pre=True)
    def _strip_required_text(cls, value: Any) -> str:
        if value is None:
            raise ValueError("required text field cannot be null")
        text = str(value).strip()
        if not text:
            raise ValueError("required text field cannot be empty")
        return text


class Citation(BaseModel):
    citation_id: str = Field(..., min_length=1)
    source_type: SourceType = SourceType.UNKNOWN
    source_id: str = Field(..., min_length=1)
    video_id: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    timestamp: str | None = None
    text: str | None = None
    visual_summary: str | None = None
    parent_chunk_id: str | None = None
    parent_event_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @validator("end_ms")
    def _end_ms_after_start_ms(cls, value: int | None, values: dict[str, Any]) -> int | None:
        start_ms = values.get("start_ms")
        if value is not None and start_ms is not None and value < start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return value

    @validator("end_seconds")
    def _end_seconds_after_start_seconds(cls, value: float | None, values: dict[str, Any]) -> float | None:
        start_seconds = values.get("start_seconds")
        if value is not None and start_seconds is not None and value < start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")
        return value


class AnswerQuality(BaseModel):
    grounded: bool = False
    has_timestamp: bool = False
    has_citations: bool = False
    uses_verified_evidence: bool = False
    requires_visual_followup: bool = False
    fallback_used: bool = False
    low_confidence_reason: str | None = None
    quality_score: float = Field(default=0.0, ge=0, le=1)


class AskResponse(BaseModel):
    outcome: Outcome
    answer: str
    video_id: str
    query: str
    answer_mode: AnswerMode = AnswerMode.STRICT_VIDEO
    timestamp: float = Field(default=0.0, ge=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    source_id: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    parent_event_id: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    citations: list[Citation] = Field(default_factory=list)
    answer_quality: AnswerQuality = Field(default_factory=AnswerQuality)
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:16]}")
    warnings: list[str] = Field(default_factory=list)

    @validator("end_ms")
    def _end_after_start(cls, value: int | None, values: dict[str, Any]) -> int | None:
        start_ms = values.get("start_ms")
        if value is not None and start_ms is not None and value < start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return value


class CandidateEvidence(BaseModel):
    candidate_id: str
    video_id: str
    source_type: SourceType
    source_id: str
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    parent_chunk_id: str | None = None
    parent_event_id: str | None = None
    text: str | None = None
    transcript: str | None = None
    visual_summary: str | None = None
    ocr_text: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    media_refs: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    versions: dict[str, Any] = Field(default_factory=dict)

    @validator("end_ms")
    def _candidate_end_after_start(cls, value: int, values: dict[str, Any]) -> int:
        if "start_ms" in values and value <= values["start_ms"]:
            raise ValueError("candidate end_ms must be greater than start_ms")
        return value


class RetrievalStep(BaseModel):
    retriever: str
    level: str
    query: str
    top_k: int = Field(default=10, ge=1, le=100)
    weight: float = Field(default=1.0, gt=0, le=10)


class ContextPolicy(BaseModel):
    direction: Literal["previous", "next", "both", "none"] = "both"
    max_previous_atoms: int = Field(default=1, ge=0, le=20)
    max_next_atoms: int = Field(default=1, ge=0, le=20)
    include_parent_chunk: bool = True
    include_parent_event: bool = True
    max_context_ms: int = Field(default=180_000, ge=1_000)


class RetrievalPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:12]}")
    strategy: str
    retrieval_steps: list[RetrievalStep]
    context_policy: ContextPolicy = Field(default_factory=ContextPolicy)
    requires_reranking: bool = True
    requires_temporal_reasoning: bool = True
    max_corrective_attempts: int = Field(default=1, ge=0, le=3)
    answer_mode: AnswerMode = AnswerMode.STRICT_VIDEO

    @validator("retrieval_steps")
    def _has_steps(cls, value: list[RetrievalStep]) -> list[RetrievalStep]:
        if not value:
            raise ValueError("retrieval plan must contain at least one step")
        return value


class RetrievalTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:16]}")
    request: dict[str, Any] = Field(default_factory=dict)
    versions: dict[str, Any] = Field(default_factory=dict)
    conversation_resolution: dict[str, Any] = Field(default_factory=dict)
    query_understanding: dict[str, Any] = Field(default_factory=dict)
    scope_decision: dict[str, Any] = Field(default_factory=dict)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_attempts: list[dict[str, Any]] = Field(default_factory=list)
    candidate_fusion: dict[str, Any] = Field(default_factory=dict)
    reranking: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    answerability: dict[str, Any] = Field(default_factory=dict)
    temporal_reasoning: dict[str, Any] = Field(default_factory=dict)
    evidence_packet_summary: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)
    claim_verification: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, Any] = Field(default_factory=dict)
    final_response: dict[str, Any] = Field(default_factory=dict)
    timings: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def parse_model(model_cls: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)
