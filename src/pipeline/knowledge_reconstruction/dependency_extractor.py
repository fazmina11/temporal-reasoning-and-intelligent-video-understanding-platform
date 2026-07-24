"""Dependency Extractor for Knowledge Reconstruction.

Extracts concept nodes and prerequisite dependency edges from retrieved video text,
OCR, events, and query contexts using lightweight rule-based heuristics without LLMs.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ConceptNode, DependencyEdge

STOP_WORDS = {
    "the", "a", "an", "he", "she", "they", "we", "you", "it", "this", "that",
    "is", "was", "are", "were", "be", "been", "being", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "about", "into", "through", "after",
    "before", "then", "next", "finally", "explained", "explaining", "explains",
    "introduced", "introducing", "introduces", "presented", "presenting",
    "showed", "showing", "shows", "covered", "covering", "covers",
}


def _clean_concept(text: str) -> str:
    """Clean and normalize a raw concept string."""
    cleaned = text.strip()
    cleaned = re.sub(r"^[^\w\s]+|[^\w\s]+$", "", cleaned)
    words = cleaned.split()
    while words and words[0].lower() in STOP_WORDS:
        words.pop(0)
    while words and words[-1].lower() in STOP_WORDS:
        words.pop(-1)
    result = " ".join(words).strip()
    return result


def _creates_cycle(parent: str, child: str, graph: dict[str, set[str]]) -> bool:
    """Check if adding parent -> child would create a cycle (i.e. child can reach parent)."""
    p_norm = parent.strip().lower()
    c_norm = child.strip().lower()

    if p_norm == c_norm:
        return True

    visited: set[str] = set()
    queue = [c_norm]

    while queue:
        curr = queue.pop(0)
        if curr == p_norm:
            return True
        visited.add(curr)
        for nxt in graph.get(curr, set()):
            if nxt not in visited:
                queue.append(nxt)

    return False


class DependencyExtractor:
    """Extracts prerequisite knowledge concepts and dependency edges from video evidence."""

    def extract_dependencies(
        self,
        query: str | None = None,
        retrieval_results: Sequence[dict[str, Any]] | Mapping[str, Sequence[dict[str, Any]]] | None = None,
    ) -> tuple[list[ConceptNode], list[DependencyEdge]]:
        """Extract concept nodes and prerequisite dependency edges."""
        text_sources: list[tuple[str, str, int | float | None, int | float | None]] = []

        if query and isinstance(query, str) and query.strip():
            text_sources.append((query.strip(), "query", None, None))

        if retrieval_results:
            if isinstance(retrieval_results, Mapping):
                for modality, items in retrieval_results.items():
                    if isinstance(items, Sequence):
                        for idx, item in enumerate(items):
                            if isinstance(item, dict):
                                sid = str(item.get("id") or item.get("source_id") or f"{modality}_{idx}")
                                txt = str(
                                    item.get("text")
                                    or item.get("transcript")
                                    or item.get("ocr_text")
                                    or item.get("caption")
                                    or item.get("description")
                                    or item.get("title")
                                    or ""
                                )
                                t_start = item.get("start_ms") or item.get("timestamp_ms") or item.get("start_seconds")
                                t_end = item.get("end_ms") or item.get("end_seconds") or t_start
                                if txt.strip():
                                    text_sources.append((txt.strip(), sid, t_start, t_end))
            elif isinstance(retrieval_results, Sequence):
                for idx, item in enumerate(retrieval_results):
                    if isinstance(item, dict):
                        sid = str(item.get("id") or item.get("source_id") or item.get("candidate_id") or f"src_{idx}")
                        txt = str(
                            item.get("text")
                            or item.get("transcript")
                            or item.get("ocr_text")
                            or item.get("caption")
                            or item.get("description")
                            or item.get("text_content")
                            or ""
                        )
                        t_start = item.get("start_ms") or item.get("timestamp_start") or item.get("timestamp_ms")
                        t_end = item.get("end_ms") or item.get("timestamp_end") or t_start
                        if txt.strip():
                            text_sources.append((txt.strip(), sid, t_start, t_end))

        nodes_map: dict[str, ConceptNode] = {}
        edges: list[DependencyEdge] = []
        seen_edges: set[tuple[str, str]] = set()
        graph: dict[str, set[str]] = defaultdict(set)

        def _add_node(raw_concept: str, sid: str, t_start: int | float | None, t_end: int | float | None) -> str:
            cleaned = _clean_concept(raw_concept)
            if not cleaned or len(cleaned) < 2:
                return ""
            norm = cleaned.lower()
            if norm not in nodes_map:
                nodes_map[norm] = ConceptNode(
                    concept=cleaned,
                    source_id=sid,
                    timestamp_start=t_start,
                    timestamp_end=t_end,
                    confidence=1.0,
                )
            return cleaned

        def _add_edge(parent_concept: str, child_concept: str, relation: str = "prerequisite_of") -> None:
            p_clean = _clean_concept(parent_concept)
            c_clean = _clean_concept(child_concept)

            if not p_clean or not c_clean:
                return

            p_norm = p_clean.lower()
            c_norm = c_clean.lower()

            if p_norm == c_norm:
                return

            edge_key = (p_norm, c_norm)
            if edge_key in seen_edges:
                return

            # Check circular dependency protection
            if _creates_cycle(p_clean, c_clean, graph):
                return

            seen_edges.add(edge_key)
            graph[p_norm].add(c_norm)

            edges.append(
                DependencyEdge(
                    parent=p_clean,
                    child=c_clean,
                    relation=relation,
                )
            )

        # Regex patterns for heuristic dependency extraction
        patterns = [
            # Pattern 1: "Before (explaining|introducing) Child he introduced Parent."
            (
                re.compile(
                    r"\bBefore\s+(?:explaining|introducing|using|showing|covering)?\s*([A-Za-z0-9_\-\s]{2,30}?)\s+(?:he|she|they|speaker|we)?\s*(?:introduced|explained|presented|showed|covered)\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\.|$|,)",
                    re.IGNORECASE,
                ),
                lambda m: (m.group(2), m.group(1), "prerequisite_of"),
            ),
            # Pattern 2: "Parent is introduced before Child" or "Parent before Child"
            (
                re.compile(
                    r"\b([A-Za-z0-9_\-\s]{2,30}?)\s+(?:is|was)?\s*(?:introduced|explained|presented|covered|shown)?\s+before\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\.|$|,)",
                    re.IGNORECASE,
                ),
                lambda m: (m.group(1), m.group(2), "introduced_before"),
            ),
            # Pattern 3: "Child (depends on|requires|is based on) Parent"
            (
                re.compile(
                    r"\b([A-Za-z0-9_\-\s]{2,30}?)\s+(?:depends\s+on|requires|is\s+based\s+on|needs)\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\.|$|,)",
                    re.IGNORECASE,
                ),
                lambda m: (m.group(2), m.group(1), "depends_on"),
            ),
            # Pattern 4: "He explains Parent before Child" -> He explains Docker before Containers => Docker -> Containers
            (
                re.compile(
                    r"\b(?:he|she|they)?\s*(?:explains|explained|introduced|covered|shows|showed)\s+([A-Za-z0-9_\-\s]{2,30}?)\s+before\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\.|$|,)",
                    re.IGNORECASE,
                ),
                lambda m: (m.group(1), m.group(2), "prerequisite_of"),
            ),

            # Pattern 5: "First Parent, then/next Child"
            (
                re.compile(
                    r"\b(?:first|initially)\s+([A-Za-z0-9_\-\s]{2,30}?),(?:\s*then|\s*next|\s*later)?\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\.|$|,)",
                    re.IGNORECASE,
                ),
                lambda m: (m.group(1), m.group(2), "prerequisite_of"),
            ),
            # Pattern 6: "Parent is a prerequisite for Child"
            (
                re.compile(
                    r"\b([A-Za-z0-9_\-\s]{2,30}?)\s+is\s+a\s+prerequisite\s+(?:for|to)\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\.|$|,)",
                    re.IGNORECASE,
                ),
                lambda m: (m.group(1), m.group(2), "prerequisite_of"),
            ),
        ]

        for text, sid, t_start, t_end in text_sources:
            # Extract concepts from technical terms, acronyms, and capitalized phrases
            cap_terms = re.findall(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*\b", text)
            for term in cap_terms:
                _add_node(term, sid, t_start, t_end)

            for pattern, extractor in patterns:
                for match in pattern.finditer(text):
                    try:
                        p_raw, c_raw, rel = extractor(match)
                        p_node = _add_node(p_raw, sid, t_start, t_end)
                        c_node = _add_node(c_raw, sid, t_start, t_end)
                        if p_node and c_node:
                            _add_edge(p_node, c_node, rel)
                    except Exception:
                        continue

        nodes_list = list(nodes_map.values())
        return nodes_list, edges


# Convenience function exposing extract_dependencies directly
def extract_dependencies(
    query: str | None = None,
    retrieval_results: Sequence[dict[str, Any]] | Mapping[str, Sequence[dict[str, Any]]] | None = None,
) -> tuple[list[ConceptNode], list[DependencyEdge]]:
    """Convenience entrypoint for dependency extraction."""
    extractor = DependencyExtractor()
    return extractor.extract_dependencies(query, retrieval_results)
