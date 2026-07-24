from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .contracts import AnswerMode
from .scope_profile import load_or_build_scope_profile

STRICT_UNRELATED_THRESHOLD = 0.12
PROBABLE_RELATED_THRESHOLD = 0.34


def analyze_video_scope(
    *,
    repo_root: Path,
    video_id: str,
    query_understanding: dict[str, Any],
    answer_mode: AnswerMode | str = AnswerMode.STRICT_VIDEO,
) -> dict[str, Any]:
    """Compare a query with the selected video's scope profile."""
    profile = load_or_build_scope_profile(repo_root=repo_root, video_id=video_id)
    query = query_understanding.get("standalone_query") or query_understanding.get("raw_query") or ""
    query_terms = _terms(query)
    profile_terms = set(profile.get("topic_keywords") or []) | set(_terms(profile.get("scope_summary", "")))
    event_terms = set(_terms(" ".join(profile.get("event_summaries") or [])))
    chapter_terms = set(_terms(" ".join(profile.get("chapter_titles") or [])))
    ocr_terms = set(str(item).lower() for item in profile.get("ocr_vocabulary") or [])
    profile_entities = {str(item).lower() for item in profile.get("top_entities") or []}
    query_entities = {str(item).lower() for item in query_understanding.get("entities") or []}

    signals = {
        "scope_embedding_similarity": _lexical_cosine(query_terms, profile_terms | event_terms | chapter_terms | ocr_terms),
        "entity_overlap_score": _overlap(query_entities, profile_entities),
        "keyword_overlap_score": _overlap(query_terms, profile_terms),
        "chapter_event_match_score": _overlap(query_terms, event_terms | chapter_terms),
        "conversation_reference_score": 1.0 if query_understanding.get("reference_resolved") else 0.0,
        "timestamp_reference_score": 1.0 if query_understanding.get("time_constraints") else 0.0,
        "speaker_reference_score": _speaker_score(query, profile),
        "visual_hint_match_score": _visual_score(query_understanding, ocr_terms | profile_terms | event_terms),
    }
    score = (
        0.35 * signals["scope_embedding_similarity"]
        + 0.20 * signals["entity_overlap_score"]
        + 0.10 * signals["keyword_overlap_score"]
        + 0.15 * signals["chapter_event_match_score"]
        + 0.10 * signals["conversation_reference_score"]
        + 0.05 * signals["timestamp_reference_score"]
        + 0.05 * signals["visual_hint_match_score"]
    )
    score = max(0.0, min(1.0, score))
    query_types = set(query_understanding.get("query_types") or [])
    clear_general_query = "unrelated_or_general" in query_types
    has_video_cue = bool(
        query_types & {
            "exact_timestamp", "visual_memory", "ocr_or_slide_text", "speaker_question",
            "audio_memory", "follow_up", "summary", "chapter_summary",
        }
    )
    if "before_after" in query_types and not clear_general_query:
        has_video_cue = True
    matched_terms = sorted(query_terms & (profile_terms | event_terms | chapter_terms | ocr_terms))
    matched_entities = sorted(query_entities & profile_entities)
    strong_topic_match = len(matched_terms) >= 2 or bool(matched_entities)
    strict_unrelated = bool(
        score < STRICT_UNRELATED_THRESHOLD
        and signals["entity_overlap_score"] == 0.0
        and signals["conversation_reference_score"] == 0.0
        and signals["timestamp_reference_score"] == 0.0
        and "system_or_help" not in query_types
        and not query_understanding.get("is_ambiguous_without_context")
        and not has_video_cue
        and not strong_topic_match
    )
    return {
        "video_id": video_id,
        "profile_schema_version": profile.get("schema_version"),
        "profile_path": str((repo_root / "data" / "processed" / "scope_profiles" / f"{video_id}.json")),
        "scope_score": round(score, 6),
        "signals": {key: round(value, 6) for key, value in signals.items()},
        "matched_terms": matched_terms,
        "matched_entities": matched_entities,
        "strict_unrelated": strict_unrelated,
        "borderline": not strict_unrelated and score < PROBABLE_RELATED_THRESHOLD,
        "probable_related": (score >= PROBABLE_RELATED_THRESHOLD or has_video_cue or strong_topic_match) and not (clear_general_query and not strong_topic_match),
        "thresholds": {
            "strict_unrelated_threshold": STRICT_UNRELATED_THRESHOLD,
            "probable_related_threshold": PROBABLE_RELATED_THRESHOLD,
        },
        "profile_artifact_counts": profile.get("artifact_counts", {}),
        "answer_mode": AnswerMode(answer_mode).value,
    }


def _terms(text: str) -> set[str]:
    stop = {
        "what", "where", "when", "which", "does", "with", "that", "this", "from",
        "there", "their", "about", "would", "could", "should", "video", "speaker",
        "lecturer", "presenter", "explains", "explain", "shown", "said", "says",
        "into", "then", "than", "have", "will", "your", "they", "them", "using",
        "after", "before", "today", "the", "was", "were", "did", "during", "recording",
        "lecture", "question", "answer", "point", "thing", "part", "can", "you", "for",
        "how", "who", "most", "recent", "world", "cup", "won", "write", "change",
        "important", "difference", "example", "slide", "recommend", "friend", "city",
        "current", "best",
    }
    return {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_+-]{2,}", text)
        if term.lower() not in stop
    }


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left))


def _lexical_cosine(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    left_counts = Counter(left)
    right_counts = Counter(right)
    dot = sum(left_counts[term] * right_counts.get(term, 0) for term in left_counts)
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _speaker_score(query: str, profile: dict[str, Any]) -> float:
    lowered = query.lower()
    speakers = {str(item).lower() for item in profile.get("speakers") or []}
    if re.search(r"\b(who said|speaker|lecturer|presenter)\b", lowered):
        return 1.0 if speakers else 0.4
    return 1.0 if any(speaker and speaker in lowered for speaker in speakers) else 0.0


def _visual_score(query_understanding: dict[str, Any], profile_terms: set[str]) -> float:
    hints = {str(item).lower() for item in (query_understanding.get("objects") or [])}
    hints.update(str(item).lower() for item in (query_understanding.get("attributes") or []))
    if not hints:
        return 0.0
    overlap = hints & profile_terms
    if overlap:
        return min(1.0, len(overlap) / max(1, len(hints)))
    return 0.35 if "visual_memory" in set(query_understanding.get("query_types") or []) else 0.0
