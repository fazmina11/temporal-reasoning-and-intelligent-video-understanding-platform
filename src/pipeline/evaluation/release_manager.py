"""Phase N calibration and regression release tooling.

The release manager runs or accepts an evaluation report, snapshots threshold
configuration, compares against a frozen baseline when available, and writes a
machine-readable release decision plus a human-readable Markdown report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baseline_manager import DEFAULT_BASELINE_ROOT
from .evaluate_ask import AskPipelineAdapter, run_evaluation_workflow
from .regression_compare import compare_reports

RELEASE_SCHEMA_VERSION = "phase-n-regression-release-v1"
DEFAULT_RELEASE_ROOT = Path("data/evaluation/releases")
DEFAULT_THRESHOLD_CONFIG = Path("config/phase_n_thresholds.yaml")

DEFAULT_RELEASE_GATES = {
    "outcome_accuracy_min": 0.90,
    "negative_abstention_min": 0.95,
    "timestamp_hit_rate_min": 0.85,
    "citation_presence_rate_min": 0.95,
    "citation_validity_rate_min": 0.98,
    "required_term_coverage_min": 0.90,
    "unsupported_claim_rate_max": 0.03,
    "fallback_rate_max": 0.35,
    "execution_failures_max": 0,
}


@dataclass(frozen=True)
class ThresholdSnapshot:
    """Loaded Phase N threshold configuration captured for release traceability."""

    path: str
    sha256: str
    raw_text: str
    values: dict[str, Any]


def run_phase_n_release(
    *,
    repo_root: Path,
    video_id: str,
    qa_dataset_path: Path | None = None,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    threshold_config_path: Path = DEFAULT_THRESHOLD_CONFIG,
    candidate_report_path: Path | None = None,
    baseline_report_path: Path | None = None,
    baseline_mode: str = "auto",
    adapter: AskPipelineAdapter | None = None,
    release_id: str | None = None,
) -> dict[str, Any]:
    """Run the N10 release workflow and persist JSON/Markdown artifacts."""
    repo_root = repo_root.resolve()
    timestamp = datetime.now(timezone.utc)
    release_id = release_id or timestamp.strftime("%Y%m%d_%H%M%S")
    release_dir = _resolve(repo_root, release_root) / video_id / release_id
    release_dir.mkdir(parents=True, exist_ok=True)

    thresholds = load_threshold_snapshot(repo_root, threshold_config_path)
    candidate_report = _load_or_run_candidate_report(
        repo_root=repo_root,
        video_id=video_id,
        qa_dataset_path=qa_dataset_path,
        release_dir=release_dir,
        candidate_report_path=candidate_report_path,
        adapter=adapter,
    )
    baseline_path = _resolve_baseline_report(
        repo_root=repo_root,
        video_id=video_id,
        baseline_report_path=baseline_report_path,
        baseline_mode=baseline_mode,
    )
    baseline_comparison = (
        compare_reports(baseline_path, candidate_report["path"]) if baseline_path else None
    )
    release_report = build_release_report(
        repo_root=repo_root,
        video_id=video_id,
        release_id=release_id,
        created_at=timestamp.isoformat(),
        candidate_report=candidate_report["data"],
        candidate_report_path=candidate_report["path"],
        threshold_snapshot=thresholds,
        baseline_report_path=baseline_path,
        baseline_comparison=baseline_comparison,
    )
    json_path, markdown_path = write_release_artifacts(release_report, release_dir)
    release_report["artifact_paths"] = {
        "release_json": str(json_path),
        "release_markdown": str(markdown_path),
    }
    json_path.write_text(
        json.dumps(release_report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return release_report


def load_threshold_snapshot(
    repo_root: Path,
    threshold_config_path: Path = DEFAULT_THRESHOLD_CONFIG,
) -> ThresholdSnapshot:
    """Read threshold config without requiring a YAML dependency."""
    path = _resolve(repo_root, threshold_config_path)
    if not path.is_file():
        raw_text = ""
        values: dict[str, Any] = {"release_gates": dict(DEFAULT_RELEASE_GATES)}
        digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        return ThresholdSnapshot(path=str(path), sha256=digest, raw_text=raw_text, values=values)
    raw_text = path.read_text(encoding="utf-8")
    return ThresholdSnapshot(
        path=str(path),
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        raw_text=raw_text,
        values=_parse_simple_yaml(raw_text),
    )


def build_release_report(
    *,
    repo_root: Path,
    video_id: str,
    release_id: str,
    created_at: str,
    candidate_report: dict[str, Any],
    candidate_report_path: Path,
    threshold_snapshot: ThresholdSnapshot,
    baseline_report_path: Path | None = None,
    baseline_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the structured release report without writing files."""
    gate_summary = assess_release_gates(
        candidate_report,
        threshold_snapshot.values.get("release_gates") or DEFAULT_RELEASE_GATES,
        repo_root=repo_root,
        video_id=video_id,
    )
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "release_id": release_id,
        "video_id": video_id,
        "created_at": created_at,
        "commit_hash": _git(["rev-parse", "HEAD"], repo_root),
        "git_status_short": _git(["status", "--short"], repo_root) or "",
        "threshold_snapshot": {
            "path": threshold_snapshot.path,
            "sha256": threshold_snapshot.sha256,
            "values": threshold_snapshot.values,
        },
        "candidate_report": {
            "path": str(candidate_report_path),
            "metadata": candidate_report.get("metadata", {}),
            "metrics": candidate_report.get("metrics", {}),
            "latency_summary": candidate_report.get("latency_summary", {}),
            "failure_count": len(candidate_report.get("failures") or []),
            "low_confidence_count": len(candidate_report.get("low_confidence_questions") or []),
        },
        "baseline_report": {"path": str(baseline_report_path)} if baseline_report_path else None,
        "baseline_comparison": baseline_comparison,
        "gate_summary": gate_summary,
        # Modality warnings are advisory and remain visible in gate_summary.
        # Only mandatory gate failures block a release.
        "release_decision": "pass" if gate_summary["failed_gate_count"] == 0 else "fail",
        "recommended_next_focus": next_focus_from_gates(gate_summary),
    }


def assess_release_gates(
    candidate_report: Mapping[str, Any],
    release_gates: Mapping[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
    video_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate candidate metrics against Phase N release gates."""
    gates = dict(DEFAULT_RELEASE_GATES)
    if release_gates:
        gates.update({key: value for key, value in release_gates.items() if value is not None})
    metrics = candidate_report.get("metrics") or {}
    metadata = candidate_report.get("metadata") or {}
    gate_records = [
        _min_gate("outcome_accuracy", metrics.get("outcome_accuracy"), gates["outcome_accuracy_min"]),
        _min_gate("negative_question_abstention_rate", metrics.get("negative_question_abstention_rate"), gates["negative_abstention_min"]),
        _min_gate("timestamp_hit_rate", metrics.get("timestamp_hit_rate"), gates["timestamp_hit_rate_min"]),
        _min_gate("citation_presence_rate", metrics.get("citation_presence_rate"), gates["citation_presence_rate_min"]),
        _min_gate("citation_validity_rate", metrics.get("citation_validity_rate"), gates["citation_validity_rate_min"]),
        _min_gate("required_term_coverage", metrics.get("required_term_coverage"), gates["required_term_coverage_min"]),
        _max_gate("unsupported_claim_rate", metrics.get("unsupported_claim_rate"), gates["unsupported_claim_rate_max"]),
        _max_gate("fallback_rate", metrics.get("fallback_rate"), gates["fallback_rate_max"]),
        _max_gate("execution_failures", metadata.get("execution_failures"), gates["execution_failures_max"]),
    ]
    modality_records = _modality_gate_records(repo_root, video_id) if repo_root and video_id else []
    all_records = gate_records + modality_records
    failed = [record for record in all_records if record["status"] == "fail"]
    warned = [record for record in all_records if record["status"] == "warn"]
    return {
        "overall_status": "fail" if failed else "warn" if warned else "pass",
        "failed_gate_count": len(failed),
        "warning_gate_count": len(warned),
        "gate_count": len(all_records),
        "metric_gates": gate_records,
        "modality_gates": modality_records,
        "failure_reasons": [record["reason"] for record in failed],
        "warning_reasons": [record["reason"] for record in warned],
    }


def next_focus_from_gates(gate_summary: Mapping[str, Any]) -> list[str]:
    """Return prioritized work items based on failed release gates."""
    reasons = " ".join(str(reason) for reason in gate_summary.get("failure_reasons") or [])
    focus: list[str] = []
    if any(key in reasons for key in ("outcome_accuracy", "negative_question_abstention_rate")):
        focus.append("expand QA labels and repair scope routing for false accept/reject cases")
    if any(key in reasons for key in ("timestamp_hit_rate", "citation")):
        focus.append("tighten primary timestamp anchoring and citation registry validation")
    if "unsupported_claim_rate" in reasons or "required_term_coverage" in reasons:
        focus.append("improve evidence packet coverage and answer claim revision")
    if any(key in reasons for key in ("ocr_quality", "speaker_quality", "audio_quality")):
        focus.append("regenerate modality artifacts and inspect low-quality OCR/speaker/audio records")
    if not focus:
        focus.append("move to a larger validation set and add a debug evidence explorer for manual QA")
    return focus


def write_release_artifacts(report: dict[str, Any], release_dir: Path) -> tuple[Path, Path]:
    """Write release JSON and Markdown reports."""
    release_dir.mkdir(parents=True, exist_ok=True)
    json_path = release_dir / "phase_n_release_report.json"
    markdown_path = release_dir / "phase_n_release_report.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(generate_release_markdown(report), encoding="utf-8", newline="\n")
    return json_path, markdown_path


def generate_release_markdown(report: Mapping[str, Any]) -> str:
    """Generate a compact Markdown release report."""
    gates = report["gate_summary"]
    candidate = report["candidate_report"]
    metrics = candidate.get("metrics") or {}
    lines = [
        f"# Phase N Release Report: {report['video_id']}",
        "",
        f"- **Release ID:** `{report['release_id']}`",
        f"- **Decision:** `{report['release_decision']}`",
        f"- **Created At:** {report['created_at']}",
        f"- **Candidate Report:** `{candidate.get('path')}`",
        f"- **Threshold SHA256:** `{report['threshold_snapshot']['sha256']}`",
        "",
        "## Metric Snapshot",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in sorted(metrics):
        value = metrics[key]
        if isinstance(value, (int, float)):
            lines.append(f"| {key} | {value:.4f} |")
    lines.extend(["", "## Release Gates", "", "| Gate | Value | Target | Status | Reason |", "| --- | ---: | ---: | --- | --- |"])
    for record in gates["metric_gates"] + gates["modality_gates"]:
        value = record.get("value")
        target = record.get("target")
        value_s = "n/a" if value is None else f"{float(value):.4f}"
        target_s = "n/a" if target is None else f"{float(target):.4f}"
        lines.append(f"| {record['name']} | {value_s} | {target_s} | {record['status']} | {record['reason']} |")
    lines.extend(["", "## Next Focus", ""])
    for item in report.get("recommended_next_focus") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _load_or_run_candidate_report(
    *,
    repo_root: Path,
    video_id: str,
    qa_dataset_path: Path | None,
    release_dir: Path,
    candidate_report_path: Path | None,
    adapter: AskPipelineAdapter | None,
) -> dict[str, Any]:
    if candidate_report_path:
        path = _resolve(repo_root, candidate_report_path)
        return {"path": path, "data": _load_json(path)}
    _, _, (json_path, _), _ = run_evaluation_workflow(
        video_id=video_id,
        dataset_path=qa_dataset_path,
        output_dir=release_dir / "evaluation_reports",
        adapter=adapter,
    )
    return {"path": json_path, "data": _load_json(json_path)}


def _resolve_baseline_report(
    *,
    repo_root: Path,
    video_id: str,
    baseline_report_path: Path | None,
    baseline_mode: str,
) -> Path | None:
    if baseline_report_path:
        return _resolve(repo_root, baseline_report_path)
    if baseline_mode == "none":
        return None
    if baseline_mode != "auto":
        raise ValueError("baseline_mode must be one of: auto, none")
    manifest = _latest_file(_resolve(repo_root, DEFAULT_BASELINE_ROOT) / video_id, "baseline_manifest.json")
    if manifest:
        payload = _load_json(manifest)
        report = payload.get("report") or {}
        frozen = report.get("frozen_path")
        if frozen and Path(frozen).is_file():
            return Path(frozen)
    return _latest_file(repo_root / "data" / "evaluation" / "reports", f"{video_id}_*.json", exclude_contains="_comparison_")


def _modality_gate_records(repo_root: Path, video_id: str) -> list[dict[str, Any]]:
    records = []
    for modality in ("ocr", "speaker", "audio"):
        path = repo_root / "data" / "processed" / "reports" / f"{video_id}_{modality}_quality.json"
        if not path.is_file():
            records.append({
                "name": f"{modality}_quality_report_exists",
                "value": 0.0,
                "target": 1.0,
                "direction": "required",
                "status": "warn",
                "reason": f"{modality}_quality report is missing",
            })
            continue
        payload = _load_json(path)
        summary = _quality_summary(payload, modality)
        low_count = int(summary.get("low_quality_count", 0) or 0)
        records.append({
            "name": f"{modality}_quality_report_exists",
            "value": 1.0,
            "target": 1.0,
            "direction": "required",
            "status": "pass",
            "reason": f"{modality}_quality report exists at {path.name}",
        })
        if low_count:
            records.append({
                "name": f"{modality}_low_quality_records",
                "value": float(low_count),
                "target": 0.0,
                "direction": "lower_is_better",
                "status": "warn",
                "reason": f"{modality}_quality has {low_count} low-quality record(s)",
            })
    return records


def _quality_summary(payload: Mapping[str, Any], modality: str) -> Mapping[str, Any]:
    if isinstance(payload.get("summary"), Mapping):
        return payload["summary"]
    keys = {
        "ocr": ("track_quality", "record_quality"),
        "speaker": ("turn_quality", "segment_quality"),
        "audio": ("event_quality",),
    }.get(modality, ())
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _min_gate(name: str, value: Any, target: Any) -> dict[str, Any]:
    number = _number(value)
    target_num = _number(target)
    passed = number is not None and target_num is not None and number >= target_num
    return {
        "name": name,
        "value": number,
        "target": target_num,
        "direction": "higher_is_better",
        "status": "pass" if passed else "fail",
        "reason": f"{name}={number} must be >= {target_num}",
    }


def _max_gate(name: str, value: Any, target: Any) -> dict[str, Any]:
    number = _number(value)
    target_num = _number(target)
    passed = number is not None and target_num is not None and number <= target_num
    return {
        "name": name,
        "value": number,
        "target": target_num,
        "direction": "lower_is_better",
        "status": "pass" if passed else "fail",
        "reason": f"{name}={number} must be <= {target_num}",
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _parse_simple_yaml(raw_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    for raw_line in raw_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            current_section = {}
            result[key] = current_section
            continue
        if not line.startswith(" "):
            key, _, value = line.partition(":")
            result[key.strip()] = _yaml_scalar(value.strip())
            current_section = None
            continue
        if current_section is not None and ":" in line:
            key, _, value = line.strip().partition(":")
            current_section[key.strip()] = _yaml_scalar(value.strip())
    return result


def _yaml_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", ""}:
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value.strip("'\"")


def _latest_file(root: Path, pattern: str, *, exclude_contains: str | None = None) -> Path | None:
    if not root.exists():
        return None
    paths = [p for p in root.rglob(pattern) if p.is_file()]
    if exclude_contains:
        paths = [p for p in paths if exclude_contains not in p.name]
    return max(paths, key=lambda p: p.stat().st_mtime, default=None)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase N calibration/regression release.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--qa-dataset", default=None)
    parser.add_argument("--candidate-report", default=None)
    parser.add_argument("--baseline-report", default=None)
    parser.add_argument("--baseline-mode", choices=["auto", "none"], default="auto")
    parser.add_argument("--release-root", default=str(DEFAULT_RELEASE_ROOT))
    parser.add_argument("--threshold-config", default=str(DEFAULT_THRESHOLD_CONFIG))
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--release-id", default=None)
    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_arg_parser()
    parsed = parser.parse_args(args)
    try:
        report = run_phase_n_release(
            repo_root=Path(parsed.repo_root),
            video_id=parsed.video_id,
            qa_dataset_path=Path(parsed.qa_dataset) if parsed.qa_dataset else None,
            release_root=Path(parsed.release_root),
            threshold_config_path=Path(parsed.threshold_config),
            candidate_report_path=Path(parsed.candidate_report) if parsed.candidate_report else None,
            baseline_report_path=Path(parsed.baseline_report) if parsed.baseline_report else None,
            baseline_mode=parsed.baseline_mode,
            release_id=parsed.release_id,
        )
    except Exception as exc:
        print(f"Phase N release failed: {exc}")
        return 1
    artifacts = report.get("artifact_paths") or {}
    print(f"Phase N release decision: {report['release_decision']}")
    print(f"Release JSON: {artifacts.get('release_json')}")
    print(f"Release Markdown: {artifacts.get('release_markdown')}")
    return 0 if report["release_decision"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
