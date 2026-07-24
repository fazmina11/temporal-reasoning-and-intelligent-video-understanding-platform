"""Descriptive statistics and exports for QA evaluation datasets.

This module describes a labelled dataset only. It does not retrieve evidence,
run an evaluation, or calculate model-quality metrics.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .qa_schema import QADataset


STATISTICS_SCHEMA_VERSION = "qa-dataset-statistics-v1"


def _sorted_counts(values: list[str]) -> dict[str, int]:
    """Return deterministic count mappings suitable for persisted output."""
    return dict(sorted(Counter(values).items()))


def generate_statistics(dataset: QADataset) -> dict[str, Any]:
    """Generate descriptive counts and frequencies for a validated QA dataset.

    ``average_query_length`` is measured in Unicode characters, including
    spaces, which makes it reproducible without language-specific tokenizers.
    """
    dataset.validate()
    items = dataset.items
    question_count = len(items)
    average_query_length = (
        round(sum(len(item.query) for item in items) / question_count, 2)
        if question_count
        else 0.0
    )
    return {
        "schema_version": STATISTICS_SCHEMA_VERSION,
        "video_id": dataset.video_id,
        "question_count": question_count,
        "query_type_distribution": _sorted_counts([item.query_type for item in items]),
        "average_query_length": average_query_length,
        "required_term_frequency": _sorted_counts(
            [term for item in items for term in item.required_terms]
        ),
        "source_type_frequency": _sorted_counts(
            [source_type for item in items for source_type in item.expected_source_types]
        ),
        "outcome_distribution": _sorted_counts(
            [item.expected_outcome for item in items]
        ),
    }


def write_json(statistics: Mapping[str, Any], path: str | Path) -> Path:
    """Write statistics as UTF-8, formatted JSON and return the output path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(dict(statistics), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return output_path


def _markdown_table(title: str, values: Mapping[str, int]) -> list[str]:
    """Build a compact Markdown table for a named count mapping."""
    lines = [f"## {title}", "", "| Value | Count |", "| --- | ---: |"]
    if not values:
        lines.append("| _None_ | 0 |")
    else:
        for value, count in sorted(values.items()):
            escaped_value = str(value).replace("|", chr(92) + "|")
            lines.append(f"| {escaped_value} | {count} |")
    lines.append("")
    return lines


def write_markdown(statistics: Mapping[str, Any], path: str | Path) -> Path:
    """Write a readable Markdown summary of generated dataset statistics."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    video_id = statistics.get("video_id", "unknown")
    question_count = statistics.get("question_count", 0)
    average_query_length = statistics.get("average_query_length", 0.0)
    lines = [
        "# QA Dataset Statistics",
        "",
        f"- Video ID: `{video_id}`",
        f"- Question count: {question_count}",
        f"- Average query length (characters): {average_query_length}",
        "",
    ]
    for title, field_name in (
        ("Query Type Distribution", "query_type_distribution"),
        ("Required Term Frequency", "required_term_frequency"),
        ("Source Type Frequency", "source_type_frequency"),
        ("Outcome Distribution", "outcome_distribution"),
    ):
        values = statistics.get(field_name, {})
        if not isinstance(values, Mapping):
            raise ValueError(f"statistics field {field_name!r} must be a mapping.")
        lines.extend(_markdown_table(title, values))

    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return output_path
