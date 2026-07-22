from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..json_artifacts import read_json
from .contracts import AnswerMode


class ScopeAction:
    RETRIEVE_VIDEO = "retrieve_video"
    GENERAL_ANSWER = "general_answer"
    CLARIFY = "clarify"
    ABSTAIN_UNRELATED = "abstain_unrelated"
    PROCESSING_INCOMPLETE = "processing_incomplete"


def route_scope(
    *,
    repo_root: Path,
    video_id: str,
    query_understanding: dict[str, Any],
    answer_mode: AnswerMode | str = AnswerMode.STRICT_VIDEO,
) -> dict[str, Any]:
    mode = AnswerMode(answer_mode)
    manifest_path = repo_root / "data" / "processed" / "manifests" / f"{video_id}.json"
    if not manifest_path.exists():
        return {
            "scope": "processing_incomplete",
            "confidence": 1.0,
            "reasons": ["manifest does not exist for selected video"],
            "policy_action": ScopeAction.PROCESSING_INCOMPLETE,
        }

    manifest = read_json(manifest_path)
    status = (manifest.get("processing") or {}).get("processing_status") or manifest.get("processing_status")
    if status == "failed":
        return {
            "scope": "processing_incomplete",
            "confidence": 0.95,
            "reasons": [f"video processing status is {status}"],
            "policy_action": ScopeAction.PROCESSING_INCOMPLETE,
        }
    readiness = _artifact_readiness(manifest)
    if status == "uploaded" and not readiness["ready"]:
        return {
            "scope": "processing_incomplete",
            "confidence": 0.9,
            "reasons": ["video is still marked uploaded", *readiness["missing"]],
            "policy_action": ScopeAction.PROCESSING_INCOMPLETE,
        }

    query_types = set(query_understanding.get("query_types") or [])
    query = query_understanding.get("standalone_query") or query_understanding.get("raw_query") or ""

    if "system_or_help" in query_types and not _has_video_reference(query):
        return _apply_policy("unrelated", 0.9, ["query asks about system usage, not selected video"], mode)

    if "unrelated_or_general" in query_types and not _has_video_reference(query):
        return _apply_policy("unrelated", 0.85, ["query matches general-knowledge cues"], mode)

    probe = _probe_video_artifacts(repo_root, video_id, query)
    if probe["score"] >= 0.18:
        return {
            "scope": "video_related",
            "confidence": min(0.95, 0.55 + probe["score"]),
            "reasons": probe["reasons"] or ["query overlaps selected video evidence"],
            "policy_action": ScopeAction.RETRIEVE_VIDEO,
            "probe": probe,
        }

    if _has_video_reference(query) or query_types & {"exact_timestamp", "visual_memory", "ocr_or_slide_text", "audio_memory", "before_after", "speaker_question", "follow_up"}:
        return {
            "scope": "probably_video_related",
            "confidence": 0.62,
            "reasons": ["query contains video/timeline/speaker cues"],
            "policy_action": ScopeAction.RETRIEVE_VIDEO,
            "probe": probe,
        }

    if mode == AnswerMode.CLARIFY_WHEN_AMBIGUOUS:
        return {
            "scope": "ambiguous",
            "confidence": 0.5,
            "reasons": ["query has weak video overlap and no clear video reference"],
            "policy_action": ScopeAction.CLARIFY,
            "probe": probe,
        }

    return _apply_policy("unrelated", 0.72, ["query has weak overlap with selected video evidence"], mode, probe)


def _apply_policy(
    scope: str,
    confidence: float,
    reasons: list[str],
    mode: AnswerMode,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode == AnswerMode.HYBRID_ASSISTANT:
        action = ScopeAction.GENERAL_ANSWER
    elif mode == AnswerMode.CLARIFY_WHEN_AMBIGUOUS and confidence < 0.8:
        scope = "ambiguous"
        action = ScopeAction.CLARIFY
    else:
        action = ScopeAction.ABSTAIN_UNRELATED
    decision = {"scope": scope, "confidence": confidence, "reasons": reasons, "policy_action": action}
    if probe is not None:
        decision["probe"] = probe
    return decision


def _has_video_reference(query: str) -> bool:
    return bool(re.search(r"\b(video|speaker|lecturer|presenter|he|she|shown|said|timestamp|scene|clip|frame)\b", query, re.I))


def _artifact_readiness(manifest: dict[str, Any]) -> dict[str, Any]:
    artifacts = manifest.get("artifacts") or {}
    required = [
        "atoms_path",
        "semantic_chunks_path",
        "events_path",
        "visual_artifacts_path",
    ]
    missing = [
        f"missing {key}"
        for key in required
        if not artifacts.get(key) or not Path(str(artifacts[key])).exists()
    ]
    validation_path = artifacts.get("hierarchy_validation_path")
    if validation_path and Path(str(validation_path)).exists():
        try:
            report = read_json(Path(str(validation_path)))
            if report.get("valid") is False:
                missing.append("hierarchy validation report is not valid")
        except Exception:
            missing.append("hierarchy validation report could not be read")
    return {"ready": not missing, "missing": missing}


def _probe_video_artifacts(repo_root: Path, video_id: str, query: str) -> dict[str, Any]:
    terms = _terms(query)
    if not terms:
        return {"score": 0.0, "matched_terms": [], "reasons": []}

    texts: list[str] = []
    for rel in [
        ("data", "processed", "events", f"{video_id}.json"),
        ("data", "processed", "semantic_chunks", f"{video_id}.json"),
        ("data", "processed", "atoms", f"{video_id}.json"),
    ]:
        path = repo_root.joinpath(*rel)
        if not path.exists():
            continue
        try:
            payload = read_json(path)
        except Exception:
            continue
        texts.extend(_collect_text(payload))

    corpus = " ".join(texts).lower()
    if not corpus:
        return {"score": 0.0, "matched_terms": [], "reasons": ["no searchable video artifacts available"]}

    matched = sorted(term for term in terms if term in corpus)
    score = len(matched) / max(1, len(terms))
    reasons = [f"matched video terms: {', '.join(matched[:8])}"] if matched else []
    return {"score": score, "matched_terms": matched, "reasons": reasons}


def _terms(text: str) -> set[str]:
    stop = {"what", "where", "when", "why", "how", "does", "did", "the", "and", "from", "that", "this", "with", "about", "tell", "explain"}
    return {t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", text) if t.lower() not in stop}


def _collect_text(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"transcript_text", "summary", "title", "text", "visual_summary"} and isinstance(item, str):
                texts.append(item)
            else:
                texts.extend(_collect_text(item))
    elif isinstance(value, list):
        for item in value:
            texts.extend(_collect_text(item))
    return texts
