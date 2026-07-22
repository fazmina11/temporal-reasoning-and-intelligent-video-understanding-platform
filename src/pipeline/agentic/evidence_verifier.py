from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..json_artifacts import read_json
from ..media_manifest import load_manifest


def verify_evidence(
    *,
    repo_root: Path,
    video_id: str,
    candidates: list[dict[str, Any]],
    query_understanding: dict[str, Any],
) -> dict[str, Any]:
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    artifacts = manifest.get("artifacts", {})
    lookups = _load_source_lookups(artifacts)
    terms = _terms(query_understanding.get("standalone_query") or query_understanding.get("raw_query") or "")
    required_modalities = set(query_understanding.get("required_modalities") or [])

    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for candidate in candidates:
        reasons = _rejection_reasons(candidate, video_id, lookups, terms, required_modalities)
        if reasons:
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            rejected.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "source_id": candidate.get("source_id"),
                    "rejection_reasons": reasons,
                }
            )
            continue
        support_score = _support_score(candidate, terms, required_modalities)
        verified.append(
            {
                **candidate,
                "verified": True,
                "support_score": round(support_score, 6),
                "support_level": "strong" if support_score >= 0.6 else "moderate" if support_score >= 0.35 else "weak",
                "evidence_types": _evidence_types(candidate),
            }
        )
    return {
        "candidate_count": len(candidates),
        "verified_count": len(verified),
        "rejected_count": len(rejected),
        "rejection_reason_counts": reason_counts,
        "verified_evidence": verified,
        "rejected_evidence": rejected,
    }


def _load_source_lookups(artifacts: dict[str, Any]) -> dict[str, set[str]]:
    lookups = {"atom": set(), "semantic_chunk": set(), "visual_chunk": set(), "event": set(), "ocr": set(), "speaker_turn": set(), "audio_event": set()}
    for path_key, list_key, lookup_key, id_key in [
        ("atoms_path", "atoms", "atom", "atom_id"),
        ("semantic_chunks_path", "chunks", "semantic_chunk", "chunk_id"),
        ("semantic_chunks_path", "chunks", "visual_chunk", "chunk_id"),
        ("events_path", "events", "event", "event_id"),
        ("ocr_path", "records", "ocr", "ocr_id"),
        ("speakers_path", "turns", "speaker_turn", "turn_id"),
        ("audio_events_path", "events", "audio_event", "audio_event_id"),
    ]:
        path = Path(artifacts.get(path_key, ""))
        if not path.exists():
            continue
        for item in read_json(path).get(list_key, []):
            if item.get(id_key):
                lookups[lookup_key].add(item[id_key])
    return lookups


def _rejection_reasons(
    candidate: dict[str, Any],
    video_id: str,
    lookups: dict[str, set[str]],
    terms: set[str],
    required_modalities: set[str],
) -> list[str]:
    reasons: list[str] = []
    if candidate.get("video_id") != video_id:
        reasons.append("wrong_video")
    if int(candidate.get("end_ms", 0)) <= int(candidate.get("start_ms", 0)):
        reasons.append("invalid_timeline")
    source_type = str(candidate.get("source_type", "unknown"))
    source_id = str(candidate.get("source_id", ""))
    if source_type in lookups and source_id not in lookups[source_type]:
        reasons.append("missing_source_artifact")
    if not (candidate.get("text") or candidate.get("transcript") or candidate.get("visual_summary")):
        reasons.append("empty_content")
    if "visual" in required_modalities and not (candidate.get("visual_summary") or (candidate.get("media_refs") or {}).get("frames")):
        reasons.append("missing_visual_artifact")
    if "ocr" in required_modalities and not candidate.get("ocr_text"):
        reasons.append("missing_ocr_artifact")
    if "speaker" in required_modalities and not (candidate.get("source_type") == "speaker_turn" or (candidate.get("media_refs") or {}).get("speaker_id")):
        reasons.append("missing_speaker_artifact")
    if "audio" in required_modalities and not (candidate.get("source_type") == "audio_event" or (candidate.get("media_refs") or {}).get("audio_event")):
        reasons.append("missing_audio_artifact")
    if terms and _support_score(candidate, terms, required_modalities) < 0.08:
        reasons.append("weak_query_match")
    return reasons


def _support_score(candidate: dict[str, Any], terms: set[str], required_modalities: set[str]) -> float:
    text = " ".join(
        str(candidate.get(key, ""))
        for key in ["text", "transcript", "visual_summary"]
        if candidate.get(key)
    ).lower()
    overlap = sum(1 for term in terms if term in text)
    term_score = overlap / max(1, len(terms))
    retrieval_score = float((candidate.get("retrieval") or {}).get("raw_score", 0.0) or 0.0)
    fused = float(candidate.get("rerank_score", candidate.get("fused_score", 0.0)) or 0.0)
    modality_score = 0.15 if "visual" not in required_modalities or candidate.get("visual_summary") or (candidate.get("media_refs") or {}).get("frames") else 0.0
    return min(1.0, (0.45 * term_score) + (0.25 * retrieval_score) + min(0.15, fused) + modality_score)


def _evidence_types(candidate: dict[str, Any]) -> list[str]:
    types = []
    if candidate.get("transcript") or candidate.get("text"):
        types.append("transcript")
    if candidate.get("visual_summary") or (candidate.get("media_refs") or {}).get("frames"):
        types.append("visual")
    if candidate.get("parent_event_id") or candidate.get("source_type") == "event":
        types.append("event")
    if candidate.get("ocr_text"):
        types.append("ocr")
    if candidate.get("source_type") == "speaker_turn":
        types.append("speaker")
    if candidate.get("source_type") == "audio_event":
        types.append("audio")
    return types


def _terms(text: str) -> set[str]:
    stop = {"what", "where", "when", "why", "how", "does", "did", "the", "and", "from", "that", "this", "with", "about", "tell", "after", "before"}
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text) if term.lower() not in stop}
