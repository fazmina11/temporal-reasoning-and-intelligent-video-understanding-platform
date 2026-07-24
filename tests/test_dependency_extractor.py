import unittest

from src.pipeline.knowledge_reconstruction.contracts import ConceptNode, DependencyEdge
from src.pipeline.knowledge_reconstruction.dependency_extractor import (
    DependencyExtractor,
    extract_dependencies,
)


class DependencyExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = DependencyExtractor()

    def test_single_dependency(self) -> None:
        query = "Before explaining MCP he introduced APIs."
        nodes, edges = extract_dependencies(query)

        self.assertGreater(len(nodes), 0)
        self.assertEqual(len(edges), 1)

        edge = edges[0]
        self.assertIsInstance(edge, DependencyEdge)
        self.assertEqual(edge.parent, "APIs")
        self.assertEqual(edge.child, "MCP")

    def test_multiple_dependencies(self) -> None:
        retrieval_results = [
            {"id": "src_1", "text": "Self Attention is introduced before Transformers."},
            {"id": "src_2", "text": "He explains Docker before Containers."},
        ]

        nodes, edges = self.extractor.extract_dependencies(retrieval_results=retrieval_results)

        self.assertGreater(len(nodes), 0)
        self.assertEqual(len(edges), 2)

        parents_children = [(e.parent, e.child) for e in edges]
        self.assertIn(("Self Attention", "Transformers"), parents_children)
        self.assertIn(("Docker", "Containers"), parents_children)


    def test_no_dependency(self) -> None:
        text = "This is a general overview without any prerequisite keywords."
        nodes, edges = extract_dependencies(text)

        self.assertEqual(edges, [])

    def test_circular_dependency_protection(self) -> None:
        retrieval_results = [
            {"id": "src_1", "text": "APIs is introduced before MCP."},
            {"id": "src_2", "text": "MCP is introduced before APIs."},  # Attempt circular edge
        ]

        nodes, edges = extract_dependencies(retrieval_results=retrieval_results)

        # Second edge should be rejected by circular dependency protection
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].parent, "APIs")
        self.assertEqual(edges[0].child, "MCP")

    def test_duplicate_removal(self) -> None:
        retrieval_results = [
            {"id": "src_1", "text": "Before explaining MCP he introduced APIs."},
            {"id": "src_2", "text": "Before explaining MCP he introduced APIs."},
        ]

        nodes, edges = extract_dependencies(retrieval_results=retrieval_results)

        self.assertEqual(len(edges), 1)
        concept_names = [n.concept for n in nodes]
        self.assertEqual(len(concept_names), len(set(concept_names)))

    def test_concept_node_and_edge_to_dict(self) -> None:
        node = ConceptNode("APIs", "src_1", 1000, 5000, 0.95)
        edge = DependencyEdge("APIs", "MCP", "prerequisite_of")

        node_dict = node.to_dict()
        edge_dict = edge.to_dict()

        self.assertEqual(node_dict["concept"], "APIs")
        self.assertEqual(node_dict["source_id"], "src_1")
        self.assertEqual(edge_dict["parent"], "APIs")
        self.assertEqual(edge_dict["child"], "MCP")


if __name__ == "__main__":
    unittest.main()
