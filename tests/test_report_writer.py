import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.evaluation.evaluate_ask import EvaluationResult, EvaluationRun
from src.pipeline.evaluation.metrics import calculate_metrics
from src.pipeline.evaluation.report_writer import (
    DEFAULT_REPORTS_DIR,
    calculate_latency_summary,
    detect_error_categories,
    find_failures,
    find_low_confidence_questions,
    generate_json_report,
    generate_markdown_report,
    summarize_top_error_categories,
    write_reports,
)


def make_test_run() -> EvaluationRun:
    first = EvaluationResult(
        question_id="q_001",
        query="What is MCP?",
        expected_outcome="grounded_answer",
        predicted_outcome="grounded_answer",
        latency_ms=100.0,
        raw_response={"answer": "MCP is Model Context Protocol."},
        confidence=0.95,
        citations=[{"source_id": "chunk_001", "source_type": "semantic_chunk", "start_ms": 1000, "end_ms": 2000}],
        success=True,
        expected_start_ms_min=500,
        expected_start_ms_max=2500,
        required_terms=["MCP"],
        expected_source_types=["semantic_chunk"],
    )
    second = EvaluationResult(
        question_id="q_002",
        query="Where is the quantum computer introduced?",
        expected_outcome="grounded_answer",
        predicted_outcome="video_evidence_not_found",
        latency_ms=200.0,
        raw_response={"answer": "Evidence not found."},
        confidence=0.4,
        success=True,
        required_terms=["quantum"],
        expected_source_types=["semantic_chunk"],
    )
    third = EvaluationResult(
        question_id="q_003",
        query="Who is speaking at 05:00?",
        expected_outcome="grounded_answer",
        predicted_outcome=None,
        latency_ms=50.0,
        error_message="RuntimeError: adapter timeout",
        success=False,
    )
    fourth = EvaluationResult(
        question_id="q_004",
        query="What is the stock price of Apple?",
        expected_outcome="unrelated_to_video",
        predicted_outcome="unrelated_to_video",
        latency_ms=80.0,
        raw_response={"answer": "Unrelated to video."},
        confidence=0.85,
        success=True,
    )

    return EvaluationRun(
        video_id="video_test_001",
        run_timestamp=datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc),
        runner_version="test-v1",
        results=[first, second, third, fourth],
    )


class ReportWriterTests(unittest.TestCase):
    def test_default_reports_dir(self) -> None:
        self.assertEqual(DEFAULT_REPORTS_DIR, Path("data/evaluation/reports"))

    def test_calculate_latency_summary(self) -> None:
        run = make_test_run()
        summary = calculate_latency_summary(run.results)

        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["average_ms"], 107.5)
        self.assertEqual(summary["min_ms"], 50.0)
        self.assertEqual(summary["max_ms"], 200.0)
        self.assertEqual(summary["p50_ms"], 90.0)
        self.assertGreater(summary["p90_ms"], 100.0)

    def test_calculate_latency_summary_empty(self) -> None:
        summary = calculate_latency_summary([])
        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["average_ms"], 0.0)
        self.assertEqual(summary["min_ms"], 0.0)

    def test_detect_error_categories(self) -> None:
        run = make_test_run()
        res_success = run.results[0]
        res_mismatch = run.results[1]
        res_exec_err = run.results[2]

        self.assertEqual(detect_error_categories(res_success), [])
        self.assertEqual(
            detect_error_categories(res_mismatch),
            ["Outcome Mismatch (expected: grounded_answer, got: video_evidence_not_found)"],
        )
        self.assertEqual(
            detect_error_categories(res_exec_err),
            ["Execution Error (RuntimeError)"],
        )

    def test_summarize_top_error_categories(self) -> None:
        run = make_test_run()
        top_errors = summarize_top_error_categories(run.results)

        self.assertEqual(len(top_errors), 2)
        categories = [item["category"] for item in top_errors]
        self.assertIn("Execution Error (RuntimeError)", categories)
        self.assertIn(
            "Outcome Mismatch (expected: grounded_answer, got: video_evidence_not_found)",
            categories,
        )

    def test_find_low_confidence_questions(self) -> None:
        run = make_test_run()
        low_conf = find_low_confidence_questions(run.results, threshold=0.5)

        self.assertEqual(len(low_conf), 1)
        self.assertEqual(low_conf[0]["question_id"], "q_002")
        self.assertEqual(low_conf[0]["confidence"], 0.4)

    def test_find_failures(self) -> None:
        run = make_test_run()
        failures = find_failures(run.results)

        self.assertEqual(len(failures), 2)
        failure_ids = [f["question_id"] for f in failures]
        self.assertIn("q_002", failure_ids)  # Outcome mismatch
        self.assertIn("q_003", failure_ids)  # Execution failure

    def test_generate_json_report(self) -> None:
        run = make_test_run()
        metrics = calculate_metrics(run)
        json_report = generate_json_report(run, metrics)

        self.assertIn("metadata", json_report)
        self.assertIn("metrics", json_report)
        self.assertIn("latency_summary", json_report)
        self.assertIn("top_error_categories", json_report)
        self.assertIn("low_confidence_questions", json_report)
        self.assertIn("failures", json_report)
        self.assertIn("per_question_summary", json_report)

        metadata = json_report["metadata"]
        self.assertEqual(metadata["video_id"], "video_test_001")
        self.assertEqual(metadata["total_questions"], 4)
        self.assertEqual(metadata["successful_questions"], 3)
        self.assertEqual(metadata["execution_failures"], 1)

    def test_generate_markdown_report(self) -> None:
        run = make_test_run()
        md_report = generate_markdown_report(run)

        self.assertIn("# Evaluation Report: video_test_001", md_report)
        self.assertIn("## Run Metadata", md_report)
        self.assertIn("## Metric Table", md_report)
        self.assertIn("## Latency Summary", md_report)
        self.assertIn("## Top Error Categories", md_report)
        self.assertIn("## Low Confidence Questions", md_report)
        self.assertIn("## Failures", md_report)
        self.assertIn("## Per-Question Summary", md_report)

        self.assertIn("Outcome Accuracy", md_report)
        self.assertIn("q_001", md_report)
        self.assertIn("q_002", md_report)
        self.assertIn("RuntimeError", md_report)

    def test_write_reports(self) -> None:
        run = make_test_run()
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "reports"
            json_path, md_path = write_reports(run, output_dir=out_dir, run_id="run_123")

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertEqual(json_path.name, "video_test_001_run_123.json")
            self.assertEqual(md_path.name, "video_test_001_run_123.md")

            with json_path.open("r", encoding="utf-8") as f:
                saved_json = json.load(f)
                self.assertEqual(saved_json["metadata"]["video_id"], "video_test_001")

            with md_path.open("r", encoding="utf-8") as f:
                saved_md = f.read()
                self.assertIn("# Evaluation Report: video_test_001", saved_md)

    def test_write_reports_default_run_id(self) -> None:
        run = make_test_run()
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path, md_path = write_reports(run, output_dir=tmp_dir)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIn("video_test_001_20260723_120000", json_path.name)


if __name__ == "__main__":
    unittest.main()
