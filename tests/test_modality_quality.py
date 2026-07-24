import tempfile
import unittest
from pathlib import Path

from src.pipeline.agentic.contracts import RetrievalPlan, RetrievalStep
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator
from src.pipeline.audio_event_detection import _merge_windows
from src.pipeline.json_artifacts import write_json_atomic
from src.pipeline.modality_common import timeline_parent_ids
from src.pipeline.ocr_extraction import _build_ocr_tracks
from src.pipeline.speaker_diarization import _merge_turns


class ModalityQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        processed = self.repo / "data" / "processed"
        self.video_id = "video_1"
        self.artifacts = {
            "atoms_path": str(processed / "atoms" / "video_1.json"),
            "semantic_chunks_path": str(processed / "semantic_chunks" / "video_1.json"),
            "events_path": str(processed / "events" / "video_1.json"),
            "ocr_path": str(processed / "ocr" / "video_1.json"),
            "speakers_path": str(processed / "speakers" / "video_1.json"),
            "audio_events_path": str(processed / "audio_events" / "video_1.json"),
        }
        write_json_atomic(
            processed / "manifests" / "video_1.json",
            {
                "video_id": self.video_id,
                "duration_ms": 30_000,
                "source_sha256": "sha",
                "pipeline_version": "base-v1",
                "artifacts": self.artifacts,
            },
        )
        write_json_atomic(
            Path(self.artifacts["atoms_path"]),
            {
                "atoms": [
                    {"atom_id": "atom_1", "start_ms": 0, "end_ms": 10_000, "semantic_chunk_id": "chunk_1"},
                    {"atom_id": "atom_2", "start_ms": 10_000, "end_ms": 20_000, "semantic_chunk_id": "chunk_1"},
                    {"atom_id": "atom_3", "start_ms": 20_000, "end_ms": 30_000, "semantic_chunk_id": "chunk_2"},
                ]
            },
        )
        write_json_atomic(
            Path(self.artifacts["semantic_chunks_path"]),
            {
                "chunks": [
                    {"chunk_id": "chunk_1", "start_ms": 0, "end_ms": 20_000, "parent_event_id": "event_1"},
                    {"chunk_id": "chunk_2", "start_ms": 20_000, "end_ms": 30_000, "parent_event_id": "event_2"},
                ]
            },
        )
        write_json_atomic(
            Path(self.artifacts["events_path"]),
            {
                "events": [
                    {"event_id": "event_1", "start_ms": 0, "end_ms": 20_000},
                    {"event_id": "event_2", "start_ms": 20_000, "end_ms": 30_000},
                ]
            },
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_timeline_parent_ids_returns_all_overlapped_atoms(self) -> None:
        from src.pipeline.media_manifest import load_manifest
        from src.pipeline.modality_common import hierarchy_maps

        maps = hierarchy_maps(load_manifest(repo_root=self.repo, video_id=self.video_id))
        result = timeline_parent_ids(9000, 21_000, maps)
        self.assertEqual(result["parent_atom_ids"], ["atom_1", "atom_2", "atom_3"])
        self.assertEqual(result["parent_chunk_ids"], ["chunk_1", "chunk_2"])

    def test_ocr_tracks_preserve_frame_references(self) -> None:
        records = [
            {
                "ocr_id": "ocr_000001",
                "video_id": self.video_id,
                "frame_id": "frame_1",
                "frame_timestamp_ms": 1000,
                "start_ms": 1000,
                "end_ms": 1001,
                "text": "MCP Context",
                "normalized_text": "mcp context",
                "quality_score": 0.8,
                "mean_confidence": 0.8,
                "parent_atom_ids": ["atom_1"],
                "frame_path_relative": "data/processed/frames/video_1/frame_1.jpg",
                "quality_flags": [],
            },
            {
                "ocr_id": "ocr_000002",
                "video_id": self.video_id,
                "frame_id": "frame_2",
                "frame_timestamp_ms": 1800,
                "start_ms": 1800,
                "end_ms": 1801,
                "text": "MCP Context",
                "normalized_text": "mcp context",
                "quality_score": 0.9,
                "mean_confidence": 0.9,
                "parent_atom_ids": ["atom_1"],
                "frame_path_relative": "data/processed/frames/video_1/frame_2.jpg",
                "quality_flags": [],
            },
        ]
        tracks = _build_ocr_tracks(records)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["frame_references"][0]["frame_id"], "frame_1")
        self.assertEqual(tracks[0]["record_ids"], ["ocr_000001", "ocr_000002"])

    def test_speaker_turn_merge_adds_quality_and_atom_links(self) -> None:
        turns = _merge_turns(
            [
                {
                    "segment_id": "s1",
                    "speaker_id": "speaker_00",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "text": "hello",
                    "parent_chunk_id": "chunk_1",
                    "parent_event_id": "event_1",
                    "parent_atom_ids": ["atom_1"],
                    "quality_score": 0.7,
                },
                {
                    "segment_id": "s2",
                    "speaker_id": "speaker_00",
                    "start_ms": 1500,
                    "end_ms": 3000,
                    "text": "again",
                    "parent_chunk_id": "chunk_1",
                    "parent_event_id": "event_1",
                    "parent_atom_ids": ["atom_1"],
                    "quality_score": 0.9,
                },
            ]
        )
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["segment_ids"], ["s1", "s2"])
        self.assertEqual(turns[0]["quality_score"], 0.8)
        self.assertEqual(turns[0]["parent_atom_ids"], ["atom_1"])

    def test_audio_events_have_transition_and_quality_fields(self) -> None:
        from src.pipeline.media_manifest import load_manifest
        from src.pipeline.modality_common import hierarchy_maps

        maps = hierarchy_maps(load_manifest(repo_root=self.repo, video_id=self.video_id))
        events = _merge_windows(
            [
                {"start_ms": 0, "end_ms": 1000, "label": "silence", "confidence": 0.9, "rms_dbfs": -60, "zero_crossing_rate": 0.0, "spectral_centroid_hz": 0.0, "spectral_flatness": 0.0, "spectral_flux": 0.0, "speech_overlap": 0.0},
                {"start_ms": 1000, "end_ms": 2000, "label": "speech", "confidence": 0.85, "rms_dbfs": -20, "zero_crossing_rate": 0.1, "spectral_centroid_hz": 500, "spectral_flatness": 0.2, "spectral_flux": 0.3, "speech_overlap": 0.8},
            ],
            maps,
        )
        self.assertEqual(events[1]["label"], "speech")
        self.assertTrue(events[1]["is_transition"])
        self.assertIn("quality_score", events[1])
        self.assertEqual(events[1]["parent_atom_ids"], ["atom_1"])

    def test_ocr_retriever_returns_frame_provenance(self) -> None:
        write_json_atomic(
            Path(self.artifacts["ocr_path"]),
            {
                "records": [
                    {
                        "ocr_id": "ocr_000001",
                        "frame_id": "frame_1",
                        "frame_timestamp_ms": 1000,
                        "timestamp_ms": 1000,
                        "start_ms": 1000,
                        "end_ms": 1001,
                        "text": "MCP Context Tools",
                        "quality_score": 0.9,
                        "mean_confidence": 0.9,
                        "frame_path_relative": "data/processed/frames/video_1/frame_1.jpg",
                        "tokens": [{"text": "MCP", "confidence": 0.9, "box": {"left": 1, "top": 2, "width": 3, "height": 4}}],
                    }
                ]
            },
        )
        plan = RetrievalPlan(
            strategy="ocr",
            retrieval_steps=[RetrievalStep(retriever="ocr_sparse", level="frame", query="MCP Context", top_k=5)],
        )
        result = RetrievalOrchestrator(self.repo).execute(
            video_id=self.video_id,
            plan=plan,
            query_understanding={"required_modalities": ["ocr"], "standalone_query": "MCP Context"},
        )
        media_refs = result["candidates"][0]["media_refs"]
        self.assertEqual(media_refs["frame_id"], "frame_1")
        self.assertEqual(media_refs["frame_path_relative"], "data/processed/frames/video_1/frame_1.jpg")
        self.assertEqual(media_refs["tokens"][0]["text"], "MCP")


if __name__ == "__main__":
    unittest.main()
