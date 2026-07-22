import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.pipeline.agentic.contracts import (
    AskRequest,
    AskResponse,
    CandidateEvidence,
    Citation,
    Outcome,
    RetrievalPlan,
    RetrievalStep,
    SourceType,
    model_to_dict,
)
from src.pipeline.agentic.trace_repository import TraceRepository


class AgenticContractTests(unittest.TestCase):
    def test_ask_request_rejects_empty_query(self) -> None:
        with self.assertRaises(ValidationError):
            AskRequest(video_id="mcp_vs_api", query="  ")

    def test_citation_rejects_invalid_timeline(self) -> None:
        with self.assertRaises(ValidationError):
            Citation(
                citation_id="S1",
                source_id="chunk_001",
                source_type=SourceType.SEMANTIC_CHUNK,
                start_ms=2000,
                end_ms=1000,
            )

    def test_response_requires_valid_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            AskResponse(
                outcome=Outcome.GROUNDED_ANSWER,
                answer="ok",
                video_id="video_1",
                query="what happened",
                confidence=1.5,
            )

    def test_candidate_requires_positive_span(self) -> None:
        with self.assertRaises(ValidationError):
            CandidateEvidence(
                candidate_id="cand_1",
                video_id="video_1",
                source_type=SourceType.ATOM,
                source_id="atom_1",
                start_ms=100,
                end_ms=100,
            )

    def test_retrieval_plan_requires_steps(self) -> None:
        with self.assertRaises(ValidationError):
            RetrievalPlan(strategy="empty", retrieval_steps=[])

        plan = RetrievalPlan(
            strategy="concept",
            retrieval_steps=[RetrievalStep(retriever="dense", level="semantic_chunk", query="MCP")],
        )
        self.assertEqual(plan.retrieval_steps[0].top_k, 10)

    def test_trace_repository_saves_and_loads_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = TraceRepository(Path(tmp))
            response = AskResponse(
                outcome=Outcome.VIDEO_EVIDENCE_NOT_FOUND,
                answer="not found",
                video_id="video_1",
                query="missing topic",
            )
            path = repo.save(
                "video_1",
                {
                    "trace_id": response.trace_id,
                    "request": {"video_id": "video_1"},
                    "final_response": model_to_dict(response),
                },
            )
            self.assertTrue(path.exists())
            loaded = repo.load("video_1", response.trace_id)
            self.assertEqual(loaded.trace_id, response.trace_id)


if __name__ == "__main__":
    unittest.main()
