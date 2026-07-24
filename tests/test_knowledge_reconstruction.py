import unittest

from src.pipeline.agentic.answer_generator import GroundedAnswerGenerator
from src.pipeline.knowledge_reconstruction.contracts import KnowledgeReconstructionResult
from src.pipeline.knowledge_reconstruction.knowledge_reconstructor import (
    KnowledgeReconstructor,
    is_explanatory_query,
    reconstruct_knowledge,
)


class KnowledgeReconstructionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reconstructor = KnowledgeReconstructor()
        self.evidence = [
            {
                "citation_id": "S1",
                "text": "Before explaining MCP he introduced APIs. First APIs, then Client Server.",
                "start_ms": 1000,
                "end_ms": 5000,
            },
            {
                "citation_id": "S2",
                "text": "Client Server is introduced before Tool Calling. Tool Calling before MCP.",
                "start_ms": 6000,
                "end_ms": 10000,
            },
        ]

    def test_explanatory_question_pipeline(self) -> None:
        query = "Explain MCP"
        self.assertTrue(is_explanatory_query(query))

        result = self.reconstructor.reconstruct_knowledge(query, self.evidence)

        self.assertIsInstance(result, KnowledgeReconstructionResult)
        self.assertEqual(result.target_concept, "MCP")
        self.assertGreater(len(result.learning_path.ordered_concepts), 1)
        self.assertEqual(result.learning_path.ordered_concepts[-1], "MCP")
        self.assertIn("Prerequisite learning path for MCP:", result.reconstruction_summary)
        self.assertGreater(result.confidence, 0.0)

    def test_factual_question_behavior(self) -> None:
        query = "What is the benchmark score for Docker?"
        self.assertFalse(is_explanatory_query(query))

        # Generator answer for factual query should NOT prefix prerequisite learning path
        generator = GroundedAnswerGenerator()
        packet = {
            "question": query,
            "verified_evidence": [
                {
                    "citation_id": "S1",
                    "text": "Docker throughput is 10000 req/sec.",
                    "start_ms": 1000,
                    "end_ms": 5000,
                }
            ],
        }
        res = generator.generate(packet)
        self.assertNotIn("Prerequisite Learning Path:", res["answer"])

    def test_explanatory_question_answer_generator_integration(self) -> None:
        query = "Explain MCP"
        generator = GroundedAnswerGenerator()
        packet = {
            "question": query,
            "verified_evidence": self.evidence,
        }
        res = generator.generate(packet)

        # For explanatory question, Prerequisite Learning Path is automatically prepended
        self.assertIn("Prerequisite Learning Path:", res["answer"])
        self.assertIn("MCP", res["answer"])

    def test_missing_prerequisites(self) -> None:
        query = "Teach me Containers"
        evidence = [
            {"citation_id": "S1", "text": "He explains Docker before Containers.", "start_ms": 1000, "end_ms": 2000}
        ]

        result = reconstruct_knowledge(query, evidence)

        self.assertEqual(result.target_concept, "Containers")
        self.assertIn("Docker", result.learning_path.ordered_concepts)
        self.assertEqual(result.learning_path.ordered_concepts[-1], "Containers")

    def test_multiple_dependency_paths(self) -> None:
        query = "How does Transformers work?"
        evidence = [
            {"citation_id": "S1", "text": "Self Attention is introduced before Transformers.", "start_ms": 1000, "end_ms": 3000},
            {"citation_id": "S2", "text": "Positional Encoding is introduced before Transformers.", "start_ms": 4000, "end_ms": 6000},
        ]

        result = reconstruct_knowledge(query, evidence)

        self.assertIn("Self Attention", result.learning_path.ordered_concepts)
        self.assertIn("Positional Encoding", result.learning_path.ordered_concepts)
        self.assertEqual(result.learning_path.ordered_concepts[-1], "Transformers")

    def test_confidence_propagation(self) -> None:
        query = "Explain MCP"
        result = reconstruct_knowledge(query, self.evidence)

        self.assertEqual(result.confidence, result.learning_path.confidence)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_to_dict_serialization(self) -> None:
        query = "Explain MCP"
        result = reconstruct_knowledge(query, self.evidence)
        res_dict = result.to_dict()

        self.assertEqual(res_dict["target_concept"], "MCP")
        self.assertIn("learning_path", res_dict)
        self.assertIn("prerequisite_concepts", res_dict)
        self.assertIn("reconstruction_summary", res_dict)
        self.assertIn("confidence", res_dict)


if __name__ == "__main__":
    unittest.main()
