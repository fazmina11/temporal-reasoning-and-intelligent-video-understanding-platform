import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.evaluation.release_manager import (
    assess_release_gates,
    build_release_report,
    load_threshold_snapshot,
    write_release_artifacts,
)


def _candidate_report(**metric_overrides):
    metrics = {
        "outcome_accuracy": 0.95,
        "timestamp_hit_rate": 0.90,
        "citation_presence_rate": 0.96,
        "citation_validity_rate": 1.0,
        "required_term_coverage": 0.94,
        "unsupported_claim_rate": 0.0,
        "negative_question_abstention_rate": 1.0,
        "average_confidence": 0.82,
        "average_latency_ms": 100.0,
        "fallback_rate": 0.1,
    }
    metrics.update(metric_overrides)
    return {
        "metadata": {
            "video_id": "mcp_vs_api",
            "run_timestamp": "2026-07-24T00:00:00+00:00",
            "runner_version": "test",
            "total_questions": 2,
            "successful_questions": 2,
            "execution_failures": 0,
        },
        "metrics": metrics,
        "latency_summary": {"average_ms": 100.0},
        "failures": [],
        "low_confidence_questions": [],
    }


class ReleaseManagerTests(unittest.TestCase):
    def test_threshold_snapshot_loads_simple_yaml_without_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            config = repo / "config" / "phase_n_thresholds.yaml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "schema_version: test\nrelease_gates:\n  outcome_accuracy_min: 0.91\n",
                encoding="utf-8",
            )
            snapshot = load_threshold_snapshot(repo)
            self.assertEqual(snapshot.values["schema_version"], "test")
            self.assertEqual(snapshot.values["release_gates"]["outcome_accuracy_min"], 0.91)
            self.assertEqual(len(snapshot.sha256), 64)

    def test_assess_release_gates_passes_perfect_candidate(self) -> None:
        summary = assess_release_gates(_candidate_report())
        self.assertEqual(summary["overall_status"], "pass")
        self.assertEqual(summary["failed_gate_count"], 0)

    def test_assess_release_gates_fails_regressed_timestamp_and_citation(self) -> None:
        summary = assess_release_gates(
            _candidate_report(timestamp_hit_rate=0.2, citation_validity_rate=0.5)
        )
        self.assertEqual(summary["overall_status"], "fail")
        reasons = " ".join(summary["failure_reasons"])
        self.assertIn("timestamp_hit_rate", reasons)
        self.assertIn("citation_validity_rate", reasons)

    def test_write_release_artifacts_creates_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            candidate_path = repo / "candidate.json"
            candidate_path.write_text(json.dumps(_candidate_report()), encoding="utf-8")
            snapshot = load_threshold_snapshot(repo)
            report = build_release_report(
                repo_root=repo,
                video_id="mcp_vs_api",
                release_id="release_001",
                created_at="2026-07-24T00:00:00+00:00",
                candidate_report=_candidate_report(),
                candidate_report_path=candidate_path,
                threshold_snapshot=snapshot,
            )
            json_path, md_path = write_release_artifacts(report, repo / "release")
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertIn("Phase N Release Report", md_path.read_text(encoding="utf-8"))

    def test_modality_warnings_do_not_block_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            reports = repo / "data" / "processed" / "reports"
            reports.mkdir(parents=True)
            for modality in ("ocr", "speaker", "audio"):
                (reports / f"mcp_vs_api_{modality}_quality.json").write_text(
                    json.dumps({"summary": {"low_quality_count": 2 if modality == "ocr" else 0}}),
                    encoding="utf-8",
                )
            candidate_path = repo / "candidate.json"
            candidate_path.write_text(json.dumps(_candidate_report()), encoding="utf-8")
            report = build_release_report(
                repo_root=repo,
                video_id="mcp_vs_api",
                release_id="release_with_warnings",
                created_at="2026-07-24T00:00:00+00:00",
                candidate_report=_candidate_report(),
                candidate_report_path=candidate_path,
                threshold_snapshot=load_threshold_snapshot(repo),
            )
            self.assertEqual(report["gate_summary"]["overall_status"], "warn")
            self.assertGreater(report["gate_summary"]["warning_gate_count"], 0)
            self.assertEqual(report["gate_summary"]["failed_gate_count"], 0)
            self.assertEqual(report["release_decision"], "pass")


if __name__ == "__main__":
    unittest.main()
