from __future__ import annotations

import re
from typing import Any
from uuid import uuid4


QUERY_TYPES = {
    "definition",
    "concept",
    "exact_quote",
    "exact_timestamp",
    "approximate_timestamp",
    "visual_memory",
    "action_memory",
    "ocr_or_slide_text",
    "speaker_question",
    "audio_memory",
    "before_after",
    "cause_effect",
    "comparison",
    "repeated_concept",
    "summary",
    "chapter_summary",
    "entity_tracking",
    "follow_up",
    "cross_video",
    "system_or_help",
    "unrelated_or_general",
    "unsafe_or_disallowed",
    "unknown",
}

VISUAL_CUES = {
    "graph",
    "chart",
    "diagram",
    "slide",
    "screen",
    "image",
    "frame",
    "drawing",
    "draw",
    "blue",
    "red",
    "green",
    "color",
    "shown",
    "displayed",
}
ACTION_CUES = {"draw", "move", "click", "open", "close", "write", "compare", "show", "switch"}
TEMPORAL_CUES = {"before", "after", "during", "around", "later", "earlier", "then", "next"}
SUMMARY_CUES = {"summarize", "summary", "overview", "recap", "chapter"}
SYSTEM_CUES = {"upload", "run", "install", "error", "port", "github", "readme", "api endpoint"}
GENERAL_CUES = {"weather", "today", "news", "president", "stock price", "who invented"}
OCR_CUES = {"text on screen", "on-screen text", "written", "caption", "title", "heading", "slide says", "read the slide"}
AUDIO_CUES = {"music", "sound", "audio", "noise", "silent", "silence", "hear", "heard", "voice"}


def parse_time_to_ms(text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    pattern = re.compile(r"(?<!\d)(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?!\d)|\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?)\b", re.I)
    for match in pattern.finditer(text):
        if match.group(2) is not None:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            total_ms = ((hours * 3600) + (minutes * 60) + seconds) * 1000
            raw = match.group(0)
        else:
            value = float(match.group(4))
            unit = match.group(5).lower()
            total_ms = int(value * 60_000) if unit.startswith("min") else int(value * 1000)
            raw = match.group(0)
        matches.append({"raw": raw, "target_ms": total_ms})
    return matches


def parse_quoted_phrases(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"[\"']([^\"']{2,})[\"']", text) if m.group(1).strip()]


def understand_query(*, raw_query: str, standalone_query: str | None = None) -> dict[str, Any]:
    query = (standalone_query or raw_query).strip()
    lowered = query.lower()
    query_types: set[str] = set()
    time_constraints = parse_time_to_ms(query)
    quoted_phrases = parse_quoted_phrases(query)

    if quoted_phrases:
        query_types.add("exact_quote")
    if time_constraints:
        query_types.add("exact_timestamp")
    if any(cue in lowered for cue in VISUAL_CUES):
        query_types.add("visual_memory")
    if any(cue in lowered for cue in OCR_CUES):
        query_types.add("ocr_or_slide_text")
    if any(cue in lowered for cue in AUDIO_CUES):
        query_types.add("audio_memory")
    if any(cue in lowered for cue in ACTION_CUES):
        query_types.add("action_memory")
    if any(cue in lowered for cue in TEMPORAL_CUES):
        query_types.add("before_after")
    if any(word in lowered for word in ("why", "reason", "because")):
        query_types.add("cause_effect")
    if any(word in lowered for word in ("compare", "versus", " vs ", "difference", "similar")):
        query_types.add("comparison")
    if any(cue in lowered for cue in SUMMARY_CUES):
        query_types.add("summary")
    if "chapter" in lowered:
        query_types.add("chapter_summary")
    if any(cue in lowered for cue in SYSTEM_CUES):
        query_types.add("system_or_help")
    if any(cue in lowered for cue in GENERAL_CUES):
        query_types.add("unrelated_or_general")
    if re.search(r"\b(what is|define|meaning of|explain)\b", lowered):
        query_types.update({"definition", "concept"})
    if re.search(r"\b(he|she|speaker|lecturer|presenter|who said)\b", lowered):
        query_types.add("speaker_question")
    if re.search(r"\b(that|this|there|same|previous|after that|before that)\b", lowered):
        query_types.add("follow_up")
    if re.search(r"\b(again|return|repeated|another time|elsewhere)\b", lowered):
        query_types.add("repeated_concept")

    entities = _extract_entities(query)
    visual_hints = sorted({cue for cue in VISUAL_CUES if cue in lowered})
    actions = sorted({cue for cue in ACTION_CUES if cue in lowered})
    temporal_relations = sorted({cue for cue in TEMPORAL_CUES if cue in lowered})
    required_modalities = ["transcript"]
    if "visual_memory" in query_types:
        required_modalities.insert(0, "visual")
    if "ocr_or_slide_text" in query_types:
        required_modalities.insert(0, "ocr")
    if "speaker_question" in query_types:
        required_modalities.insert(0, "speaker")
    if "audio_memory" in query_types:
        required_modalities.insert(0, "audio")

    if not query_types:
        query_types.add("unknown")

    return {
        "query_id": f"query_{uuid4().hex[:12]}",
        "raw_query": raw_query,
        "standalone_query": query,
        "normalized_query": _normalize(query),
        "query_types": sorted(query_types),
        "entities": entities,
        "persons": [],
        "objects": visual_hints,
        "attributes": [cue for cue in visual_hints if cue in {"blue", "red", "green", "color"}],
        "actions": actions,
        "quoted_phrases": quoted_phrases,
        "ocr_hints": sorted({cue for cue in OCR_CUES if cue in lowered}),
        "time_constraints": time_constraints,
        "temporal_relations": temporal_relations,
        "requested_granularity": _granularity(query_types),
        "required_modalities": required_modalities,
        "requires_multi_moment_reasoning": bool(query_types & {"comparison", "before_after", "repeated_concept", "cause_effect"}),
        "requires_visual_search": "visual" in required_modalities,
        "requires_transcript_search": True,
        "requires_event_search": bool(query_types & {"summary", "comparison", "cause_effect", "definition", "concept"}),
        "classification_confidence": 0.85 if "unknown" not in query_types else 0.45,
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_entities(text: str) -> list[str]:
    entities = set(re.findall(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*\b", text))
    acronyms = set(re.findall(r"\b[A-Z]{2,}\b", text))
    return sorted(entities | acronyms)


def _granularity(query_types: set[str]) -> str:
    if "exact_timestamp" in query_types or "exact_quote" in query_types:
        return "atom"
    if "summary" in query_types or "chapter_summary" in query_types:
        return "event"
    if "visual_memory" in query_types or "cause_effect" in query_types:
        return "event"
    return "semantic_chunk"
