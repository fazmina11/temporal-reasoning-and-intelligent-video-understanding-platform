from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now
from .modality_common import hierarchy_maps, timeline_parent_ids
from .modality_quality import quality_summary, write_quality_report

OCR_SCHEMA_VERSION = "ocr-artifacts-v2"
OCR_MIN_TRACK_QUALITY = 0.55
OCR_TEMPORAL_MERGE_GAP_MS = 1200


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
    processed_count = 0
    unreadable_frames: list[dict[str, Any]] = []
    for frame in frame_payload.get("frames", []):
        frame_path = Path(frame.get("path") or repo_root / frame["path_relative"])
        image = cv2.imread(str(frame_path))
        if image is None:
            unreadable_frames.append({"frame_id": frame.get("frame_id"), "path_relative": frame.get("path_relative")})
            continue
        processed_count += 1
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
        tokens = _sort_tokens(tokens)
        text = " ".join(token["text"] for token in tokens)
        if not text:
            continue
        timestamp_ms = int(frame["timestamp_ms"])
        parents = timeline_parent_ids(timestamp_ms, min(int(manifest["duration_ms"]), timestamp_ms + 1), maps)
        mean_confidence = round(sum(t["confidence"] for t in tokens) / len(tokens), 4)
        box_coverage = _box_coverage(tokens, image.shape[1], image.shape[0])
        quality_score = _ocr_quality(mean_confidence, len(tokens), box_coverage)
        records.append(
            {
                "ocr_id": f"ocr_{len(records) + 1:06d}",
                "video_id": video_id,
                "frame_id": frame["frame_id"],
                "frame_timestamp_ms": timestamp_ms,
                "timestamp_ms": timestamp_ms,
                "start_ms": timestamp_ms,
                "end_ms": min(int(manifest["duration_ms"]), timestamp_ms + 1),
                **parents,
                "text": text,
                "normalized_text": _normalize_text(text),
                "tokens": tokens,
                "token_count": len(tokens),
                "mean_confidence": mean_confidence,
                "box_coverage_ratio": box_coverage,
                "quality_score": quality_score,
                "quality_flags": _ocr_quality_flags(mean_confidence, len(tokens), box_coverage),
                "frame_path_relative": frame.get("path_relative"),
                "frame_uri": _frame_uri(frame.get("path_relative")),
                "frame_role": frame.get("role"),
            }
        )

    tracks = _build_ocr_tracks(records)
    track_by_record = {
        record_id: track["ocr_track_id"]
        for track in tracks
        for record_id in track["record_ids"]
    }
    for record in records:
        record["ocr_track_id"] = track_by_record.get(record["ocr_id"])

    output_path = Path(manifest["artifacts"]["ocr_path"])
    quality_report_path = write_quality_report(
        repo_root=repo_root,
        video_id=video_id,
        modality="ocr",
        payload={
            "backend": "tesseract",
            "frame_count_total": len(frame_payload.get("frames", [])),
            "frame_count_processed": processed_count,
            "unreadable_frame_count": len(unreadable_frames),
            "record_quality": quality_summary([row["quality_score"] for row in records], minimum=OCR_MIN_TRACK_QUALITY),
            "track_quality": quality_summary([row["quality_score"] for row in tracks], minimum=OCR_MIN_TRACK_QUALITY),
            "track_count": len(tracks),
            "unreadable_frames": unreadable_frames[:50],
        },
    )
    payload = {
        "schema_version": OCR_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "backend": "tesseract",
        "backend_path": executable.name,
        "language": language,
        "config": {
            "min_confidence": min_confidence,
            "temporal_merge_gap_ms": OCR_TEMPORAL_MERGE_GAP_MS,
        },
        "frame_count_total": len(frame_payload.get("frames", [])),
        "frame_count_processed": processed_count,
        "unreadable_frame_count": len(unreadable_frames),
        "record_count": len(records),
        "track_count": len(tracks),
        "records": records,
        "tracks": tracks,
        "quality_report_path": str(quality_report_path),
        "created_at": utc_now(),
    }
    write_json_atomic(output_path, payload)
    manifest.setdefault("artifact_metadata", {})["ocr"] = {
        "schema_version": OCR_SCHEMA_VERSION,
        "record_count": len(records),
        "track_count": len(tracks),
        "backend": "tesseract",
        "quality_report_path": str(quality_report_path),
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return payload


def _sort_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tokens, key=lambda item: (item["box"]["top"], item["box"]["left"]))


def _frame_uri(path_relative: Any) -> str:
    rel = str(path_relative or "").replace("\\", "/").lstrip("/")
    if rel.startswith("data/"):
        rel = rel[len("data/") :]
    return f"/data/{rel}" if rel else ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", text).lower()).strip()


def _box_coverage(tokens: list[dict[str, Any]], width: int, height: int) -> float:
    if not tokens or width <= 0 or height <= 0:
        return 0.0
    area = sum(max(0, token["box"]["width"]) * max(0, token["box"]["height"]) for token in tokens)
    return round(min(1.0, area / max(1, width * height)), 6)


def _ocr_quality(mean_confidence: float, token_count: int, box_coverage: float) -> float:
    token_score = min(1.0, token_count / 8)
    coverage_score = min(1.0, box_coverage / 0.18) if box_coverage else 0.2
    return round(min(1.0, (0.70 * mean_confidence) + (0.20 * token_score) + (0.10 * coverage_score)), 4)


def _ocr_quality_flags(mean_confidence: float, token_count: int, box_coverage: float) -> list[str]:
    flags = []
    if mean_confidence < OCR_MIN_TRACK_QUALITY:
        flags.append("low_confidence")
    if token_count <= 1:
        flags.append("single_token")
    if box_coverage > 0.40:
        flags.append("large_overlay_or_noisy_region")
    if box_coverage < 0.0005:
        flags.append("tiny_text_region")
    return flags


def _build_ocr_tracks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for record in sorted(records, key=lambda row: (row["normalized_text"], row["start_ms"])):
        if (
            groups
            and groups[-1][-1]["normalized_text"] == record["normalized_text"]
            and record["start_ms"] - groups[-1][-1]["end_ms"] <= OCR_TEMPORAL_MERGE_GAP_MS
        ):
            groups[-1].append(record)
        else:
            groups.append([record])
    tracks = []
    for group in groups:
        text = max((row["text"] for row in group), key=len)
        parent_atom_ids = sorted({atom_id for row in group for atom_id in row.get("parent_atom_ids", [])})
        frame_refs = [
            {
                "frame_id": row["frame_id"],
                "timestamp_ms": row["frame_timestamp_ms"],
                "frame_path_relative": row.get("frame_path_relative"),
                "quality_score": row["quality_score"],
            }
            for row in group
        ]
        quality = round(sum(row["quality_score"] for row in group) / len(group), 4)
        tracks.append(
            {
                "ocr_track_id": f"ocr_track_{len(tracks) + 1:06d}",
                "video_id": group[0]["video_id"],
                "start_ms": min(row["start_ms"] for row in group),
                "end_ms": max(row["end_ms"] for row in group),
                "text": text,
                "normalized_text": group[0]["normalized_text"],
                "record_ids": [row["ocr_id"] for row in group],
                "frame_references": frame_refs,
                "frame_count": len(frame_refs),
                "parent_atom_ids": parent_atom_ids,
                "parent_chunk_id": group[0].get("parent_chunk_id"),
                "parent_event_id": group[0].get("parent_event_id"),
                "mean_confidence": round(sum(row["mean_confidence"] for row in group) / len(group), 4),
                "quality_score": quality,
                "quality_flags": sorted({flag for row in group for flag in row.get("quality_flags", [])}),
            }
        )
    return tracks
