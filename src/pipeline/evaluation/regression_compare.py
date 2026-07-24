"""Regression comparison utility for evaluation reports.

Compares two evaluation run reports (baseline vs candidate) and generates
metric differences, improved/regressed metrics, new/resolved failures, and latency deltas
in both JSON and Markdown formats.

Does NOT rerun pipeline evaluations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evaluate_ask import EvaluationRun
from .report_writer import DEFAULT_REPORTS_DIR, generate_json_report

LOWER_IS_BETTER_METRICS = {
    "unsupported_claim_rate",
    "fallback_rate",
    "average_latency_ms",
}

PERCENTAGE_METRICS = {
    "outcome_accuracy",
    "timestamp_hit_rate",
    "citation_presence_rate",
    "citation_validity_rate",
    "required_term_coverage",
    "unsupported_claim_rate",
    "negative_question_abstention_rate",
    "fallback_rate",
}


def _load_report_dict(
    report_input: dict[str, Any] | str | Path | EvaluationRun,
) -> dict[str, Any]:
    """Normalize file path, EvaluationRun, or dictionary into a report dictionary."""
    if isinstance(report_input, EvaluationRun):
        return generate_json_report(report_input)
    if isinstance(report_input, (str, Path)):
        path = Path(report_input)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    if isinstance(report_input, Mapping):
        return dict(report_input)
    raise TypeError(f"Unsupported report input type: {type(report_input)}")


def compare_reports(
    baseline: dict[str, Any] | str | Path | EvaluationRun,
    candidate: dict[str, Any] | str | Path | EvaluationRun,
) -> dict[str, Any]:
    """Compare two evaluation report dictionaries or files without running evaluations."""
    b_report = _load_report_dict(baseline)
    c_report = _load_report_dict(candidate)

    b_meta = b_report.get("metadata", {})
    c_meta = c_report.get("metadata", {})

    b_video = b_meta.get("video_id", "unknown")
    c_video = c_meta.get("video_id", "unknown")
    video_id = b_video if b_video == c_video else f"{b_video}_vs_{c_video}"

    metadata = {
        "video_id": video_id,
        "baseline_video_id": b_video,
        "candidate_video_id": c_video,
        "baseline_timestamp": b_meta.get("run_timestamp"),
        "candidate_timestamp": c_meta.get("run_timestamp"),
        "baseline_runner_version": b_meta.get("runner_version"),
        "candidate_runner_version": c_meta.get("runner_version"),
        "baseline_total_questions": b_meta.get("total_questions", 0),
        "candidate_total_questions": c_meta.get("total_questions", 0),
        "comparison_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    b_metrics = b_report.get("metrics", {})
    c_metrics = c_report.get("metrics", {})

    metric_differences: dict[str, dict[str, Any]] = {}
    improved_metrics: list[dict[str, Any]] = []
    regressed_metrics: list[dict[str, Any]] = []
    unchanged_metrics: list[dict[str, Any]] = []

    all_metric_keys = sorted(set(b_metrics.keys()) | set(c_metrics.keys()))

    for key in all_metric_keys:
        b_val = float(b_metrics.get(key, 0.0))
        c_val = float(c_metrics.get(key, 0.0))
        delta = round(c_val - b_val, 4)

        lower_is_better = key in LOWER_IS_BETTER_METRICS
        direction = "lower_is_better" if lower_is_better else "higher_is_better"

        if abs(delta) < 1e-4:
            status = "unchanged"
        elif lower_is_better:
            status = "improved" if delta < 0 else "regressed"
        else:
            status = "improved" if delta > 0 else "regressed"

        diff_record = {
            "metric": key,
            "baseline": b_val,
            "candidate": c_val,
            "delta": delta,
            "direction": direction,
            "status": status,
        }

        metric_differences[key] = diff_record

        if status == "improved":
            improved_metrics.append(diff_record)
        elif status == "regressed":
            regressed_metrics.append(diff_record)
        else:
            unchanged_metrics.append(diff_record)

    # Latency Delta
    b_latency = b_report.get("latency_summary", {})
    c_latency = c_report.get("latency_summary", {})
    latency_keys = ["average_ms", "min_ms", "max_ms", "p50_ms", "p90_ms", "p95_ms"]
    latency_delta: dict[str, dict[str, Any]] = {}

    for l_key in latency_keys:
        b_lat = float(b_latency.get(l_key, 0.0))
        c_lat = float(c_latency.get(l_key, 0.0))
        l_delta = round(c_lat - b_lat, 3)

        if abs(l_delta) < 1e-3:
            l_status = "unchanged"
        else:
            l_status = "improved" if l_delta < 0 else "regressed"

        latency_delta[l_key] = {
            "baseline": b_lat,
            "candidate": c_lat,
            "delta": l_delta,
            "status": l_status,
        }

    # Failures & Question tracking
    b_failures = {f["question_id"]: f for f in b_report.get("failures", [])}
    c_failures = {f["question_id"]: f for f in c_report.get("failures", [])}

    b_questions = {q["question_id"]: q for q in b_report.get("per_question_summary", [])}
    c_questions = {q["question_id"]: q for q in c_report.get("per_question_summary", [])}

    new_failures: list[dict[str, Any]] = []
    for q_id, c_fail in c_failures.items():
        if q_id not in b_failures:
            b_q = b_questions.get(q_id, {})
            new_failures.append({
                "question_id": q_id,
                "query": c_fail.get("query"),
                "expected_outcome": c_fail.get("expected_outcome"),
                "baseline_predicted": b_q.get("predicted_outcome"),
                "candidate_predicted": c_fail.get("predicted_outcome"),
                "baseline_success": b_q.get("success", True),
                "candidate_success": c_fail.get("success", False),
                "error_message": c_fail.get("error_message"),
            })

    resolved_failures: list[dict[str, Any]] = []
    for q_id, b_fail in b_failures.items():
        if q_id not in c_failures:
            c_q = c_questions.get(q_id, {})
            resolved_failures.append({
                "question_id": q_id,
                "query": b_fail.get("query"),
                "expected_outcome": b_fail.get("expected_outcome"),
                "baseline_predicted": b_fail.get("predicted_outcome"),
                "candidate_predicted": c_q.get("predicted_outcome"),
                "baseline_error_message": b_fail.get("error_message"),
                "candidate_success": c_q.get("success", True),
            })

    return {
        "metadata": metadata,
        "metric_differences": metric_differences,
        "improved_metrics": improved_metrics,
        "regressed_metrics": regressed_metrics,
        "unchanged_metrics": unchanged_metrics,
        "latency_delta": latency_delta,
        "new_failures": new_failures,
        "resolved_failures": resolved_failures,
    }


def generate_markdown_comparison(comparison_data: dict[str, Any]) -> str:
    """Generate Markdown formatted comparison report from comparison dict."""
    meta = comparison_data["metadata"]
    metrics_diff = comparison_data["metric_differences"]
    improved = comparison_data["improved_metrics"]
    regressed = comparison_data["regressed_metrics"]
    latency = comparison_data["latency_delta"]
    new_fails = comparison_data["new_failures"]
    resolved_fails = comparison_data["resolved_failures"]

    video_id = meta["video_id"]
    lines: list[str] = [
        f"# Evaluation Regression Comparison Report: {video_id}",
        "",
        "## Metadata",
        "",
        f"- **Video ID:** `{video_id}`",
        f"- **Baseline Run:** Timestamp `{meta.get('baseline_timestamp')}` (version `{meta.get('baseline_runner_version')}`)",
        f"- **Candidate Run:** Timestamp `{meta.get('candidate_timestamp')}` (version `{meta.get('candidate_runner_version')}`)",
        f"- **Total Questions:** Baseline: {meta.get('baseline_total_questions')} | Candidate: {meta.get('candidate_total_questions')}",
        "",
        "## Metric Comparison Summary",
        "",
        "| Metric | Baseline | Candidate | Delta | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]

    for key, item in metrics_diff.items():
        b_val = item["baseline"]
        c_val = item["candidate"]
        delta = item["delta"]
        status = item["status"].upper()

        if key in PERCENTAGE_METRICS:
            b_str = f"{b_val * 100:.2f}%"
            c_str = f"{c_val * 100:.2f}%"
            d_str = f"{delta * 100:+.2f}%"
        elif key == "average_latency_ms":
            b_str = f"{b_val:.2f} ms"
            c_str = f"{c_val:.2f} ms"
            d_str = f"{delta:+.2f} ms"
        else:
            b_str = f"{b_val:.4f}"
            c_str = f"{c_val:.4f}"
            d_str = f"{delta:+.4f}"

        key_title = key.replace("_", " ").title()
        lines.append(f"| {key_title} | {b_str} | {c_str} | {d_str} | **{status}** |")

    lines.extend(["", "## Improved Metrics", ""])
    if not improved:
        lines.extend(["_No improved metrics._", ""])
    else:
        for item in improved:
            key_title = item["metric"].replace("_", " ").title()
            b_val, c_val, delta = item["baseline"], item["candidate"], item["delta"]
            if item["metric"] in PERCENTAGE_METRICS:
                lines.append(f"- **{key_title}:** {b_val * 100:.2f}% -> {c_val * 100:.2f}% ({delta * 100:+.2f}%)")
            else:
                lines.append(f"- **{key_title}:** {b_val:.4f} -> {c_val:.4f} ({delta:+.4f})")
        lines.append("")

    lines.extend(["## Regressed Metrics", ""])
    if not regressed:
        lines.extend(["_No regressed metrics._", ""])
    else:
        for item in regressed:
            key_title = item["metric"].replace("_", " ").title()
            b_val, c_val, delta = item["baseline"], item["candidate"], item["delta"]
            if item["metric"] in PERCENTAGE_METRICS:
                lines.append(f"- **{key_title}:** {b_val * 100:.2f}% -> {c_val * 100:.2f}% ({delta * 100:+.2f}%)")
            else:
                lines.append(f"- **{key_title}:** {b_val:.4f} -> {c_val:.4f} ({delta:+.4f})")
        lines.append("")

    lines.extend([
        "## Latency Delta",
        "",
        "| Latency Metric | Baseline (ms) | Candidate (ms) | Delta (ms) | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ])
    for l_key, item in latency.items():
        l_title = l_key.replace("_", " ").title()
        b_val, c_val, l_delta, l_status = item["baseline"], item["candidate"], item["delta"], item["status"].upper()
        lines.append(f"| {l_title} | {b_val:.2f} ms | {c_val:.2f} ms | {l_delta:+.2f} ms | **{l_status}** |")
    lines.append("")

    lines.extend(["## New Failures (Regressions)", ""])
    if not new_fails:
        lines.extend(["_No new failures recorded._", ""])
    else:
        lines.extend([
            "| Question ID | Query | Expected | Baseline Predicted | Candidate Predicted | Error / Details |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for f in new_fails:
            q_id = f["question_id"]
            query_esc = str(f.get("query") or "").replace("|", "\\|")
            exp_esc = str(f.get("expected_outcome") or "").replace("|", "\\|")
            b_pred = str(f.get("baseline_predicted") or "None").replace("|", "\\|")
            c_pred = str(f.get("candidate_predicted") or "None").replace("|", "\\|")
            err_esc = str(f.get("error_message") or "Outcome mismatch").replace("|", "\\|")
            lines.append(f"| {q_id} | {query_esc} | {exp_esc} | {b_pred} | {c_pred} | {err_esc} |")
        lines.append("")

    lines.extend(["## Resolved Failures (Improvements)", ""])
    if not resolved_fails:
        lines.extend(["_No resolved failures recorded._", ""])
    else:
        lines.extend([
            "| Question ID | Query | Expected | Baseline Predicted | Candidate Predicted | Details |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for f in resolved_fails:
            q_id = f["question_id"]
            query_esc = str(f.get("query") or "").replace("|", "\\|")
            exp_esc = str(f.get("expected_outcome") or "").replace("|", "\\|")
            b_pred = str(f.get("baseline_predicted") or "None").replace("|", "\\|")
            c_pred = str(f.get("candidate_predicted") or "None").replace("|", "\\|")
            lines.append(f"| {q_id} | {query_esc} | {exp_esc} | {b_pred} | {c_pred} | Resolved |")
        lines.append("")

    return "\n".join(lines)


def compare_and_write_reports(
    baseline: dict[str, Any] | str | Path | EvaluationRun,
    candidate: dict[str, Any] | str | Path | EvaluationRun,
    output_dir: str | Path = DEFAULT_REPORTS_DIR,
    comparison_id: str | None = None,
) -> tuple[Path, Path]:
    """Compare two evaluation runs and save JSON and Markdown comparison reports.

    Returns tuple of (json_path, markdown_path).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    comparison_data = compare_reports(baseline, candidate)
    video_id = comparison_data["metadata"]["video_id"]

    if not comparison_id:
        timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        comparison_id = f"comparison_{timestamp_slug}"

    json_path = out_path / f"{video_id}_{comparison_id}.json"
    md_path = out_path / f"{video_id}_{comparison_id}.md"

    markdown_content = generate_markdown_comparison(comparison_data)

    with json_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(comparison_data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    with md_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(markdown_content)

    return json_path, md_path
