from __future__ import annotations

from typing import Any


def temporal_iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    start = max(int(a["start_ms"]), int(b["start_ms"]))
    end = min(int(a["end_ms"]), int(b["end_ms"]))
    overlap = max(0, end - start)
    union = max(int(a["end_ms"]), int(b["end_ms"])) - min(int(a["start_ms"]), int(b["start_ms"]))
    return overlap / union if union > 0 else 0.0


def deduplicate_temporal_candidates(
    *,
    candidates: list[dict[str, Any]],
    threshold: float = 0.72,
) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    collapsed: list[dict[str, Any]] = []
    for candidate in candidates:
        match = None
        for existing in kept:
            if candidate["video_id"] != existing["video_id"]:
                continue
            if temporal_iou(candidate, existing) >= threshold:
                match = existing
                break
        if match is None:
            kept.append({**candidate, "temporal_duplicates": []})
            continue
        match.setdefault("temporal_duplicates", []).append(
            {
                "candidate_id": candidate["candidate_id"],
                "source_type": candidate["source_type"],
                "source_id": candidate["source_id"],
                "rerank_score": candidate.get("rerank_score"),
                "temporal_iou": round(temporal_iou(candidate, match), 6),
            }
        )
        collapsed.append({"kept": match["candidate_id"], "removed": candidate["candidate_id"]})
    return {
        "input_candidate_count": len(candidates),
        "deduplicated_candidate_count": len(kept),
        "collapsed": collapsed,
        "candidates": kept,
    }
