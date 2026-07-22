import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.query_understanding import understand_query
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator
from src.pipeline.agentic.retrieval_planner import create_retrieval_plan
from src.pipeline.agentic.contracts import RetrievalPlan, RetrievalStep
from src.pipeline.json_artifacts import write_json_atomic
from src.pipeline.speaker_diarization import _merge_turns


class ModalityRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        processed = self.repo / "data" / "processed"
        artifacts = {
            "ocr_path": str(processed / "ocr" / "video_1.json"),
            "speakers_path": str(processed / "speakers" / "video_1.json"),
            "audio_events_path": str(processed / "audio_events" / "video_1.json"),
        }
        write_json_atomic(
            processed / "manifests" / "video_1.json",
            {"video_id": "video_1", "pipeline_version": "2.0.0", "artifacts": artifacts},
        )
        write_json_atomic(
            Path(artifacts["ocr_path"]),
            {"records": [{"ocr_id": "ocr_1", "frame_id": "frame_1", "start_ms": 5000, "end_ms": 5001, "text": "MCP vs API", "mean_confidence": 0.95, "parent_chunk_id": "chunk_1", "parent_event_id": "event_1"}]},
        )
        write_json_atomic(
            Path(artifacts["speakers_path"]),
            {"turns": [{"turn_id": "turn_1", "speaker_id": "speaker_00", "start_ms": 6000, "end_ms": 12000, "text": "MCP is a protocol for connecting tools.", "parent_chunk_id": "chunk_1", "parent_event_id": "event_1"}]},
        )
        write_json_atomic(
            Path(artifacts["audio_events_path"]),
            {"events": [{"audio_event_id": "audio_event_1", "label": "music_or_tonal_audio", "start_ms": 0, "end_ms": 3000, "confidence": 0.8, "parent_chunk_id": "chunk_1", "parent_event_id": "event_1"}]},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _retrieve(self, retriever: str, query: str):
        understanding = understand_query(raw_query=query)
        plan = RetrievalPlan(
            strategy="test",
            retrieval_steps=[RetrievalStep(retriever=retriever, level="test", query=query, top_k=5)],
        )
        return RetrievalOrchestrator(self.repo).execute(
            video_id="video_1", plan=plan, query_understanding=understanding
        )

    def test_ocr_retriever_returns_frame_citation(self) -> None:
        result = self._retrieve("ocr_sparse", "What slide says MCP vs API?")
        self.assertEqual(result["candidates"][0]["source_type"], "ocr")
        self.assertEqual(result["candidates"][0]["media_refs"]["frames"], ["frame_1"])

    def test_speaker_retriever_returns_diarized_turn(self) -> None:
        result = self._retrieve("speaker", "What did the speaker say about MCP?")
        self.assertEqual(result["candidates"][0]["source_type"], "speaker_turn")
        self.assertEqual(result["candidates"][0]["media_refs"]["speaker_id"], "speaker_00")

    def test_audio_retriever_returns_audio_event(self) -> None:
        result = self._retrieve("audio_event", "When was music heard?")
        self.assertEqual(result["candidates"][0]["source_type"], "audio_event")
        self.assertEqual(result["candidates"][0]["start_ms"], 0)

    def test_planner_selects_each_modality(self) -> None:
        ocr = create_retrieval_plan(query_understanding=understand_query(raw_query="What text on screen says MCP?"))
        speaker = create_retrieval_plan(query_understanding=understand_query(raw_query="What did the speaker say about MCP?"))
        audio = create_retrieval_plan(query_understanding=understand_query(raw_query="When did the music start?"))
        self.assertIn("ocr_sparse", [step.retriever for step in ocr.retrieval_steps])
        self.assertIn("speaker", [step.retriever for step in speaker.retrieval_steps])
        self.assertIn("audio_event", [step.retriever for step in audio.retrieval_steps])

    def test_turn_merging_is_bounded_and_chunk_aligned(self) -> None:
        segments = [
            {"segment_id": "s1", "speaker_id": "speaker_00", "start_ms": 0, "end_ms": 15000, "text": "a", "parent_chunk_id": "c1"},
            {"segment_id": "s2", "speaker_id": "speaker_00", "start_ms": 15100, "end_ms": 29000, "text": "b", "parent_chunk_id": "c1"},
            {"segment_id": "s3", "speaker_id": "speaker_00", "start_ms": 29100, "end_ms": 35000, "text": "c", "parent_chunk_id": "c1"},
        ]
        turns = _merge_turns(segments)
        self.assertEqual(len(turns), 2)
        self.assertLessEqual(max(turn["end_ms"] - turn["start_ms"] for turn in turns), 30_000)


if __name__ == "__main__":
    unittest.main()
