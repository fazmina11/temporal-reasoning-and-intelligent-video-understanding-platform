import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.evaluation.evaluate_ask import EvaluationResult, EvaluationRun
from src.pipeline.evaluation.regression_compare import (
    compare_and_write_reports,
    compare_reports,
    generate_markdown_comparison,
)
from src.pipeline.evaluation.report_writer import generate_json_report


def make_baseline_report() -> dict[str, object]:
    return {
        "metadata": {
            "video_id": "mcp_vs_api",
            "run_timestamp": "2026-07-23T10:00:00+00:00",
            "runner_version": "v1.0",
            "total_questions": 3,
            "successful_questions": 3,
            "execution_failures": 0,
        },
        "metrics": {
            "outcome_accuracy": 0.6667,
            "timestamp_hit_rate": 0.5000,
            "citation_presence_rate": 0.5000,
            "citation_validity_rate": 0.5000,
            "required_term_coverage": 0.5000,
            "unsupported_claim_rate": 0.3333,
            "negative_question_abstention_rate": 1.0000,
            "average_confidence": 0.7000,
            "average_latency_ms": 200.0,
            "fallback_rate": 0.1000,
        },
        "latency_summary": {
            "count": 3,
            "average_ms": 200.0,
            "min_ms": 100.0,
            "max_ms": 300.0,
            "p50_ms": 200.0,
            "p90_ms": 280.0,
            "p95_ms": 290.0,
        },
        "top_error_categories": [
            {"category": "Outcome Mismatch (expected: grounded_answer, got: video_evidence_not_found)", "count": 1}
        ],
        "low_confidence_questions": [],
        "failures": [
            {
                "question_id": "q_001",
                "query": "What is MCP?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "video_evidence_not_found",
                "success": True,
                "error_message": None,
                "confidence": 0.40,
                "latency_ms": 200.0,
            }
        ],
        "per_question_summary": [
            {
                "question_id": "q_001",
                "query": "What is MCP?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "video_evidence_not_found",
                "success": True,
                "confidence": 0.40,
                "latency_ms": 200.0,
                "error_message": None,
            },
            {
                "question_id": "q_002",
                "query": "Where is protocol defined?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "grounded_answer",
                "success": True,
                "confidence": 0.90,
                "latency_ms": 100.0,
                "error_message": None,
            },
            {
                "question_id": "q_003",
                "query": "What is current GDP of France?",
                "expected_outcome": "unrelated_to_video",
                "predicted_outcome": "unrelated_to_video",
                "success": True,
                "confidence": 0.80,
                "latency_ms": 300.0,
                "error_message": None,
            },
        ],
    }


def make_candidate_report() -> dict[str, object]:
    return {
        "metadata": {
            "video_id": "mcp_vs_api",
            "run_timestamp": "2026-07-23T14:00:00+00:00",
            "runner_version": "v1.1",
            "total_questions": 3,
            "successful_questions": 3,
            "execution_failures": 0,
        },
        "metrics": {
            "outcome_accuracy": 1.0000,  # Improved
            "timestamp_hit_rate": 0.5000,  # Unchanged
            "citation_presence_rate": 1.0000,  # Improved
            "citation_validity_rate": 1.0000,  # Improved
            "required_term_coverage": 1.0000,  # Improved
            "unsupported_claim_rate": 0.0000,  # Improved (lower is better)
            "negative_question_abstention_rate": 1.0000,  # Unchanged
            "average_confidence": 0.9000,  # Improved
            "average_latency_ms": 120.0,  # Improved (lower is better)
            "fallback_rate": 0.3333,  # Regressed (lower is better, grew)
        },
        "latency_summary": {
            "count": 3,
            "average_ms": 120.0,
            "min_ms": 80.0,
            "max_ms": 180.0,
            "p50_ms": 100.0,
            "p90_ms": 164.0,
            "p95_ms": 172.0,
        },
        "top_error_categories": [],
        "low_confidence_questions": [],
        "failures": [],  # q_001 resolved
        "per_question_summary": [
            {
                "question_id": "q_001",
                "query": "What is MCP?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "grounded_answer",  # Resolved!
                "success": True,
                "confidence": 0.95,
                "latency_ms": 100.0,
                "error_message": None,
            },
            {
                "question_id": "q_002",
                "query": "Where is protocol defined?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "grounded_answer",
                "success": True,
                "confidence": 0.95,
                "latency_ms": 80.0,
                "error_message": None,
            },
            {
                "question_id": "q_003",
                "query": "What is current GDP of France?",
                "expected_outcome": "unrelated_to_video",
                "predicted_outcome": "unrelated_to_video",
                "success": True,
                "confidence": 0.80,
                "latency_ms": 180.0,
                "error_message": None,
            },
        ],
    }


class RegressionCompareTests(unittest.TestCase):
    def test_compare_reports_identifies_improved_and_regressed_metrics(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()

        comp = compare_reports(b_rep, c_rep)

        self.assertIn("metadata", comp)
        self.assertEqual(comp["metadata"]["video_id"], "mcp_vs_api")

        improved_names = [m["metric"] for m in comp["improved_metrics"]]
        regressed_names = [m["metric"] for m in comp["regressed_metrics"]]

        self.assertIn("outcome_accuracy", improved_names)
        self.assertIn("unsupported_claim_rate", improved_names)
        self.assertIn("average_latency_ms", improved_names)

        self.assertIn("fallback_rate", regressed_names)

    def test_compare_reports_resolved_and_new_failures(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()

        comp = compare_reports(b_rep, c_rep)

        self.assertEqual(len(comp["resolved_failures"]), 1)
        self.assertEqual(comp["resolved_failures"][0]["question_id"], "q_001")
        self.assertEqual(len(comp["new_failures"]), 0)

    def test_compare_reports_detects_new_failures(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()
        # Add a new failure to candidate
        c_rep["failures"] = [
            {
                "question_id": "q_002",
                "query": "Where is protocol defined?",
                "expected_outcome": "grounded_answer",
                "predicted_outcome": "video_evidence_not_found",
                "success": True,
                "error_message": None,
            }
        ]

        comp = compare_reports(b_rep, c_rep)

        self.assertEqual(len(comp["new_failures"]), 1)
        self.assertEqual(comp["new_failures"][0]["question_id"], "q_002")

    def test_latency_delta_calculation(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()

        comp = compare_reports(b_rep, c_rep)
        lat_delta = comp["latency_delta"]

        self.assertEqual(lat_delta["average_ms"]["baseline"], 200.0)
        self.assertEqual(lat_delta["average_ms"]["candidate"], 120.0)
        self.assertEqual(lat_delta["average_ms"]["delta"], -80.0)
        self.assertEqual(lat_delta["average_ms"]["status"], "improved")

    def test_generate_markdown_comparison(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()

        comp = compare_reports(b_rep, c_rep)
        md_text = generate_markdown_comparison(comp)

        self.assertIn("# Evaluation Regression Comparison Report: mcp_vs_api", md_text)
        self.assertIn("## Metric Comparison Summary", md_text)
        self.assertIn("## Improved Metrics", md_text)
        self.assertIn("## Regressed Metrics", md_text)
        self.assertIn("## Latency Delta", md_text)
        self.assertIn("## Resolved Failures (Improvements)", md_text)
        self.assertIn("q_001", md_text)

    def test_compare_and_write_reports(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path, md_path = compare_and_write_reports(
                b_rep, c_rep, output_dir=tmp_dir, comparison_id="comp_001"
            )

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertEqual(json_path.name, "mcp_vs_api_comp_001.json")
            self.assertEqual(md_path.name, "mcp_vs_api_comp_001.md")

            with json_path.open("r", encoding="utf-8") as f:
                saved_comp = json.load(f)
                self.assertEqual(saved_comp["metadata"]["video_id"], "mcp_vs_api")

    def test_compare_reports_accepts_file_paths(self) -> None:
        b_rep = make_baseline_report()
        c_rep = make_candidate_report()

        with tempfile.TemporaryDirectory() as tmp_dir:
            b_path = Path(tmp_dir) / "baseline.json"
            c_path = Path(tmp_dir) / "candidate.json"

            b_path.write_text(json.dumps(b_rep), encoding="utf-8")
            c_path.write_text(json.dumps(c_rep), encoding="utf-8")

            comp = compare_reports(b_path, c_path)
            self.assertEqual(comp["metadata"]["video_id"], "mcp_vs_api")
            self.assertEqual(len(comp["improved_metrics"]), 7)


    def test_compare_reports_accepts_evaluation_run(self) -> None:
        res1 = EvaluationResult(
            question_id="q_001", query="Q1", expected_outcome="grounded_answer",
            predicted_outcome="grounded_answer", latency_ms=50.0, success=True,
        )
        run1 = EvaluationRun(
            video_id="video_run", run_timestamp=datetime.now(timezone.utc),
            runner_version="v1", results=[res1],
        )
        res2 = EvaluationResult(
            question_id="q_001", query="Q1", expected_outcome="grounded_answer",
            predicted_outcome="video_evidence_not_found", latency_ms=100.0, success=True,
        )
        run2 = EvaluationRun(
            video_id="video_run", run_timestamp=datetime.now(timezone.utc),
            runner_version="v1", results=[res2],
        )

        comp = compare_reports(run1, run2)
        self.assertEqual(comp["metadata"]["video_id"], "video_run")
        self.assertEqual(len(comp["new_failures"]), 1)


if __name__ == "__main__":
    unittest.main()
