from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.pipeline.atomic_spans import build_atomic_spans, validate_atomic_spans
from src.pipeline.json_artifacts import read_json, write_json_atomic
from src.pipeline.media_manifest import save_manifest, utc_now


class AtomicSpanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name)
        self.video_id = "video_test"
        processed = self.repo_root / "data" / "processed"
        now = utc_now()
        self.manifest = {
            "video_id": self.video_id,
            "source_sha256": "a" * 64,
            "duration_ms": 31_000,
            "fps": 30.0,
            "frame_count": 930,
            "timeline": {
                "start_ms": 0,
                "end_ms": 31_000,
                "duration_ms": 31_000,
            },
            "artifacts": {
                "boundaries_path": str(processed / "boundaries" / "video_test.json"),
                "atoms_path": str(processed / "atoms" / "video_test.json"),
                "atom_validation_path": str(
                    processed / "reports" / "video_test_atom_validation.json"
                ),
            },
            "pipeline_version": "base-v1",
            "created_at": now,
            "updated_at": now,
        }
        save_manifest(repo_root=self.repo_root, manifest=self.manifest)
        write_json_atomic(
            Path(self.manifest["artifacts"]["boundaries_path"]),
            {
                "schema_version": "boundary-signals-v1",
                "video_id": self.video_id,
                "source_sha256": "a" * 64,
                "duration_ms": 31_000,
                "candidates": [
                    {
                        "boundary_id": "boundary_000001",
                        "timestamp_ms": 7_900,
                        "signals": ["sentence_boundary"],
                        "score": 0.68,
                    },
                    {
                        "boundary_id": "boundary_000002",
                        "timestamp_ms": 16_100,
                        "signals": ["sentence_boundary", "pause"],
                        "score": 0.90,
                    },
                    {
                        "boundary_id": "boundary_000003",
                        "timestamp_ms": 29_500,
                        "signals": ["scene_cut"],
                        "score": 0.86,
                    },
                ],
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builder_creates_an_exact_non_overlapping_timeline(self) -> None:
        result = build_atomic_spans(
            repo_root=self.repo_root,
            video_id=self.video_id,
        )
        report = validate_atomic_spans(
            repo_root=self.repo_root,
            video_id=self.video_id,
        )

        atoms = result["atoms"]
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(atoms[0]["start_ms"], 0)
        self.assertEqual(atoms[-1]["end_ms"], 31_000)
        self.assertTrue(
            all(left["end_ms"] == right["start_ms"] for left, right in zip(atoms, atoms[1:]))
        )
        self.assertTrue(all(atom["duration_ms"] <= 20_000 for atom in atoms))

    def test_validator_detects_a_gap_and_bad_pointer(self) -> None:
        build_atomic_spans(repo_root=self.repo_root, video_id=self.video_id)
        atoms_path = Path(self.manifest["artifacts"]["atoms_path"])
        payload = read_json(atoms_path)
        payload["atoms"][1]["start_ms"] += 100
        payload["atoms"][1]["duration_ms"] -= 100
        payload["atoms"][0]["next_atom_id"] = "atom_missing"
        write_json_atomic(atoms_path, payload)

        report = validate_atomic_spans(
            repo_root=self.repo_root,
            video_id=self.video_id,
        )
        error_codes = {item["code"] for item in report["errors"]}
        self.assertFalse(report["valid"])
        self.assertIn("timeline_gap", error_codes)
        self.assertIn("next_pointer", error_codes)


if __name__ == "__main__":
    unittest.main()
