"""Knowledge Reconstructor for Phase N12.

Pipeline:
1. Identify target concept from query.
2. Extract prerequisite dependency edges and concept nodes using DependencyExtractor.
3. Construct topologically sorted learning path using KnowledgeReconstructionPlanner.
4. Return KnowledgeReconstructionResult.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import (
    KnowledgeReconstructionResult,
    LearningPath,
)
from .dependency_extractor import DependencyExtractor
from .reconstruction_planner import build_learning_path

EXPLANATORY_PREFIXES = (
    "explain ",
    "teach me ",
    "how does ",
    "how do ",
    "overview of ",
    "understand ",
    "learn ",
    "guide to ",
    "walkthrough of ",
    "tutorial on ",
)


def is_explanatory_query(query: str) -> bool:
    """Determine if a query is an explanatory question requiring prerequisite reconstruction."""
    if not query or not isinstance(query, str):
        return False
    q = query.strip().lower()
    return any(q.startswith(kw) or f" {kw.strip()} " in f" {q} " for kw in EXPLANATORY_PREFIXES)


def extract_target_concept(query: str) -> str:
    """Extract primary subject concept from explanatory queries like 'Explain MCP'."""
    if not query or not isinstance(query, str):
        return ""

    q = query.strip()
    match = re.search(
        r"(?:explain|teach\s+me|how\s+does|how\s+do|overview\s+of|details\s+on)\s+([A-Za-z0-9_\-\s]{2,30}?)(?:\s+work|\?|\.|$)",
        q,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    cap_match = re.findall(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*\b", q)
    if cap_match:
        return cap_match[-1].strip()

    cleaned = re.sub(
        r"^(?:explain|teach\s+me|how|what|why|is|are|the|a|an|\s)+",
        "",
        q,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[?\.]+$", "", cleaned).strip()
    return cleaned if cleaned else q


class KnowledgeReconstructor:
    """Orchestrates concept identification, dependency extraction, and learning path construction."""

    def __init__(self) -> None:
        self.extractor = DependencyExtractor()

    def reconstruct_knowledge(
        self,
        query: str,
        retrieval_results: Sequence[dict[str, Any]] | Mapping[str, Sequence[dict[str, Any]]] | None = None,
    ) -> KnowledgeReconstructionResult:
        """Run the end-to-end knowledge reconstruction pipeline."""
        target_concept = extract_target_concept(query)

        # 1. Extract dependencies
        nodes, edges = self.extractor.extract_dependencies(query, retrieval_results)

        # 2. Construct learning path
        learning_path = build_learning_path(nodes, edges, target_concept)

        # 3. Prerequisites list (concepts before target)
        prerequisites = [c for c in learning_path.ordered_concepts if c.lower() != target_concept.lower()]

        # 4. Human-readable summary
        if learning_path.ordered_concepts:
            chain_str = " -> ".join(learning_path.ordered_concepts)
            summary = f"Prerequisite learning path for {target_concept}: {chain_str}"
        else:
            summary = f"No prerequisite dependencies found for {target_concept}."

        if learning_path.missing_prerequisites:
            missing_str = ", ".join(learning_path.missing_prerequisites)
            summary += f" (Missing prerequisites: {missing_str})"

        return KnowledgeReconstructionResult(
            target_concept=target_concept,
            learning_path=learning_path,
            prerequisite_concepts=prerequisites,
            reconstruction_summary=summary,
            confidence=learning_path.confidence,
        )


def reconstruct_knowledge(
    query: str,
    retrieval_results: Sequence[dict[str, Any]] | Mapping[str, Sequence[dict[str, Any]]] | None = None,
) -> KnowledgeReconstructionResult:
    """Convenience entrypoint for knowledge reconstruction."""
    reconstructor = KnowledgeReconstructor()
    return reconstructor.reconstruct_knowledge(query, retrieval_results)
