"""End-to-end pytest coverage for the QA evaluation dataset package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.evaluation.dataset_statistics import (
    STATISTICS_SCHEMA_VERSION,
    generate_statistics,
    write_json,
    write_markdown,
)
from src.pipeline.evaluation.qa_loader import DATASET_REGISTRY, get_dataset, load_dataset


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATASET_PATH = (
    REPOSITORY_ROOT / "data" / "evaluation" / "qa_sets" / "mcp_vs_api_qa.json"
)


@pytest.fixture(autouse=True)
def clear_dataset_registry() -> None:
    """Keep the loader's process-local registry isolated between tests."""
    DATASET_REGISTRY.clear()
    yield
    DATASET_REGISTRY.clear()


def test_sample_dataset_complete_statistics_workflow(tmp_path: Path) -> None:
    """Load, validate, summarize, and export the shipped sample QA dataset."""
    dataset = load_dataset(SAMPLE_DATASET_PATH)

    # Explicitly exercise schema validation after the loader's immediate validation.
    dataset.validate()
    assert dataset.video_id == "mcp_vs_api"
    assert len(dataset.items) == 60
    assert get_dataset(dataset.video_id) is dataset

    statistics = generate_statistics(dataset)
    assert statistics["schema_version"] == STATISTICS_SCHEMA_VERSION
    assert statistics["video_id"] == "mcp_vs_api"
    assert statistics["question_count"] == 60
    assert statistics["query_type_distribution"] == {
        "ambiguous_query": 10,
        "concept": 10,
        "definition": 10,
        "exact_timestamp": 10,
        "unrelated_or_general": 10,
        "visual_memory": 10,
    }
    assert statistics["outcome_distribution"] == {
        "clarification_required": 10,
        "grounded_answer": 40,
        "unrelated_to_video": 10,
    }

    json_path = write_json(statistics, tmp_path / "exports" / "statistics.json")
    markdown_path = write_markdown(statistics, tmp_path / "exports" / "statistics.md")

    assert json.loads(json_path.read_text(encoding="utf-8")) == statistics
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# QA Dataset Statistics" in markdown
    assert "Question count: 60" in markdown
    assert "## Query Type Distribution" in markdown
    assert "| definition | 10 |" in markdown
    assert "## Outcome Distribution" in markdown
