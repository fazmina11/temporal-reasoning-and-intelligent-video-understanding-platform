import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.answerability_gate import evaluate_answerability
from src.pipeline.agentic.candidate_fusion import fuse_candidates
from src.pipeline.agentic.contracts import AnswerMode, RetrievalPlan, RetrievalStep
from src.pipeline.agentic.contracts import model_to_dict
from src.pipeline.agentic.evidence_verifier import verify_evidence
from src.pipeline.agentic.query_understanding import understand_query
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator
from src.pipeline.agentic.retrieval_planner import create_retrieval_plan
from src.pipeline.agentic.reranker import rerank_candidates
from src.pipeline.agentic.temporal_deduplicator import deduplicate_temporal_candidates, temporal_iou
from src.pipeline.json_artifacts import write_json_atomic


class AgenticRetrievalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.video_id = "video_1"
        atoms_path = self.repo / "data" / "processed" / "atoms" / "video_1.json"
        chunks_path = self.repo / "data" / "processed" / "semantic_chunks" / "video_1.json"
        events_path = self.repo / "data" / "processed" / "events" / "video_1.json"
        visual_path = self.repo / "data" / "processed" / "visual_artifacts" / "video_1.json"
        write_json_atomic(
            self.repo / "data" / "processed" / "manifests" / "video_1.json",
            {
                "video_id": self.video_id,
                "pipeline_version": "2.0.0",
                "artifacts": {
                    "atoms_path": str(atoms_path),
                    "semantic_chunks_path": str(chunks_path),
                    "events_path": str(events_path),
                    "visual_artifacts_path": str(visual_path),
                },
            },
        )
        write_json_atomic(
            atoms_path,
            {
                "video_id": self.video_id,
                "atoms": [
                    {
                        "atom_id": "atom_1",
                        "start_ms": 0,
                        "end_ms": 8000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools.",
                        "representative_frame_ids": ["frame_1"],
                    },
                    {
                        "atom_id": "atom_2",
                        "start_ms": 8000,
                        "end_ms": 16000,
                        "semantic_chunk_id": "chunk_1",
                        "parent_event_id": "event_1",
                        "transcript_text": "He compares MCP and API integration.",
                        "representative_frame_ids": ["frame_2"],
                    },
                ],
            },
        )
        write_json_atomic(
            chunks_path,
            {
                "video_id": self.video_id,
                "chunks": [
                    {
                        "chunk_id": "chunk_1",
                        "start_ms": 0,
                        "end_ms": 16000,
                        "parent_event_id": "event_1",
                        "atom_ids": ["atom_1", "atom_2"],
                        "title": "MCP and API comparison",
                        "summary_text": "The speaker explains MCP and compares it with APIs.",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools. He compares MCP and API integration.",
                    }
                ],
            },
        )
        write_json_atomic(
            events_path,
            {
                "video_id": self.video_id,
                "events": [
                    {
                        "event_id": "event_1",
                        "start_ms": 0,
                        "end_ms": 16000,
                        "chunk_ids": ["chunk_1"],
                        "atom_ids": ["atom_1", "atom_2"],
                        "title": "MCP explanation",
                        "summary_text": "MCP is explained as a context protocol.",
                        "transcript_text": "The speaker explains MCP as a protocol for context and tools.",
                    }
                ],
            },
        )
        write_json_atomic(
            visual_path,
            {
                "video_id": self.video_id,
                "records": [
                    {
                        "atom_id": "atom_1",
                        "start_ms": 0,
                        "end_ms": 8000,
                        "frame_references": [{"frame_id": "frame_1", "role": "middle"}],
                        "clip": {"clip_path_relative": "data/processed/clips/video_1/atom_1.mp4"},
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exact_timestamp_plan_bypasses_dense_retrieval(self) -> None:
        understanding = understand_query(raw_query="What happens at 00:00:08?")
        plan = create_retrieval_plan(query_understanding=understanding)
        self.assertEqual(plan.strategy, "exact_timeline_lookup")
        self.assertEqual([step.retriever for step in plan.retrieval_steps], ["exact_timeline"])

    def test_visual_and_comparison_plans_include_expected_retrievers(self) -> None:
        visual = create_retrieval_plan(
            query_understanding=understand_query(raw_query="Why did he draw the blue graph?")
        )
        self.assertIn("visual_dense", [step.retriever for step in visual.retrieval_steps])
        self.assertIn("event_dense", [step.retriever for step in visual.retrieval_steps])

        comparison = create_retrieval_plan(
            query_understanding=understand_query(raw_query="Compare MCP and API")
        )
        retrievers = [step.retriever for step in comparison.retrieval_steps]
        self.assertIn("event_dense", retrievers)
        self.assertIn("sparse_text", retrievers)

    def test_orchestrator_runs_exact_and_sparse_adapters(self) -> None:
        understanding = understand_query(raw_query="What happens at 00:00:08 MCP?")
        plan = RetrievalPlan(
            strategy="unit",
            retrieval_steps=[
                RetrievalStep(retriever="exact_timeline", level="atomic_span", query="00:00:08 MCP", top_k=5, weight=2.0),
                RetrievalStep(retriever="sparse_text", level="semantic_chunk", query="MCP API", top_k=5, weight=1.0),
            ],
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        result = RetrievalOrchestrator(self.repo).execute(
            video_id=self.video_id,
            plan=plan,
            query_understanding=understanding,
        )
        self.assertEqual(len(result["attempts"]), 2)
        self.assertGreaterEqual(len(result["candidates"]), 2)

    def test_fusion_rerank_dedup_verify_and_answerability(self) -> None:
        understanding = understand_query(raw_query="What is MCP protocol?")
        plan = RetrievalPlan(
            strategy="unit",
            retrieval_steps=[
                RetrievalStep(retriever="sparse_text", level="semantic_chunk", query="MCP protocol", top_k=5, weight=1.5)
            ],
        )
        retrieval = RetrievalOrchestrator(self.repo).execute(
            video_id=self.video_id,
            plan=plan,
            query_understanding=understanding,
        )
        fusion = fuse_candidates(
            candidates=retrieval["candidates"],
            plan=model_to_dict(plan),
            query_understanding=understanding,
        )
        reranked = rerank_candidates(candidates=fusion["candidates"], query_understanding=understanding)
        deduped = deduplicate_temporal_candidates(candidates=reranked["candidates"])
        verification = verify_evidence(
            repo_root=self.repo,
            video_id=self.video_id,
            candidates=deduped["candidates"],
            query_understanding=understanding,
        )
        answerability = evaluate_answerability(
            verified_evidence=verification["verified_evidence"],
            query_understanding=understanding,
            scope_decision={"policy_action": "retrieve_video"},
        )

        self.assertGreaterEqual(fusion["fused_candidate_count"], 1)
        self.assertGreaterEqual(verification["verified_count"], 1)
        self.assertIn(answerability["decision"], {"answer", "partial_answer"})

    def test_temporal_iou_collapses_duplicate_windows(self) -> None:
        a = {"video_id": "v", "candidate_id": "a", "source_type": "atom", "source_id": "a", "start_ms": 0, "end_ms": 10000, "rerank_score": 0.9}
        b = {"video_id": "v", "candidate_id": "b", "source_type": "atom", "source_id": "b", "start_ms": 1000, "end_ms": 9000, "rerank_score": 0.8}
        self.assertGreater(temporal_iou(a, b), 0.7)
        deduped = deduplicate_temporal_candidates(candidates=[a, b])
        self.assertEqual(deduped["deduplicated_candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
