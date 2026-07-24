"""JSON loading utilities for QA evaluation datasets.

The loader owns a process-local registry only; persistence and evaluation are
deliberately outside this module's scope.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .qa_schema import QADataset, QAItem, QAValidationError


LOGGER = logging.getLogger(__name__)

# The registry is intentionally module-local and keyed by the canonical dataset video ID.
DATASET_REGISTRY: dict[str, QADataset] = {}


class QADatasetLoadError(ValueError):
    """Raised when a QA dataset file cannot be parsed, built, or registered."""


def _parse_created_at(value: object, path: Path) -> datetime:
    """Parse the dataset's ISO-8601 creation timestamp."""
    if not isinstance(value, str) or not value.strip():
        raise QADatasetLoadError(f"Dataset {path} is missing a non-empty 'created_at' value.")
    try:
        # Python's ISO parser accepts explicit offsets; normalize the common UTC suffix.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QADatasetLoadError(
            f"Dataset {path} has an invalid ISO-8601 'created_at' value: {value!r}."
        ) from exc


def _build_dataset(payload: object, path: Path) -> QADataset:
    """Convert a decoded JSON object into a validated :class:`QADataset`."""
    if not isinstance(payload, Mapping):
        raise QADatasetLoadError(f"Dataset {path} must contain a JSON object at its root.")

    required_fields = {"video_id", "description", "created_at", "items"}
    missing_fields = sorted(required_fields - payload.keys())
    if missing_fields:
        raise QADatasetLoadError(f"Dataset {path} is missing required field(s): {missing_fields}.")

    raw_items = payload["items"]
    if not isinstance(raw_items, list):
        raise QADatasetLoadError(f"Dataset {path} field 'items' must be a JSON array.")

    items: list[QAItem] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise QADatasetLoadError(f"Dataset {path} items[{index}] must be a JSON object.")
        try:
            items.append(QAItem(**dict(raw_item)))
        except TypeError as exc:
            raise QADatasetLoadError(
                f"Dataset {path} items[{index}] has missing or unsupported field(s): {exc}."
            ) from exc

    try:
        dataset = QADataset(
            video_id=payload["video_id"],
            description=payload["description"],
            created_at=_parse_created_at(payload["created_at"], path),
            items=items,
        )
        dataset.validate()
    except QAValidationError as exc:
        raise QADatasetLoadError(f"Dataset {path} failed schema validation: {exc}") from exc
    except TypeError as exc:
        raise QADatasetLoadError(f"Dataset {path} has invalid field values: {exc}") from exc
    return dataset


def load_dataset(path: str | Path) -> QADataset:
    """Load, validate, and register one UTF-8 JSON QA dataset file.

    A duplicate ``video_id`` is rejected to prevent silently replacing an
    already-loaded dataset.
    """
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise QADatasetLoadError(f"QA dataset file does not exist or is not a file: {dataset_path}")
    if dataset_path.suffix.lower() != ".json":
        raise QADatasetLoadError(f"QA dataset file must use a .json extension: {dataset_path}")

    try:
        with dataset_path.open("r", encoding="utf-8") as handle:
            payload: Any = json.load(handle)
    except UnicodeDecodeError as exc:
        raise QADatasetLoadError(f"QA dataset file is not valid UTF-8: {dataset_path}") from exc
    except json.JSONDecodeError as exc:
        raise QADatasetLoadError(
            f"QA dataset file contains invalid JSON at line {exc.lineno}, column {exc.colno}: "
            f"{dataset_path}"
        ) from exc
    except OSError as exc:
        raise QADatasetLoadError(f"Unable to read QA dataset file {dataset_path}: {exc}") from exc

    dataset = _build_dataset(payload, dataset_path)
    if dataset.video_id in DATASET_REGISTRY:
        raise QADatasetLoadError(
            f"A QA dataset for video_id {dataset.video_id!r} is already registered."
        )
    DATASET_REGISTRY[dataset.video_id] = dataset
    LOGGER.info("Loaded QA dataset for video_id=%s from %s", dataset.video_id, dataset_path)
    return dataset


def load_directory(directory: str | Path) -> list[QADataset]:
    """Load every JSON dataset directly contained in ``directory``.

    Non-JSON files are ignored. Files are processed in lexical order for
    deterministic diagnostics and registry contents.
    """
    directory_path = Path(directory)
    if not directory_path.is_dir():
        raise QADatasetLoadError(f"QA dataset directory does not exist or is not a directory: {directory_path}")

    datasets: list[QADataset] = []
    for path in sorted(directory_path.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        datasets.append(load_dataset(path))
    LOGGER.info("Loaded %d QA dataset(s) from %s", len(datasets), directory_path)
    return datasets


def get_dataset(video_id: str) -> QADataset:
    """Return a previously loaded dataset for ``video_id``."""
    try:
        return DATASET_REGISTRY[video_id]
    except KeyError as exc:
        raise KeyError(f"No QA dataset is registered for video_id {video_id!r}.") from exc
