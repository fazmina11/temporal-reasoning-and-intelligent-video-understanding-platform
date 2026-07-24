from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..json_artifacts import read_json
from .scope_analyzer import analyze_video_scope
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

    if query_understanding.get("is_ambiguous_without_context"):
        return {
            "scope": "ambiguous",
            "confidence": 0.88,
            "reasons": query_understanding.get("ambiguity_reasons")
            or ["query contains unresolved references and no usable conversation anchor"],
            "policy_action": ScopeAction.CLARIFY,
            "unresolved_references": query_understanding.get("unresolved_references") or [],
        }

    scope_analysis = analyze_video_scope(
        repo_root=repo_root,
        video_id=video_id,
        query_understanding=query_understanding,
        answer_mode=mode,
    )
    if _needs_clarification_from_scope(query_understanding, scope_analysis):
        return {
            "scope": "ambiguous",
            "confidence": 0.78,
            "reasons": ["query references a broad visual, example, comparison, model, or key point without a specific anchor"],
            "policy_action": ScopeAction.CLARIFY,
            "scope_analysis": scope_analysis,
        }

    if "system_or_help" in query_types and not _has_video_reference(query) and scope_analysis["scope_score"] < 0.18:
        return _apply_policy(
            "unrelated",
            0.9,
            ["query asks about system usage, not selected video"],
            mode,
            scope_analysis,
        )

    if scope_analysis["strict_unrelated"]:
        return _apply_policy(
            "unrelated",
            0.86,
            ["scope profile found no meaningful overlap with the selected video"],
            mode,
            scope_analysis,
        )

    if scope_analysis.get("probable_related") or scope_analysis["scope_score"] >= scope_analysis["thresholds"]["probable_related_threshold"]:
        return {
            "scope": "video_related",
            "confidence": min(0.95, 0.55 + scope_analysis["scope_score"]),
            "reasons": _scope_reasons(scope_analysis) or ["query overlaps selected video scope profile"],
            "policy_action": ScopeAction.RETRIEVE_VIDEO,
            "scope_analysis": scope_analysis,
        }

    if _has_video_reference(query) or query_types & {"exact_timestamp", "visual_memory", "ocr_or_slide_text", "audio_memory", "before_after", "speaker_question", "follow_up"}:
        return {
            "scope": "probably_video_related",
            "confidence": 0.62,
            "reasons": ["query contains video/timeline/speaker cues"],
            "policy_action": ScopeAction.RETRIEVE_VIDEO,
            "scope_analysis": scope_analysis,
        }

    if mode == AnswerMode.CLARIFY_WHEN_AMBIGUOUS:
        return {
            "scope": "ambiguous",
            "confidence": 0.5,
            "reasons": ["query has weak video overlap and no clear video reference"],
            "policy_action": ScopeAction.CLARIFY,
            "scope_analysis": scope_analysis,
        }

    return _apply_policy("unrelated", 0.72, ["query has weak overlap with selected video scope"], mode, scope_analysis)


def _needs_clarification_from_scope(
    query_understanding: dict[str, Any],
    scope_analysis: dict[str, Any],
) -> bool:
    query_types = set(query_understanding.get("query_types") or [])
    if "unrelated_or_general" in query_types:
        return False
    lowered = str(query_understanding.get("standalone_query") or query_understanding.get("raw_query") or "").lower()
    if re.search(r"\b(?:opening|first|initial|intro(?:duction)?)\s+slide\b", lowered):
        return False
    if (
        re.search(r"\bthe model\b", lowered)
        and "exact_timestamp" not in query_types
        and not re.search(r"\b(mcp|api|apis|app code|reasoning layer|model context protocol)\b", lowered)
    ):
        return True
    if re.search(
        r"\b(who was (?:the )?speaker talking about|"
        r"timestamp for (?:the )?key point|where is (?:the )?example)\b",
        lowered,
    ):
        return True
    matched_terms = set(scope_analysis.get("matched_terms") or [])
    matched_entities = set(scope_analysis.get("matched_entities") or [])
    if matched_terms or matched_entities or query_understanding.get("time_constraints"):
        return False
    if query_types & {"visual_memory", "comparison", "before_after"}:
        return True
    return bool(re.search(r"\b(example|key point|important difference|the model|the slide)\b", lowered))


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


def _scope_reasons(scope_analysis: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if scope_analysis.get("matched_entities"):
        reasons.append(f"matched video entities: {', '.join(scope_analysis['matched_entities'][:6])}")
    if scope_analysis.get("matched_terms"):
        reasons.append(f"matched video terms: {', '.join(scope_analysis['matched_terms'][:8])}")
    signals = scope_analysis.get("signals") or {}
    if signals.get("conversation_reference_score"):
        reasons.append("conversation reference resolves into the selected video")
    if signals.get("timestamp_reference_score"):
        reasons.append("query contains a timestamp reference")
    return reasons
