"""Data contracts for Knowledge Reconstruction dependency extraction and learning path planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConceptNode:
    """A concept extracted from video evidence or query context."""

    concept: str
    source_id: str
    timestamp_start: int | float | None = None
    timestamp_end: int | float | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert ConceptNode into a structured dictionary."""
        return {
            "concept": self.concept,
            "source_id": self.source_id,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class DependencyEdge:
    """A prerequisite or dependency relationship between two concepts."""

    parent: str
    child: str
    relation: str = "prerequisite_of"

    def to_dict(self) -> dict[str, Any]:
        """Convert DependencyEdge into a structured dictionary."""
        return {
            "parent": self.parent,
            "child": self.child,
            "relation": self.relation,
        }


@dataclass
class LearningPath:
    """An ordered prerequisite learning path leading to a target concept."""

    ordered_concepts: list[str] = field(default_factory=list)
    dependency_chain: list[DependencyEdge] = field(default_factory=list)
    missing_prerequisites: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert LearningPath into a structured dictionary."""
        return {
            "ordered_concepts": self.ordered_concepts,
            "dependency_chain": [e.to_dict() for e in self.dependency_chain],
            "missing_prerequisites": self.missing_prerequisites,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class KnowledgeReconstructionResult:
    """End-to-end Knowledge Reconstruction result."""

    target_concept: str
    learning_path: LearningPath
    prerequisite_concepts: list[str] = field(default_factory=list)
    reconstruction_summary: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert KnowledgeReconstructionResult into a structured dictionary."""
        return {
            "target_concept": self.target_concept,
            "learning_path": self.learning_path.to_dict(),
            "prerequisite_concepts": self.prerequisite_concepts,
            "reconstruction_summary": self.reconstruction_summary,
            "confidence": round(self.confidence, 4),
        }
