import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.contracts import RetrievalPlan, RetrievalStep
from src.pipeline.agentic.query_understanding import is_episodic_memory_query, understand_query
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator


class MemoryRetrievalIntegrationTests(unittest.TestCase):
    def test_episodic_memory_query_detection(self) -> None:
        episodic_queries = [
            "I remember there was a blue graph.",
            "He showed two circles.",
            "There was a table comparing APIs.",
            "The slide had yellow text.",
        ]
        for query in episodic_queries:
            self.assertTrue(
                is_episodic_memory_query(query),
                msg=f"Expected query '{query}' to be classified as episodic memory.",
            )
            understanding = understand_query(raw_query=query)
            self.assertTrue(understanding.get("is_episodic_memory"))

    def test_explicit_factual_query_not_classified_as_episodic(self) -> None:
        factual_queries = [
            "What is MCP?",
            "Define protocol.",
            "Explain the architecture.",
        ]
        for query in factual_queries:
            self.assertFalse(
                is_episodic_memory_query(query),
                msg=f"Expected factual query '{query}' not to be classified as episodic memory.",
            )
            understanding = understand_query(raw_query=query)
            self.assertFalse(understanding.get("is_episodic_memory"))

    def test_orchestrator_invokes_memory_retriever_for_episodic_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            orchestrator = RetrievalOrchestrator(repo_root)

            raw_query = "I remember there was a blue graph."
            understanding = understand_query(raw_query=raw_query)

            # Minimal retrieval plan
            plan = RetrievalPlan(
                strategy="test_strategy",
                retrieval_steps=[
                    RetrievalStep(retriever="sparse_text", level="semantic_chunk", query=raw_query, top_k=1, weight=1.0)
                ],
            )

            result = orchestrator.execute(
                video_id="video_001",
                plan=plan,
                query_understanding=understanding,
            )

            # Check that memory_retriever was automatically invoked in attempts
            attempt_names = [a["retriever"] for a in result["attempts"]]
            self.assertIn("memory_retriever", attempt_names)

    def test_orchestrator_skips_memory_retriever_for_factual_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            orchestrator = RetrievalOrchestrator(repo_root)

            raw_query = "What is MCP?"
            understanding = understand_query(raw_query=raw_query)

            plan = RetrievalPlan(
                strategy="test_strategy",
                retrieval_steps=[
                    RetrievalStep(retriever="sparse_text", level="semantic_chunk", query=raw_query, top_k=1, weight=1.0)
                ],
            )

            result = orchestrator.execute(
                video_id="video_001",
                plan=plan,
                query_understanding=understanding,
            )

            attempt_names = [a["retriever"] for a in result["attempts"]]
            self.assertNotIn("memory_retriever", attempt_names)


if __name__ == "__main__":
    unittest.main()
