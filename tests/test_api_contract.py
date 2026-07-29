from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(api.app, raise_server_exceptions=False)

    def test_openapi_schema_includes_question_and_media_routes(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/videos/{video_id}/questions", paths)
        self.assertIn("/videos/{video_id}/media", paths)

    def test_media_endpoint_supports_byte_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            source_path = repo_root / "data" / "uploads" / "video_001.mp4"
            source_path.parent.mkdir(parents=True)
            source_path.write_bytes(b"0123456789abcdef")

            manifest_path = (
                repo_root / "data" / "processed" / "manifests" / "video_001.json"
            )
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "video_id": "video_001",
                        "video_path": str(source_path),
                        "artifacts": {},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(api, "REPO_ROOT", repo_root):
                response = self.client.get(
                    "/videos/video_001/media",
                    headers={"Range": "bytes=4-7"},
                )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"4567")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-range"], "bytes 4-7/16")
        self.assertTrue(response.headers["content-type"].startswith("video/mp4"))

    def test_media_endpoint_rejects_unmanaged_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            outside_path = repo_root / "outside.mp4"
            outside_path.write_bytes(b"video")
            manifest_path = (
                repo_root / "data" / "processed" / "manifests" / "video_001.json"
            )
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "video_id": "video_001",
                        "video_path": str(outside_path),
                        "artifacts": {},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(api, "REPO_ROOT", repo_root):
                response = self.client.get("/videos/video_001/media")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
