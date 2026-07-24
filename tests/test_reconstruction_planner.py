import unittest

from src.pipeline.knowledge_reconstruction.contracts import (
    ConceptNode,
    DependencyEdge,
    LearningPath,
)
from src.pipeline.knowledge_reconstruction.reconstruction_planner import (
    KnowledgeReconstructionPlanner,
    build_learning_path,
)


class ReconstructionPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = KnowledgeReconstructionPlanner()

    def test_linear_chain(self) -> None:
        nodes = [
            ConceptNode("API", "src_1", 1000, 2000, 1.0),
            ConceptNode("Client Server", "src_2", 2000, 3000, 1.0),
            ConceptNode("Tool Calling", "src_3", 3000, 4000, 1.0),
            ConceptNode("MCP", "src_4", 4000, 5000, 1.0),
        ]
        edges = [
            DependencyEdge("API", "Client Server", "prerequisite_of"),
            DependencyEdge("Client Server", "Tool Calling", "prerequisite_of"),
            DependencyEdge("Tool Calling", "MCP", "prerequisite_of"),
        ]

        path = build_learning_path(nodes, edges, "MCP")

        self.assertIsInstance(path, LearningPath)
        self.assertEqual(
            path.ordered_concepts,
            ["API", "Client Server", "Tool Calling", "MCP"],
        )
        self.assertEqual(len(path.dependency_chain), 3)
        self.assertEqual(path.missing_prerequisites, [])
        self.assertGreater(path.confidence, 0.0)

    def test_branching_graph(self) -> None:
        nodes = [
            ConceptNode("API", "src_1"),
            ConceptNode("WebSockets", "src_2"),
            ConceptNode("MCP", "src_3"),
        ]
        edges = [
            DependencyEdge("API", "MCP", "introduced_before"),
            DependencyEdge("WebSockets", "MCP", "prerequisite_of"),
        ]

        path = self.planner.build_learning_path(nodes, edges, "MCP")

        self.assertIn("API", path.ordered_concepts)
        self.assertIn("WebSockets", path.ordered_concepts)
        self.assertEqual(path.ordered_concepts[-1], "MCP")
        self.assertEqual(len(path.dependency_chain), 2)

    def test_cycle_detection(self) -> None:
        nodes = [
            ConceptNode("A", "src_1"),
            ConceptNode("B", "src_2"),
            ConceptNode("C", "src_3"),
        ]
        # Cyclic dependency A -> B -> C -> A
        edges = [
            DependencyEdge("A", "B"),
            DependencyEdge("B", "C"),
            DependencyEdge("C", "A"),
        ]

        path = build_learning_path(nodes, edges, "C")

        # Cycle should be safely broken without infinite looping
        self.assertIn("C", path.ordered_concepts)
        self.assertEqual(len(path.ordered_concepts), 3)
        self.assertEqual(path.ordered_concepts[-1], "C")

    def test_duplicate_nodes(self) -> None:
        nodes = [
            ConceptNode("API", "src_1", confidence=0.8),
            ConceptNode("API", "src_2", confidence=0.95),
            ConceptNode("MCP", "src_3", confidence=1.0),
        ]
        edges = [DependencyEdge("API", "MCP")]

        path = build_learning_path(nodes, edges, "MCP")

        # Duplicate "API" nodes should be deduplicated
        self.assertEqual(path.ordered_concepts, ["API", "MCP"])
        self.assertEqual(len(path.ordered_concepts), len(set(path.ordered_concepts)))

    def test_missing_prerequisite(self) -> None:
        nodes = [
            ConceptNode("MCP", "src_1"),
        ]
        edges = [
            DependencyEdge("UnknownParent", "MCP", "depends_on"),
        ]

        path = build_learning_path(nodes, edges, "MCP")

        self.assertIn("UnknownParent", path.ordered_concepts)
        self.assertIn("UnknownParent", path.missing_prerequisites)
        self.assertEqual(path.ordered_concepts[-1], "MCP")

    def test_single_concept(self) -> None:
        nodes = [ConceptNode("API", "src_1")]
        edges = []

        path = build_learning_path(nodes, edges, "API")

        self.assertEqual(path.ordered_concepts, ["API"])
        self.assertEqual(path.dependency_chain, [])
        self.assertEqual(path.missing_prerequisites, [])
        self.assertEqual(path.confidence, 1.0)

    def test_to_dict_serialization(self) -> None:
        path = LearningPath(
            ordered_concepts=["API", "MCP"],
            dependency_chain=[DependencyEdge("API", "MCP")],
            missing_prerequisites=[],
            confidence=0.95,
        )
        p_dict = path.to_dict()

        self.assertEqual(p_dict["ordered_concepts"], ["API", "MCP"])
        self.assertEqual(len(p_dict["dependency_chain"]), 1)
        self.assertEqual(p_dict["confidence"], 0.95)


if __name__ == "__main__":
    unittest.main()
