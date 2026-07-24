import unittest

from src.pipeline.memory_recovery.contracts import CandidateMemory
from src.pipeline.memory_recovery.memory_ranker import (
    calculate_rerank_score,
    rank_candidates,
    rank_memory_candidates,
)


class PhaseN11MemoryRankerTests(unittest.TestCase):
    def test_single_candidate(self) -> None:
        cand = CandidateMemory(
            source_type="frame",
            source_id="frame_101",
            timestamp_start=2000,
            timestamp_end=2000,
            matched_features=["color:blue", "object:graph"],
            score=5.0,
            evidence={"caption": "Blue graph on screen"},
        )

        ranked = rank_candidates([cand])
        self.assertEqual(len(ranked), 1)

        res = ranked[0]
        # Score normalized between 0.0 and 1.0
        self.assertGreaterEqual(res.score, 0.0)
        self.assertLessEqual(res.score, 1.0)

        # Explanation field populated
        self.assertIn("Matched color: blue", res.explanation)
        self.assertIn("Matched object: graph", res.explanation)

    def test_multiple_candidates_ranking_order(self) -> None:
        c1 = CandidateMemory(
            source_type="ocr",
            source_id="ocr_101",
            timestamp_start=1000,
            timestamp_end=5000,
            matched_features=["text_clue:Docker", "object:slide"],
            score=6.0,
        )
        c2 = CandidateMemory(
            source_type="frame",
            source_id="frame_101",
            timestamp_start=2000,
            timestamp_end=4000,
            matched_features=["color:blue", "object:graph", "text_clue:Docker"],
            score=8.5,
        )
        c3 = CandidateMemory(
            source_type="event",
            source_id="event_101",
            timestamp_start=9000,
            timestamp_end=12000,
            matched_features=["action:explained"],
            score=2.0,
        )

        ranked = rank_candidates([c1, c2, c3])
        self.assertEqual(len(ranked), 3)

        # Candidate with highest score and most feature matches should be top
        self.assertEqual(ranked[0].source_id, "frame_101")
        self.assertEqual(ranked[1].source_id, "ocr_101")
        self.assertEqual(ranked[2].source_id, "event_101")

        # Ranking order descending by score
        scores = [c.score for c in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_equal_scores_deterministic_tie_breaking(self) -> None:
        c_b = CandidateMemory(
            source_type="ocr",
            source_id="ocr_b",
            matched_features=["object:graph"],
            score=5.0,
        )
        c_a = CandidateMemory(
            source_type="ocr",
            source_id="ocr_a",
            matched_features=["object:graph"],
            score=5.0,
        )

        ranked = rank_candidates([c_b, c_a])
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0].score, ranked[1].score)
        # Deterministic tie-break by source_id ("ocr_a" < "ocr_b")
        self.assertEqual(ranked[0].source_id, "ocr_a")
        self.assertEqual(ranked[1].source_id, "ocr_b")

    def test_no_matches_normalization_and_explanation(self) -> None:
        cand = CandidateMemory(
            source_type="semantic_chunk",
            source_id="chunk_001",
            matched_features=[],
            score=0.0,
        )

        ranked = rank_candidates([cand])
        self.assertEqual(len(ranked), 1)
        res = ranked[0]

        self.assertEqual(res.score, 0.0)
        self.assertEqual(res.explanation, "No specific feature matches")

    def test_confidence_normalization(self) -> None:
        candidates = [
            CandidateMemory(
                source_type="frame",
                source_id=f"frame_{i:03d}",
                matched_features=["color:blue", "object:graph", "text_clue:Docker", "action:showed"],
                score=float(i * 10),
            )
            for i in range(1, 10)
        ]

        ranked = rank_candidates(candidates)
        for c in ranked:
            self.assertGreaterEqual(c.score, 0.0)
            self.assertLessEqual(c.score, 1.0)

    def test_backward_compatibility(self) -> None:
        cand = CandidateMemory(
            candidate_id="c_legacy_001",
            modality="frame",
            video_id="v_test",
            score=6.0,
            start_ms=1000,
            end_ms=3000,
            matched_features=["color:blue", "object:graph"],
        )

        raw_score, breakdown = calculate_rerank_score(cand, [cand])
        self.assertGreater(raw_score, 0.0)
        self.assertIn("raw_score", breakdown)

        ranked_legacy = rank_memory_candidates([cand], top_k=1)
        self.assertEqual(len(ranked_legacy), 1)
        self.assertEqual(ranked_legacy[0].candidate_id, "c_legacy_001")
        self.assertEqual(ranked_legacy[0].modality, "frame")


if __name__ == "__main__":
    unittest.main()
