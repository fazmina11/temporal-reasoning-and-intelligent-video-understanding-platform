"""Deterministic quality metrics for raw QA evaluation execution records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from .evaluate_ask import EvaluationResult, EvaluationRun


@dataclass(frozen=True)
class EvaluationMetrics:
    """Aggregate measurements for one evaluation run."""

    outcome_accuracy: float
    timestamp_hit_rate: float
    citation_presence_rate: float
    citation_validity_rate: float
    required_term_coverage: float
    unsupported_claim_rate: float
    negative_question_abstention_rate: float
    average_confidence: float
    average_latency_ms: float
    fallback_rate: float


def _rate(numerator: int, denominator: int, *, empty: float = 0.0) -> float:
    return round(numerator / denominator, 4) if denominator else empty


def _mapping(value: Any) -> Mapping[str, Any]:
    """Normalize dict and Pydantic-style values into a mapping."""
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump) and isinstance((dumped := model_dump()), Mapping):
        return dumped
    legacy_dict = getattr(value, "dict", None)
    if callable(legacy_dict) and isinstance((dumped := legacy_dict()), Mapping):
        return dumped
    return {}


def _outcome(value: str | None) -> str | None:
    """Normalize the clarification label shared by schema and ask contracts."""
    return "clarification_required" if value == "ambiguous_query" else value


def _expected_outcomes(result: EvaluationResult) -> set[str]:
    values = result.acceptable_outcomes or [result.expected_outcome]
    return {_outcome(value) or "" for value in values}


def _grounded(result: EvaluationResult) -> bool:
    return bool(_expected_outcomes(result) & {"grounded_answer", "partial_answer"})


def _interval(value: Mapping[str, Any]) -> tuple[int, int] | None:
    start, end = value.get("start_ms"), value.get("end_ms")
    if isinstance(start, bool) or not isinstance(start, int):
        return None
    end = start if end is None else end
    if isinstance(end, bool) or not isinstance(end, int) or end < start:
        return None
    return start, end


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] <= right[1] and right[0] <= left[1]


def _answer(result: EvaluationResult) -> str:
    value = _mapping(result.raw_response).get("answer", "")
    return value if isinstance(value, str) else ""


def outcome_accuracy(results: Iterable[EvaluationResult]) -> float:
    """Rate of expected-outcome agreement, including clarification aliases."""
    values = list(results)
    correct = 0
    for result in values:
        predicted = _outcome(result.predicted_outcome)
        if predicted in _expected_outcomes(result) and predicted not in {
            _outcome(value) for value in result.forbidden_outcomes
        }:
            correct += 1
    return _rate(correct, len(values))


def timestamp_hit_rate(results: Iterable[EvaluationResult]) -> float:
    """Rate of expected windows overlapped by a response or citation timestamp."""
    eligible = [
        r for r in results
        if _expected_windows(r) or r.requires_timestamp is True
    ]
    hits = 0
    for result in eligible:
        windows = _expected_windows(result)
        candidates = [_mapping(result.raw_response), *(_mapping(citation) for citation in result.citations)]
        if windows and any(
            (interval := _interval(candidate)) is not None
            and any(_overlaps(expected, interval) for expected in windows)
            for candidate in candidates
        ):
            hits += 1
    return _rate(hits, len(eligible))


def citation_presence_rate(results: Iterable[EvaluationResult]) -> float:
    """Rate of grounded items with at least one returned citation."""
    eligible = [r for r in results if _grounded(r)]
    return _rate(sum(bool(r.citations) for r in eligible), len(eligible))


def is_valid_citation(citation: Any, result: EvaluationResult) -> bool:
    """Check citation structure against the source and time labels on a result."""
    values = _mapping(citation)
    source_id, source_type = values.get("source_id"), values.get("source_type")
    source_type = getattr(source_type, "value", source_type)
    if not isinstance(source_id, str) or not source_id.strip() or not isinstance(source_type, str) or not source_type.strip():
        return False
    expected_source_types = result.acceptable_source_types or result.expected_source_types
    if expected_source_types and source_type not in expected_source_types:
        return False
    windows = _expected_windows(result)
    if windows:
        interval = _interval(values)
        return interval is not None and any(_overlaps(expected, interval) for expected in windows)
    return True


def citation_validity_rate(results: Iterable[EvaluationResult]) -> float:
    """Proportion of returned citations that satisfy available QA labels."""
    pairs = [(citation, result) for result in results for citation in result.citations]
    return _rate(sum(is_valid_citation(citation, result) for citation, result in pairs), len(pairs))


def required_term_coverage(results: Iterable[EvaluationResult]) -> float:
    """Case-insensitive required-term coverage across grounded answer text."""
    total = 0
    matched = 0
    for result in results:
        if not _grounded(result):
            continue
        answer = _answer(result).casefold()
        for term in result.required_terms:
            total += 1
            matched += term.casefold() in answer
        for group in result.required_concepts:
            total += 1
            matched += any(term.casefold() in answer for term in group)
    return _rate(matched, total, empty=1.0)


def unsupported_claim_rate(results: Iterable[EvaluationResult]) -> float:
    """Rate of grounded responses lacking valid evidence or using forbidden terms."""
    grounded = [result for result in results if _grounded(result)]
    unsupported = 0
    for result in grounded:
        forbidden = any(term.casefold() in _answer(result).casefold() for term in result.forbidden_terms)
        supported = any(is_valid_citation(citation, result) for citation in result.citations)
        unsupported += forbidden or not supported
    return _rate(unsupported, len(grounded))


def negative_question_abstention_rate(results: Iterable[EvaluationResult]) -> float:
    """Rate of correctly abstained unrelated or evidence-not-found questions."""
    negatives = {"unrelated_to_video", "video_evidence_not_found"}
    eligible = [result for result in results if _expected_outcomes(result) & negatives]
    return _rate(sum(_outcome(r.predicted_outcome) in _expected_outcomes(r) for r in eligible), len(eligible))


def average_confidence(results: Iterable[EvaluationResult]) -> float:
    """Average finite confidence values for successful executions."""
    values = [r.confidence for r in results if r.success and r.confidence is not None and isfinite(r.confidence)]
    return round(sum(values) / len(values), 4) if values else 0.0


def average_latency_ms(results: Iterable[EvaluationResult]) -> float:
    """Average finite latency across every attempted question."""
    values = [r.latency_ms for r in results if isfinite(r.latency_ms)]
    return round(sum(values) / len(values), 4) if values else 0.0


def fallback_rate(results: Iterable[EvaluationResult]) -> float:
    """Rate of successful responses marked as fallback-used in trace metadata."""
    successful = [r for r in results if r.success]
    fallbacks = sum(
        isinstance(r.trace_metadata.get("answer_quality"), Mapping)
        and r.trace_metadata["answer_quality"].get("fallback_used") is True
        for r in successful
    )
    return _rate(fallbacks, len(successful))


def calculate_metrics(run: EvaluationRun) -> EvaluationMetrics:
    """Calculate all supported metrics for one execution run."""
    results = run.results
    return EvaluationMetrics(
        outcome_accuracy=outcome_accuracy(results), timestamp_hit_rate=timestamp_hit_rate(results),
        citation_presence_rate=citation_presence_rate(results), citation_validity_rate=citation_validity_rate(results),
        required_term_coverage=required_term_coverage(results), unsupported_claim_rate=unsupported_claim_rate(results),
        negative_question_abstention_rate=negative_question_abstention_rate(results),
        average_confidence=average_confidence(results), average_latency_ms=average_latency_ms(results),
        fallback_rate=fallback_rate(results),
    )


def _expected_windows(result: EvaluationResult) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    if result.expected_start_ms_min is not None and result.expected_start_ms_max is not None:
        windows.append((result.expected_start_ms_min, result.expected_start_ms_max))
    for window in result.expected_time_windows:
        start = window.get("start_ms")
        end = window.get("end_ms")
        if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool) and start <= end:
            windows.append((start, end))
    return windows
