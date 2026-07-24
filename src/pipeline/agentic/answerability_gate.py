from __future__ import annotations

from typing import Any


ANSWER_THRESHOLD = 0.72
PARTIAL_THRESHOLD = 0.55
RETRY_THRESHOLD = 0.38
NOT_FOUND_THRESHOLD = 0.24


def evaluate_answerability(
    *,
    verified_evidence: list[dict[str, Any]],
    query_understanding: dict[str, Any],
    scope_decision: dict[str, Any],
    verification_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scope_decision.get("policy_action") in {"processing_incomplete", "abstain_unrelated", "clarify", "general_answer"}:
        return {
            "decision": scope_decision["policy_action"],
            "score": 0.0,
            "reasons": ["scope policy stopped video answering"],
            "reason_codes": ["SCOPE_POLICY_STOP"],
        }
    verification_summary = verification_summary or {}
    missing_required = _missing_required_modalities(query_understanding, verification_summary, verified_evidence)
    if missing_required:
        return {
            "decision": "processing_incomplete",
            "score": 0.0,
            "reasons": [f"required modality evidence is unavailable: {', '.join(missing_required)}"],
            "reason_codes": ["REQUIRED_MODALITY_UNAVAILABLE"],
            "missing_modalities": missing_required,
        }
    if not verified_evidence:
        return {
            "decision": "video_evidence_not_found",
            "score": 0.0,
            "reasons": ["no verified evidence"],
            "reason_codes": ["NO_VERIFIED_EVIDENCE"],
        }

    features = _sufficiency_features(verified_evidence, query_understanding)
    score = _evidence_sufficiency(features)

    if score >= ANSWER_THRESHOLD:
        decision = "answer"
    elif score >= PARTIAL_THRESHOLD:
        decision = "partial_answer"
    elif score >= RETRY_THRESHOLD:
        decision = "corrective_retrieval"
    else:
        decision = "video_evidence_not_found"

    return {
        "decision": decision,
        "score": round(score, 6),
        "evidence_sufficiency": round(score, 6),
        "features": {key: round(value, 6) for key, value in features.items()},
        "best_support_score": round(features["top_rerank_score"], 6),
        "strong_evidence_count": sum(1 for item in verified_evidence if item.get("support_level") == "strong"),
        "verified_evidence_count": len(verified_evidence),
        "required_modalities": query_understanding.get("required_modalities", []),
        "reason_codes": _reason_codes(decision, features),
        "reasons": _reasons(decision, features),
        "thresholds": {
            "answerable_threshold": ANSWER_THRESHOLD,
            "partial_threshold": PARTIAL_THRESHOLD,
            "retry_threshold": RETRY_THRESHOLD,
            "not_found_threshold": NOT_FOUND_THRESHOLD,
        },
    }


def _missing_required_modalities(
    query_understanding: dict[str, Any],
    verification_summary: dict[str, Any],
    verified_evidence: list[dict[str, Any]],
) -> list[str]:
    required = set(query_understanding.get("required_modalities") or []) - {"transcript"}
    if not required:
        return []
    evidence_types = {evidence_type for item in verified_evidence for evidence_type in item.get("evidence_types", [])}
    missing = sorted(required - evidence_types)
    if not missing:
        return []
    reasons = verification_summary.get("rejection_reason_counts") or {}
    reason_text = " ".join(reasons)
    warning_text = " ".join(str(warning) for warning in verification_summary.get("retrieval_warnings") or [])
    attempt_text = " ".join(
        " ".join(str(item) for item in (attempt.get("readiness") or {}).get("missing_artifacts", []))
        for attempt in verification_summary.get("retrieval_attempts") or []
    )
    return [
        modality
        for modality in missing
        if (
            f"missing_{modality}_artifact" in reason_text
            or modality in warning_text
            or _modality_artifact_key(modality) in warning_text
            or _modality_artifact_key(modality) in attempt_text
        )
    ]


def _modality_artifact_key(modality: str) -> str:
    return {
        "visual": "visual_artifacts_path",
        "ocr": "ocr_path",
        "speaker": "speakers_path",
        "audio": "audio_events_path",
    }.get(modality, modality)


def _modality_coverage(verified_evidence: list[dict[str, Any]], query_understanding: dict[str, Any]) -> float:
    required = set(query_understanding.get("required_modalities") or [])
    if not required:
        return 1.0
    evidence_types = {evidence_type for item in verified_evidence for evidence_type in item.get("evidence_types", [])}
    return len(required & evidence_types) / max(1, len(required))


def _sufficiency_features(
    verified_evidence: list[dict[str, Any]],
    query_understanding: dict[str, Any],
) -> dict[str, float]:
    scores = sorted(
        [float(item.get("rerank_score", item.get("support_score", 0.0)) or 0.0) for item in verified_evidence],
        reverse=True,
    )
    support_scores = sorted(
        [float(item.get("support_score", 0.0) or 0.0) for item in verified_evidence],
        reverse=True,
    )
    top_rerank = max(support_scores[0] if support_scores else 0.0, min(1.0, scores[0] if scores else 0.0))
    consensus = min(1.0, len([item for item in verified_evidence[:5] if item.get("support_level") in {"strong", "moderate"}]) / 3)
    modality_coverage = _modality_coverage(verified_evidence, query_understanding)
    entity_coverage = _entity_coverage(verified_evidence, query_understanding)
    temporal_alignment = _temporal_alignment(verified_evidence, query_understanding)
    source_quality = sum(float(item.get("support_score", 0.0) or 0.0) for item in verified_evidence[:5]) / max(1, min(5, len(verified_evidence)))
    evidence_diversity = len({str(item.get("source_type")) for item in verified_evidence}) / max(1, min(4, len(verified_evidence)))
    retrieval_margin = max(0.0, (scores[0] if scores else 0.0) - (scores[1] if len(scores) > 1 else 0.0))
    return {
        "top_rerank_score": min(1.0, top_rerank),
        "top_k_consensus": consensus,
        "required_modality_coverage": modality_coverage,
        "entity_coverage": entity_coverage,
        "temporal_alignment": temporal_alignment,
        "source_quality": min(1.0, source_quality),
        "evidence_diversity": min(1.0, evidence_diversity),
        "retrieval_margin": min(1.0, retrieval_margin),
        "contradiction_penalty": 0.0,
        "uncertainty_penalty": 0.08 if len(verified_evidence) == 1 else 0.0,
    }


def _evidence_sufficiency(features: dict[str, float]) -> float:
    return max(
        0.0,
        min(
            1.0,
            0.22 * features["top_rerank_score"]
            + 0.15 * features["top_k_consensus"]
            + 0.15 * features["required_modality_coverage"]
            + 0.14 * features["entity_coverage"]
            + 0.12 * features["temporal_alignment"]
            + 0.10 * features["source_quality"]
            + 0.07 * features["evidence_diversity"]
            + 0.05 * features["retrieval_margin"]
            - features["contradiction_penalty"]
            - features["uncertainty_penalty"],
        ),
    )


def _entity_coverage(verified_evidence: list[dict[str, Any]], query_understanding: dict[str, Any]) -> float:
    entities = {str(entity).lower() for entity in query_understanding.get("entities") or []}
    if not entities:
        return 1.0
    text = " ".join(
        " ".join(str(item.get(key, "")) for key in ("text", "transcript", "visual_summary"))
        for item in verified_evidence[:5]
    ).lower()
    return sum(1 for entity in entities if entity and entity in text) / max(1, len(entities))


def _temporal_alignment(verified_evidence: list[dict[str, Any]], query_understanding: dict[str, Any]) -> float:
    constraints = query_understanding.get("time_constraints") or []
    if not constraints:
        return 0.82
    for constraint in constraints:
        target = constraint.get("target_ms")
        if not isinstance(target, int):
            continue
        for item in verified_evidence:
            if int(item.get("start_ms", 0)) <= target <= int(item.get("end_ms", 0)):
                return 1.0
    return 0.35


def _reason_codes(decision: str, features: dict[str, float]) -> list[str]:
    codes = [decision.upper()]
    if features["required_modality_coverage"] < 1.0:
        codes.append("PARTIAL_MODALITY_COVERAGE")
    if features["entity_coverage"] < 1.0:
        codes.append("PARTIAL_ENTITY_COVERAGE")
    if features["retrieval_margin"] < 0.03:
        codes.append("LOW_RETRIEVAL_MARGIN")
    return codes


def _reasons(decision: str, features: dict[str, float]) -> list[str]:
    reasons = [f"answerability decision: {decision}"]
    if features["required_modality_coverage"] >= 1.0:
        reasons.append("required modality coverage is complete")
    if features["entity_coverage"] >= 1.0:
        reasons.append("required entity coverage is complete")
    if features["retrieval_margin"] < 0.03:
        reasons.append("top candidates are close together")
    return reasons
