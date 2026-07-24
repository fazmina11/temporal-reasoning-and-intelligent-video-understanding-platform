"""Data contracts for memory query parsing and vague episodic retrieval features."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeatureType(str, Enum):
    """Categories of visual and episodic memory features."""

    OBJECT = "object"
    COLOR = "color"
    ACTION = "action"
    TEXT_CLUE = "text_clue"
    SPATIAL_CLUE = "spatial_clue"
    TEMPORAL_CLUE = "temporal_clue"
    VISUAL_CLUE = "visual_clue"


@dataclass
class MemoryFeature:
    """An individual extracted feature from a vague memory query."""

    feature_type: FeatureType | str
    value: str
    confidence: float = 1.0
    source: str = "rule_based"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert MemoryFeature to a plain dictionary."""
        ft = self.feature_type.value if isinstance(self.feature_type, FeatureType) else str(self.feature_type)
        return {
            "feature_type": ft,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class MemoryQuery:
    """Parsed representation of a vague episodic memory request."""

    original_query: str
    features: list[MemoryFeature] = field(default_factory=list)
    is_memory_query: bool = True

    @property
    def raw_query(self) -> str:
        """Alias for original_query for backward compatibility."""
        return self.original_query

    @property
    def objects(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.OBJECT or str(f.feature_type) == "object")
        ]

    @property
    def colors(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.COLOR or str(f.feature_type) == "color")
        ]

    @property
    def actions(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.ACTION or str(f.feature_type) == "action")
        ]

    @property
    def text_clues(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.TEXT_CLUE or str(f.feature_type) == "text_clue")
        ]

    @property
    def spatial_clues(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.SPATIAL_CLUE or str(f.feature_type) == "spatial_clue")
        ]

    @property
    def temporal_clues(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.TEMPORAL_CLUE or str(f.feature_type) == "temporal_clue")
        ]

    @property
    def visual_clues(self) -> list[str]:
        return [
            f.value for f in self.features
            if (f.feature_type == FeatureType.VISUAL_CLUE or str(f.feature_type) == "visual_clue")
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert MemoryQuery into a structured dictionary."""
        return {
            "original_query": self.original_query,
            "raw_query": self.raw_query,
            "features": [f.to_dict() for f in self.features],
            "is_memory_query": self.is_memory_query,
            "objects": self.objects,
            "colors": self.colors,
            "actions": self.actions,
            "text_clues": self.text_clues,
            "spatial_clues": self.spatial_clues,
            "temporal_clues": self.temporal_clues,
            "visual_clues": self.visual_clues,
        }


@dataclass
class CandidateMemory:
    """A ranked candidate evidence item matching a vague episodic memory query."""

    source_type: str = ""
    source_id: str = ""
    timestamp_start: int | float | None = None
    timestamp_end: int | float | None = None
    matched_features: list[str] = field(default_factory=list)
    score: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    video_id: str = "default_video"

    def __init__(
        self,
        source_type: str = "",
        source_id: str = "",
        timestamp_start: int | float | None = None,
        timestamp_end: int | float | None = None,
        matched_features: list[str] | None = None,
        score: float = 0.0,
        evidence: dict[str, Any] | None = None,
        video_id: str = "default_video",
        *,
        candidate_id: str | None = None,
        modality: str | None = None,
        start_ms: int | float | None = None,
        end_ms: int | float | None = None,
        text_content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.source_type = modality if modality is not None else source_type
        self.source_id = candidate_id if candidate_id is not None else source_id
        self.timestamp_start = start_ms if start_ms is not None else timestamp_start
        self.timestamp_end = end_ms if end_ms is not None else timestamp_end
        self.matched_features = matched_features if matched_features is not None else []
        self.score = score
        if metadata is not None:
            self.evidence = dict(metadata)
        elif evidence is not None:
            self.evidence = dict(evidence)
        else:
            self.evidence = {}
        if text_content and "text" not in self.evidence:
            self.evidence["text"] = text_content
        self.video_id = video_id

    @property
    def candidate_id(self) -> str:
        """Alias for source_id for backward compatibility."""
        return self.source_id

    @property
    def modality(self) -> str:
        """Alias for source_type for backward compatibility."""
        return self.source_type

    @property
    def start_ms(self) -> int | None:
        """Alias for timestamp_start for backward compatibility."""
        return int(self.timestamp_start) if self.timestamp_start is not None else None

    @property
    def end_ms(self) -> int | None:
        """Alias for timestamp_end for backward compatibility."""
        return int(self.timestamp_end) if self.timestamp_end is not None else None

    @property
    def text_content(self) -> str:
        """Alias for text content inside evidence for backward compatibility."""
        if isinstance(self.evidence, dict):
            return str(
                self.evidence.get("text")
                or self.evidence.get("ocr_text")
                or self.evidence.get("transcript")
                or self.evidence.get("caption")
                or self.evidence.get("description")
                or self.evidence.get("visual_summary")
                or ""
            )
        return str(self.evidence)

    @property
    def metadata(self) -> dict[str, Any]:
        """Alias for evidence dictionary for backward compatibility."""
        if isinstance(self.evidence, dict):
            return self.evidence
        return {"text": self.evidence}

    @property
    def explanation(self) -> str:
        """Human-readable explanation describing why candidate received its score."""
        if isinstance(self.evidence, dict):
            return str(self.evidence.get("explanation") or "")
        return ""

    def to_dict(self) -> dict[str, Any]:
        """Convert CandidateMemory into a structured dictionary."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "matched_features": self.matched_features,
            "score": round(self.score, 4),
            "evidence": self.evidence,
            "explanation": self.explanation,
            "candidate_id": self.candidate_id,
            "modality": self.modality,
            "video_id": self.video_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text_content": self.text_content,
            "metadata": self.metadata,
        }


@dataclass
class MemoryRetrievalResult:
    """End-to-end memory retrieval result containing candidate moments and evidence traces."""

    original_query: str = ""
    parsed_query: MemoryQuery = field(default_factory=lambda: MemoryQuery(original_query="", features=[], is_memory_query=False))
    candidates: list[CandidateMemory] = field(default_factory=list)
    best_candidate: CandidateMemory | None = None
    confidence: float = 0.0
    matched_features: list[str] = field(default_factory=list)
    retrieval_time_ms: float = 0.0

    @property
    def query(self) -> str:
        """Alias for original_query for backward compatibility."""
        return self.original_query

    @property
    def parsed_memory(self) -> MemoryQuery:
        """Alias for parsed_query for backward compatibility."""
        return self.parsed_query

    @property
    def candidate_moments(self) -> list[CandidateMemory]:
        """Alias for candidates for backward compatibility."""
        return self.candidates

    @property
    def evidence_ids(self) -> list[str]:
        """Alias for evidence_ids for backward compatibility."""
        return [c.source_id for c in self.candidates]

    def to_dict(self) -> dict[str, Any]:
        """Convert MemoryRetrievalResult into a structured dictionary."""
        return {
            "original_query": self.original_query,
            "query": self.query,
            "parsed_query": self.parsed_query.to_dict(),
            "parsed_memory": self.parsed_memory.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "candidate_moments": [c.to_dict() for c in self.candidates],
            "best_candidate": self.best_candidate.to_dict() if self.best_candidate else None,
            "confidence": round(self.confidence, 4),
            "matched_features": self.matched_features,
            "evidence_ids": self.evidence_ids,
            "retrieval_time_ms": round(self.retrieval_time_ms, 3),
        }
