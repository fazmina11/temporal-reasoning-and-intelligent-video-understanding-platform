from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .atomic_spans import ATOM_SCHEMA_VERSION, validate_atomic_spans
from .boundary_signals import BOUNDARY_SCHEMA_VERSION
from .frame_extraction import (
    FrameExtractionConfig,
    run_frame_extraction,
    validate_frame_index,
)
from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now, validate_manifest_timeline
from .media_tools import MediaToolError, resolve_media_tool

VISUAL_ARTIFACT_SCHEMA_VERSION = "visual-artifacts-v1"


class VisualAttachmentError(RuntimeError):
    """Raised when frame or clip evidence cannot be attached to atoms."""


def _load_atoms(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(Path(manifest["artifacts"]["atoms_path"]))
    if not isinstance(payload, dict) or payload.get("schema_version") != ATOM_SCHEMA_VERSION:
        raise VisualAttachmentError("Atomic span artifact has an unsupported schema.")
    if payload.get("video_id") != manifest["video_id"]:
        raise VisualAttachmentError("Atom video_id does not match manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise VisualAttachmentError("Atom source hash does not match manifest.")
    return payload


def _load_frame_index(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(Path(manifest["artifacts"]["frame_index_path"]))
    if not isinstance(payload, dict) or not isinstance(payload.get("frames"), list):
        raise VisualAttachmentError("Frame index artifact has an invalid structure.")
    if payload.get("video_id") != manifest["video_id"]:
        raise VisualAttachmentError("Frame index video_id does not match manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise VisualAttachmentError("Frame index source hash does not match manifest.")
    return payload


def _load_visual_boundaries(manifest: dict[str, Any]) -> list[int]:
    path = Path(manifest["artifacts"]["boundaries_path"])
    if not path.is_file():
        return []
    payload = read_json(path)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != BOUNDARY_SCHEMA_VERSION
        or payload.get("video_id") != manifest["video_id"]
    ):
        return []
    return [
        int(candidate["timestamp_ms"])
        for candidate in payload.get("candidates", [])
        if isinstance(candidate, dict)
        and "visual_difference" in candidate.get("signals", [])
        and isinstance(candidate.get("timestamp_ms"), int)
    ]


def _frames_for_atom(frames: list[dict[str, Any]], atom: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        frame
        for frame in frames
        if frame.get("atom_id") == atom["atom_id"]
        or atom["atom_id"] in frame.get("related_atom_ids", [])
        or atom["start_ms"] <= int(frame.get("timestamp_ms", -1)) < atom["end_ms"]
    ]


def _closest_frame(
    frames: list[dict[str, Any]],
    timestamp_ms: int,
    label: str,
) -> dict[str, Any] | None:
    if not frames:
        return None
    frame = min(
        frames,
        key=lambda item: abs(int(item["timestamp_ms"]) - timestamp_ms),
    )
    return {
        "role": label,
        "frame_id": frame["frame_id"],
        "timestamp_ms": frame["timestamp_ms"],
        "path_relative": frame["path_relative"],
        "source_frame_index": frame["source_frame_index"],
    }


def _ocr_readability_score(frame: dict[str, Any]) -> float:
    sharpness = float(frame.get("sharpness_laplacian_variance") or 0.0)
    luminance = float(frame.get("mean_luminance") or 0.0)
    black_ratio = float(frame.get("black_pixel_ratio") or 0.0)
    luminance_score = 1.0 - min(1.0, abs(luminance - 170.0) / 170.0)
    sharpness_score = min(1.0, sharpness / 250.0)
    contrast_penalty = min(0.6, black_ratio)
    return round(max(0.0, 0.65 * sharpness_score + 0.35 * luminance_score - contrast_penalty), 4)


def _best_frame(frames: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    if not frames:
        return None
    scored = [
        (
            _ocr_readability_score(frame),
            float(frame.get("sharpness_laplacian_variance") or 0.0),
            frame,
        )
        for frame in frames
    ]
    _score, _sharpness, frame = max(scored, key=lambda item: (item[0], item[1]))
    return {
        "role": label,
        "frame_id": frame["frame_id"],
        "timestamp_ms": frame["timestamp_ms"],
        "path_relative": frame["path_relative"],
        "source_frame_index": frame["source_frame_index"],
        "ocr_readability_score": _ocr_readability_score(frame),
    }


def _highest_visual_change_frame(
    frames: list[dict[str, Any]],
    visual_boundary_timestamps: list[int],
    atom: dict[str, Any],
) -> dict[str, Any] | None:
    timestamps = [
        timestamp
        for timestamp in visual_boundary_timestamps
        if atom["start_ms"] <= timestamp < atom["end_ms"]
    ]
    if timestamps:
        target = timestamps[0]
        return _closest_frame(frames, target, "highest_visual_change")
    return _best_frame(frames, "highest_visual_change_fallback")


def _unique_references(references: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for reference in references:
        if not reference:
            continue
        frame_id = reference["frame_id"]
        existing = unique.get(frame_id)
        if existing:
            roles = set(str(existing["role"]).split("+"))
            roles.update(str(reference["role"]).split("+"))
            existing["role"] = "+".join(sorted(roles))
        else:
            unique[frame_id] = dict(reference)
    return sorted(unique.values(), key=lambda item: item["timestamp_ms"])


def _extract_clip(
    *,
    ffmpeg: Path,
    repo_root: Path,
    manifest: dict[str, Any],
    atom: dict[str, Any],
    clip_path: Path,
) -> dict[str, Any]:
    start_seconds = atom["start_ms"] / 1000
    duration_seconds = atom["duration_ms"] / 1000
    temporary_path = clip_path.with_suffix(".tmp.mp4")
    command = [
        str(ffmpeg),
        "-v",
        "error",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        manifest["video_path"],
        "-t",
        f"{duration_seconds:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(temporary_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        temporary_path.unlink(missing_ok=True)
        raise VisualAttachmentError(
            "FFmpeg clip extraction failed: " + completed.stderr.strip()
        )
    temporary_path.replace(clip_path)
    return {
        "clip_path": str(clip_path),
        "clip_path_relative": str(clip_path.relative_to(repo_root)),
        "clip_start_ms": atom["start_ms"],
        "clip_end_ms": atom["end_ms"],
        "clip_duration_ms": atom["duration_ms"],
        "file_size_bytes": clip_path.stat().st_size,
    }


def attach_visual_artifacts(
    *,
    repo_root: Path,
    video_id: str,
    create_clips: bool = True,
) -> dict[str, Any]:
    """Run Phase C7 and attach frame plus short-clip evidence to every atom."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)

    run_frame_extraction(
        repo_root=repo_root,
        video_id=video_id,
        config=FrameExtractionConfig(
            mode="atom_coverage",
            interval_ms=2_000,
            include_atom_start=True,
            include_atom_midpoint=True,
            include_atom_end=True,
        ),
    )
    frame_validation = validate_frame_index(repo_root=repo_root, video_id=video_id)
    if not frame_validation["valid"]:
        raise VisualAttachmentError("Frame validation failed before visual attachment.")

    atom_payload = _load_atoms(manifest)
    frame_payload = _load_frame_index(manifest)
    frames = sorted(frame_payload["frames"], key=lambda item: item["timestamp_ms"])
    visual_boundary_timestamps = _load_visual_boundaries(manifest)
    clips_dir = Path(manifest["artifacts"]["clips_dir"])
    clips_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg: Path | None = None
    if create_clips:
        try:
            ffmpeg = resolve_media_tool("ffmpeg")
        except MediaToolError as exc:
            raise VisualAttachmentError(str(exc)) from exc
        if ffmpeg is None:
            raise VisualAttachmentError("FFmpeg is required for clip extraction.")

    records: list[dict[str, Any]] = []
    for atom in atom_payload["atoms"]:
        atom_frames = _frames_for_atom(frames, atom)
        midpoint_ms = (atom["start_ms"] + atom["end_ms"]) // 2
        end_probe_ms = max(atom["start_ms"], atom["end_ms"] - 1)
        references = _unique_references(
            [
                _closest_frame(atom_frames, atom["start_ms"], "start"),
                _closest_frame(atom_frames, midpoint_ms, "middle"),
                _closest_frame(atom_frames, end_probe_ms, "end"),
                _highest_visual_change_frame(atom_frames, visual_boundary_timestamps, atom),
                _best_frame(atom_frames, "best_ocr_readable"),
            ]
        )
        clip_record = None
        if create_clips and ffmpeg is not None:
            clip_path = clips_dir / f"{atom['atom_id']}.mp4"
            clip_record = _extract_clip(
                ffmpeg=ffmpeg,
                repo_root=repo_root,
                manifest=manifest,
                atom=atom,
                clip_path=clip_path,
            )
        atom["representative_frame_ids"] = [reference["frame_id"] for reference in references]
        atom["frame_timestamps_ms"] = [reference["timestamp_ms"] for reference in references]
        atom["visual_evidence"] = {
            "schema_version": VISUAL_ARTIFACT_SCHEMA_VERSION,
            "frame_references": references,
            "clip": clip_record,
        }
        records.append(
            {
                "video_id": video_id,
                "atom_id": atom["atom_id"],
                "start_ms": atom["start_ms"],
                "end_ms": atom["end_ms"],
                "frame_references": references,
                "clip": clip_record,
            }
        )

    payload = {
        "schema_version": VISUAL_ARTIFACT_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": manifest["duration_ms"],
        "frame_index_path": manifest["artifacts"]["frame_index_path"],
        "clips_dir": manifest["artifacts"]["clips_dir"],
        "atom_count": len(records),
        "clip_count": sum(record["clip"] is not None for record in records),
        "records": records,
        "created_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["visual_artifacts_path"]), payload)
    atom_payload["visual_attachment"] = {
        "schema_version": VISUAL_ARTIFACT_SCHEMA_VERSION,
        "visual_artifacts_path": manifest["artifacts"]["visual_artifacts_path"],
        "attached_atom_count": len(records),
        "clip_count": payload["clip_count"],
        "completed_at": utc_now(),
    }
    atom_payload["updated_at"] = utc_now()
    write_json_atomic(Path(manifest["artifacts"]["atoms_path"]), atom_payload)
    validation = validate_atomic_spans(repo_root=repo_root, video_id=video_id)
    if not validation["valid"]:
        raise VisualAttachmentError("Atom validation failed after visual attachment.")

    manifest.setdefault("artifact_metadata", {})["visual_attachment"] = atom_payload[
        "visual_attachment"
    ]
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return payload
