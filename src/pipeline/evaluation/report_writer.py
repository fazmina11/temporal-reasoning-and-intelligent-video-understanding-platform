"""Report writer for QA evaluation execution runs and metrics.

Generates structured JSON and Markdown summary reports from evaluation runs
and writes them to disk under `data/evaluation/reports/`.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .evaluate_ask import EvaluationResult, EvaluationRun
from .metrics import EvaluationMetrics, calculate_metrics, is_valid_citation

DEFAULT_REPORTS_DIR = Path("data/evaluation/reports")
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5


def _outcome(value: str | None) -> str | None:
    """Normalize outcome strings consistent with evaluation metrics."""
    return "clarification_required" if value == "ambiguous_query" else value


def _grounded(result: EvaluationResult) -> bool:
    return _outcome(result.expected_outcome) == "grounded_answer"


def _answer(result: EvaluationResult) -> str:
    if isinstance(result.raw_response, Mapping):
        ans = result.raw_response.get("answer", "")
        return ans if isinstance(ans, str) else ""
    return ""


def calculate_latency_summary(results: list[EvaluationResult]) -> dict[str, float | int]:
    """Calculate summary statistics for question latencies in milliseconds."""
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    if not latencies:
        return {
            "count": 0,
            "average_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p95_ms": 0.0,
        }

    sorted_l = sorted(latencies)
    count = len(sorted_l)
    avg = round(sum(sorted_l) / count, 3)
    min_v = round(sorted_l[0], 3)
    max_v = round(sorted_l[-1], 3)

    p50 = _percentile(sorted_l, 50.0)
    p90 = _percentile(sorted_l, 90.0)
    p95 = _percentile(sorted_l, 95.0)

    return {
        "count": count,
        "average_ms": avg,
        "min_ms": min_v,
        "max_ms": max_v,
        "p50_ms": p50,
        "p90_ms": p90,
        "p95_ms": p95,
    }


def _percentile(values: list[float], percentile: float) -> float:
    """Compute percentile using linear interpolation on sorted float values."""
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    k = (len(values) - 1) * (percentile / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(values):
        return round(values[-1], 3)
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return round(d0 + d1, 3)


def detect_error_categories(result: EvaluationResult) -> list[str]:
    """Categorize execution errors, outcome mismatches, and evidence quality issues."""
    categories: list[str] = []
    if not result.success or result.error_message:
        err_msg = result.error_message or "Execution Error"
        exc_type = err_msg.split(":")[0].strip()
        categories.append(f"Execution Error ({exc_type})")
        return categories

    expected_norm = _outcome(result.expected_outcome)
    predicted_norm = _outcome(result.predicted_outcome)

    if expected_norm != predicted_norm:
        exp_str = result.expected_outcome or "None"
        pred_str = result.predicted_outcome or "None"
        categories.append(f"Outcome Mismatch (expected: {exp_str}, got: {pred_str})")
        return categories

    # Detailed quality checks for matching outcomes
    if _grounded(result):
        ans_text = _answer(result).casefold()
        if result.required_terms and any(t.casefold() not in ans_text for t in result.required_terms):
            categories.append("Missing Required Terms")

        forbidden = any(t.casefold() in ans_text for t in result.forbidden_terms)
        has_valid_citation = any(is_valid_citation(c, result) for c in result.citations)
        if forbidden or not has_valid_citation:
            categories.append("Unsupported Claim")

    return categories


def summarize_top_error_categories(results: list[EvaluationResult]) -> list[dict[str, Any]]:
    """Group and count top error categories across evaluation results."""
    counter: Counter[str] = Counter()
    for result in results:
        for category in detect_error_categories(result):
            counter[category] += 1

    sorted_items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [{"category": cat, "count": count} for cat, count in sorted_items]


def find_low_confidence_questions(
    results: list[EvaluationResult],
    threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Filter questions with recorded confidence strictly below threshold."""
    low_conf: list[dict[str, Any]] = []
    for r in results:
        if r.confidence is not None and r.confidence < threshold:
            low_conf.append({
                "question_id": r.question_id,
                "query": r.query,
                "confidence": r.confidence,
                "expected_outcome": r.expected_outcome,
                "predicted_outcome": r.predicted_outcome,
                "success": r.success,
            })
    return low_conf


def find_failures(results: list[EvaluationResult]) -> list[dict[str, Any]]:
    """Extract all execution failures and outcome mismatch results."""
    failures: list[dict[str, Any]] = []
    for r in results:
        is_exec_failure = not r.success or r.error_message is not None
        is_outcome_mismatch = _outcome(r.expected_outcome) != _outcome(r.predicted_outcome)
        if is_exec_failure or is_outcome_mismatch:
            failures.append({
                "question_id": r.question_id,
                "query": r.query,
                "expected_outcome": r.expected_outcome,
                "predicted_outcome": r.predicted_outcome,
                "success": r.success,
                "error_message": r.error_message,
                "confidence": r.confidence,
                "latency_ms": r.latency_ms,
            })
    return failures


def generate_json_report(
    run: EvaluationRun,
    metrics: EvaluationMetrics | None = None,
    *,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    """Generate structured dictionary representing the full JSON report."""
    if metrics is None:
        metrics = calculate_metrics(run)

    timestamp_str = (
        run.run_timestamp.isoformat()
        if isinstance(run.run_timestamp, datetime)
        else str(run.run_timestamp)
    )

    metadata = {
        "video_id": run.video_id,
        "run_timestamp": timestamp_str,
        "runner_version": run.runner_version,
        "total_questions": len(run.results),
        "successful_questions": sum(1 for r in run.results if r.success),
        "execution_failures": sum(1 for r in run.results if not r.success),
    }

    per_question_summary = [
        {
            "question_id": r.question_id,
            "query": r.query,
            "expected_outcome": r.expected_outcome,
            "predicted_outcome": r.predicted_outcome,
            "success": r.success,
            "confidence": r.confidence,
            "latency_ms": r.latency_ms,
            "error_message": r.error_message,
        }
        for r in run.results
    ]

    return {
        "metadata": metadata,
        "metrics": asdict(metrics),
        "latency_summary": calculate_latency_summary(run.results),
        "top_error_categories": summarize_top_error_categories(run.results),
        "low_confidence_questions": find_low_confidence_questions(
            run.results, threshold=low_confidence_threshold
        ),
        "failures": find_failures(run.results),
        "per_question_summary": per_question_summary,
    }


def generate_markdown_report(
    run: EvaluationRun,
    metrics: EvaluationMetrics | None = None,
    *,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> str:
    """Generate formatted Markdown report string for an evaluation run."""
    report_data = generate_json_report(
        run, metrics, low_confidence_threshold=low_confidence_threshold
    )

    metadata = report_data["metadata"]
    m = report_data["metrics"]
    latency = report_data["latency_summary"]
    errors = report_data["top_error_categories"]
    low_conf = report_data["low_confidence_questions"]
    failures = report_data["failures"]
    questions = report_data["per_question_summary"]

    lines: list[str] = [
        f"# Evaluation Report: {metadata['video_id']}",
        "",
        "## Run Metadata",
        "",
        f"- **Video ID:** `{metadata['video_id']}`",
        f"- **Run Timestamp:** {metadata['run_timestamp']}",
        f"- **Runner Version:** `{metadata['runner_version']}`",
        f"- **Total Questions:** {metadata['total_questions']}",
        f"- **Successful Executions:** {metadata['successful_questions']}",
        f"- **Execution Failures:** {metadata['execution_failures']}",
        "",
        "## Metric Table",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Outcome Accuracy | {m['outcome_accuracy'] * 100:.2f}% |",
        f"| Timestamp Hit Rate | {m['timestamp_hit_rate'] * 100:.2f}% |",
        f"| Citation Presence Rate | {m['citation_presence_rate'] * 100:.2f}% |",
        f"| Citation Validity Rate | {m['citation_validity_rate'] * 100:.2f}% |",
        f"| Required Term Coverage | {m['required_term_coverage'] * 100:.2f}% |",
        f"| Unsupported Claim Rate | {m['unsupported_claim_rate'] * 100:.2f}% |",
        f"| Negative Question Abstention Rate | {m['negative_question_abstention_rate'] * 100:.2f}% |",
        f"| Average Confidence | {m['average_confidence']:.4f} |",
        f"| Average Latency (ms) | {m['average_latency_ms']:.2f} ms |",
        f"| Fallback Rate | {m['fallback_rate'] * 100:.2f}% |",
        "",
        "## Latency Summary",
        "",
        "| Metric | Latency (ms) |",
        "| --- | ---: |",
        f"| Count | {latency['count']} |",
        f"| Average | {latency['average_ms']:.2f} ms |",
        f"| Min | {latency['min_ms']:.2f} ms |",
        f"| Max | {latency['max_ms']:.2f} ms |",
        f"| P50 (Median) | {latency['p50_ms']:.2f} ms |",
        f"| P90 | {latency['p90_ms']:.2f} ms |",
        f"| P95 | {latency['p95_ms']:.2f} ms |",
        "",
        "## Top Error Categories",
        "",
    ]

    if not errors:
        lines.extend(["_No error categories recorded._", ""])
    else:
        lines.extend([
            "| Category | Count |",
            "| --- | ---: |",
        ])
        for err in errors:
            cat_escaped = str(err["category"]).replace("|", "\\|")
            lines.append(f"| {cat_escaped} | {err['count']} |")
        lines.append("")

    lines.extend([
        f"## Low Confidence Questions (< {low_confidence_threshold})",
        "",
    ])
    if not low_conf:
        lines.extend(["_No low confidence questions recorded._", ""])
    else:
        lines.extend([
            "| Question ID | Query | Confidence | Expected | Predicted |",
            "| --- | --- | ---: | --- | --- |",
        ])
        for q in low_conf:
            q_id = q["question_id"]
            query_esc = str(q["query"]).replace("|", "\\|")
            conf_str = f"{q['confidence']:.4f}" if q["confidence"] is not None else "N/A"
            exp_esc = str(q["expected_outcome"]).replace("|", "\\|")
            pred_esc = str(q["predicted_outcome"]).replace("|", "\\|")
            lines.append(f"| {q_id} | {query_esc} | {conf_str} | {exp_esc} | {pred_esc} |")
        lines.append("")

    lines.extend([
        "## Failures",
        "",
    ])
    if not failures:
        lines.extend(["_No failures recorded._", ""])
    else:
        lines.extend([
            "| Question ID | Query | Expected | Predicted | Success | Error / Details |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for f in failures:
            q_id = f["question_id"]
            query_esc = str(f["query"]).replace("|", "\\|")
            exp_esc = str(f["expected_outcome"]).replace("|", "\\|")
            pred_esc = str(f["predicted_outcome"]).replace("|", "\\|")
            succ_str = "Yes" if f["success"] else "No"
            err_esc = str(f["error_message"] or "Outcome mismatch").replace("|", "\\|")
            lines.append(
                f"| {q_id} | {query_esc} | {exp_esc} | {pred_esc} | {succ_str} | {err_esc} |"
            )
        lines.append("")

    lines.extend([
        "## Per-Question Summary",
        "",
        "| Question ID | Query | Status | Expected | Predicted | Confidence | Latency (ms) |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ])
    for q in questions:
        q_id = q["question_id"]
        query_esc = str(q["query"]).replace("|", "\\|")
        status_str = "PASSED" if (q["success"] and _outcome(q["expected_outcome"]) == _outcome(q["predicted_outcome"])) else "FAILED"
        exp_esc = str(q["expected_outcome"]).replace("|", "\\|")
        pred_esc = str(q["predicted_outcome"]).replace("|", "\\|")
        conf_str = f"{q['confidence']:.4f}" if q["confidence"] is not None else "N/A"
        lat_str = f"{q['latency_ms']:.2f}"
        lines.append(
            f"| {q_id} | {query_esc} | {status_str} | {exp_esc} | {pred_esc} | {conf_str} | {lat_str} |"
        )
    lines.append("")

    return "\n".join(lines)


def write_reports(
    run: EvaluationRun,
    metrics: EvaluationMetrics | None = None,
    output_dir: str | Path = DEFAULT_REPORTS_DIR,
    run_id: str | None = None,
    *,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> tuple[Path, Path]:
    """Write both JSON and Markdown evaluation reports to disk.

    Returns a tuple of (json_file_path, markdown_file_path).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not run_id:
        if isinstance(run.run_timestamp, datetime):
            run_id = run.run_timestamp.strftime("%Y%m%d_%H%M%S")
        else:
            run_id = "report"

    video_id = run.video_id or "unknown"
    json_path = out_path / f"{video_id}_{run_id}.json"
    md_path = out_path / f"{video_id}_{run_id}.md"

    json_report = generate_json_report(
        run, metrics, low_confidence_threshold=low_confidence_threshold
    )
    markdown_report = generate_markdown_report(
        run, metrics, low_confidence_threshold=low_confidence_threshold
    )

    with json_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(json_report, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    with md_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(markdown_report)

    return json_path, md_path
