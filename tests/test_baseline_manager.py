import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.evaluation.baseline_manager import (
    BASELINE_SCHEMA_VERSION,
    freeze_baseline,
)
from src.pipeline.evaluation.qa_loader import DATASET_REGISTRY


class BaselineManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        DATASET_REGISTRY.clear()

    def tearDown(self) -> None:
        DATASET_REGISTRY.clear()

    def test_freeze_baseline_writes_manifest_and_copies_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            dataset_path = repo / "qa.json"
            dataset_path.write_text(
                json.dumps(
                    {
                        "video_id": "video_001",
                        "description": "Baseline fixture.",
                        "created_at": "2026-07-24T00:00:00+00:00",
                        "items": [
                            {
                                "question_id": "q_001",
                                "video_id": "video_001",
                                "query": "What is retrieval?",
                                "expected_outcome": "grounded_answer",
                                "expected_start_ms_min": 1000,
                                "expected_start_ms_max": 2000,
                                "expected_time_windows": [
                                    {"start_ms": 1000, "end_ms": 2500}
                                ],
                                "required_concepts": [["retrieval", "lookup"]],
                                "expected_source_types": ["semantic_chunk"],
                                "acceptable_source_types": ["semantic_chunk", "event"],
                                "notes": "Fixture.",
                                "query_type": "definition",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report_path = repo / "report.json"
            report_path.write_text('{"metrics": {}}\n', encoding="utf-8")

            result = freeze_baseline(
                repo_root=repo,
                video_id="video_001",
                qa_dataset_path=dataset_path,
                report_path=report_path,
                output_root=repo / "baselines",
                run_id="baseline_test",
            )

            manifest_path = Path(result["baseline_manifest_path"])
            self.assertTrue(manifest_path.is_file())
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], BASELINE_SCHEMA_VERSION)
            self.assertEqual(payload["qa_dataset"]["question_count"], 1)
            self.assertEqual(payload["qa_dataset"]["query_type_counts"], {"definition": 1})
            self.assertTrue(Path(payload["report"]["frozen_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
