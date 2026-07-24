"""Rule-based parser for vague episodic memory queries.

Extracts visual objects, colors, actions, text clues, spatial clues,
temporal clues, and visual modality clues without LLMs or embeddings.
"""

from __future__ import annotations

import re
from typing import Any

from .contracts import FeatureType, MemoryFeature, MemoryQuery

# Color Vocabulary
COLOR_PATTERNS = {
    "blue",
    "red",
    "green",
    "yellow",
    "black",
    "white",
    "purple",
    "orange",
    "pink",
    "cyan",
    "gray",
    "grey",
}

# Visual Objects & Structures
OBJECT_PATTERNS = {
    "graph",
    "graphs",
    "table",
    "tables",
    "diagram",
    "diagrams",
    "circle",
    "circles",
    "arrow",
    "arrows",
    "image",
    "images",
    "chart",
    "charts",
    "slide",
    "slides",
    "code",
    "terminal",
    "terminals",
    "browser",
    "browsers",
    "window",
    "windows",
    "box",
    "boxes",
}

# Action Verbs
ACTION_PATTERNS = {
    "draw",
    "drew",
    "drawing",
    "compare",
    "compared",
    "comparing",
    "show",
    "showed",
    "showing",
    "shows",
    "write",
    "wrote",
    "writing",
    "highlight",
    "highlighted",
    "highlighting",
    "point",
    "pointed",
    "pointing",
    "explain",
    "explained",
    "explaining",
}

# Visual Modality Indicators
VISUAL_CLUE_PATTERNS = {
    "slide",
    "slides",
    "screen",
    "presentation",
    "table",
    "tables",
    "diagram",
    "diagrams",
    "graph",
    "graphs",
    "chart",
    "charts",
    "board",
    "whiteboard",
    "code",
    "terminal",
    "browser",
    "window",
    "demo",
}

# Spatial & Layout Descriptors
SPATIAL_PATTERNS = {
    "left",
    "right",
    "top",
    "bottom",
    "center",
    "middle",
    "two",
    "three",
    "four",
    "top left",
    "top right",
    "bottom left",
    "bottom right",
}

# Temporal & Sequencing Descriptors
TEMPORAL_PATTERNS = {
    "before",
    "after",
    "earlier",
    "later",
    "beginning",
    "end",
    "middle",
    "during",
    "then",
    "next",
}

# Episodic Memory Language Cues
EPISODIC_MEMORY_PHRASES = (
    "i remember",
    "i recall",
    "i vaguely remember",
    "there was",
    "there were",
    "he drew",
    "she drew",
    "he showed",
    "she showed",
    "they showed",
    "earlier there",
    "after apis",
    "slide with",
    "slide had",
)

EXPLICIT_FACTUAL_QUESTION_PREFIXES = (
    "what ",
    "where ",
    "who ",
    "when ",
    "why ",
    "how ",
    "which ",
    "define ",
    "explain ",
)


def parse_memory_query(query: str) -> MemoryQuery:
    """Parse a vague episodic memory query into structured MemoryQuery using rule-based NLP."""
    if not isinstance(query, str):
        raise TypeError("query must be a string")

    clean_query = query.strip()
    if not clean_query:
        return MemoryQuery(original_query="", features=[], is_memory_query=False)

    words = re.findall(r"\b\w+\b", clean_query)
    words_lower = [w.lower() for w in words]

    features: list[MemoryFeature] = []
    seen_features: set[tuple[str, str]] = set()

    def _add_feature(ftype: FeatureType, val: str, source: str = "rule_based") -> None:
        ft_str = ftype.value if isinstance(ftype, FeatureType) else str(ftype)
        key = (ft_str, val)
        if val and key not in seen_features:
            seen_features.add(key)
            features.append(
                MemoryFeature(
                    feature_type=ftype,
                    value=val,
                    confidence=1.0,
                    source=source,
                )
            )

    # 1. Colors
    for w in words_lower:
        if w in COLOR_PATTERNS:
            _add_feature(FeatureType.COLOR, w)

    # 2. Objects
    for w in words_lower:
        if w in OBJECT_PATTERNS:
            _add_feature(FeatureType.OBJECT, w)

    # 3. Actions
    for w in words_lower:
        if w in ACTION_PATTERNS:
            _add_feature(FeatureType.ACTION, w)

    # 4. Visual Clues
    for w in words_lower:
        if w in VISUAL_CLUE_PATTERNS:
            _add_feature(FeatureType.VISUAL_CLUE, w)

    # Multi-word visual clues (e.g., "blue graph")
    for i in range(len(words_lower) - 1):
        if words_lower[i] in COLOR_PATTERNS and words_lower[i + 1] in OBJECT_PATTERNS:
            _add_feature(FeatureType.VISUAL_CLUE, f"{words_lower[i]} {words_lower[i + 1]}")

    # 5. Spatial Clues
    lower_query = clean_query.lower()
    for spatial_phrase in ("top left", "top right", "bottom left", "bottom right"):
        if spatial_phrase in lower_query:
            _add_feature(FeatureType.SPATIAL_CLUE, spatial_phrase)

    for w in words_lower:
        if w in SPATIAL_PATTERNS:
            if any(w in phrase for phrase in ("top left", "top right", "bottom left", "bottom right")):
                continue
            _add_feature(FeatureType.SPATIAL_CLUE, w)

    # 6. Temporal Clues
    for w in words_lower:
        if w in TEMPORAL_PATTERNS:
            _add_feature(FeatureType.TEMPORAL_CLUE, w)

    # 7. Text Clues
    # a) Quoted text
    quoted_matches = re.findall(r"[\"']([^\"']+)[\"']", clean_query)
    for qm in quoted_matches:
        _add_feature(FeatureType.TEXT_CLUE, qm.strip())

    # b) Capitalized terms & acronyms (e.g. Docker, APIs, MCP, REST, gRPC)
    for word in words:
        if word.isupper() and len(word) >= 2 and word.lower() not in ("the", "and", "for", "was"):
            _add_feature(FeatureType.TEXT_CLUE, word)
        elif word[0].isupper() and len(word) >= 3 and word.lower() not in (
            "the", "there", "this", "that", "what", "where", "when", "why", "how", "after", "before", "earlier", "later"
        ):
            _add_feature(FeatureType.TEXT_CLUE, word)

    # c) Phrases after context triggers
    trigger_match = re.search(
        r"\b(?:comparing|showing|labeled|titled|text|about|with)\s+([A-Za-z0-9_\-\s]{2,30})",
        clean_query,
        re.IGNORECASE,
    )
    if trigger_match:
        extracted = trigger_match.group(1).strip()
        extracted = re.sub(r"\s+(?:in|on|at|the|a|an|video|slide)\b.*$", "", extracted, flags=re.IGNORECASE).strip()
        if extracted and extracted.lower() not in ("a", "an", "the"):
            _add_feature(FeatureType.TEXT_CLUE, extracted)

    # Determine is_memory_query flag
    is_memory = False
    if not any(lower_query.startswith(prefix) for prefix in EXPLICIT_FACTUAL_QUESTION_PREFIXES):
        if any(phrase in lower_query for phrase in EPISODIC_MEMORY_PHRASES) or bool(features):
            is_memory = True

    return MemoryQuery(
        original_query=clean_query,
        features=features,
        is_memory_query=is_memory,
    )
