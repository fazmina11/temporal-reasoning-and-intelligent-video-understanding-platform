from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.pipeline.boundary_signals import BoundaryConfig, extract_boundary_signals
from src.pipeline.json_artifacts import write_json_atomic
from src.pipeline.media_manifest import save_manifest, utc_now


class BoundarySignalTests(unittest.TestCase):
    def test_duration_sentence_and_pause_candidates_are_merged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            processed = repo_root / "data" / "processed"
            video_path = repo_root / "data" / "uploads" / "video_test.mp4"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"test-placeholder")
            transcript_path = processed / "transcripts" / "video_test.json"
            now = utc_now()
            manifest = {
                "video_id": "video_test",
                "source_sha256": "b" * 64,
                "video_path": str(video_path),
                "duration_ms": 31_000,
                "fps": 30.0,
                "frame_count": 930,
                "timeline": {
                    "start_ms": 0,
                    "end_ms": 31_000,
                    "duration_ms": 31_000,
                },
                "artifacts": {
                    "transcript_path": str(transcript_path),
                    "boundaries_path": str(
                        processed / "boundaries" / "video_test.json"
                    ),
                },
                "pipeline_version": "base-v1",
                "created_at": now,
                "updated_at": now,
            }
            save_manifest(repo_root=repo_root, manifest=manifest)
            write_json_atomic(
                transcript_path,
                [
                    {
                        "start": 0.5,
                        "end": 4.0,
                        "text": "First idea.",
                        "words": [
                            {"word": " First", "start": 0.5, "end": 2.0},
                            {"word": " idea.", "start": 2.0, "end": 4.0},
                        ],
                    },
                    {
                        "start": 5.2,
                        "end": 8.0,
                        "text": "Second idea.",
                        "words": [
                            {"word": " Second", "start": 5.2, "end": 6.0},
                            {"word": " idea.", "start": 6.0, "end": 8.0},
                        ],
                    },
                ],
            )

            result = extract_boundary_signals(
                repo_root=repo_root,
                video_id="video_test",
                config=BoundaryConfig(
                    enable_scene_cut=False,
                    enable_visual_difference=False,
                ),
            )

            all_signals = {
                signal
                for candidate in result["candidates"]
                for signal in candidate["signals"]
            }
            self.assertEqual(result["duration_ms"], 31_000)
            self.assertIn("duration", all_signals)
            self.assertIn("sentence_boundary", all_signals)
            self.assertIn("pause", all_signals)
            self.assertEqual(result["transcript_stats"]["pause_count"], 1)
            self.assertTrue(
                all(
                    0 < candidate["timestamp_ms"] < 31_000
                    for candidate in result["candidates"]
                )
            )


if __name__ == "__main__":
    unittest.main()
