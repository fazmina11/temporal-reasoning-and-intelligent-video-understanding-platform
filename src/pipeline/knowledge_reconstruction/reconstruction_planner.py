"""Knowledge Reconstruction Planner for constructing prerequisite learning paths.

Constructs topologically sorted learning paths leading to a target concept while removing duplicates,
detecting cycles, selecting highest-confidence paths, and flagging missing prerequisites.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence

from .contracts import ConceptNode, DependencyEdge, LearningPath


class KnowledgeReconstructionPlanner:
    """Planner for reconstructing ordered prerequisite learning paths for target concepts."""

    def build_learning_path(
        self,
        concept_nodes: Sequence[ConceptNode],
        dependency_edges: Sequence[DependencyEdge],
        target_concept: str,
    ) -> LearningPath:
        """Construct an ordered prerequisite learning path leading to target_concept."""
        if not target_concept or not target_concept.strip():
            return LearningPath(ordered_concepts=[], dependency_chain=[], missing_prerequisites=[], confidence=0.0)

        node_by_norm: dict[str, ConceptNode] = {}
        casing_by_norm: dict[str, str] = {}

        for node in concept_nodes:
            norm = node.concept.strip().lower()
            if norm not in node_by_norm or node.confidence > node_by_norm[norm].confidence:
                node_by_norm[norm] = node
            casing_by_norm[norm] = node.concept.strip()

        target_norm = target_concept.strip().lower()
        if target_norm not in casing_by_norm:
            casing_by_norm[target_norm] = target_concept.strip()

        parent_to_children: dict[str, set[str]] = defaultdict(set)
        child_to_parents: dict[str, set[str]] = defaultdict(set)
        edge_map: dict[tuple[str, str], DependencyEdge] = {}

        for edge in dependency_edges:
            p_norm = edge.parent.strip().lower()
            c_norm = edge.child.strip().lower()

            if p_norm not in casing_by_norm:
                casing_by_norm[p_norm] = edge.parent.strip()
            if c_norm not in casing_by_norm:
                casing_by_norm[c_norm] = edge.child.strip()

            if p_norm != c_norm:
                parent_to_children[p_norm].add(c_norm)
                child_to_parents[c_norm].add(p_norm)
                edge_map[(p_norm, c_norm)] = edge

        # Find all ancestor prerequisite concepts required to reach target_concept
        required_concepts: set[str] = {target_norm}
        visited_ancestors: set[str] = set()
        queue = deque([target_norm])

        while queue:
            curr = queue.popleft()
            if curr in visited_ancestors:
                continue
            visited_ancestors.add(curr)
            required_concepts.add(curr)

            for parent in child_to_parents.get(curr, set()):
                if parent not in visited_ancestors:
                    queue.append(parent)

        # Build sub-graph for required_concepts
        sub_in_degree: dict[str, int] = {c: 0 for c in required_concepts}
        sub_adj: dict[str, set[str]] = defaultdict(set)

        for p in required_concepts:
            for c in parent_to_children.get(p, set()):
                if c in required_concepts:
                    sub_adj[p].add(c)
                    sub_in_degree[c] += 1

        # Topological sorting via Kahn's Algorithm
        topo_queue = deque([c for c in required_concepts if sub_in_degree[c] == 0])
        ordered_norms: list[str] = []

        while topo_queue:
            curr = topo_queue.popleft()
            ordered_norms.append(curr)

            for nxt in sub_adj.get(curr, set()):
                sub_in_degree[nxt] -= 1
                if sub_in_degree[nxt] == 0:
                    topo_queue.append(nxt)

        # Cycle detection fallback (if graph contains cycles, append remaining nodes deterministically)
        if len(ordered_norms) < len(required_concepts):
            remaining = [c for c in required_concepts if c not in ordered_norms]
            for r in remaining:
                if r not in ordered_norms:
                    ordered_norms.append(r)
            if target_norm in ordered_norms:
                ordered_norms.remove(target_norm)
                ordered_norms.append(target_norm)

        # Format ordered concepts with clean display casing
        ordered_concepts: list[str] = []
        seen_concepts: set[str] = set()
        for norm in ordered_norms:
            display = casing_by_norm.get(norm, norm)
            if norm not in seen_concepts:
                seen_concepts.add(norm)
                ordered_concepts.append(display)

        # Construct dependency chain edges along ordered concepts path
        dependency_chain: list[DependencyEdge] = []
        seen_chain_edges: set[tuple[str, str]] = set()

        for i in range(len(ordered_norms)):
            p_norm = ordered_norms[i]
            for j in range(i + 1, len(ordered_norms)):
                c_norm = ordered_norms[j]
                if (p_norm, c_norm) in edge_map and (p_norm, c_norm) not in seen_chain_edges:
                    seen_chain_edges.add((p_norm, c_norm))
                    dependency_chain.append(edge_map[(p_norm, c_norm)])

        # Identify missing prerequisite nodes
        missing_prerequisites: list[str] = []
        for norm in ordered_norms:
            if norm != target_norm and norm not in node_by_norm:
                missing_prerequisites.append(casing_by_norm.get(norm, norm))

        # Calculate overall path confidence
        confidences = [node_by_norm[c].confidence for c in ordered_norms if c in node_by_norm]
        confidence = round(sum(confidences) / len(confidences), 4) if confidences else (1.0 if ordered_concepts else 0.0)

        return LearningPath(
            ordered_concepts=ordered_concepts,
            dependency_chain=dependency_chain,
            missing_prerequisites=missing_prerequisites,
            confidence=confidence,
        )


def build_learning_path(
    concept_nodes: Sequence[ConceptNode],
    dependency_edges: Sequence[DependencyEdge],
    target_concept: str,
) -> LearningPath:
    """Convenience entrypoint for building a learning path."""
    planner = KnowledgeReconstructionPlanner()
    return planner.build_learning_path(concept_nodes, dependency_edges, target_concept)
