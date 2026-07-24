import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.evaluation.qa_loader import (
    DATASET_REGISTRY,
    QADatasetLoadError,
    get_dataset,
    load_dataset,
    load_directory,
)


def dataset_payload(video_id: str = "video_001") -> dict[str, object]:
    return {
        "video_id": video_id,
        "description": "Questions for a short retrieval lecture.",
        "created_at": "2026-07-23T12:00:00+00:00",
        "items": [
            {
                "question_id": "q_001",
                "video_id": video_id,
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


class QALoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        DATASET_REGISTRY.clear()

    def tearDown(self) -> None:
        DATASET_REGISTRY.clear()

    @staticmethod
    def _write_json(directory: Path, name: str, payload: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_and_registers_a_valid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = self._write_json(Path(temporary_directory), "lecture.json", dataset_payload())
            dataset = load_dataset(path)

        self.assertEqual(dataset.video_id, "video_001")
        self.assertIs(get_dataset("video_001"), dataset)

    def test_invalid_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "broken.json"
            path.write_text("{not valid JSON", encoding="utf-8")
            with self.assertRaisesRegex(QADatasetLoadError, "invalid JSON"):
                load_dataset(path)

    def test_missing_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = dataset_payload()
            del payload["description"]
            path = self._write_json(Path(temporary_directory), "missing.json", payload)
            with self.assertRaisesRegex(QADatasetLoadError, "missing required field"):
                load_dataset(path)

    def test_load_directory_loads_json_and_ignores_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self._write_json(directory, "one.json", dataset_payload("video_001"))
            self._write_json(directory, "two.json", dataset_payload("video_002"))
            (directory / "readme.txt").write_text("ignored", encoding="utf-8")

            datasets = load_directory(directory)

        self.assertEqual([dataset.video_id for dataset in datasets], ["video_001", "video_002"])
        self.assertEqual(len(DATASET_REGISTRY), 2)

    def test_duplicate_video_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            first = self._write_json(directory, "first.json", dataset_payload("video_001"))
            second = self._write_json(directory, "second.json", dataset_payload("video_001"))
            load_dataset(first)
            with self.assertRaisesRegex(QADatasetLoadError, "already registered"):
                load_dataset(second)


if __name__ == "__main__":
    unittest.main()
