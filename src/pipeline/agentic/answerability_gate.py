from __future__ import annotations

from typing import Any


ANSWER_THRESHOLD = 0.55
PARTIAL_THRESHOLD = 0.38
UNCERTAIN_THRESHOLD = 0.22


def evaluate_answerability(
    *,
    verified_evidence: list[dict[str, Any]],
    query_understanding: dict[str, Any],
    scope_decision: dict[str, Any],
) -> dict[str, Any]:
    if scope_decision.get("policy_action") in {"processing_incomplete", "abstain_unrelated", "clarify", "general_answer"}:
        return {
            "decision": scope_decision["policy_action"],
            "score": 0.0,
            "reasons": ["scope policy stopped video answering"],
        }
    if not verified_evidence:
        return {
            "decision": "video_evidence_not_found",
            "score": 0.0,
            "reasons": ["no verified evidence"],
        }

    best = max(float(item.get("support_score", 0.0)) for item in verified_evidence)
    strong_count = sum(1 for item in verified_evidence if item.get("support_level") == "strong")
    modality_coverage = _modality_coverage(verified_evidence, query_understanding)
    score = min(1.0, best + (0.06 * min(strong_count, 3)) + modality_coverage)

    if score >= ANSWER_THRESHOLD:
        decision = "answer"
    elif score >= PARTIAL_THRESHOLD:
        decision = "partial_answer"
    elif score >= UNCERTAIN_THRESHOLD:
        decision = "corrective_retrieval"
    else:
        decision = "video_evidence_not_found"

    return {
        "decision": decision,
        "score": round(score, 6),
        "best_support_score": round(best, 6),
        "strong_evidence_count": strong_count,
        "verified_evidence_count": len(verified_evidence),
        "required_modalities": query_understanding.get("required_modalities", []),
        "reasons": _reasons(decision, modality_coverage, strong_count),
    }


def _modality_coverage(verified_evidence: list[dict[str, Any]], query_understanding: dict[str, Any]) -> float:
    required = set(query_understanding.get("required_modalities") or [])
    if not required:
        return 0.08
    evidence_types = {evidence_type for item in verified_evidence for evidence_type in item.get("evidence_types", [])}
    coverage = len(required & evidence_types) / max(1, len(required))
    return 0.12 * coverage


def _reasons(decision: str, modality_coverage: float, strong_count: int) -> list[str]:
    reasons = [f"answerability decision: {decision}"]
    if strong_count:
        reasons.append(f"{strong_count} strong evidence item(s)")
    if modality_coverage:
        reasons.append("required modality coverage present")
    return reasons
