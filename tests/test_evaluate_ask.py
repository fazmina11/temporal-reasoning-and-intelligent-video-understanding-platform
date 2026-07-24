import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.pipeline.evaluation.evaluate_ask import (
    AskPipelineAdapter,
    DefaultAskPipelineAdapter,
    EvaluationResult,
    EvaluationRunner,
    build_arg_parser,
    main,
    run_evaluation_workflow,
)
from src.pipeline.evaluation.qa_loader import DATASET_REGISTRY


def dataset_payload(item_count: int = 1) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for index in range(item_count):
        items.append(
            {
                "question_id": f"q_{index + 1:03d}",
                "video_id": "video_001",
                "query": f"What is retrieval {index + 1}?",
                "expected_outcome": "grounded_answer",
                "expected_start_ms_min": 1000,
                "expected_start_ms_max": 4000,
                "required_terms": ["retrieval"],
                "forbidden_terms": [],
                "expected_source_types": ["semantic_chunk"],
                "notes": "Evaluation runner fixture.",
                "query_type": "definition",
            }
        )
    return {
        "video_id": "video_001",
        "description": "Evaluation runner test dataset.",
        "created_at": "2026-07-23T12:00:00+00:00",
        "items": items,
    }


def sample_report_payload() -> dict[str, object]:
    return {
        "metadata": {
            "video_id": "video_001",
            "run_timestamp": "2026-07-23T10:00:00+00:00",
            "runner_version": "v1.0",
            "total_questions": 1,
            "successful_questions": 1,
            "execution_failures": 0,
        },
        "metrics": {
            "outcome_accuracy": 1.0,
            "timestamp_hit_rate": 1.0,
            "citation_presence_rate": 1.0,
            "citation_validity_rate": 1.0,
            "required_term_coverage": 1.0,
            "unsupported_claim_rate": 0.0,
            "negative_question_abstention_rate": 1.0,
            "average_confidence": 0.9,
            "average_latency_ms": 50.0,
            "fallback_rate": 0.0,
        },
        "latency_summary": {
            "count": 1,
            "average_ms": 50.0,
            "min_ms": 50.0,
            "max_ms": 50.0,
            "p50_ms": 50.0,
            "p90_ms": 50.0,
            "p95_ms": 50.0,
        },
        "top_error_categories": [],
        "low_confidence_questions": [],
        "failures": [],
        "per_question_summary": [
            {
                "question_id": "q_001",
                "query": "What is retrieval 1?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "grounded_answer",
                "success": True,
                "confidence": 0.9,
                "latency_ms": 50.0,
                "error_message": None,
            }
        ],
    }


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        DATASET_REGISTRY.clear()

    def tearDown(self) -> None:
        DATASET_REGISTRY.clear()

    def _write_dataset(self, payload: dict[str, object]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        path = Path(temporary_directory.name) / "dataset.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return temporary_directory, path

    def test_successful_execution_records_adapter_response(self) -> None:
        adapter = Mock(spec=AskPipelineAdapter)
        adapter.ask.return_value = {
            "outcome": "grounded_answer",
            "confidence": 0.91,
            "citations": [{"source_id": "chunk_001"}],
            "trace_id": "trace_001",
        }
        temporary_directory, path = self._write_dataset(dataset_payload())
        with temporary_directory:
            run = EvaluationRunner(adapter).run(path)

        self.assertEqual(len(run.results), 1)
        result = run.results[0]
        self.assertTrue(result.success)
        self.assertEqual(result.predicted_outcome, "grounded_answer")
        self.assertEqual(result.confidence, 0.91)
        self.assertEqual(result.citations, [{"source_id": "chunk_001"}])
        self.assertEqual(result.trace_metadata["trace_id"], "trace_001")
        adapter.ask.assert_called_once_with(question="What is retrieval 1?", video_id="video_001")

    def test_exception_is_recorded_and_later_questions_continue(self) -> None:
        adapter = Mock(spec=AskPipelineAdapter)
        adapter.ask.side_effect = [RuntimeError("pipeline unavailable"), {"outcome": "grounded_answer"}]
        temporary_directory, path = self._write_dataset(dataset_payload(item_count=2))
        with temporary_directory:
            run = EvaluationRunner(adapter).run(path)

        self.assertEqual(len(run.results), 2)
        self.assertFalse(run.results[0].success)
        self.assertIn("RuntimeError: pipeline unavailable", run.results[0].error_message or "")
        self.assertTrue(run.results[1].success)
        self.assertEqual(adapter.ask.call_count, 2)

    def test_latency_is_recorded(self) -> None:
        adapter = Mock(spec=AskPipelineAdapter)
        adapter.ask.return_value = {"outcome": "grounded_answer"}
        temporary_directory, path = self._write_dataset(dataset_payload())
        with temporary_directory:
            result = EvaluationRunner(adapter).run(path).results[0]

        self.assertGreaterEqual(result.latency_ms, 0.0)

    def test_collect_results_preserves_records_without_metrics(self) -> None:
        runner = EvaluationRunner(Mock(spec=AskPipelineAdapter), runner_version="test-runner")
        result = EvaluationResult(
            question_id="q_001", query="Question", expected_outcome="grounded_answer",
            predicted_outcome="grounded_answer", latency_ms=1.0, success=True,
        )
        run = runner.collect_results("video_001", [result])

        self.assertEqual(run.video_id, "video_001")
        self.assertEqual(run.runner_version, "test-runner")
        self.assertEqual(run.results, [result])
        self.assertEqual(run.summary, {})

    def test_empty_dataset_returns_empty_run(self) -> None:
        adapter = Mock(spec=AskPipelineAdapter)
        temporary_directory, path = self._write_dataset(dataset_payload(item_count=0))
        with temporary_directory:
            run = EvaluationRunner(adapter).run(path)

        self.assertEqual(run.video_id, "video_001")
        self.assertEqual(run.results, [])
        self.assertEqual(run.summary, {})
        adapter.ask.assert_not_called()


class EvaluationCLITests(unittest.TestCase):
    def setUp(self) -> None:
        DATASET_REGISTRY.clear()

    def tearDown(self) -> None:
        DATASET_REGISTRY.clear()

    def test_build_arg_parser_arguments(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args([
            "--video-id", "mcp_vs_api",
            "--dataset", "path/to/dataset.json",
            "--output", "path/to/output",
            "--compare", "path/to/baseline.json",
            "--offline-placeholder",
        ])
        self.assertEqual(args.video_id, "mcp_vs_api")
        self.assertEqual(args.dataset, "path/to/dataset.json")
        self.assertEqual(args.output, "path/to/output")
        self.assertEqual(args.compare, "path/to/baseline.json")
        self.assertTrue(args.offline_placeholder)

    def test_run_evaluation_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ds_path = Path(tmp_dir) / "dataset.json"
            ds_path.write_text(json.dumps(dataset_payload(2)), encoding="utf-8")
            out_dir = Path(tmp_dir) / "reports"

            adapter = DefaultAskPipelineAdapter()
            run, metrics, (json_path, md_path), comp_paths = run_evaluation_workflow(
                dataset_path=ds_path,
                output_dir=out_dir,
                adapter=adapter,
            )

            self.assertEqual(run.video_id, "video_001")
            self.assertEqual(len(run.results), 2)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIsNone(comp_paths)

    def test_run_evaluation_workflow_with_compare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ds_path = Path(tmp_dir) / "dataset.json"
            ds_path.write_text(json.dumps(dataset_payload(1)), encoding="utf-8")
            base_rep_path = Path(tmp_dir) / "baseline.json"
            base_rep_path.write_text(json.dumps(sample_report_payload()), encoding="utf-8")

            out_dir = Path(tmp_dir) / "reports"
            adapter = DefaultAskPipelineAdapter()

            run, metrics, (json_path, md_path), comp_paths = run_evaluation_workflow(
                dataset_path=ds_path,
                output_dir=out_dir,
                compare_path=base_rep_path,
                adapter=adapter,
            )

            self.assertIsNotNone(comp_paths)
            assert comp_paths is not None
            self.assertTrue(comp_paths[0].exists())
            self.assertTrue(comp_paths[1].exists())

    def test_main_cli_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ds_path = Path(tmp_dir) / "dataset.json"
            ds_path.write_text(json.dumps(dataset_payload(1)), encoding="utf-8")
            out_dir = Path(tmp_dir) / "reports"

            exit_code = main([
                "--dataset", str(ds_path),
                "--output", str(out_dir),
                "--offline-placeholder",
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue(out_dir.exists())


if __name__ == "__main__":
    unittest.main()
