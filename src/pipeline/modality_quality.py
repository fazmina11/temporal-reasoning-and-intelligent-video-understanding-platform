from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_artifacts import write_json_atomic
from .media_manifest import utc_now


def write_quality_report(
    *,
    repo_root: Path,
    video_id: str,
    modality: str,
    payload: dict[str, Any],
) -> Path:
    path = repo_root / "data" / "processed" / "reports" / f"{video_id}_{modality}_quality.json"
    report = {
        "schema_version": f"{modality}-quality-report-v1",
        "video_id": video_id,
        "modality": modality,
        "created_at": utc_now(),
        **payload,
    }
    return write_json_atomic(path, report)


def quality_summary(values: list[float], *, minimum: float) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean_quality": 0.0,
            "minimum_quality": minimum,
            "low_quality_count": 0,
            "low_quality_ratio": 0.0,
        }
    low = sum(value < minimum for value in values)
    return {
        "count": len(values),
        "mean_quality": round(sum(values) / len(values), 4),
        "minimum_quality": minimum,
        "low_quality_count": low,
        "low_quality_ratio": round(low / len(values), 4),
    }
