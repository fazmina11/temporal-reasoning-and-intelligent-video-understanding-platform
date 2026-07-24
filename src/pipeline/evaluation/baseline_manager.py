"""Freeze evaluation baseline metadata before behavior-changing work."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .qa_loader import load_dataset

BASELINE_SCHEMA_VERSION = "phase-n-baseline-freeze-v1"
DEFAULT_BASELINE_ROOT = Path("data/evaluation/baselines")


def freeze_baseline(
    *,
    repo_root: Path,
    video_id: str,
    qa_dataset_path: Path,
    report_path: Path | None = None,
    output_root: Path = DEFAULT_BASELINE_ROOT,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Create a baseline snapshot with enough metadata for regression comparison."""
    repo_root = repo_root.resolve()
    dataset = load_dataset(_resolve(repo_root, qa_dataset_path))
    if dataset.video_id != video_id:
        raise ValueError(
            f"QA dataset video_id {dataset.video_id!r} does not match requested {video_id!r}."
        )

    timestamp = datetime.now(timezone.utc)
    baseline_id = run_id or timestamp.strftime("%Y%m%d_%H%M%S")
    output_dir = _resolve(repo_root, output_root) / video_id / baseline_id
    output_dir.mkdir(parents=True, exist_ok=True)

    report = _copy_json_or_markdown(
        source=_resolve(repo_root, report_path) if report_path else None,
        destination_dir=output_dir,
    )
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_id": baseline_id,
        "video_id": video_id,
        "created_at": timestamp.isoformat(),
        "commit_hash": _git_commit(repo_root),
        "git_status_short": _git_status(repo_root),
        "qa_dataset": {
            "path": str(_resolve(repo_root, qa_dataset_path)),
            "question_count": len(dataset.items),
            "query_type_counts": _counts(item.query_type for item in dataset.items),
            "outcome_counts": _counts(item.expected_outcome for item in dataset.items),
        },
        "report": report,
        "configuration": {
            "threshold_config_path": str(repo_root / "config" / "phase_n_thresholds.yaml"),
            "evaluation_runner": "src.pipeline.evaluation.evaluate_ask",
        },
        "known_failure_list": [],
    }
    manifest_path = output_dir / "baseline_manifest.json"
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    payload["baseline_manifest_path"] = str(manifest_path)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze a Phase N evaluation baseline snapshot.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--qa-dataset", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_BASELINE_ROOT))
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--run-id", default=None)
    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_arg_parser()
    parsed = parser.parse_args(args)
    try:
        result = freeze_baseline(
            repo_root=Path(parsed.repo_root),
            video_id=parsed.video_id,
            qa_dataset_path=Path(parsed.qa_dataset),
            report_path=Path(parsed.report) if parsed.report else None,
            output_root=Path(parsed.output_root),
            run_id=parsed.run_id,
        )
    except Exception as exc:
        print(f"Baseline freeze failed: {exc}")
        return 1
    print(f"Baseline frozen: {result['baseline_manifest_path']}")
    return 0


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _git_commit(repo_root: Path) -> str | None:
    return _git(["rev-parse", "HEAD"], repo_root)


def _git_status(repo_root: Path) -> str:
    return _git(["status", "--short"], repo_root) or ""


def _git(args: list[str], repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
    except Exception:
        return None
    return completed.stdout.strip()


def _copy_json_or_markdown(source: Path | None, destination_dir: Path) -> dict[str, Any] | None:
    if source is None:
        return None
    if not source.is_file():
        raise FileNotFoundError(f"Evaluation report does not exist: {source}")
    target = destination_dir / source.name
    target.write_bytes(source.read_bytes())
    return {"source_path": str(source), "frozen_path": str(target), "bytes": target.stat().st_size}


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
