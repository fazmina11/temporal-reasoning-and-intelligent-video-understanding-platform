"""Command-line validation for a single QA evaluation dataset."""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path
from typing import Sequence

from .qa_loader import QADatasetLoadError, load_dataset
from .qa_schema import QADataset


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the QA dataset validation command."""
    parser = argparse.ArgumentParser(
        description="Validate one QA evaluation dataset JSON file."
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to the UTF-8 QA dataset JSON file.",
    )
    return parser


def format_summary(dataset: QADataset) -> str:
    """Return a stable, human-readable validation summary for a dataset."""
    question_type_counts = Counter(item.query_type for item in dataset.items)
    type_summary = "\n".join(
        f"  - {query_type}: {count}"
        for query_type, count in sorted(question_type_counts.items())
    )
    if not type_summary:
        type_summary = "  - none"
    return "\n".join(
        (
            "Dataset Summary",
            f"Video ID: {dataset.video_id}",
            f"Number of questions: {len(dataset.items)}",
            "Question type counts:",
            type_summary,
            "Validation success: yes",
        )
    )


def validate_file(path: Path) -> QADataset:
    """Load and validate one dataset, returning it when validation succeeds."""
    LOGGER.info("Validating QA dataset file: %s", path)
    return load_dataset(path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run dataset validation and return a conventional process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        dataset = validate_file(args.file)
    except QADatasetLoadError as exc:
        LOGGER.error("QA dataset validation failed: %s", exc)
        print(f"Validation success: no\nValidation errors:\n  - {exc}")
        return 1

    print(format_summary(dataset))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
