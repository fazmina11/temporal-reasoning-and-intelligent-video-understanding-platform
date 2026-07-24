"""Typed schemas for manually authored video question-answer evaluations.

These models intentionally define data and validate it only. They do not load
datasets, execute evaluations, calculate metrics, or produce reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, TypeAlias


ExpectedOutcome: TypeAlias = Literal[
    "grounded_answer",
    "video_evidence_not_found",
    "unrelated_to_video",
    "clarification_required",
]

SourceType: TypeAlias = Literal[
    "semantic_chunk",
    "atom",
    "event",
    "ocr",
    "speaker",
    "audio_event",
    "frame",
    "clip",
]

QueryType: TypeAlias = Literal[
    "definition",
    "concept",
    "exact_timestamp",
    "visual_memory",
    "ocr_or_slide_text",
    "speaker_question",
    "before_after",
    "comparison",
    "summary",
    "repeated_concept",
    "unrelated_or_general",
    "video_evidence_not_found",
    "ambiguous_query",
]

_VALID_OUTCOMES = frozenset((
    "grounded_answer",
    "video_evidence_not_found",
    "unrelated_to_video",
    "clarification_required",
))
_VALID_SOURCE_TYPES = frozenset((
    "semantic_chunk", "atom", "event", "ocr", "speaker", "audio_event", "frame", "clip",
))
_VALID_QUERY_TYPES = frozenset((
    "definition", "concept", "exact_timestamp", "visual_memory", "ocr_or_slide_text",
    "speaker_question", "before_after", "comparison", "summary", "repeated_concept",
    "unrelated_or_general", "video_evidence_not_found", "ambiguous_query",
))


class QAValidationError(ValueError):
    """Raised when a QA evaluation item or dataset violates the schema."""


def _require_non_empty_string(value: object, field_name: str) -> None:
    """Ensure a required textual field is a non-blank string."""
    if not isinstance(value, str) or not value.strip():
        raise QAValidationError(f"{field_name} must be a non-empty string.")


@dataclass
class QAItem:
    """Expected behavior for one question against a single indexed video."""

    question_id: str
    video_id: str
    query: str
    expected_outcome: ExpectedOutcome
    expected_start_ms_min: Optional[int] = None
    expected_start_ms_max: Optional[int] = None
    required_terms: list[str] = field(default_factory=list)
    forbidden_terms: list[str] = field(default_factory=list)
    expected_source_types: list[SourceType] = field(default_factory=list)
    notes: str = ""
    query_type: QueryType = "concept"

    def validate(self) -> None:
        """Validate this item and raise :class:`QAValidationError` if invalid."""
        for field_name, value in (
            ("question_id", self.question_id),
            ("video_id", self.video_id),
            ("query", self.query),
            ("notes", self.notes),
        ):
            _require_non_empty_string(value, field_name)

        if self.expected_outcome not in _VALID_OUTCOMES:
            raise QAValidationError(
                f"expected_outcome must be one of {sorted(_VALID_OUTCOMES)}; "
                f"got {self.expected_outcome!r}."
            )
        if self.query_type not in _VALID_QUERY_TYPES:
            raise QAValidationError(
                f"query_type must be one of {sorted(_VALID_QUERY_TYPES)}; got {self.query_type!r}."
            )

        self._validate_timestamp_range()
        self._validate_terms("required_terms", self.required_terms)
        self._validate_terms("forbidden_terms", self.forbidden_terms)
        self._validate_source_types()
        self._validate_outcome_combination()

    def _validate_timestamp_range(self) -> None:
        """Validate an optional inclusive expected evidence time range."""
        start_min, start_max = self.expected_start_ms_min, self.expected_start_ms_max
        if (start_min is None) != (start_max is None):
            raise QAValidationError(
                "expected_start_ms_min and expected_start_ms_max must be provided together."
            )
        if start_min is None:
            return
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (start_min, start_max)):
            raise QAValidationError("Expected timestamp bounds must be integers in milliseconds.")
        if start_min < 0 or start_max < 0:
            raise QAValidationError("Expected timestamp bounds must be non-negative.")
        if start_min > start_max:
            raise QAValidationError(
                "expected_start_ms_min must be less than or equal to expected_start_ms_max."
            )

    @staticmethod
    def _validate_terms(field_name: str, terms: object) -> None:
        """Validate term collections used by later evaluation stages."""
        if not isinstance(terms, list):
            raise QAValidationError(f"{field_name} must be a list of non-empty strings.")
        invalid_terms = [term for term in terms if not isinstance(term, str) or not term.strip()]
        if invalid_terms:
            raise QAValidationError(f"{field_name} contains an empty or non-string term.")

    def _validate_source_types(self) -> None:
        """Ensure every requested evidence source type is recognized."""
        if not isinstance(self.expected_source_types, list):
            raise QAValidationError("expected_source_types must be a list.")
        invalid_types = sorted(set(self.expected_source_types) - _VALID_SOURCE_TYPES)
        if invalid_types:
            raise QAValidationError(f"Invalid expected_source_types: {invalid_types}.")

    def _validate_outcome_combination(self) -> None:
        """Keep evidence expectations consistent with the anticipated outcome."""
        outcome_query_type = {
            "video_evidence_not_found": "video_evidence_not_found",
            "unrelated_to_video": "unrelated_or_general",
            "clarification_required": "ambiguous_query",
        }
        required_query_type = outcome_query_type.get(self.expected_outcome)
        if required_query_type and self.query_type != required_query_type:
            raise QAValidationError(
                f"expected_outcome {self.expected_outcome!r} requires query_type "
                f"{required_query_type!r}."
            )
        if self.expected_outcome == "grounded_answer":
            if self.query_type in outcome_query_type.values():
                raise QAValidationError(
                    "grounded_answer cannot use a non-grounded query_type."
                )
            return
        if self.expected_start_ms_min is not None or self.expected_source_types:
            raise QAValidationError(
                f"expected_outcome {self.expected_outcome!r} cannot specify expected timestamps "
                "or expected_source_types."
            )


@dataclass
class QADataset:
    """A validated collection of QA items for one video."""

    video_id: str
    description: str
    created_at: datetime
    items: list[QAItem] = field(default_factory=list)

    def validate(self) -> None:
        """Validate dataset metadata, contained items, and unique question IDs."""
        _require_non_empty_string(self.video_id, "video_id")
        _require_non_empty_string(self.description, "description")
        if not isinstance(self.created_at, datetime):
            raise QAValidationError("created_at must be a datetime.")
        if not isinstance(self.items, list):
            raise QAValidationError("items must be a list of QAItem instances.")

        seen_ids: set[str] = set()
        duplicate_ids: set[str] = set()
        for index, item in enumerate(self.items):
            if not isinstance(item, QAItem):
                raise QAValidationError(f"items[{index}] must be a QAItem instance.")
            item.validate()
            if item.video_id != self.video_id:
                raise QAValidationError(
                    f"items[{index}] video_id {item.video_id!r} does not match dataset video_id "
                    f"{self.video_id!r}."
                )
            if item.question_id in seen_ids:
                duplicate_ids.add(item.question_id)
            seen_ids.add(item.question_id)
        if duplicate_ids:
            raise QAValidationError(
                f"Duplicate question_id values: {sorted(duplicate_ids)}."
            )
