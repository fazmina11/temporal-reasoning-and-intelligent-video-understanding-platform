"""Comprehensive end-to-end evaluation and integration tests for Memory Recovery AI system.

Verifies complete pipeline workflow:
Memory Parser -> Candidate Generator -> Ranker -> Memory Retriever -> Pipeline Integration

Covering:
- color-based memories
- object-based memories
- OCR text memories
- temporal memories
- spatial memories
- action memories
- multiple matching candidates
- no matching candidate
- non-memory factual questions
- confidence scoring
- timestamp propagation
- retrieval context propagation
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from src.pipeline.agentic.contracts import RetrievalPlan, RetrievalStep
from src.pipeline.agentic.query_understanding import is_episodic_memory_query, understand_query
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator
from src.pipeline.memory_recovery import (
    CandidateMemory,
    FeatureType,
    MemoryFeature,
    MemoryQuery,
    MemoryRetrievalResult,
    MemoryRetriever,
    generate_candidates,
    parse_memory_query,
    rank_candidates,
    retrieve_memory,
)


def build_evaluation_evidence_store() -> dict[str, list[dict[str, Any]]]:
    """Build a synthetic evidence store containing multi-modality video artifacts."""
    return {
        "ocr": [
            {
                "id": "ocr_101",
                "ocr_text": "System Architecture Overview and API Specifications for Docker",
                "start_ms": 1000,
                "end_ms": 5000,
                "tags": ["architecture", "api", "docker"],
            },
            {
                "id": "ocr_102",
                "ocr_text": "Performance Benchmarks and Low Latency Results",
                "start_ms": 10000,
                "end_ms": 15000,
                "tags": ["benchmarks", "latency"],
            },
        ],
        "frames": [
            {
                "id": "frame_101",
                "caption": "Slide displaying a blue graph with performance metrics",
                "timestamp_ms": 2000,
                "colors": ["blue"],
                "objects": ["graph", "slide"],
            },
            {
                "id": "frame_102",
                "caption": "Diagram showing two circles connected by arrows at top left",
                "timestamp_ms": 6000,
                "colors": ["red", "blue"],
                "objects": ["circles", "diagram"],
                "tags": ["top left"],
            },
            {
                "id": "frame_103",
                "caption": "Slide with yellow text highlighting API comparison table",
                "timestamp_ms": 11000,
                "colors": ["yellow"],
                "objects": ["slide", "text", "table"],
            },
        ],
        "events": [
            {
                "id": "event_101",
                "title": "Presenter demonstrates blue graph",
                "description": "Speaker explains the blue graph data points.",
                "start_ms": 1500,
                "end_ms": 4500,
            },
            {
                "id": "event_102",
                "title": "API comparison table discussion",
                "description": "Presenter compares REST and gRPC APIs on table.",
                "start_ms": 10500,
                "end_ms": 14000,
            },
        ],
        "semantic_chunks": [
            {
                "id": "chunk_101",
                "transcript": "As you can see on the blue graph, throughput scales linearly.",
                "start_ms": 1000,
                "end_ms": 5000,
            },
            {
                "id": "chunk_102",
                "transcript": "Here we compare the two API models in a comparison table.",
                "start_ms": 10000,
                "end_ms": 15000,
            },
        ],
        "clips": [
            {
                "id": "clip_101",
                "visual_summary": "Video clip showing blue graph visualization",
                "start_ms": 1500,
                "end_ms": 4000,
            }
        ],
    }


class EndToEndMemoryRecoveryPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = build_evaluation_evidence_store()
        self.retriever = MemoryRetriever(self.store)

    # 1. Color-based memories
    def test_color_based_memories_e2e(self) -> None:
        query = "I remember there was a blue graph."
        result = self.retriever.retrieve_memory(query)

        self.assertTrue(result.parsed_query.is_memory_query)
        self.assertIn("blue", result.parsed_query.colors)
        self.assertGreater(len(result.candidates), 0)
        self.assertIsNotNone(result.best_candidate)
        self.assertIn("color:blue", result.matched_features)

    # 2. Object-based memories
    def test_object_based_memories_e2e(self) -> None:
        query = "He showed two circles."
        result = self.retriever.retrieve_memory(query)

        self.assertTrue(result.parsed_query.is_memory_query)
        self.assertIn("circles", result.parsed_query.objects)
        self.assertIsNotNone(result.best_candidate)
        self.assertEqual(result.best_candidate.source_id, "frame_102")

    # 3. OCR text memories
    def test_ocr_text_memories_e2e(self) -> None:
        query = "There was a slide with Docker."
        result = self.retriever.retrieve_memory(query)

        self.assertTrue(result.parsed_query.is_memory_query)
        self.assertIn("Docker", result.parsed_query.text_clues)
        self.assertIsNotNone(result.best_candidate)
        self.assertTrue(any(c.source_id == "ocr_101" for c in result.candidates))
        self.assertIn("text_clue:Docker", result.matched_features)

    # 4. Temporal memories
    def test_temporal_memories_e2e(self) -> None:
        query = "After APIs he explained benchmarks earlier in the beginning."
        parsed = parse_memory_query(query)

        self.assertIn("after", parsed.temporal_clues)
        self.assertIn("earlier", parsed.temporal_clues)
        self.assertIn("beginning", parsed.temporal_clues)

        result = self.retriever.retrieve_memory(query)
        self.assertGreater(len(result.candidates), 0)
        self.assertTrue(len(result.parsed_query.temporal_clues) >= 3)


    # 5. Spatial memories
    def test_spatial_memories_e2e(self) -> None:
        query = "There was a diagram at the top left."
        result = self.retriever.retrieve_memory(query)

        self.assertIn("top left", result.parsed_query.spatial_clues)
        self.assertIsNotNone(result.best_candidate)
        self.assertEqual(result.best_candidate.source_id, "frame_102")
        self.assertIn("spatial_clue:top left", result.matched_features)

    # 6. Action memories
    def test_action_memories_e2e(self) -> None:
        query = "Here we compare the two API models."
        result = self.retriever.retrieve_memory(query)

        self.assertIn("compare", result.parsed_query.actions)
        self.assertGreater(len(result.candidates), 0)
        self.assertIn("action:compare", result.matched_features)

    # 7. Multiple matching candidates
    def test_multiple_matching_candidates_e2e(self) -> None:
        query = "I remember a blue graph in the presentation."
        result = self.retriever.retrieve_memory(query, top_k=5)

        self.assertGreater(len(result.candidates), 1)
        self.assertEqual(result.best_candidate, result.candidates[0])
        modalities = {c.source_type for c in result.candidates}
        self.assertGreaterEqual(len(modalities), 3)

    # 8. No matching candidate
    def test_no_matching_candidate_e2e(self) -> None:
        query = "I remember a purple dragon dancing in a spaceship."
        result = self.retriever.retrieve_memory(query)

        self.assertTrue(result.parsed_query.is_memory_query)
        self.assertEqual(result.candidates, [])
        self.assertIsNone(result.best_candidate)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.matched_features, [])

    # 9. Non-memory factual questions
    def test_non_memory_factual_questions_e2e(self) -> None:
        query = "What is MCP?"
        result = self.retriever.retrieve_memory(query)

        self.assertFalse(result.parsed_query.is_memory_query)
        self.assertEqual(result.candidates, [])
        self.assertIsNone(result.best_candidate)
        self.assertEqual(result.confidence, 0.0)

    # 10. Confidence scoring
    def test_confidence_scoring_calibration_e2e(self) -> None:
        strong_result = self.retriever.retrieve_memory("I remember a blue graph showing API benchmarks for Docker.")
        weak_result = self.retriever.retrieve_memory("There was a diagram.")
        none_result = self.retriever.retrieve_memory("I remember a flying dragon.")

        self.assertGreater(strong_result.confidence, weak_result.confidence)
        self.assertGreater(weak_result.confidence, none_result.confidence)
        self.assertEqual(none_result.confidence, 0.0)

    # 11. Timestamp propagation
    def test_timestamp_propagation_e2e(self) -> None:
        query = "I remember there was a blue graph."
        result = self.retriever.retrieve_memory(query)

        self.assertIsNotNone(result.best_candidate)
        best = result.best_candidate
        self.assertEqual(best.timestamp_start, 2000)
        self.assertEqual(best.timestamp_end, 2000)
        self.assertEqual(best.start_ms, 2000)
        self.assertEqual(best.end_ms, 2000)

    # 12. Retrieval context propagation
    def test_retrieval_context_propagation_e2e(self) -> None:
        query = "There was a slide with Docker."
        custom_retriever = MemoryRetriever()

        # Injected via retrieve_memory call
        result = custom_retriever.retrieve_memory(query, retrieval_context=self.store)
        self.assertGreater(len(result.candidates), 0)
        self.assertIsNotNone(result.best_candidate)
        self.assertTrue(any(c.source_id == "ocr_101" for c in result.candidates))
        self.assertIn("text_clue:Docker", result.matched_features)


    # 13. Complete Memory Recovery Pipeline Trace
    def test_complete_memory_recovery_pipeline_trace(self) -> None:
        raw_query = "I remember there was a blue graph."

        # Step 1: Memory Parser
        parsed = parse_memory_query(raw_query)
        self.assertTrue(parsed.is_memory_query)
        self.assertIn("blue", parsed.colors)
        self.assertIn("graph", parsed.objects)

        # Step 2: Candidate Generator
        gen_candidates = generate_candidates(parsed, self.store)
        self.assertGreater(len(gen_candidates), 0)

        # Step 3: Ranker
        ranked_candidates = rank_candidates(gen_candidates)
        self.assertEqual(ranked_candidates[0].score, max(c.score for c in ranked_candidates))
        self.assertIn("explanation", ranked_candidates[0].evidence)

        # Step 4: Memory Retriever
        retrieval_result = retrieve_memory(raw_query, self.store)
        self.assertEqual(retrieval_result.best_candidate.source_id, ranked_candidates[0].source_id)

        # Step 5: Pipeline Integration (RetrievalOrchestrator)
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            orchestrator = RetrievalOrchestrator(repo_root)
            understanding = understand_query(raw_query=raw_query)
            plan = RetrievalPlan(
                strategy="test_plan",
                retrieval_steps=[
                    RetrievalStep(query=raw_query, retriever="sparse_text", level="semantic_chunk", top_k=1, weight=1.0)
                ],
            )

            orch_result = orchestrator.execute(
                video_id="eval_video",
                plan=plan,
                query_understanding=understanding,
            )

            attempt_names = [a["retriever"] for a in orch_result["attempts"]]
            self.assertIn("memory_retriever", attempt_names)


if __name__ == "__main__":
    unittest.main()
