from __future__ import annotations

import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from .media_tools import MediaToolError, resolve_media_tool

PIPELINE_VERSION = "base-v1"
STATUS_UPLOADED = "uploaded"
STATUS_FAILED = "failed"
TIME_UNIT = "milliseconds"


class ManifestError(RuntimeError):
    """Raised when a video manifest cannot be created or loaded."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def manifest_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "processed" / "manifests"


def manifest_path(repo_root: Path, video_id: str) -> Path:
    return manifest_dir(repo_root) / f"{video_id}.json"


def planned_audio_path(repo_root: Path, video_id: str) -> Path:
    return repo_root / "data" / "processed" / "audio" / f"{video_id}.wav"


def calculate_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _codec_from_fourcc(raw_fourcc: float) -> str:
    fourcc_int = int(raw_fourcc)
    if fourcc_int <= 0:
        return "unknown"
    chars = [chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]
    codec = "".join(chars).strip()
    return codec or "unknown"


def _milliseconds(value: float | int | None) -> int:
    if value is None:
        return 0
    return max(0, int(float(value) * 1000 + 0.5))


def _run_ffprobe(video_path: Path) -> dict[str, Any] | None:
    try:
        ffprobe = resolve_media_tool("ffprobe")
    except MediaToolError:
        return None
    if not ffprobe:
        return None

    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _parse_fps(raw_rate: str | None) -> float:
    if not raw_rate or raw_rate == "0/0":
        return 0.0
    if "/" in raw_rate:
        numerator, denominator = raw_rate.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 0.0
    return float(raw_rate)


def _inspect_with_ffprobe(video_path: Path) -> dict[str, Any] | None:
    probe = _run_ffprobe(video_path)
    if not probe:
        return None

    streams = probe.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    format_info = probe.get("format", {})

    duration_seconds = float(
        video_stream.get("duration")
        or format_info.get("duration")
        or 0.0
    )
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    frame_count = int(float(video_stream.get("nb_frames") or 0))
    if not frame_count and fps > 0 and duration_seconds > 0:
        frame_count = int(round(fps * duration_seconds))

    audio_sample_rate = audio_stream.get("sample_rate")

    return {
        "probe_backend": "ffprobe",
        "duration_ms": _milliseconds(duration_seconds),
        "duration_seconds": round(duration_seconds, 3),
        "fps": round(fps, 3),
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "resolution": {
            "width": width,
            "height": height,
        },
        "video_codec": video_stream.get("codec_name") or "unknown",
        "audio_codec": audio_stream.get("codec_name") or None,
        "audio_sample_rate": int(audio_sample_rate) if audio_sample_rate else None,
        "has_audio": bool(audio_stream),
        "probe_warnings": [],
    }


def inspect_video(video_path: Path) -> dict[str, Any]:
    if not video_path.exists():
        raise ManifestError(f"Video file does not exist: {video_path}")

    ffprobe_metadata = _inspect_with_ffprobe(video_path)
    if ffprobe_metadata:
        return ffprobe_metadata

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ManifestError(f"Could not open video file: {video_path}")

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        codec = _codec_from_fourcc(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    finally:
        cap.release()

    duration_seconds = frame_count / fps if fps > 0 else 0.0

    return {
        "probe_backend": "opencv",
        "duration_ms": _milliseconds(duration_seconds),
        "duration_seconds": round(duration_seconds, 3),
        "fps": round(fps, 3),
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "resolution": {
            "width": width,
            "height": height,
        },
        "video_codec": codec,
        "audio_codec": None,
        "audio_sample_rate": None,
        "has_audio": None,
        "probe_warnings": [
            "ffprobe was not available; audio metadata could not be inspected."
        ],
    }


def create_media_manifest(
    *,
    repo_root: Path,
    video_id: str,
    original_filename: str,
    video_path: Path,
    upload_extension: str,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    video_path = video_path.resolve()
    audio_path = planned_audio_path(repo_root, video_id)
    processed_root = repo_root / "data" / "processed"
    for path in [
        processed_root / "manifests",
        processed_root / "audio",
        processed_root / "transcripts",
        processed_root / "atoms",
        processed_root / "chunks",
        processed_root / "boundaries",
        processed_root / "semantic_chunks",
        processed_root / "frames" / video_id,
        processed_root / "clips" / video_id,
        processed_root / "visual_artifacts",
        processed_root / "ocr",
        processed_root / "speakers",
        processed_root / "audio_events",
        processed_root / "scope_profiles",
        processed_root / "evidence_registry",
        processed_root / "events",
        processed_root / "chapters",
        processed_root / "reports",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    metadata = inspect_video(video_path)
    source_sha256 = calculate_sha256(video_path)
    created_at = utc_now()
    duration_ms = metadata["duration_ms"]

    manifest = {
        "video_id": video_id,
        "source_filename": original_filename,
        "original_filename": original_filename,
        "upload_extension": upload_extension,
        "source_path": str(video_path),
        "source_path_relative": str(video_path.relative_to(repo_root)),
        "source_sha256": source_sha256,
        "video_path": str(video_path),
        "video_path_relative": str(video_path.relative_to(repo_root)),
        "audio_path": str(audio_path),
        "audio_path_relative": str(audio_path.relative_to(repo_root)),
        "duration_ms": duration_ms,
        "duration_seconds": metadata["duration_seconds"],
        "fps": metadata["fps"],
        "frame_count": metadata["frame_count"],
        "resolution": metadata["resolution"],
        "width": metadata["width"],
        "height": metadata["height"],
        "video_codec": metadata["video_codec"],
        "audio_codec": metadata["audio_codec"],
        "audio_sample_rate": metadata["audio_sample_rate"],
        "has_audio": metadata["has_audio"],
        "codec": metadata["video_codec"],
        "probe_backend": metadata["probe_backend"],
        "probe_warnings": metadata["probe_warnings"],
        "timeline": {
            "time_unit": TIME_UNIT,
            "start_ms": 0,
            "end_ms": duration_ms,
            "duration_ms": duration_ms,
            "duration_seconds_display": metadata["duration_seconds"],
            "normalized": True,
            "normalization_version": "timeline-v1",
            "source_start_offset_ms": 0,
            "audio_start_offset_ms": 0,
            "video_start_offset_ms": 0,
            "conflict_policy": {
                "primary_time_field": "milliseconds",
                "rounding": "positive_seconds_to_nearest_integer_ms",
                "float_seconds_allowed_for_display_only": True,
            },
        },
        "processing": {
            "status": STATUS_UPLOADED,
            "processing_status": STATUS_UPLOADED,
            "progress": 0,
            "current_phase": "upload",
            "error": None,
            "started_at": None,
            "completed_at": None,
            "updated_at": created_at,
        },
        "artifacts": {
            "manifest_path": str(manifest_path(repo_root, video_id)),
            "audio_path": str(audio_path),
            "transcript_path": str(repo_root / "data" / "processed" / "transcripts" / f"{video_id}.json"),
            "atoms_path": str(repo_root / "data" / "processed" / "atoms" / f"{video_id}.json"),
            "chunks_path": str(repo_root / "data" / "processed" / "chunks" / f"{video_id}.json"),
            "frames_dir": str(repo_root / "data" / "processed" / "frames" / video_id),
            "frame_index_path": str(repo_root / "data" / "processed" / "frames" / video_id / "frames.json"),
            "clips_dir": str(repo_root / "data" / "processed" / "clips" / video_id),
            "visual_artifacts_path": str(repo_root / "data" / "processed" / "visual_artifacts" / f"{video_id}.json"),
            "ocr_path": str(repo_root / "data" / "processed" / "ocr" / f"{video_id}.json"),
            "speakers_path": str(repo_root / "data" / "processed" / "speakers" / f"{video_id}.json"),
            "audio_events_path": str(repo_root / "data" / "processed" / "audio_events" / f"{video_id}.json"),
            "scope_profile_path": str(repo_root / "data" / "processed" / "scope_profiles" / f"{video_id}.json"),
            "evidence_registry_path": str(repo_root / "data" / "processed" / "evidence_registry" / f"{video_id}.jsonl"),
            "boundaries_path": str(repo_root / "data" / "processed" / "boundaries" / f"{video_id}.json"),
            "semantic_chunks_path": str(repo_root / "data" / "processed" / "semantic_chunks" / f"{video_id}.json"),
            "events_path": str(repo_root / "data" / "processed" / "events" / f"{video_id}.json"),
            "chapters_path": str(repo_root / "data" / "processed" / "chapters" / f"{video_id}.json"),
            "timeline_validation_path": str(repo_root / "data" / "processed" / "reports" / f"{video_id}_timeline_validation.json"),
            "atom_validation_path": str(repo_root / "data" / "processed" / "reports" / f"{video_id}_atom_validation.json"),
            "chunk_validation_path": str(repo_root / "data" / "processed" / "reports" / f"{video_id}_chunk_validation.json"),
            "hierarchy_validation_path": str(repo_root / "data" / "processed" / "reports" / f"{video_id}_hierarchy_validation.json"),
            "frame_validation_path": str(repo_root / "data" / "processed" / "reports" / f"{video_id}_frame_validation.json"),
        },
        "pipeline_version": PIPELINE_VERSION,
        "created_at": created_at,
        "updated_at": created_at,
    }

    validate_manifest_timeline(manifest)
    save_manifest(repo_root=repo_root, manifest=manifest)
    return manifest


def save_manifest(*, repo_root: Path, manifest: dict[str, Any]) -> Path:
    video_id = manifest["video_id"]
    validate_manifest_timeline(manifest)
    path = manifest_path(repo_root, video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_manifest(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    path = manifest_path(repo_root, video_id)
    if not path.exists():
        raise ManifestError(f"Manifest not found for video_id={video_id}: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = manifest.setdefault("artifacts", {})
    frames_dir = repo_root / "data" / "processed" / "frames" / video_id
    artifacts.setdefault("frames_dir", str(frames_dir))
    artifacts.setdefault("frame_index_path", str(frames_dir / "frames.json"))
    artifacts.setdefault(
        "clips_dir",
        str(repo_root / "data" / "processed" / "clips" / video_id),
    )
    artifacts.setdefault(
        "visual_artifacts_path",
        str(repo_root / "data" / "processed" / "visual_artifacts" / f"{video_id}.json"),
    )
    artifacts.setdefault(
        "ocr_path",
        str(repo_root / "data" / "processed" / "ocr" / f"{video_id}.json"),
    )
    artifacts.setdefault(
        "speakers_path",
        str(repo_root / "data" / "processed" / "speakers" / f"{video_id}.json"),
    )
    artifacts.setdefault(
        "audio_events_path",
        str(repo_root / "data" / "processed" / "audio_events" / f"{video_id}.json"),
    )
    artifacts.setdefault(
        "scope_profile_path",
        str(repo_root / "data" / "processed" / "scope_profiles" / f"{video_id}.json"),
    )
    artifacts.setdefault(
        "evidence_registry_path",
        str(repo_root / "data" / "processed" / "evidence_registry" / f"{video_id}.jsonl"),
    )
    artifacts.setdefault(
        "chunk_validation_path",
        str(
            repo_root
            / "data"
            / "processed"
            / "reports"
            / f"{video_id}_chunk_validation.json"
        ),
    )
    artifacts.setdefault(
        "hierarchy_validation_path",
        str(
            repo_root
            / "data"
            / "processed"
            / "reports"
            / f"{video_id}_hierarchy_validation.json"
        ),
    )
    artifacts.setdefault(
        "frame_validation_path",
        str(
            repo_root
            / "data"
            / "processed"
            / "reports"
            / f"{video_id}_frame_validation.json"
        ),
    )
    return manifest


def update_manifest_status(
    *,
    repo_root: Path,
    video_id: str,
    status: str,
    progress: int,
    current_phase: str,
    error: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    now = utc_now()
    processing = manifest.setdefault("processing", {})
    processing["status"] = status
    processing["processing_status"] = status
    processing["progress"] = progress
    processing["current_phase"] = current_phase
    processing["updated_at"] = now
    processing["error"] = error

    if processing.get("started_at") is None and status not in {STATUS_UPLOADED, STATUS_FAILED}:
        processing["started_at"] = now

    if status in {"completed", STATUS_FAILED}:
        processing["completed_at"] = now

    manifest["updated_at"] = now
    save_manifest(repo_root=repo_root, manifest=manifest)
    return manifest


def validate_manifest_timeline(manifest: dict[str, Any]) -> None:
    timeline = manifest.get("timeline") or {}
    duration_ms = manifest.get("duration_ms")
    start_ms = timeline.get("start_ms")
    end_ms = timeline.get("end_ms")
    timeline_duration_ms = timeline.get("duration_ms")

    required_integer_fields = {
        "duration_ms": duration_ms,
        "timeline.start_ms": start_ms,
        "timeline.end_ms": end_ms,
        "timeline.duration_ms": timeline_duration_ms,
    }
    for name, value in required_integer_fields.items():
        if not isinstance(value, int):
            raise ManifestError(f"{name} must be an integer millisecond value.")
        if value < 0:
            raise ManifestError(f"{name} must not be negative.")

    if start_ms != 0:
        raise ManifestError("Normalized timeline must start at 0 ms.")
    if end_ms != duration_ms:
        raise ManifestError("timeline.end_ms must match manifest.duration_ms.")
    if timeline_duration_ms != duration_ms:
        raise ManifestError("timeline.duration_ms must match manifest.duration_ms.")
    if end_ms < start_ms:
        raise ManifestError("timeline.end_ms must be greater than or equal to timeline.start_ms.")
    if manifest.get("frame_count", 0) < 0:
        raise ManifestError("frame_count must not be negative.")
    if manifest.get("fps", 0) < 0:
        raise ManifestError("fps must not be negative.")
