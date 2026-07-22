import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.answer_generator import GroundedAnswerGenerator
from src.pipeline.agentic.claim_verifier import verify_claims
from src.pipeline.agentic.confidence_calibrator import calibrate_confidence
from src.pipeline.agentic.contracts import RetrievalPlan, RetrievalStep, model_to_dict
from src.pipeline.agentic.corrective_retrieval import create_corrective_plan, should_retry
from src.pipeline.agentic.evidence_packet import build_evidence_packet
from src.pipeline.agentic.temporal_reasoner import build_temporal_context
from src.pipeline.json_artifacts import write_json_atomic


class AgenticAnswerPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.video_id = "video_1"
        atoms_path = self.repo / "data" / "processed" / "atoms" / "video_1.json"
        chunks_path = self.repo / "data" / "processed" / "semantic_chunks" / "video_1.json"
        events_path = self.repo / "data" / "processed" / "events" / "video_1.json"
        write_json_atomic(
            self.repo / "data" / "processed" / "manifests" / "video_1.json",
            {
                "video_id": self.video_id,
                "duration_ms": 30_000,
                "pipeline_version": "2.0.0",
                "artifacts": {
                    "atoms_path": str(atoms_path),
                    "semantic_chunks_path": str(chunks_path),
                    "events_path": str(events_path),
                },
            },
        )
        write_json_atomic(
            atoms_path,
            {
                "atoms": [
                    {
                        "atom_id": "atom_1",
                        "start_ms": 0,
                        "end_ms": 10_000,
                        "semantic_chunk_id": "chunk_1",
                        "transcript_text": "The speaker introduces context.",
                    },
                    {
                        "atom_id": "atom_2",
                        "start_ms": 10_000,
                        "end_ms": 20_000,
                        "semantic_chunk_id": "chunk_1",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools.",
                    },
                    {
                        "atom_id": "atom_3",
                        "start_ms": 20_000,
                        "end_ms": 30_000,
                        "semantic_chunk_id": "chunk_1",
                        "transcript_text": "Then he compares MCP with API integration.",
                    },
                ]
            },
        )
        write_json_atomic(
            chunks_path,
            {
                "chunks": [
                    {
                        "chunk_id": "chunk_1",
                        "start_ms": 0,
                        "end_ms": 30_000,
                        "parent_event_id": "event_1",
                        "atom_ids": ["atom_1", "atom_2", "atom_3"],
                        "title": "MCP explanation",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools.",
                    }
                ]
            },
        )
        write_json_atomic(
            events_path,
            {
                "events": [
                    {
                        "event_id": "event_1",
                        "start_ms": 0,
                        "end_ms": 30_000,
                        "atom_ids": ["atom_1", "atom_2", "atom_3"],
                        "title": "MCP event",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools.",
                    }
                ]
            },
        )
        self.evidence = [
            {
                "candidate_id": "cand_1",
                "video_id": self.video_id,
                "source_type": "semantic_chunk",
                "source_id": "chunk_1",
                "start_ms": 0,
                "end_ms": 30_000,
                "parent_chunk_id": "chunk_1",
                "parent_event_id": "event_1",
                "text": "The speaker explains MCP as a protocol for context and tools.",
                "transcript": "The speaker explains MCP as a protocol for context and tools.",
                "visual_summary": "",
                "support_score": 0.82,
                "support_level": "strong",
                "evidence_types": ["transcript", "event"],
                "fused_score": 0.21,
                "rerank_score": 0.5,
                "retrieval": {"raw_score": 0.8},
            }
        ]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_corrective_plan_adds_safe_expansions(self) -> None:
        plan = RetrievalPlan(
            strategy="broad",
            retrieval_steps=[RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query="MCP", top_k=5)],
            max_corrective_attempts=2,
        )
        answerability = {"decision": "corrective_retrieval"}
        self.assertTrue(should_retry(answerability, 0, plan.max_corrective_attempts))
        corrective = create_corrective_plan(
            original_plan=plan,
            query_understanding={"standalone_query": "What is MCP?", "entities": ["MCP"], "required_modalities": ["transcript"]},
            answerability=answerability,
            attempt=0,
        )
        self.assertIn("corrective", corrective.strategy)
        self.assertGreaterEqual(len(corrective.retrieval_steps), len(plan.retrieval_steps))

    def test_temporal_context_expands_within_video_duration(self) -> None:
        context = build_temporal_context(
            repo_root=self.repo,
            video_id=self.video_id,
            verified_evidence=self.evidence,
            retrieval_plan={"context_policy": {"max_previous_atoms": 1, "max_next_atoms": 1, "max_context_ms": 30_000}},
            query_understanding={"requires_multi_moment_reasoning": True, "query_types": []},
        )
        self.assertEqual(context["primary_moment"]["source_id"], "chunk_1")
        self.assertTrue(context["context_within_video_duration"])
        self.assertEqual(context["expanded_atom_ids"], ["atom_1", "atom_2", "atom_3"])

    def test_packet_generation_claim_verification_and_confidence(self) -> None:
        temporal = build_temporal_context(
            repo_root=self.repo,
            video_id=self.video_id,
            verified_evidence=self.evidence,
            retrieval_plan={"context_policy": {"max_previous_atoms": 1, "max_next_atoms": 1, "max_context_ms": 30_000}},
            query_understanding={"requires_multi_moment_reasoning": False, "query_types": []},
        )
        packet = build_evidence_packet(
            request={"video_id": self.video_id, "query": "What is MCP?", "answer_mode": "strict_video"},
            outcome_candidate="answer",
            verified_evidence=self.evidence,
            temporal_context=temporal,
            answerability={"decision": "answer", "score": 0.8},
        )
        generator = GroundedAnswerGenerator()
        generator.client = None
        generation = generator.generate(packet)
        verification = verify_claims(generation["answer"], packet)
        confidence = calibrate_confidence(
            retrieval_gate={"verification": {"verified_evidence": self.evidence}, "corrective_attempts": []},
            temporal_context=temporal,
            evidence_packet=packet,
            claim_verification=verification,
            generation=generation,
        )
        self.assertIn("[S1]", generation["answer"])
        self.assertTrue(verification["passed"])
        self.assertGreater(confidence["score"], 0.5)

    def test_claim_verifier_rejects_invalid_citation(self) -> None:
        packet = {
            "verified_evidence": [
                {"citation_id": "S1", "text": "MCP is a protocol.", "visual_summary": "", "start_ms": 0, "end_ms": 1000}
            ]
        }
        verification = verify_claims("MCP is a protocol [S9].", packet)
        self.assertFalse(verification["passed"])
        self.assertIn("S9", verification["invalid_citations"])


if __name__ == "__main__":
    unittest.main()
