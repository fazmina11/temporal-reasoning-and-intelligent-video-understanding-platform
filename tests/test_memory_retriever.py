import unittest

from src.pipeline.memory_recovery.contracts import CandidateMemory, MemoryQuery, MemoryRetrievalResult
from src.pipeline.memory_recovery.memory_parser import parse_memory_query
from src.pipeline.memory_recovery.memory_retriever import MemoryRetriever, retrieve_memory


def make_sample_context() -> dict[str, list[dict[str, object]]]:
    return {
        "ocr": [
            {
                "id": "ocr_101",
                "ocr_text": "Quarterly Performance Benchmarks for Docker Containers",
                "start_ms": 1000,
                "end_ms": 5000,
                "tags": ["docker", "benchmarks"],
            }
        ],
        "frames": [
            {
                "id": "frame_101",
                "caption": "Frame displaying a blue graph with performance metrics",
                "timestamp_ms": 2000,
                "colors": ["blue"],
                "objects": ["graph"],
            }
        ],
        "events": [
            {
                "id": "event_101",
                "title": "Demonstration of Docker blue graph",
                "start_ms": 1500,
                "end_ms": 4500,
            }
        ],
    }


class PhaseN11MemoryRetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = make_sample_context()
        self.retriever = MemoryRetriever(self.context)

    def test_valid_memory_query(self) -> None:
        query = "I remember there was a blue graph."
        result = self.retriever.retrieve_memory(query)

        self.assertIsInstance(result, MemoryRetrievalResult)
        self.assertEqual(result.original_query, query)
        self.assertEqual(result.query, query)
        self.assertTrue(result.parsed_query.is_memory_query)

        self.assertGreater(len(result.candidates), 0)
        self.assertIsNotNone(result.best_candidate)

        self.assertEqual(result.best_candidate.source_id, "frame_101")
        self.assertEqual(result.confidence, result.best_candidate.score)
        self.assertGreater(result.confidence, 0.0)

        self.assertIn("color:blue", result.matched_features)
        self.assertIn("object:graph", result.matched_features)

        self.assertGreaterEqual(result.retrieval_time_ms, 0.0)

    def test_normal_factual_question_no_exception(self) -> None:
        query = "What is MCP?"
        result = self.retriever.retrieve_memory(query)

        self.assertIsInstance(result, MemoryRetrievalResult)
        self.assertEqual(result.original_query, query)
        self.assertFalse(result.parsed_query.is_memory_query)

        self.assertEqual(result.candidates, [])
        self.assertIsNone(result.best_candidate)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.matched_features, [])
        self.assertGreaterEqual(result.retrieval_time_ms, 0.0)

    def test_empty_query(self) -> None:
        result = retrieve_memory("", self.context)

        self.assertEqual(result.original_query, "")
        self.assertFalse(result.parsed_query.is_memory_query)
        self.assertEqual(result.candidates, [])
        self.assertIsNone(result.best_candidate)
        self.assertEqual(result.confidence, 0.0)

    def test_no_candidates_found(self) -> None:
        query = "I remember a purple dragon dancing in a spaceship."
        result = self.retriever.retrieve_memory(query)

        self.assertTrue(result.parsed_query.is_memory_query)
        self.assertEqual(result.candidates, [])
        self.assertIsNone(result.best_candidate)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.matched_features, [])

    def test_multiple_candidates_best_candidate_selection(self) -> None:
        query = "I remember a blue graph with Docker benchmarks."
        result = self.retriever.retrieve_memory(query, top_k=3)

        self.assertGreater(len(result.candidates), 1)
        self.assertIsNotNone(result.best_candidate)
        self.assertEqual(result.best_candidate, result.candidates[0])
        self.assertEqual(result.confidence, result.candidates[0].score)

    def test_confidence_propagation_and_retrieval_timing(self) -> None:
        query = "There was a slide with Docker."
        result = self.retriever.retrieve_memory(query)

        self.assertIsNotNone(result.best_candidate)
        self.assertEqual(result.confidence, result.best_candidate.score)
        self.assertGreaterEqual(result.retrieval_time_ms, 0.0)

    def test_to_dict_structure(self) -> None:
        query = "I remember there was a blue graph."
        result = self.retriever.retrieve_memory(query)
        res_dict = result.to_dict()

        self.assertEqual(res_dict["original_query"], query)
        self.assertIn("parsed_query", res_dict)
        self.assertIn("candidates", res_dict)
        self.assertIn("best_candidate", res_dict)
        self.assertIn("confidence", res_dict)
        self.assertIn("matched_features", res_dict)
        self.assertIn("retrieval_time_ms", res_dict)


if __name__ == "__main__":
    unittest.main()
