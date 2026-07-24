import unittest

from src.pipeline.memory_recovery.contracts import CandidateMemory, MemoryQuery
from src.pipeline.memory_recovery.memory_candidate_generator import (
    generate_candidates,
    generate_memory_candidates,
)
from src.pipeline.memory_recovery.memory_parser import parse_memory_query


def make_test_retrieval_context() -> dict[str, list[dict[str, object]]]:
    return {
        "ocr": [
            {
                "id": "ocr_101",
                "ocr_text": "Quarterly Performance Benchmarks for Docker Containers",
                "start_ms": 1000,
                "end_ms": 5000,
                "tags": ["docker", "benchmarks"],
            },
            {
                "id": "ocr_102",
                "ocr_text": "API Protocol Specs",
                "start_ms": 6000,
                "end_ms": 9000,
                "tags": ["api"],
            },
        ],
        "frames": [
            {
                "id": "frame_101",
                "caption": "Frame displaying a blue graph with performance metrics",
                "timestamp_ms": 2000,
                "colors": ["blue"],
                "objects": ["graph"],
            },
            {
                "id": "frame_102",
                "caption": "Red diagram showing two circles",
                "timestamp_ms": 7000,
                "colors": ["red"],
                "objects": ["circles", "diagram"],
            },
        ],
        "semantic_chunks": [
            {
                "id": "chunk_101",
                "transcript": "Here we see a blue graph comparing Docker container performance.",
                "start_ms": 1000,
                "end_ms": 5000,
            }
        ],
        "events": [
            {
                "id": "event_101",
                "title": "Demonstration of Docker blue graph",
                "description": "Presenter showed the blue graph.",
                "start_ms": 1500,
                "end_ms": 4500,
            }
        ],
    }


class PhaseN112CandidateGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = make_test_retrieval_context()

    def test_color_match(self) -> None:
        query = "I remember a blue chart."
        candidates = generate_candidates(query, self.context)

        self.assertGreater(len(candidates), 0)
        blue_matches = [c for c in candidates if any("color:blue" in f for f in c.matched_features)]
        self.assertGreater(len(blue_matches), 0)

        top = candidates[0]
        self.assertEqual(top.source_id, "frame_101")
        self.assertIn("color:blue", top.matched_features)

    def test_object_match(self) -> None:
        query = "He showed two circles."
        candidates = generate_candidates(query, self.context)

        self.assertGreater(len(candidates), 0)
        circle_candidate = candidates[0]
        self.assertEqual(circle_candidate.source_id, "frame_102")
        self.assertIn("object:circles", circle_candidate.matched_features)

    def test_ocr_text_match(self) -> None:
        query = "There was a slide with Docker."
        candidates = generate_candidates(query, self.context)

        self.assertGreater(len(candidates), 0)
        ocr_candidate = candidates[0]
        self.assertEqual(ocr_candidate.source_type, "ocr")
        self.assertEqual(ocr_candidate.source_id, "ocr_101")
        self.assertIn("text_clue:Docker", ocr_candidate.matched_features)

    def test_multiple_feature_match(self) -> None:
        query = "I remember a blue graph with Docker performance benchmarks."
        candidates = generate_candidates(query, self.context)

        self.assertGreater(len(candidates), 0)
        top_cand = candidates[0]
        # Should match color:blue, object:graph, and text_clue:Docker
        matched = top_cand.matched_features
        self.assertTrue(any("color:blue" in f for f in matched))
        self.assertTrue(any("object:graph" in f for f in matched))

    def test_no_match(self) -> None:
        query = "I remember a purple dragon dancing in a spaceship."
        candidates = generate_candidates(query, self.context)

        self.assertEqual(len(candidates), 0)

    def test_ranking_order(self) -> None:
        query = "I remember a blue graph with Docker benchmarks."
        candidates = generate_candidates(query, self.context)

        self.assertGreater(len(candidates), 1)
        scores = [c.score for c in candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_backward_compatibility_properties(self) -> None:
        query = "I remember a blue graph."
        candidates = generate_candidates(query, self.context)

        self.assertGreater(len(candidates), 0)
        top = candidates[0]

        # Verify new fields
        self.assertIsInstance(top.source_type, str)
        self.assertIsInstance(top.source_id, str)
        self.assertIsInstance(top.score, float)
        self.assertIsInstance(top.evidence, dict)

        # Verify backward compatibility properties
        self.assertEqual(top.candidate_id, top.source_id)
        self.assertEqual(top.modality, top.source_type)
        self.assertEqual(top.start_ms, top.timestamp_start)
        self.assertEqual(top.end_ms, top.timestamp_end)
        self.assertIsInstance(top.text_content, str)
        self.assertIsInstance(top.metadata, dict)


if __name__ == "__main__":
    unittest.main()
