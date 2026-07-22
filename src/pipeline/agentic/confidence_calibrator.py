from __future__ import annotations

from typing import Any


def calibrate_confidence(
    *,
    retrieval_gate: dict[str, Any],
    temporal_context: dict[str, Any],
    evidence_packet: dict[str, Any],
    claim_verification: dict[str, Any],
    generation: dict[str, Any],
) -> dict[str, Any]:
    verified = retrieval_gate.get("verification", {}).get("verified_evidence", [])
    top_fused = max((float(item.get("fused_score", 0.0)) for item in verified), default=0.0)
    top_rerank = max((float(item.get("rerank_score", 0.0)) for item in verified), default=0.0)
    evidence_count_score = min(1.0, len(verified) / 5)
    citation_count = len(evidence_packet.get("citations", []))
    claim_count = max(1, len(claim_verification.get("claims", [])))
    supported_claims = sum(1 for claim in claim_verification.get("claims", []) if claim.get("label") == "supported")
    claim_support = supported_claims / claim_count
    citation_coverage = min(1.0, citation_count / max(1, claim_count))
    timeline_consistency = 1.0 if temporal_context.get("context_within_video_duration") else 0.0
    modality_coverage = 1.0 if evidence_packet.get("verified_evidence") else 0.0
    fallback_penalty = 0.06 if generation.get("fallback_used") else 0.0
    unsupported_penalty = 0.2 if claim_verification.get("unsupported_claim_count", 0) else 0.0

    score = (
        0.18 * min(1.0, top_fused * 4)
        + 0.16 * min(1.0, top_rerank * 3)
        + 0.16 * evidence_count_score
        + 0.14 * citation_coverage
        + 0.18 * claim_support
        + 0.10 * timeline_consistency
        + 0.08 * modality_coverage
        - fallback_penalty
        - unsupported_penalty
    )
    score = max(0.0, min(1.0, score))
    low_reason = None
    if score < 0.35:
        low_reason = "weak_evidence_or_claim_support"
    elif claim_verification.get("unsupported_claim_count", 0):
        low_reason = "unsupported_claims_present"
    elif generation.get("fallback_used"):
        low_reason = "generator_fallback_used"

    return {
        "score": round(score, 6),
        "features": {
            "top_fused_score": top_fused,
            "top_rerank_score": top_rerank,
            "verified_evidence_count": len(verified),
            "citation_count": citation_count,
            "citation_coverage": round(citation_coverage, 6),
            "claim_support": round(claim_support, 6),
            "timeline_consistency": timeline_consistency,
            "modality_coverage": modality_coverage,
            "corrective_retrieval_used": bool(retrieval_gate.get("corrective_attempts")),
            "generator_fallback_used": bool(generation.get("fallback_used")),
        },
        "low_confidence_reason": low_reason,
    }
