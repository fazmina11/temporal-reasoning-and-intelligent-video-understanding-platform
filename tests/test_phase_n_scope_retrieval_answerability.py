import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.answerability_gate import evaluate_answerability
from src.pipeline.agentic.contracts import AnswerMode, RetrievalPlan, RetrievalStep
from src.pipeline.agentic.corrective_retrieval import create_corrective_plan, should_retry
from src.pipeline.agentic.query_understanding import understand_query
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator
from src.pipeline.agentic.reranker import rerank_candidates
from src.pipeline.agentic.scope_analyzer import analyze_video_scope
from src.pipeline.agentic.scope_profile import build_video_scope_profile
from src.pipeline.agentic.scope_router import ScopeAction, route_scope
from src.pipeline.json_artifacts import write_json_atomic


class PhaseNScopeRetrievalAnswerabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.video_id = "video_1"
        base = self.repo / "data" / "processed"
        self.atoms_path = base / "atoms" / "video_1.json"
        self.chunks_path = base / "semantic_chunks" / "video_1.json"
        self.events_path = base / "events" / "video_1.json"
        self.visual_path = base / "visual_artifacts" / "video_1.json"
        self.ocr_path = base / "ocr" / "video_1.json"
        write_json_atomic(
            base / "manifests" / "video_1.json",
            {
                "video_id": self.video_id,
                "source_filename": "MCP vs API.mp4",
                "duration_ms": 20_000,
                "pipeline_version": "base-v1",
                "processing": {"processing_status": "completed"},
                "artifacts": {
                    "atoms_path": str(self.atoms_path),
                    "semantic_chunks_path": str(self.chunks_path),
                    "events_path": str(self.events_path),
                    "visual_artifacts_path": str(self.visual_path),
                    "ocr_path": str(self.ocr_path),
                },
                "timeline": {"start_ms": 0, "end_ms": 20_000, "duration_ms": 20_000},
                "fps": 30.0,
                "frame_count": 600,
            },
        )
        write_json_atomic(
            self.atoms_path,
            {
                "video_id": self.video_id,
                "atoms": [
                    {
                        "atom_id": "atom_1",
                        "start_ms": 0,
                        "end_ms": 9000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "MCP is a protocol for giving models context and tools.",
                    },
                    {
                        "atom_id": "atom_2",
                        "start_ms": 9000,
                        "end_ms": 18_000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "The speaker compares MCP with API integration.",
                    },
                ],
            },
        )
        write_json_atomic(
            self.chunks_path,
            {
                "video_id": self.video_id,
                "chunks": [
                    {
                        "chunk_id": "chunk_1",
                        "start_ms": 0,
                        "end_ms": 18_000,
                        "parent_event_id": "event_1",
                        "atom_ids": ["atom_1", "atom_2"],
                        "title": "MCP and API comparison",
                        "summary_text": "The speaker explains MCP and compares it with APIs.",
                        "transcript_text": "MCP is a protocol for context and tools. MCP is compared with APIs.",
                    }
                ],
            },
        )
        write_json_atomic(
            self.events_path,
            {
                "video_id": self.video_id,
                "events": [
                    {
                        "event_id": "event_1",
                        "start_ms": 0,
                        "end_ms": 18_000,
                        "title": "MCP explanation",
                        "summary_text": "MCP is explained as a protocol for context and tools.",
                        "transcript_text": "MCP is a protocol for context and tools.",
                    }
                ],
            },
        )
        write_json_atomic(self.visual_path, {"video_id": self.video_id, "records": []})
        write_json_atomic(
            self.ocr_path,
            {
                "video_id": self.video_id,
                "records": [
                    {
                        "ocr_id": "ocr_1",
                        "frame_id": "frame_1",
                        "start_ms": 1000,
                        "end_ms": 2000,
                        "text": "MCP context tools",
                        "mean_confidence": 0.9,
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_n3_builds_profile_and_routes_conservatively(self) -> None:
        profile = build_video_scope_profile(repo_root=self.repo, video_id=self.video_id)
        self.assertIn("mcp", profile["topic_keywords"])
        self.assertTrue((self.repo / "data" / "processed" / "scope_profiles" / "video_1.json").is_file())

        related = route_scope(
            repo_root=self.repo,
            video_id=self.video_id,
            query_understanding=understand_query(raw_query="What is MCP?"),
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(related["policy_action"], ScopeAction.RETRIEVE_VIDEO)
        self.assertIn("scope_analysis", related)

        unrelated = route_scope(
            repo_root=self.repo,
            video_id=self.video_id,
            query_understanding=understand_query(raw_query="What is today's weather in Tokyo?"),
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(unrelated["policy_action"], ScopeAction.ABSTAIN_UNRELATED)

    def test_n3_scope_analyzer_exposes_independent_signals(self) -> None:
        analysis = analyze_video_scope(
            repo_root=self.repo,
            video_id=self.video_id,
            query_understanding=understand_query(raw_query="Explain MCP context tools"),
        )
        self.assertGreater(analysis["scope_score"], 0.3)
        self.assertIn("entity_overlap_score", analysis["signals"])
        self.assertIn("keyword_overlap_score", analysis["signals"])

    def test_n4_orchestrator_normalizes_and_records_readiness(self) -> None:
        plan = RetrievalPlan(
            strategy="unit",
            retrieval_steps=[
                RetrievalStep(retriever="sparse_text", level="semantic_chunk", query="MCP protocol", top_k=5, weight=1.4),
                RetrievalStep(retriever="speaker", level="speaker_turn", query="who said MCP", top_k=5, weight=1.1),
            ],
        )
        result = RetrievalOrchestrator(self.repo).execute(
            video_id=self.video_id,
            plan=plan,
            query_understanding=understand_query(raw_query="What is MCP protocol?"),
        )
        self.assertGreaterEqual(len(result["candidates"]), 1)
        self.assertTrue(all("retrieval" in candidate for candidate in result["candidates"]))
        self.assertIn("source_type_counts", result["attempts"][0])
        self.assertTrue(any("speaker readiness missing artifact" in warning for warning in result["warnings"]))

    def test_n4_reranker_reports_retrieval_margin(self) -> None:
        candidates = [
            {
                "candidate_id": "c1",
                "video_id": self.video_id,
                "source_type": "semantic_chunk",
                "source_id": "chunk_1",
                "start_ms": 0,
                "end_ms": 9000,
                "fused_score": 0.3,
                "text": "MCP protocol context tools",
            },
            {
                "candidate_id": "c2",
                "video_id": self.video_id,
                "source_type": "event",
                "source_id": "event_1",
                "start_ms": 0,
                "end_ms": 18_000,
                "fused_score": 0.2,
                "text": "API integration",
            },
        ]
        reranked = rerank_candidates(
            candidates=candidates,
            query_understanding=understand_query(raw_query="MCP protocol"),
        )
        self.assertGreater(reranked["retrieval_margin"], 0)
        self.assertIn("answer_likelihood", reranked["candidates"][0])

    def test_n5_answerability_and_corrective_plan_are_bounded(self) -> None:
        understanding = understand_query(raw_query="What is MCP?")
        weak = [
            {
                "candidate_id": "c1",
                "video_id": self.video_id,
                "source_type": "semantic_chunk",
                "source_id": "chunk_1",
                "start_ms": 0,
                "end_ms": 9000,
                "text": "MCP context",
                "support_score": 0.34,
                "support_level": "weak",
                "evidence_types": ["transcript"],
                "rerank_score": 0.35,
            }
        ]
        answerability = evaluate_answerability(
            verified_evidence=weak,
            query_understanding=understanding,
            scope_decision={"policy_action": ScopeAction.RETRIEVE_VIDEO},
        )
        self.assertIn(answerability["decision"], {"corrective_retrieval", "video_evidence_not_found"})
        plan = RetrievalPlan(
            strategy="unit",
            retrieval_steps=[RetrievalStep(retriever="chunk_dense", level="semantic_chunk", query="MCP", top_k=10)],
            max_corrective_attempts=1,
        )
        corrective = create_corrective_plan(
            original_plan=plan,
            query_understanding=understanding,
            answerability={"decision": "corrective_retrieval", "reason_codes": ["LOW_RETRIEVAL_MARGIN"]},
            attempt=0,
        )
        self.assertLessEqual(len(corrective.retrieval_steps), 8)
        self.assertEqual(corrective.retry_number, 1)
        self.assertTrue(corrective.corrective_actions)
        self.assertTrue(should_retry({"decision": "corrective_retrieval"}, 0, 1))


if __name__ == "__main__":
    unittest.main()
