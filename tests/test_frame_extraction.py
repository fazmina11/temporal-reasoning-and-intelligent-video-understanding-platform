from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.frame_extraction import (
    FRAME_MODE_ALL,
    FrameExtractionConfig,
    build_frame_targets,
    run_frame_extraction,
)
from src.pipeline.json_artifacts import write_json_atomic
from src.pipeline.media_manifest import create_media_manifest


class FrameTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.atoms = [
            {"atom_id": "atom_000001", "start_ms": 0, "end_ms": 7_000},
            {"atom_id": "atom_000002", "start_ms": 7_000, "end_ms": 15_000},
            {"atom_id": "atom_000003", "start_ms": 15_000, "end_ms": 23_000},
        ]

    def test_atom_coverage_targets_include_every_atom(self) -> None:
        targets = build_frame_targets(
            duration_ms=23_000,
            fps=30.0,
            frame_count=690,
            atoms=self.atoms,
            config=FrameExtractionConfig(interval_ms=2_000),
        )
        related_atoms = {
            atom_id
            for target in targets.values()
            for atom_id in target["related_atom_ids"]
        }
        self.assertEqual(
            related_atoms,
            {"atom_000001", "atom_000002", "atom_000003"},
        )
        self.assertIn(0, targets)
        self.assertIn(689, targets)
        self.assertLess(len(targets), 690)

    def test_all_frames_mode_targets_every_source_frame(self) -> None:
        targets = build_frame_targets(
            duration_ms=23_000,
            fps=30.0,
            frame_count=690,
            atoms=self.atoms,
            config=FrameExtractionConfig(mode=FRAME_MODE_ALL),
        )
        self.assertEqual(len(targets), 690)
        self.assertEqual(min(targets), 0)
        self.assertEqual(max(targets), 689)


@unittest.skipUnless(
    os.getenv("RUN_MEDIA_INTEGRATION") == "1",
    "Set RUN_MEDIA_INTEGRATION=1 to run FFmpeg media integration tests.",
)
class AllFramesMediaIntegrationTests(unittest.TestCase):
    def test_all_frames_mode_exports_every_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            video_path = repo_root / "data" / "uploads" / "all_frames_test.mp4"
            video_path.parent.mkdir(parents=True)
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                10.0,
                (64, 48),
            )
            self.assertTrue(writer.isOpened())
            for frame_index in range(30):
                frame = np.full(
                    (48, 64, 3),
                    (frame_index * 7) % 255,
                    dtype=np.uint8,
                )
                cv2.putText(
                    frame,
                    str(frame_index),
                    (5, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                writer.write(frame)
            writer.release()

            manifest = create_media_manifest(
                repo_root=repo_root,
                video_id="all_frames_test",
                original_filename="all_frames_test.mp4",
                video_path=video_path,
                upload_extension="mp4",
            )
            write_json_atomic(
                Path(manifest["artifacts"]["atoms_path"]),
                {
                    "schema_version": "atomic-spans-v1",
                    "video_id": "all_frames_test",
                    "source_sha256": manifest["source_sha256"],
                    "pipeline_version": manifest["pipeline_version"],
                    "duration_ms": manifest["duration_ms"],
                    "atoms": [
                        {
                            "video_id": "all_frames_test",
                            "atom_id": "atom_000001",
                            "start_ms": 0,
                            "end_ms": manifest["duration_ms"],
                            "duration_ms": manifest["duration_ms"],
                            "previous_atom_id": None,
                            "next_atom_id": None,
                            "pipeline_version": manifest["pipeline_version"],
                        }
                    ],
                },
            )

            result = run_frame_extraction(
                repo_root=repo_root,
                video_id="all_frames_test",
                config=FrameExtractionConfig(mode=FRAME_MODE_ALL),
            )
            frame_index = result["frame_index"]
            self.assertEqual(frame_index["source_frame_count"], 30)
            self.assertEqual(frame_index["extracted_frame_count"], 30)
            self.assertTrue(frame_index["all_source_frames_exported"])
            self.assertTrue(result["validation"]["valid"])


if __name__ == "__main__":
    unittest.main()
