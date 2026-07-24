import unittest
from datetime import datetime, timezone

from src.pipeline.evaluation.qa_schema import QADataset, QAItem, QAValidationError


def valid_item(**overrides: object) -> QAItem:
    values: dict[str, object] = {
        "question_id": "q_001",
        "video_id": "video_001",
        "query": "What does the instructor define as retrieval?",
        "expected_outcome": "grounded_answer",
        "expected_start_ms_min": 10_000,
        "expected_start_ms_max": 15_000,
        "required_terms": ["retrieval"],
        "forbidden_terms": ["hallucination"],
        "expected_source_types": ["semantic_chunk", "atom"],
        "notes": "Definition appears near the beginning.",
        "query_type": "definition",
    }
    values.update(overrides)
    return QAItem(**values)  # type: ignore[arg-type]


class QASchemaTests(unittest.TestCase):
    def test_valid_schema(self) -> None:
        dataset = QADataset(
            video_id="video_001",
            description="Core concepts from the lecture.",
            created_at=datetime.now(timezone.utc),
            items=[valid_item()],
        )
        dataset.validate()

    def test_duplicate_question_ids_are_rejected(self) -> None:
        dataset = QADataset(
            video_id="video_001",
            description="Duplicate-ID test dataset.",
            created_at=datetime.now(timezone.utc),
            items=[valid_item(), valid_item(query="Repeat the question differently.")],
        )
        with self.assertRaisesRegex(QAValidationError, "Duplicate question_id"):
            dataset.validate()

    def test_invalid_timestamp_range_is_rejected(self) -> None:
        item = valid_item(expected_start_ms_min=15_000, expected_start_ms_max=10_000)
        with self.assertRaisesRegex(QAValidationError, "less than or equal"):
            item.validate()

    def test_empty_query_is_rejected(self) -> None:
        item = valid_item(query="   ")
        with self.assertRaisesRegex(QAValidationError, "query must be a non-empty string"):
            item.validate()

    def test_invalid_source_types_are_rejected(self) -> None:
        item = valid_item(expected_source_types=["database_row"])
        with self.assertRaisesRegex(QAValidationError, "Invalid expected_source_types"):
            item.validate()

    def test_invalid_expected_outcome_is_rejected(self) -> None:
        item = valid_item(expected_outcome="unknown")
        with self.assertRaisesRegex(QAValidationError, "expected_outcome must be one of"):
            item.validate()


if __name__ == "__main__":
    unittest.main()
