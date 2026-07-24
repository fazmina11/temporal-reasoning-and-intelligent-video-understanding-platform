import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from src.pipeline.evaluation.qa_loader import DATASET_REGISTRY
from src.pipeline.evaluation.validate_dataset import format_summary, main


def dataset_payload() -> dict[str, object]:
    return {
        "video_id": "video_001",
        "description": "Validation command test dataset.",
        "created_at": "2026-07-23T12:00:00+00:00",
        "items": [
            {
                "question_id": "q_001",
                "video_id": "video_001",
                "query": "What is retrieval?",
                "expected_outcome": "grounded_answer",
                "expected_start_ms_min": 1000,
                "expected_start_ms_max": 4000,
                "required_terms": ["retrieval"],
                "forbidden_terms": [],
                "expected_source_types": ["semantic_chunk"],
                "notes": "Definition segment.",
                "query_type": "definition",
            }
        ],
    }


class ValidateDatasetCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        DATASET_REGISTRY.clear()

    def tearDown(self) -> None:
        DATASET_REGISTRY.clear()

    def test_main_prints_summary_for_valid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "valid.json"
            path.write_text(json.dumps(dataset_payload()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--file", str(path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("Dataset Summary", output.getvalue())
        self.assertIn("Video ID: video_001", output.getvalue())
        self.assertIn("Number of questions: 1", output.getvalue())
        self.assertIn("definition: 1", output.getvalue())
        self.assertIn("Validation success: yes", output.getvalue())

    def test_main_prints_detailed_error_for_invalid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.json"
            path.write_text("{not valid json", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--file", str(path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Validation success: no", output.getvalue())
        self.assertIn("invalid JSON", output.getvalue())

    def test_summary_reports_all_question_type_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "valid.json"
            payload = dataset_payload()
            item = payload["items"][0]
            assert isinstance(item, dict)
            second_item = dict(item)
            second_item["question_id"] = "q_002"
            second_item["query"] = "Explain retrieval in detail."
            second_item["query_type"] = "concept"
            payload["items"] = [item, second_item]
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--file", str(path)]), 0)

        self.assertIn("concept: 1", output.getvalue())
        self.assertIn("definition: 1", output.getvalue())


if __name__ == "__main__":
    unittest.main()
