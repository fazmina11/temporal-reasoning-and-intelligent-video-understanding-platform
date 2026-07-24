import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.contracts import AnswerMode
from src.pipeline.agentic.conversation_resolver import resolve_conversation_references
from src.pipeline.agentic.query_understanding import understand_query
from src.pipeline.agentic.scope_router import ScopeAction, route_scope
from src.pipeline.json_artifacts import write_json_atomic


class AgenticScopeRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        write_json_atomic(
            self.repo / "data" / "processed" / "manifests" / "video_1.json",
            {
                "video_id": "video_1",
                "processing": {"processing_status": "completed"},
            },
        )
        write_json_atomic(
            self.repo / "data" / "processed" / "events" / "video_1.json",
            {
                "video_id": "video_1",
                "events": [
                    {
                        "event_id": "event_1",
                        "summary": "The speaker explains MCP and API integration.",
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_related_query_routes_to_video_retrieval(self) -> None:
        understanding = understand_query(raw_query="What is MCP?")
        decision = route_scope(
            repo_root=self.repo,
            video_id="video_1",
            query_understanding=understanding,
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.RETRIEVE_VIDEO)
        self.assertEqual(decision["scope"], "video_related")

    def test_unrelated_query_abstains_in_strict_mode(self) -> None:
        understanding = understand_query(raw_query="What is today's weather?")
        decision = route_scope(
            repo_root=self.repo,
            video_id="video_1",
            query_understanding=understanding,
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.ABSTAIN_UNRELATED)

    def test_unrelated_query_routes_general_in_hybrid_mode(self) -> None:
        understanding = understand_query(raw_query="What is today's weather?")
        decision = route_scope(
            repo_root=self.repo,
            video_id="video_1",
            query_understanding=understanding,
            answer_mode=AnswerMode.HYBRID_ASSISTANT,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.GENERAL_ANSWER)

    def test_missing_manifest_reports_processing_incomplete(self) -> None:
        understanding = understand_query(raw_query="What is MCP?")
        decision = route_scope(
            repo_root=self.repo,
            video_id="missing",
            query_understanding=understanding,
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.PROCESSING_INCOMPLETE)

    def test_uploaded_status_is_allowed_when_mature_artifacts_exist(self) -> None:
        write_json_atomic(
            self.repo / "data" / "processed" / "manifests" / "video_ready.json",
            {
                "video_id": "video_ready",
                "processing": {"processing_status": "uploaded"},
                "artifacts": {
                    "atoms_path": str(self.repo / "data" / "processed" / "atoms" / "video_ready.json"),
                    "semantic_chunks_path": str(self.repo / "data" / "processed" / "semantic_chunks" / "video_ready.json"),
                    "events_path": str(self.repo / "data" / "processed" / "events" / "video_ready.json"),
                    "visual_artifacts_path": str(self.repo / "data" / "processed" / "visual_artifacts" / "video_ready.json"),
                },
            },
        )
        for folder, key in [
            ("atoms", "atoms"),
            ("semantic_chunks", "chunks"),
            ("events", "events"),
            ("visual_artifacts", "records"),
        ]:
            write_json_atomic(
                self.repo / "data" / "processed" / folder / "video_ready.json",
                {"video_id": "video_ready", key: []},
            )
        decision = route_scope(
            repo_root=self.repo,
            video_id="video_ready",
            query_understanding=understand_query(raw_query="What did the speaker say?"),
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.RETRIEVE_VIDEO)

    def test_unresolved_follow_up_routes_to_clarification(self) -> None:
        resolved = resolve_conversation_references(
            raw_query="What does that mean?",
            conversation_context=[],
        )
        understanding = understand_query(
            raw_query="What does that mean?",
            standalone_query=resolved["standalone_query"],
            conversation_resolution=resolved,
        )
        decision = route_scope(
            repo_root=self.repo,
            video_id="video_1",
            query_understanding=understanding,
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.CLARIFY)
        self.assertEqual(decision["scope"], "ambiguous")

    def test_resolved_follow_up_can_retrieve(self) -> None:
        resolved = resolve_conversation_references(
            raw_query="What does he say after that?",
            conversation_context=[
                {
                    "citations": [
                        {
                            "source_id": "event_1",
                            "source_type": "event",
                            "start_ms": 1000,
                            "end_ms": 5000,
                        }
                    ]
                }
            ],
        )
        understanding = understand_query(
            raw_query="What does he say after that?",
            standalone_query=resolved["standalone_query"],
            conversation_resolution=resolved,
        )
        decision = route_scope(
            repo_root=self.repo,
            video_id="video_1",
            query_understanding=understanding,
            answer_mode=AnswerMode.STRICT_VIDEO,
        )
        self.assertEqual(decision["policy_action"], ScopeAction.RETRIEVE_VIDEO)


if __name__ == "__main__":
    unittest.main()
