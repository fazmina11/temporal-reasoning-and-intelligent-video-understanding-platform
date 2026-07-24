import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.citation_registry import (
    build_evidence_registry,
    citation_source_compatible,
    validate_citation_objects,
)
from src.pipeline.agentic.claim_verifier import verify_claims
from src.pipeline.agentic.answer_generator import GroundedAnswerGenerator
from src.pipeline.agentic.evidence_packet import build_evidence_packet
from src.pipeline.json_artifacts import write_json_atomic


class PhaseNCitationRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.video_id = "video_1"
        base = self.repo / "data" / "processed"
        atoms_path = base / "atoms" / "video_1.json"
        chunks_path = base / "semantic_chunks" / "video_1.json"
        events_path = base / "events" / "video_1.json"
        ocr_path = base / "ocr" / "video_1.json"
        write_json_atomic(
            base / "manifests" / "video_1.json",
            {
                "video_id": self.video_id,
                "duration_ms": 30_000,
                "pipeline_version": "base-v1",
                "artifacts": {
                    "atoms_path": str(atoms_path),
                    "semantic_chunks_path": str(chunks_path),
                    "events_path": str(events_path),
                    "ocr_path": str(ocr_path),
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
                        "parent_event_id": "event_1",
                        "transcript_text": "The speaker introduces context.",
                    },
                    {
                        "atom_id": "atom_2",
                        "start_ms": 10_000,
                        "end_ms": 20_000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools.",
                    },
                    {
                        "atom_id": "atom_3",
                        "start_ms": 20_000,
                        "end_ms": 24_000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "That is the value of standardization.",
                    },
                    {
                        "atom_id": "atom_4",
                        "start_ms": 24_000,
                        "end_ms": 27_000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "HTTP made websites interoperable.",
                    },
                    {
                        "atom_id": "atom_5",
                        "start_ms": 27_000,
                        "end_ms": 30_000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "MCP makes AI environments interoperable.",
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
                        "end_ms": 20_000,
                        "parent_event_id": "event_1",
                        "atom_ids": ["atom_1", "atom_2", "atom_3", "atom_4", "atom_5"],
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
                        "end_ms": 20_000,
                        "atom_ids": ["atom_1", "atom_2", "atom_3", "atom_4", "atom_5"],
                        "title": "MCP event",
                        "transcript_text": "The speaker explains MCP.",
                    }
                ]
            },
        )
        write_json_atomic(
            ocr_path,
            {
                "records": [
                    {
                        "ocr_id": "ocr_1",
                        "start_ms": 11_000,
                        "end_ms": 12_000,
                        "text": "MCP context tools",
                        "mean_confidence": 0.92,
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_registry_is_written_for_canonical_sources(self) -> None:
        result = build_evidence_registry(repo_root=self.repo, video_id=self.video_id)
        self.assertGreaterEqual(result["record_count"], 4)
        self.assertTrue((self.repo / "data" / "processed" / "evidence_registry" / "video_1.jsonl").is_file())
        self.assertIn("semantic_chunk", result["source_type_counts"])

    def test_packet_separates_anchor_context_and_citation_interval(self) -> None:
        evidence = [
            {
                "candidate_id": "cand_1",
                "video_id": self.video_id,
                "source_type": "semantic_chunk",
                "source_id": "chunk_1",
                "start_ms": 0,
                "end_ms": 20_000,
                "parent_chunk_id": "chunk_1",
                "parent_event_id": "event_1",
                "text": "The speaker explains MCP as a protocol for context and tools.",
                "support_score": 0.8,
            }
        ]
        temporal = {
            "primary_moment": {"source_type": "semantic_chunk", "source_id": "chunk_1", "start_ms": 0, "end_ms": 20_000},
            "expanded_atoms": [
                {"atom_id": "atom_1", "start_ms": 0, "end_ms": 10_000, "transcript_text": "The speaker introduces context."},
                {"atom_id": "atom_2", "start_ms": 10_000, "end_ms": 20_000, "transcript_text": "The speaker explains MCP as a protocol for context and tools."},
            ],
        }
        packet = build_evidence_packet(
            request={"video_id": self.video_id, "query": "What is MCP?", "answer_mode": "strict_video"},
            outcome_candidate="answer",
            verified_evidence=evidence,
            temporal_context=temporal,
            answerability={"decision": "answer", "score": 0.8},
            repo_root=self.repo,
            query_understanding={"standalone_query": "What is MCP?"},
        )
        citation = packet["citations"][0]
        self.assertEqual(citation["evidence_anchor"]["start_ms"], 10_000)
        self.assertEqual(citation["citation_interval"]["start_ms"], 10_000)
        self.assertEqual(citation["start_ms"], 10_000)
        self.assertEqual(citation["source_interval"]["start_ms"], 0)
        self.assertTrue(packet["citation_validation"]["valid"])

    def test_claim_verifier_rejects_incompatible_visible_text_source(self) -> None:
        packet = {
            "citation_validation": {"valid": True},
            "verified_evidence": [
                {
                    "citation_id": "S1",
                    "canonical_source_type": "semantic_chunk",
                    "text": "The speaker explains MCP.",
                    "visual_summary": "",
                    "start_ms": 0,
                    "end_ms": 10_000,
                    "evidence_anchor": {"start_ms": 0, "end_ms": 10_000},
                }
            ],
        }
        result = verify_claims("The slide text says MCP context tools [S1].", packet)
        self.assertFalse(result["passed"])
        self.assertIn("S1", result["incompatible_citations"])
        self.assertFalse(citation_source_compatible("The slide text says MCP [S1].", packet["verified_evidence"][0]))

    def test_comparison_uses_contiguous_multi_atom_anchor_and_grounded_excerpt(self) -> None:
        evidence = [
            {
                "candidate_id": "cand_1",
                "video_id": self.video_id,
                "source_type": "semantic_chunk",
                "source_id": "chunk_1",
                "start_ms": 0,
                "end_ms": 30_000,
                "parent_chunk_id": "chunk_1",
                "parent_event_id": "event_1",
                "text": (
                    "That is the value of standardization. "
                    "HTTP made websites interoperable. "
                    "MCP makes AI environments interoperable."
                ),
                "support_score": 0.9,
            }
        ]
        expanded_atoms = [
            {
                "atom_id": f"atom_{index}",
                "start_ms": start,
                "end_ms": end,
                "transcript_text": text,
            }
            for index, start, end, text in (
                (1, 0, 10_000, "The speaker introduces context."),
                (2, 10_000, 20_000, "The speaker explains MCP as a protocol."),
                (3, 20_000, 24_000, "That is the value of standardization."),
                (4, 24_000, 27_000, "HTTP made websites interoperable."),
                (5, 27_000, 30_000, "MCP makes AI environments interoperable."),
            )
        ]
        question = "How is MCP compared to HTTP standardization?"
        packet = build_evidence_packet(
            request={"video_id": self.video_id, "query": question, "answer_mode": "strict_video"},
            outcome_candidate="answer",
            verified_evidence=evidence,
            temporal_context={
                "primary_moment": {
                    "source_type": "semantic_chunk",
                    "source_id": "chunk_1",
                    "start_ms": 0,
                    "end_ms": 30_000,
                },
                "expanded_atoms": expanded_atoms,
            },
            answerability={"decision": "answer", "score": 0.9},
            repo_root=self.repo,
            query_understanding={
                "standalone_query": question,
                "query_types": ["comparison"],
            },
        )
        citation = packet["citations"][0]
        self.assertEqual(citation["start_ms"], 20_000)
        self.assertEqual(citation["end_ms"], 30_000)
        self.assertEqual(citation["evidence_anchor"]["reason"], "comparison_atom_window")

        generator = GroundedAnswerGenerator()
        generator.client = None
        generation = generator.generate(packet)
        self.assertIn("HTTP", generation["answer"])
        self.assertIn("MCP", generation["answer"])
        self.assertTrue(verify_claims(generation["answer"], packet)["passed"])

    def test_citation_validation_catches_bad_intervals(self) -> None:
        result = validate_citation_objects(
            [
                {
                    "citation_id": "S1",
                    "evidence_id": "E1",
                    "source_id": "x",
                    "start_ms": 10,
                    "end_ms": 5,
                    "evidence_anchor": {"start_ms": 0, "end_ms": 1},
                    "answer_context_window": {"start_ms": 0, "end_ms": 1},
                    "citation_interval": {"start_ms": 10, "end_ms": 5},
                }
            ]
        )
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
