from __future__ import annotations

import argparse
import bisect
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .atomic_spans import ATOM_SCHEMA_VERSION
from .json_artifacts import read_json, write_json_atomic
from .media_manifest import (
    calculate_sha256,
    load_manifest,
    save_manifest,
    utc_now,
    validate_manifest_timeline,
)

FRAME_INDEX_SCHEMA_VERSION = "frame-index-v1"
FRAME_VALIDATION_SCHEMA_VERSION = "frame-validation-v1"
FRAME_MODE_ATOM_COVERAGE = "atom_coverage"
FRAME_MODE_ALL = "all_frames"


class FrameExtractionError(RuntimeError):
    """Raised when frame evidence cannot be generated or validated."""


@dataclass(frozen=True)
class FrameExtractionConfig:
    mode: str = FRAME_MODE_ATOM_COVERAGE
    interval_ms: int = 2_000
    include_atom_start: bool = False
    include_atom_midpoint: bool = False
    include_atom_end: bool = False
    max_width: int = 1_920
    jpeg_quality: int = 2

    def validate(self) -> None:
        if self.mode not in {FRAME_MODE_ATOM_COVERAGE, FRAME_MODE_ALL}:
            raise FrameExtractionError(
                f"Unsupported frame extraction mode: {self.mode}"
            )
        if self.interval_ms <= 0:
            raise FrameExtractionError("interval_ms must be positive.")
        if self.max_width <= 0:
            raise FrameExtractionError("max_width must be positive.")
        if not 2 <= self.jpeg_quality <= 31:
            raise FrameExtractionError("jpeg_quality must be between 2 and 31.")


def _load_atoms(manifest: dict[str, Any]) -> dict[str, Any]:
    atoms_path = Path(manifest["artifacts"]["atoms_path"])
    if not atoms_path.is_file():
        raise FrameExtractionError(f"Atomic span artifact is missing: {atoms_path}")
    payload = read_json(atoms_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != ATOM_SCHEMA_VERSION:
        raise FrameExtractionError("Atomic span artifact has an unsupported schema.")
    if payload.get("video_id") != manifest["video_id"]:
        raise FrameExtractionError("Atomic span video_id does not match the manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise FrameExtractionError("Atomic span source hash does not match the manifest.")
    if payload.get("duration_ms") != manifest["duration_ms"]:
        raise FrameExtractionError("Atomic span duration does not match the manifest.")
    return payload


def _timestamp_to_frame(timestamp_ms: int, fps: float, frame_count: int) -> int:
    return min(
        frame_count - 1,
        max(0, int(timestamp_ms * fps / 1000 + 0.5)),
    )


def build_frame_targets(
    *,
    duration_ms: int,
    fps: float,
    frame_count: int,
    atoms: list[dict[str, Any]],
    config: FrameExtractionConfig,
) -> dict[int, dict[str, set[str]]]:
    """Create stable source-frame targets with reasons and related atom IDs."""
    config.validate()
    if duration_ms <= 0 or fps <= 0 or frame_count <= 0:
        raise FrameExtractionError(
            "Frame extraction requires positive duration, FPS, and frame count."
        )

    targets: dict[int, dict[str, set[str]]] = {}

    def add(timestamp_ms: int, reason: str, atom_id: str | None = None) -> None:
        frame_index = _timestamp_to_frame(timestamp_ms, fps, frame_count)
        target = targets.setdefault(
            frame_index,
            {"reasons": set(), "related_atom_ids": set()},
        )
        target["reasons"].add(reason)
        if atom_id:
            target["related_atom_ids"].add(atom_id)

    if config.mode == FRAME_MODE_ALL:
        for frame_index in range(frame_count):
            targets[frame_index] = {
                "reasons": {"all_frames"},
                "related_atom_ids": set(),
            }
        return targets

    for timestamp_ms in range(0, duration_ms, config.interval_ms):
        add(timestamp_ms, "timeline_interval")
    add(0, "timeline_start")
    add(max(0, duration_ms - int(1000 / fps + 0.5)), "timeline_end")

    for atom in atoms:
        atom_id = atom["atom_id"]
        start_ms = atom["start_ms"]
        end_ms = atom["end_ms"]
        if config.include_atom_start:
            add(start_ms, "atom_start", atom_id)
        if config.include_atom_midpoint:
            add((start_ms + end_ms) // 2, "atom_midpoint", atom_id)
        if config.include_atom_end:
            end_frame_time = max(start_ms, end_ms - int(1000 / fps + 0.5))
            add(end_frame_time, "atom_end", atom_id)

    # Associate interval targets to atoms and add one compact fallback only when
    # a custom interval is wider than an atom.
    covered_atom_ids: set[str] = set()
    for source_frame_index, target in targets.items():
        timestamp_ms = int(source_frame_index * 1000 / fps + 0.5)
        for atom in atoms:
            if atom["start_ms"] <= timestamp_ms < atom["end_ms"]:
                target["related_atom_ids"].add(atom["atom_id"])
                covered_atom_ids.add(atom["atom_id"])
                break
    for atom in atoms:
        if atom["atom_id"] not in covered_atom_ids:
            add(
                (atom["start_ms"] + atom["end_ms"]) // 2,
                "atom_coverage_fallback",
                atom["atom_id"],
            )
    return targets


def _atom_for_timestamp(atoms: list[dict[str, Any]], timestamp_ms: int) -> str | None:
    starts = [atom["start_ms"] for atom in atoms]
    index = bisect.bisect_right(starts, timestamp_ms) - 1
    if index < 0:
        return None
    atom = atoms[index]
    if atom["start_ms"] <= timestamp_ms < atom["end_ms"]:
        return atom["atom_id"]
    if index == len(atoms) - 1 and timestamp_ms == atom["end_ms"]:
        return atom["atom_id"]
    return None


def _inspect_frame(path: Path) -> dict[str, Any]:
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise FrameExtractionError(f"Extracted frame is not decodable: {path}")
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    black_pixel_ratio = float(np.mean(gray <= 5))
    return {
        "width": width,
        "height": height,
        "sharpness_laplacian_variance": round(sharpness, 3),
        "mean_luminance": round(float(np.mean(gray)), 3),
        "black_pixel_ratio": round(black_pixel_ratio, 6),
    }


def _resize_frame(frame: np.ndarray, max_width: int) -> np.ndarray:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    resized_height = max(2, int(height * scale + 0.5))
    if resized_height % 2:
        resized_height += 1
    return cv2.resize(
        frame,
        (max_width, resized_height),
        interpolation=cv2.INTER_AREA,
    )


def _extract_target_frames_with_opencv(
    *,
    video_path: Path,
    target_indices: list[int],
    staging_dir: Path,
    max_width: int,
    jpeg_quality: int,
) -> list[Path]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FrameExtractionError(f"Could not open video for frame extraction: {video_path}")

    output_paths: list[Path] = []
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, 100 - jpeg_quality * 3))]
    try:
        for output_number, source_frame_index in enumerate(target_indices, start=1):
            capture.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                raise FrameExtractionError(
                    f"Could not decode source frame {source_frame_index}."
                )
            frame = _resize_frame(frame, max_width)
            output_path = staging_dir / f"extract_{output_number:09d}.jpg"
            if not cv2.imwrite(str(output_path), frame, encode_params):
                raise FrameExtractionError(f"Could not write extracted frame: {output_path}")
            output_paths.append(output_path)
    finally:
        capture.release()
    return output_paths


def extract_frames(
    *,
    repo_root: Path,
    video_id: str,
    config: FrameExtractionConfig | None = None,
) -> dict[str, Any]:
    """Extract clear per-video frame evidence and persist a manifest-backed index."""
    config = config or FrameExtractionConfig()
    config.validate()
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    atoms_payload = _load_atoms(manifest)
    atoms = atoms_payload["atoms"]
    fps = float(manifest["fps"])
    frame_count = int(manifest["frame_count"])
    duration_ms = int(manifest["duration_ms"])
    targets = build_frame_targets(
        duration_ms=duration_ms,
        fps=fps,
        frame_count=frame_count,
        atoms=atoms,
        config=config,
    )
    target_indices = sorted(targets)

    frames_dir = Path(manifest["artifacts"]["frames_dir"]).resolve()
    expected_frames_root = (
        repo_root / "data" / "processed" / "frames" / video_id
    ).resolve()
    if frames_dir != expected_frames_root:
        raise FrameExtractionError(
            "Manifest frames_dir is outside the expected video-scoped directory."
        )
    frames_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = frames_dir / f".staging_{uuid.uuid4().hex}"
    staging_dir.mkdir(parents=False)

    try:
        staged_files = _extract_target_frames_with_opencv(
            video_path=Path(manifest["video_path"]),
            target_indices=target_indices,
            staging_dir=staging_dir,
            max_width=config.max_width,
            jpeg_quality=config.jpeg_quality,
        )
        if len(staged_files) != len(target_indices):
            raise FrameExtractionError(
                "Extracted frame count does not match the planned source-frame count: "
                f"expected {len(target_indices)}, got {len(staged_files)}."
            )

        records: list[dict[str, Any]] = []
        for staged_path, source_frame_index in zip(staged_files, target_indices):
            timestamp_ms = min(
                duration_ms - 1,
                max(0, int(source_frame_index * 1000 / fps + 0.5)),
            )
            inspection = _inspect_frame(staged_path)
            final_name = f"frame_{source_frame_index:09d}.jpg"
            final_path = frames_dir / final_name
            target = targets[source_frame_index]
            atom_id = _atom_for_timestamp(atoms, timestamp_ms)
            records.append(
                {
                    "video_id": video_id,
                    "frame_id": final_name.removesuffix(".jpg"),
                    "timestamp_ms": timestamp_ms,
                    "source_frame_index": source_frame_index,
                    "atom_id": atom_id,
                    "related_atom_ids": sorted(target["related_atom_ids"]),
                    "sampling_reasons": sorted(target["reasons"]),
                    "path": str(final_path),
                    "path_relative": str(final_path.relative_to(repo_root)),
                    "file_size_bytes": staged_path.stat().st_size,
                    "sha256": calculate_sha256(staged_path),
                    **inspection,
                    "pipeline_version": manifest["pipeline_version"],
                }
            )

        for old_frame in frames_dir.glob("frame_*.jpg"):
            old_frame.unlink()
        for staged_path, record in zip(staged_files, records):
            staged_path.replace(Path(record["path"]))
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    timestamps = [record["timestamp_ms"] for record in records]
    gaps = [right - left for left, right in zip(timestamps, timestamps[1:])]
    payload = {
        "schema_version": FRAME_INDEX_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": duration_ms,
        "source_frame_count": frame_count,
        "source_fps": fps,
        "config": asdict(config),
        "mode": config.mode,
        "all_source_frames_exported": (
            config.mode == FRAME_MODE_ALL and len(records) == frame_count
        ),
        "extracted_frame_count": len(records),
        "extracted_fraction": round(len(records) / frame_count, 6),
        "maximum_sample_gap_ms": max(gaps, default=0),
        "frames": records,
        "created_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["frame_index_path"]), payload)
    return payload


def validate_frame_index(
    *,
    repo_root: Path,
    video_id: str,
) -> dict[str, Any]:
    """Validate frame files, source identity, ordering, and atom coverage."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    atoms_payload = _load_atoms(manifest)
    atoms = atoms_payload["atoms"]
    frame_index_path = Path(manifest["artifacts"]["frame_index_path"])
    if not frame_index_path.is_file():
        raise FrameExtractionError(f"Frame index is missing: {frame_index_path}")
    payload = read_json(frame_index_path)
    frames = payload.get("frames") if isinstance(payload, dict) else None
    if not isinstance(frames, list):
        raise FrameExtractionError("Frame index has an invalid structure.")

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    atom_ids = {atom["atom_id"] for atom in atoms}
    covered_atom_ids: set[str] = set()
    previous_timestamp = -1
    missing_file_count = 0
    unreadable_file_count = 0

    if payload.get("schema_version") != FRAME_INDEX_SCHEMA_VERSION:
        errors.append({"code": "schema_version", "message": "Unsupported schema."})
    if payload.get("video_id") != video_id:
        errors.append({"code": "video_id", "message": "video_id does not match."})
    if payload.get("source_sha256") != manifest["source_sha256"]:
        errors.append({"code": "source_sha256", "message": "Source hash differs."})
    if payload.get("duration_ms") != manifest["duration_ms"]:
        errors.append({"code": "duration_ms", "message": "Duration differs."})

    for record in frames:
        timestamp_ms = record.get("timestamp_ms")
        frame_id = record.get("frame_id")
        if not isinstance(timestamp_ms, int) or not 0 <= timestamp_ms < manifest["duration_ms"]:
            errors.append(
                {"code": "timestamp", "frame_id": frame_id, "message": "Invalid timestamp."}
            )
            continue
        if timestamp_ms < previous_timestamp:
            errors.append(
                {"code": "ordering", "frame_id": frame_id, "message": "Frames are not ordered."}
            )
        previous_timestamp = timestamp_ms
        atom_id = record.get("atom_id")
        if atom_id in atom_ids:
            covered_atom_ids.add(atom_id)
        else:
            errors.append(
                {"code": "atom_id", "frame_id": frame_id, "message": "Invalid atom_id."}
            )

        frame_path = Path(str(record.get("path") or ""))
        if not frame_path.is_file():
            missing_file_count += 1
            errors.append(
                {"code": "missing_file", "frame_id": frame_id, "message": str(frame_path)}
            )
            continue
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            unreadable_file_count += 1
            errors.append(
                {"code": "unreadable_file", "frame_id": frame_id, "message": str(frame_path)}
            )

    uncovered_atoms = sorted(atom_ids - covered_atom_ids)
    if uncovered_atoms:
        errors.append(
            {
                "code": "atom_coverage",
                "message": f"{len(uncovered_atoms)} atoms have no extracted frame.",
                "atom_ids": uncovered_atoms,
            }
        )
    if payload.get("mode") != FRAME_MODE_ALL:
        warnings.append(
            {
                "code": "sampled_mode",
                "message": (
                    "Timeline evidence is complete, but not every source frame is exported. "
                    "Use all_frames mode only when archival frame-by-frame output is required."
                ),
            }
        )

    report = {
        "schema_version": FRAME_VALIDATION_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "valid": len(errors) == 0,
        "mode": payload.get("mode"),
        "all_source_frames_exported": payload.get("all_source_frames_exported", False),
        "complete_atom_coverage": not uncovered_atoms,
        "checks": {
            "source_identity_matches": not any(
                issue["code"] == "source_sha256" for issue in errors
            ),
            "timestamps_are_ordered_and_valid": not any(
                issue["code"] in {"timestamp", "ordering"} for issue in errors
            ),
            "all_frame_files_exist": missing_file_count == 0,
            "all_frame_files_are_decodable": unreadable_file_count == 0,
            "every_atom_has_frame_evidence": not uncovered_atoms,
        },
        "metrics": {
            "source_frame_count": manifest["frame_count"],
            "extracted_frame_count": len(frames),
            "covered_atom_count": len(covered_atom_ids),
            "total_atom_count": len(atom_ids),
            "missing_file_count": missing_file_count,
            "unreadable_file_count": unreadable_file_count,
            "maximum_sample_gap_ms": payload.get("maximum_sample_gap_ms"),
        },
        "errors": errors,
        "warnings": warnings,
        "validated_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["frame_validation_path"]), report)
    return report


def run_frame_extraction(
    *,
    repo_root: Path,
    video_id: str,
    config: FrameExtractionConfig | None = None,
) -> dict[str, Any]:
    frame_index = extract_frames(
        repo_root=repo_root,
        video_id=video_id,
        config=config,
    )
    validation = validate_frame_index(repo_root=repo_root, video_id=video_id)
    if not validation["valid"]:
        raise FrameExtractionError(
            f"Frame validation failed with {len(validation['errors'])} error(s)."
        )

    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    manifest.setdefault("artifact_metadata", {})["frame_extraction"] = {
        "schema_version": frame_index["schema_version"],
        "mode": frame_index["mode"],
        "source_frame_count": frame_index["source_frame_count"],
        "extracted_frame_count": frame_index["extracted_frame_count"],
        "all_source_frames_exported": frame_index["all_source_frames_exported"],
        "complete_atom_coverage": validation["complete_atom_coverage"],
        "validation_passed": True,
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return {"frame_index": frame_index, "validation": validation}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract validated frame evidence.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
    )
    parser.add_argument(
        "--all-frames",
        action="store_true",
        help="Export every source frame. This can require substantial storage.",
    )
    parser.add_argument("--interval-ms", type=int, default=2_000)
    args = parser.parse_args()
    config = FrameExtractionConfig(
        mode=FRAME_MODE_ALL if args.all_frames else FRAME_MODE_ATOM_COVERAGE,
        interval_ms=args.interval_ms,
    )
    result = run_frame_extraction(
        repo_root=Path(args.repo_root),
        video_id=args.video_id,
        config=config,
    )
    print(
        f"Frame extraction complete: "
        f"{result['frame_index']['extracted_frame_count']} / "
        f"{result['frame_index']['source_frame_count']} source frames exported; "
        f"all atoms covered."
    )


if __name__ == "__main__":
    main()
