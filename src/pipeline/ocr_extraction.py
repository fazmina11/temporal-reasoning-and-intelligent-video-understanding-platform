from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now
from .modality_common import hierarchy_maps, timeline_parents

OCR_SCHEMA_VERSION = "ocr-artifacts-v1"


class OCRExtractionError(RuntimeError):
    pass


def resolve_tesseract() -> Path | None:
    candidates = []
    configured = os.getenv("TESSERACT_PATH")
    if configured:
        candidates.append(Path(configured))
    discovered = shutil.which("tesseract")
    if discovered:
        candidates.append(Path(discovered))
    if os.name == "nt":
        candidates.extend(
            [
                Path(os.getenv("PROGRAMFILES", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe",
                Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
            ]
        )
    return next((path.resolve() for path in candidates if path.is_file()), None)


def extract_ocr_artifacts(
    *, repo_root: Path, video_id: str, language: str = "eng", min_confidence: float = 35.0
) -> dict[str, Any]:
    try:
        import cv2
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise OCRExtractionError("OCR requires opencv-python and pytesseract.") from exc

    executable = resolve_tesseract()
    if executable is None:
        raise OCRExtractionError(
            "Tesseract executable was not found. Install Tesseract OCR or set TESSERACT_PATH."
        )
    pytesseract.pytesseract.tesseract_cmd = str(executable)

    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    frame_payload = read_json(Path(manifest["artifacts"]["frame_index_path"]))
    maps = hierarchy_maps(manifest)
    records = []
    for frame in frame_payload.get("frames", []):
        frame_path = Path(frame.get("path") or repo_root / frame["path_relative"])
        image = cv2.imread(str(frame_path))
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 5, 45, 45)
        processed = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        result = pytesseract.image_to_data(
            processed, lang=language, config="--oem 3 --psm 11", output_type=Output.DICT
        )
        tokens = []
        for index, raw_text in enumerate(result.get("text", [])):
            text = " ".join(str(raw_text).split())
            try:
                confidence = float(result["conf"][index])
            except (TypeError, ValueError, KeyError):
                confidence = -1.0
            if not text or confidence < min_confidence:
                continue
            tokens.append(
                {
                    "text": text,
                    "confidence": round(confidence / 100.0, 4),
                    "box": {
                        "left": int(result["left"][index]),
                        "top": int(result["top"][index]),
                        "width": int(result["width"][index]),
                        "height": int(result["height"][index]),
                    },
                }
            )
        text = " ".join(token["text"] for token in tokens)
        if not text:
            continue
        timestamp_ms = int(frame["timestamp_ms"])
        records.append(
            {
                "ocr_id": f"ocr_{len(records) + 1:06d}",
                "video_id": video_id,
                "frame_id": frame["frame_id"],
                "timestamp_ms": timestamp_ms,
                "start_ms": timestamp_ms,
                "end_ms": min(int(manifest["duration_ms"]), timestamp_ms + 1),
                **timeline_parents(timestamp_ms, maps),
                "text": text,
                "tokens": tokens,
                "mean_confidence": round(sum(t["confidence"] for t in tokens) / len(tokens), 4),
                "frame_path_relative": frame.get("path_relative"),
            }
        )

    output_path = Path(manifest["artifacts"]["ocr_path"])
    payload = {
        "schema_version": OCR_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "backend": "tesseract",
        "backend_path": executable.name,
        "language": language,
        "frame_count_processed": len(frame_payload.get("frames", [])),
        "record_count": len(records),
        "records": records,
        "created_at": utc_now(),
    }
    write_json_atomic(output_path, payload)
    manifest.setdefault("artifact_metadata", {})["ocr"] = {
        "schema_version": OCR_SCHEMA_VERSION,
        "record_count": len(records),
        "backend": "tesseract",
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return payload
