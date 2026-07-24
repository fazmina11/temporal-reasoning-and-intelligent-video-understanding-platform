"""Pure-Python execution runner and CLI for QA evaluation datasets.

The runner invokes an injected ask adapter and records raw execution results.
It can be run as a CLI tool:
    python -m src.pipeline.evaluation.evaluate_ask --video-id mcp_vs_api

The module intentionally does not depend on FastAPI and remains reusable by other components.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from time import perf_counter_ns
from typing import Any

from .qa_loader import load_dataset
from .qa_schema import QADataset, QAItem

LOGGER = logging.getLogger(__name__)
EVALUATION_RUNNER_VERSION = "evaluation-runner-v1"
DEFAULT_REPORTS_DIR = Path("data/evaluation/reports")


class AskPipelineAdapter(ABC):
    """Adapter boundary between evaluation code and an ask-pipeline implementation."""

    @abstractmethod
    def ask(self, question: str, video_id: str) -> Any:
        """Return the ask pipeline's response for one question and video."""


class DefaultAskPipelineAdapter(AskPipelineAdapter):
    """Offline placeholder adapter for tests and dry-run report generation."""

    def __init__(self, ask_fn: Any | None = None) -> None:
        self._ask_fn = ask_fn

    def ask(self, question: str, video_id: str) -> dict[str, Any]:
        if self._ask_fn is not None:
            return self._ask_fn(question, video_id)
        # Default response shape for offline/standalone execution
        return {
            "outcome": "grounded_answer",
            "confidence": 0.85,
            "answer": f"Evaluated response for query: {question}",
            "citations": [
                {
                    "source_id": f"{video_id}_chunk_01",
                    "source_type": "semantic_chunk",
                    "start_ms": 1000,
                    "end_ms": 5000,
                }
            ],
            "trace_id": "eval_trace_001",
        }


class LocalAskPipelineAdapter(AskPipelineAdapter):
    """Run evaluation against the project's in-process agentic ask pipeline."""

    def ask(self, question: str, video_id: str) -> Any:
        from api import QueryRequest, ask_question

        request = QueryRequest(video_id=video_id, query=question)
        return _run_async_sync(ask_question(request))


@dataclass
class EvaluationResult:
    """Recorded execution details for one QA item without any quality scoring."""

    question_id: str
    query: str
    expected_outcome: str
    predicted_outcome: str | None
    latency_ms: float
    raw_response: Any = None
    confidence: float | None = None
    citations: list[Any] = field(default_factory=list)
    trace_metadata: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    success: bool = False
    expected_start_ms_min: int | None = None
    expected_start_ms_max: int | None = None
    required_terms: list[str] = field(default_factory=list)
    forbidden_terms: list[str] = field(default_factory=list)
    expected_source_types: list[str] = field(default_factory=list)


@dataclass
class EvaluationRun:
    """The raw execution record for one dataset run."""

    video_id: str
    run_timestamp: datetime
    runner_version: str
    results: list[EvaluationResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class EvaluationRunner:
    """Execute all QA items with an injected :class:`AskPipelineAdapter`."""

    def __init__(
        self,
        adapter: AskPipelineAdapter,
        *,
        runner_version: str = EVALUATION_RUNNER_VERSION,
    ) -> None:
        self._adapter = adapter
        self._runner_version = runner_version
        self._run_timestamp: datetime | None = None

    def run(self, dataset_path: str | Path) -> EvaluationRun:
        """Load a dataset and execute each item, continuing after item failures."""
        dataset = load_dataset(dataset_path)
        return self.run_dataset(dataset)

    def run_dataset(self, dataset: QADataset) -> EvaluationRun:
        """Execute an already-loaded dataset preserving failure isolation."""
        dataset.validate()
        self._run_timestamp = datetime.now(timezone.utc)
        LOGGER.info(
            "Starting evaluation run for video_id=%s with %d question(s).",
            dataset.video_id,
            len(dataset.items),
        )
        results = [self.run_question(item) for item in dataset.items]
        run = self.collect_results(dataset.video_id, results)
        LOGGER.info(
            "Completed evaluation run for video_id=%s: %d question(s), %d execution failure(s).",
            run.video_id,
            len(run.results),
            sum(not result.success for result in run.results),
        )
        return run

    def run_question(self, item: QAItem) -> EvaluationResult:
        """Execute one question and convert any adapter failure into a result record."""
        started_ns = perf_counter_ns()
        try:
            raw_response = self._adapter.ask(question=item.query, video_id=item.video_id)
            latency_ms = _elapsed_ms(started_ns)
            response = _response_to_mapping(raw_response)
            result = EvaluationResult(
                question_id=item.question_id,
                query=item.query,
                expected_outcome=item.expected_outcome,
                predicted_outcome=_string_value(response.get("outcome")),
                latency_ms=latency_ms,
                raw_response=raw_response,
                confidence=_numeric_value(response.get("confidence")),
                citations=_citations(response.get("citations")),
                trace_metadata=_trace_metadata(response),
                success=True,
                expected_start_ms_min=item.expected_start_ms_min,
                expected_start_ms_max=item.expected_start_ms_max,
                required_terms=list(item.required_terms),
                forbidden_terms=list(item.forbidden_terms),
                expected_source_types=list(item.expected_source_types),
            )
            LOGGER.debug(
                "Executed question_id=%s in %.3f ms.", item.question_id, result.latency_ms
            )
            return result
        except Exception as exc:
            latency_ms = _elapsed_ms(started_ns)
            LOGGER.exception("Ask adapter failed for question_id=%s.", item.question_id)
            return EvaluationResult(
                question_id=item.question_id,
                query=item.query,
                expected_outcome=item.expected_outcome,
                predicted_outcome=None,
                latency_ms=latency_ms,
                error_message=f"{type(exc).__name__}: {exc}",
                success=False,
                expected_start_ms_min=item.expected_start_ms_min,
                expected_start_ms_max=item.expected_start_ms_max,
                required_terms=list(item.required_terms),
                forbidden_terms=list(item.forbidden_terms),
                expected_source_types=list(item.expected_source_types),
            )

    def collect_results(
        self,
        video_id: str,
        results: Iterable[EvaluationResult],
    ) -> EvaluationRun:
        """Create an execution run from collected results without computing metrics."""
        return EvaluationRun(
            video_id=video_id,
            run_timestamp=self._run_timestamp or datetime.now(timezone.utc),
            runner_version=self._runner_version,
            results=list(results),
        )


def run_evaluation_workflow(
    video_id: str | None = None,
    dataset_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_REPORTS_DIR,
    compare_path: str | Path | None = None,
    adapter: AskPipelineAdapter | None = None,
) -> tuple[
    EvaluationRun,
    EvaluationMetrics,
    tuple[Path, Path],
    tuple[Path, Path] | None,
]:
    """Execute the full evaluation workflow: load dataset, run evaluation, calculate metrics, generate reports, and compare reports."""
    if dataset_path is not None:
        path = Path(dataset_path)
    elif video_id is not None:
        path = Path("data/evaluation/qa_sets") / f"{video_id}_qa.json"
    else:
        raise ValueError("Either video_id or dataset_path must be specified.")

    LOGGER.info("Loading QA dataset from %s", path)
    dataset = load_dataset(path)
    if video_id is not None and dataset.video_id != video_id:
        LOGGER.warning(
            "Specified video_id '%s' differs from dataset video_id '%s'. Using dataset video_id.",
            video_id,
            dataset.video_id,
        )

    if adapter is None:
        adapter = LocalAskPipelineAdapter()

    runner = EvaluationRunner(adapter=adapter)
    LOGGER.info("Executing dataset questions for video_id=%s...", dataset.video_id)
    run = runner.run_dataset(dataset)

    LOGGER.info("Computing metrics...")
    from .metrics import EvaluationMetrics, calculate_metrics
    metrics = calculate_metrics(run)


    LOGGER.info("Writing reports to %s...", output_dir)
    from .report_writer import write_reports

    json_path, md_path = write_reports(run, metrics, output_dir=output_dir)


    comparison_paths: tuple[Path, Path] | None = None
    if compare_path is not None:
        LOGGER.info("Comparing run against previous report: %s", compare_path)
        from .regression_compare import compare_and_write_reports

        comparison_paths = compare_and_write_reports(
            baseline=compare_path,
            candidate=json_path,
            output_dir=output_dir,
        )


    return run, metrics, (json_path, md_path), comparison_paths


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser for the evaluation runner."""
    parser = argparse.ArgumentParser(
        description="Run evaluation dataset against the ask pipeline and generate reports."
    )
    parser.add_argument(
        "--video-id",
        type=str,
        default=None,
        help="Video ID for evaluation (e.g. mcp_vs_api).",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to QA dataset JSON file.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_REPORTS_DIR),
        help="Output directory for reports (default: data/evaluation/reports).",
    )
    parser.add_argument(
        "--compare",
        type=str,
        default=None,
        help="Path to previous evaluation report JSON to compare against.",
    )
    parser.add_argument(
        "--offline-placeholder",
        action="store_true",
        help=(
            "Use a deterministic placeholder adapter instead of the real local ask "
            "pipeline. Intended for CLI smoke tests only."
        ),
    )
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entrypoint for evaluation runner."""
    parser = build_arg_parser()
    parsed_args = parser.parse_args(args)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if parsed_args.video_id is None and parsed_args.dataset is None:
        parser.error("At least one of --video-id or --dataset must be provided.")

    try:
        adapter = DefaultAskPipelineAdapter() if parsed_args.offline_placeholder else None
        run, metrics, (json_path, md_path), comp_paths = run_evaluation_workflow(
            video_id=parsed_args.video_id,
            dataset_path=parsed_args.dataset,
            output_dir=parsed_args.output,
            compare_path=parsed_args.compare,
            adapter=adapter,
        )
        LOGGER.info("Report JSON written to: %s", json_path)
        LOGGER.info("Report Markdown written to: %s", md_path)
        if comp_paths:
            LOGGER.info("Comparison JSON written to: %s", comp_paths[0])
            LOGGER.info("Comparison Markdown written to: %s", comp_paths[1])
        return 0
    except Exception as exc:
        LOGGER.error("Evaluation CLI failed: %s", exc, exc_info=True)
        return 1


def _elapsed_ms(started_ns: int) -> float:
    """Calculate elapsed monotonic time in milliseconds."""
    return round((perf_counter_ns() - started_ns) / 1_000_000, 3)


def _run_async_sync(awaitable: Any) -> Any:
    """Run an async ask call from either plain sync code or an active event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread
            result["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _response_to_mapping(response: Any) -> Mapping[str, Any]:
    """Extract public fields from common dictionary and model response shapes."""
    if isinstance(response, Mapping):
        return response
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    legacy_dict = getattr(response, "dict", None)
    if callable(legacy_dict):
        dumped = legacy_dict()
        if isinstance(dumped, Mapping):
            return dumped
    return {
        field_name: getattr(response, field_name)
        for field_name in ("outcome", "confidence", "citations", "trace_id", "trace_metadata")
        if hasattr(response, field_name)
    }


def _string_value(value: Any) -> str | None:
    """Normalize enum-like outcome values without validating or scoring them."""
    if value is None:
        return None
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _numeric_value(value: Any) -> float | None:
    """Return finite adapter confidence values when representable as floats."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _citations(value: Any) -> list[Any]:
    """Preserve list or tuple citations from the raw adapter response."""
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _trace_metadata(response: Mapping[str, Any]) -> dict[str, Any]:
    """Collect trace fields when the adapter response exposes them."""
    metadata_value = response.get("trace_metadata")
    metadata = dict(metadata_value) if isinstance(metadata_value, Mapping) else {}
    for field_name in ("trace_id", "warnings", "answer_quality"):
        if field_name in response:
            metadata[field_name] = response[field_name]
    return metadata


if __name__ == "__main__":
    sys.exit(main())
