from __future__ import annotations

import re
from typing import Any

from .citation_registry import citation_source_compatible


def verify_claims(answer: str, evidence_packet: dict[str, Any]) -> dict[str, Any]:
    evidence_by_citation = {
        item["citation_id"]: item
        for item in evidence_packet.get("verified_evidence", [])
    }
    citation_ids = set(evidence_by_citation)
    evidence_text = " ".join(
        f"{item.get('text', '')} {item.get('visual_summary', '')}"
        for item in evidence_packet.get("verified_evidence", [])
    ).lower()
    claims = []
    unsupported = 0
    invalid_citations = []
    incompatible_citations = []

    for index, sentence in enumerate(_sentences(answer), start=1):
        cited = set(re.findall(r"\bS\d+\b", sentence))
        if cited - citation_ids:
            invalid_citations.extend(sorted(cited - citation_ids))
        incompatible = [
            citation_id
            for citation_id in cited & citation_ids
            if not citation_source_compatible(sentence, evidence_by_citation[citation_id])
        ]
        incompatible_citations.extend(incompatible)
        label = _label_sentence(sentence, cited, citation_ids, evidence_text)
        if incompatible and label == "supported":
            label = "partially_supported"
        if label in {"unsupported", "contradicted"}:
            unsupported += 1
        claims.append(
            {
                "claim_id": f"claim_{index:03d}",
                "text": sentence,
                "citations": sorted(cited),
                "label": label,
                "claim_type": _claim_type(sentence),
                "incompatible_citations": sorted(incompatible),
                "required_citation": sorted(cited)[0] if cited else None,
            }
        )

    timestamp_ok = _timestamp_within_citations(answer, evidence_packet)
    citation_validation = evidence_packet.get("citation_validation") or {"valid": True}
    passed = (
        unsupported == 0
        and not invalid_citations
        and not incompatible_citations
        and timestamp_ok
        and citation_validation.get("valid", False)
    )
    return {
        "passed": passed,
        "claims": claims,
        "unsupported_claim_count": unsupported,
        "invalid_citations": sorted(set(invalid_citations)),
        "incompatible_citations": sorted(set(incompatible_citations)),
        "citation_validation": citation_validation,
        "timestamp_ok": timestamp_ok,
        "can_revise": bool(unsupported or invalid_citations or incompatible_citations or not timestamp_ok),
    }


def _sentences(answer: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if s.strip()]


def _label_sentence(sentence: str, cited: set[str], citation_ids: set[str], evidence_text: str) -> str:
    if not cited:
        if re.search(r"\b(I could not|not enough|limitations?|uncertain|partial)\b", sentence, re.I):
            return "not_video_claim"
        return "unsupported"
    if cited - citation_ids:
        return "unsupported"
    terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9]{4,}", re.sub(r"\bS\d+\b", "", sentence))
        if term.lower() not in {"around", "video", "evidence", "says", "nearby", "supporting", "moment", "adds"}
    }
    overlap = sum(1 for term in terms if term in evidence_text)
    if not terms:
        return "supported"
    coverage = overlap / max(1, len(terms))
    if coverage >= 0.35:
        return "supported"
    if coverage >= 0.15:
        return "partially_supported"
    return "unsupported"


def _timestamp_within_citations(answer: str, packet: dict[str, Any]) -> bool:
    times = re.findall(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b", answer)
    if not times:
        return True
    windows = [
        (
            (item.get("evidence_anchor") or {}).get("start_ms", item["start_ms"]),
            (item.get("evidence_anchor") or {}).get("end_ms", item["end_ms"]),
        )
        for item in packet.get("verified_evidence", [])
    ]
    for hours, minutes, seconds in times:
        ms = ((int(hours or 0) * 3600) + (int(minutes) * 60) + int(seconds)) * 1000
        if not any(start - 3000 <= ms <= end + 3000 for start, end in windows):
            return False
    return True


def _claim_type(sentence: str) -> str:
    from .citation_registry import infer_claim_type

    return infer_claim_type(sentence)
