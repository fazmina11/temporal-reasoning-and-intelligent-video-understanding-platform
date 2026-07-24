import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.evaluation.dataset_statistics import (
    STATISTICS_SCHEMA_VERSION,
    generate_statistics,
    write_json,
    write_markdown,
)
from src.pipeline.evaluation.qa_schema import QADataset, QAItem


def make_dataset() -> QADataset:
    return QADataset(
        video_id="video_001",
        description="Statistics test dataset.",
        created_at=datetime.now(timezone.utc),
        items=[
            QAItem(
                question_id="q_001", video_id="video_001", query="What is RAG?",
                expected_outcome="grounded_answer", expected_start_ms_min=1000,
                expected_start_ms_max=3000, required_terms=["RAG", "retrieval"],
                forbidden_terms=[], expected_source_types=["semantic_chunk", "atom"],
                notes="Definition.", query_type="definition",
            ),
            QAItem(
                question_id="q_002", video_id="video_001", query="Explain retrieval.",
                expected_outcome="grounded_answer", expected_start_ms_min=4000,
                expected_start_ms_max=7000, required_terms=["retrieval"],
                forbidden_terms=[], expected_source_types=["semantic_chunk"],
                notes="Concept.", query_type="concept",
            ),
            QAItem(
                question_id="q_003", video_id="video_001", query="What is the weather?",
                expected_outcome="unrelated_to_video", required_terms=["weather"],
                forbidden_terms=[], expected_source_types=[], notes="Negative question.",
                query_type="unrelated_or_general",
            ),
        ],
    )


class DatasetStatisticsTests(unittest.TestCase):
    def test_generate_statistics_returns_requested_measurements(self) -> None:
        statistics = generate_statistics(make_dataset())

        self.assertEqual(statistics["schema_version"], STATISTICS_SCHEMA_VERSION)
        self.assertEqual(statistics["video_id"], "video_001")
        self.assertEqual(statistics["question_count"], 3)
        self.assertEqual(statistics["query_type_distribution"], {
            "concept": 1, "definition": 1, "unrelated_or_general": 1,
        })
        self.assertEqual(statistics["average_query_length"], 16.67)
        self.assertEqual(statistics["required_term_frequency"], {
            "RAG": 1, "retrieval": 2, "weather": 1,
        })
        self.assertEqual(statistics["source_type_frequency"], {
            "atom": 1, "semantic_chunk": 2,
        })
        self.assertEqual(statistics["outcome_distribution"], {
            "grounded_answer": 2, "unrelated_to_video": 1,
        })

    def test_write_json_exports_statistics(self) -> None:
        statistics = generate_statistics(make_dataset())
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = write_json(statistics, Path(temporary_directory) / "nested" / "stats.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded, statistics)

    def test_write_markdown_exports_statistics(self) -> None:
        statistics = generate_statistics(make_dataset())
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = write_markdown(statistics, Path(temporary_directory) / "stats.md")
            content = path.read_text(encoding="utf-8")

        self.assertIn("# QA Dataset Statistics", content)
        self.assertIn("Question count: 3", content)
        self.assertIn("## Required Term Frequency", content)
        self.assertIn("| retrieval | 2 |", content)
        self.assertIn("## Outcome Distribution", content)


if __name__ == "__main__":
    unittest.main()
