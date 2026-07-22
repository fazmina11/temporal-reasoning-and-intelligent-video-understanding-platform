from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, utc_now, validate_manifest_timeline
from .media_tools import MediaToolError, resolve_media_tool

BOUNDARY_SCHEMA_VERSION = "boundary-signals-v1"
SIGNAL_ORDER = (
    "duration",
    "sentence_boundary",
    "pause",
    "scene_cut",
    "visual_difference",
)
PLANNED_SIGNAL_ORDER = (
    "speaker_change",
    "ocr_change",
    "topic_embedding_shift",
    "motion_change",
    "audio_event_change",
)


class BoundaryExtractionError(RuntimeError):
    """Raised when boundary signals cannot be produced safely."""


@dataclass(frozen=True)
class BoundaryConfig:
    max_duration_ms: int = 15_000
    pause_threshold_ms: int = 800
    merge_tolerance_ms: int = 350
    scene_cut_threshold: float = 27.0
    visual_sample_interval_ms: int = 1_000
    visual_width: int = 160
    visual_height: int = 90
    visual_difference_threshold: float = 0.08
    enable_transcript: bool = True
    enable_scene_cut: bool = True
    enable_visual_difference: bool = True

    def validate(self) -> None:
        integer_values = {
            "max_duration_ms": self.max_duration_ms,
            "pause_threshold_ms": self.pause_threshold_ms,
            "merge_tolerance_ms": self.merge_tolerance_ms,
            "visual_sample_interval_ms": self.visual_sample_interval_ms,
            "visual_width": self.visual_width,
            "visual_height": self.visual_height,
        }
        for name, value in integer_values.items():
            if not isinstance(value, int) or value <= 0:
                raise BoundaryExtractionError(f"{name} must be a positive integer.")
        if self.scene_cut_threshold <= 0:
            raise BoundaryExtractionError("scene_cut_threshold must be positive.")
        if not 0 < self.visual_difference_threshold <= 1:
            raise BoundaryExtractionError(
                "visual_difference_threshold must be in the interval (0, 1]."
            )


def _seconds_to_ms(value: float | int) -> int:
    return max(0, int(float(value) * 1000 + 0.5))


def _clamp_timestamp(timestamp_ms: int, duration_ms: int) -> int | None:
    if timestamp_ms <= 0 or timestamp_ms >= duration_ms:
        return None
    return timestamp_ms


def _raw_candidate(
    timestamp_ms: int,
    signal: str,
    score: float,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp_ms": timestamp_ms,
        "signal": signal,
        "score": round(max(0.0, min(1.0, score)), 4),
        "details": details or {},
    }


def _duration_candidates(duration_ms: int, config: BoundaryConfig) -> list[dict[str, Any]]:
    candidates = []
    timestamp_ms = config.max_duration_ms
    while timestamp_ms < duration_ms:
        candidates.append(
            _raw_candidate(
                timestamp_ms,
                "duration",
                0.45,
                {"interval_ms": config.max_duration_ms},
            )
        )
        timestamp_ms += config.max_duration_ms
    return candidates


def _load_transcript_segments(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        segments = payload
    elif isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        segments = payload["segments"]
    else:
        raise BoundaryExtractionError(
            f"Transcript must be a segment list or an object containing 'segments': {path}"
        )
    return [segment for segment in segments if isinstance(segment, dict)]


def _transcript_candidates(
    transcript_path: Path,
    duration_ms: int,
    config: BoundaryConfig,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    segments = _load_transcript_segments(transcript_path)
    candidates: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    sentence_count = 0
    pause_count = 0
    sentence_pattern = re.compile(r"[.!?][\"')\]]*$")

    for segment_index, segment in enumerate(segments):
        segment_words = segment.get("words")
        found_word_sentence = False
        if isinstance(segment_words, list):
            for word_index, word in enumerate(segment_words):
                if not isinstance(word, dict):
                    continue
                try:
                    start_ms = _seconds_to_ms(word["start"])
                    end_ms = _seconds_to_ms(word["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                if end_ms < start_ms:
                    continue
                text = str(word.get("word") or "").strip()
                word_record = {
                    "word_id": f"word_{segment_index:06d}_{word_index:06d}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                }
                words.append(word_record)
                timestamp_ms = _clamp_timestamp(end_ms, duration_ms)
                if timestamp_ms is not None and sentence_pattern.search(text):
                    candidates.append(
                        _raw_candidate(
                            timestamp_ms,
                            "sentence_boundary",
                            0.68,
                            {
                                "word_id": word_record["word_id"],
                                "terminal_word": text,
                            },
                        )
                    )
                    sentence_count += 1
                    found_word_sentence = True

        text = str(segment.get("text") or "").strip()
        if not found_word_sentence and sentence_pattern.search(text):
            try:
                timestamp_ms = _clamp_timestamp(
                    _seconds_to_ms(segment["end"]), duration_ms
                )
            except (KeyError, TypeError, ValueError):
                timestamp_ms = None
            if timestamp_ms is not None:
                candidates.append(
                    _raw_candidate(
                        timestamp_ms,
                        "sentence_boundary",
                        0.62,
                        {"segment_index": segment_index},
                    )
                )
                sentence_count += 1

    words.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["word_id"]))
    if words:
        timed_items = words
    else:
        timed_items = []
        for segment_index, segment in enumerate(segments):
            try:
                start_ms = _seconds_to_ms(segment["start"])
                end_ms = _seconds_to_ms(segment["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if end_ms >= start_ms:
                timed_items.append(
                    {
                        "word_id": f"segment_{segment_index:06d}",
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "text": str(segment.get("text") or "").strip(),
                    }
                )
        timed_items.sort(key=lambda item: (item["start_ms"], item["end_ms"]))

    for previous, current in zip(timed_items, timed_items[1:]):
        gap_ms = current["start_ms"] - previous["end_ms"]
        if gap_ms < config.pause_threshold_ms:
            continue
        timestamp_ms = _clamp_timestamp(
            previous["end_ms"] + gap_ms // 2,
            duration_ms,
        )
        if timestamp_ms is None:
            continue
        strength = min(1.0, gap_ms / 3_000)
        candidates.append(
            _raw_candidate(
                timestamp_ms,
                "pause",
                0.55 + 0.35 * strength,
                {
                    "pause_start_ms": previous["end_ms"],
                    "pause_end_ms": current["start_ms"],
                    "pause_duration_ms": gap_ms,
                    "previous_word_id": previous["word_id"],
                    "next_word_id": current["word_id"],
                },
            )
        )
        pause_count += 1

    return candidates, {
        "segment_count": len(segments),
        "word_count": len(words),
        "sentence_boundary_count": sentence_count,
        "pause_count": pause_count,
    }


def _scene_cut_candidates(
    video_path: Path,
    duration_ms: int,
    config: BoundaryConfig,
) -> list[dict[str, Any]]:
    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=config.scene_cut_threshold))
    scene_manager.detect_scenes(video, show_progress=False)
    scene_list = scene_manager.get_scene_list(start_in_scene=True)

    candidates = []
    for scene_index, (start_time, _end_time) in enumerate(scene_list[1:], start=1):
        timestamp_ms = _clamp_timestamp(
            _seconds_to_ms(start_time.get_seconds()), duration_ms
        )
        if timestamp_ms is not None:
            candidates.append(
                _raw_candidate(
                    timestamp_ms,
                    "scene_cut",
                    0.86,
                    {
                        "scene_index": scene_index,
                        "source_frame": start_time.get_frames(),
                    },
                )
            )
    return candidates


def _read_exact(stream: Any, byte_count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = byte_count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _visual_candidates_ffmpeg(
    ffmpeg: Path,
    video_path: Path,
    duration_ms: int,
    config: BoundaryConfig,
) -> list[dict[str, Any]]:
    fps_expression = f"1000/{config.visual_sample_interval_ms}"
    frame_size = config.visual_width * config.visual_height
    command = [
        str(ffmpeg),
        "-v",
        "error",
        "-i",
        str(video_path),
        "-an",
        "-vf",
        (
            f"fps={fps_expression},"
            f"scale={config.visual_width}:{config.visual_height},format=gray"
        ),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise BoundaryExtractionError("Could not open FFmpeg output pipes.")

    candidates: list[dict[str, Any]] = []
    previous_frame: np.ndarray | None = None
    frame_index = 0
    try:
        while True:
            raw_frame = _read_exact(process.stdout, frame_size)
            if not raw_frame:
                break
            if len(raw_frame) != frame_size:
                raise BoundaryExtractionError("FFmpeg returned a partial sampled frame.")
            frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape(
                config.visual_height, config.visual_width
            )
            timestamp_ms = frame_index * config.visual_sample_interval_ms
            if previous_frame is not None and 0 < timestamp_ms < duration_ms:
                difference = float(
                    np.mean(cv2.absdiff(previous_frame, frame), dtype=np.float64) / 255.0
                )
                if difference >= config.visual_difference_threshold:
                    excess = (
                        difference - config.visual_difference_threshold
                    ) / max(1e-9, 1.0 - config.visual_difference_threshold)
                    candidates.append(
                        _raw_candidate(
                            timestamp_ms,
                            "visual_difference",
                            0.50 + 0.40 * min(1.0, excess),
                            {
                                "normalized_mean_absolute_difference": round(
                                    difference, 6
                                ),
                                "sampling_backend": "ffmpeg",
                            },
                        )
                    )
            previous_frame = frame.copy()
            frame_index += 1
    except Exception:
        process.kill()
        process.wait(timeout=10)
        raise
    finally:
        process.stdout.close()

    stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
    return_code = process.wait(timeout=30)
    process.stderr.close()
    if return_code != 0:
        raise BoundaryExtractionError(
            f"FFmpeg visual sampling failed with code {return_code}: {stderr}"
        )
    return candidates


def _visual_candidates_opencv(
    video_path: Path,
    duration_ms: int,
    config: BoundaryConfig,
) -> list[dict[str, Any]]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise BoundaryExtractionError(f"Could not open video: {video_path}")

    candidates: list[dict[str, Any]] = []
    previous_frame: np.ndarray | None = None
    try:
        for timestamp_ms in range(0, duration_ms, config.visual_sample_interval_ms):
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
            ok, frame = capture.read()
            if not ok:
                continue
            gray = cv2.cvtColor(
                cv2.resize(frame, (config.visual_width, config.visual_height)),
                cv2.COLOR_BGR2GRAY,
            )
            if previous_frame is not None and timestamp_ms > 0:
                difference = float(
                    np.mean(cv2.absdiff(previous_frame, gray), dtype=np.float64) / 255.0
                )
                if difference >= config.visual_difference_threshold:
                    excess = (
                        difference - config.visual_difference_threshold
                    ) / max(1e-9, 1.0 - config.visual_difference_threshold)
                    candidates.append(
                        _raw_candidate(
                            timestamp_ms,
                            "visual_difference",
                            0.50 + 0.40 * min(1.0, excess),
                            {
                                "normalized_mean_absolute_difference": round(
                                    difference, 6
                                ),
                                "sampling_backend": "opencv",
                            },
                        )
                    )
            previous_frame = gray
    finally:
        capture.release()
    return candidates


def _visual_candidates(
    video_path: Path,
    duration_ms: int,
    config: BoundaryConfig,
) -> tuple[list[dict[str, Any]], str]:
    try:
        ffmpeg = resolve_media_tool("ffmpeg")
    except MediaToolError as exc:
        raise BoundaryExtractionError(str(exc)) from exc
    if ffmpeg:
        return (
            _visual_candidates_ffmpeg(ffmpeg, video_path, duration_ms, config),
            "ffmpeg",
        )
    return _visual_candidates_opencv(video_path, duration_ms, config), "opencv"


def _combine_probability(scores: Iterable[float]) -> float:
    remaining_probability = 1.0
    for score in scores:
        remaining_probability *= 1.0 - max(0.0, min(1.0, score))
    return round(1.0 - remaining_probability, 4)


def _merge_candidates(
    raw_candidates: list[dict[str, Any]],
    merge_tolerance_ms: int,
) -> list[dict[str, Any]]:
    ordered = sorted(
        raw_candidates,
        key=lambda item: (item["timestamp_ms"], SIGNAL_ORDER.index(item["signal"])),
    )
    clusters: list[list[dict[str, Any]]] = []
    for candidate in ordered:
        if not clusters or (
            candidate["timestamp_ms"] - clusters[-1][0]["timestamp_ms"]
            > merge_tolerance_ms
        ):
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)

    merged: list[dict[str, Any]] = []
    for boundary_index, cluster in enumerate(clusters, start=1):
        strongest = max(
            cluster,
            key=lambda item: (item["score"], -item["timestamp_ms"]),
        )
        signal_scores: dict[str, float] = {}
        evidence: dict[str, list[dict[str, Any]]] = {}
        for item in cluster:
            signal = item["signal"]
            signal_scores[signal] = max(signal_scores.get(signal, 0.0), item["score"])
            evidence.setdefault(signal, []).append(
                {"timestamp_ms": item["timestamp_ms"], **item["details"]}
            )
        signals = [signal for signal in SIGNAL_ORDER if signal in signal_scores]
        merged.append(
            {
                "boundary_id": f"boundary_{boundary_index:06d}",
                "timestamp_ms": strongest["timestamp_ms"],
                "signals": signals,
                "score": _combine_probability(signal_scores.values()),
                "signal_scores": signal_scores,
                "evidence": evidence,
            }
        )
    return merged


def extract_boundary_signals(
    *,
    repo_root: Path,
    video_id: str,
    config: BoundaryConfig | None = None,
) -> dict[str, Any]:
    """Run Phase C3 and persist video-scoped boundary candidates."""
    config = config or BoundaryConfig()
    config.validate()
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)

    duration_ms = manifest["duration_ms"]
    video_path = Path(manifest["video_path"])
    transcript_path = Path(manifest["artifacts"]["transcript_path"])
    output_path = Path(manifest["artifacts"]["boundaries_path"])
    if duration_ms <= 0:
        raise BoundaryExtractionError("Boundary extraction requires a positive duration.")
    if not video_path.is_file():
        raise BoundaryExtractionError(f"Source video does not exist: {video_path}")

    warnings: list[str] = []
    raw_candidates = _duration_candidates(duration_ms, config)
    availability: dict[str, Any] = {
        "duration": {"available": True},
        "transcript": {"available": False, "path": str(transcript_path)},
        "scene_cut": {"available": False},
        "visual_difference": {"available": False, "backend": None},
    }
    for planned_signal in PLANNED_SIGNAL_ORDER:
        availability[planned_signal] = {
            "available": False,
            "status": "planned",
            "reason": "Not enabled in the C3 base implementation.",
        }
    transcript_stats = {
        "segment_count": 0,
        "word_count": 0,
        "sentence_boundary_count": 0,
        "pause_count": 0,
    }

    if config.enable_transcript:
        if transcript_path.is_file():
            transcript_candidates, transcript_stats = _transcript_candidates(
                transcript_path, duration_ms, config
            )
            raw_candidates.extend(transcript_candidates)
            availability["transcript"]["available"] = True
        else:
            warnings.append(
                "Transcript artifact is absent; sentence and pause signals were skipped."
            )

    if config.enable_scene_cut:
        try:
            scene_candidates = _scene_cut_candidates(video_path, duration_ms, config)
            raw_candidates.extend(scene_candidates)
            availability["scene_cut"] = {
                "available": True,
                "candidate_count": len(scene_candidates),
            }
        except Exception as exc:
            warnings.append(f"Scene-cut extraction failed: {exc}")

    if config.enable_visual_difference:
        try:
            visual_candidates, backend = _visual_candidates(
                video_path, duration_ms, config
            )
            raw_candidates.extend(visual_candidates)
            availability["visual_difference"] = {
                "available": True,
                "backend": backend,
                "candidate_count": len(visual_candidates),
            }
        except Exception as exc:
            warnings.append(f"Visual-difference extraction failed: {exc}")

    candidates = _merge_candidates(raw_candidates, config.merge_tolerance_ms)
    signal_counts = {
        signal: sum(signal in candidate["signals"] for candidate in candidates)
        for signal in SIGNAL_ORDER
    }
    multimodal_candidate_count = sum(
        len(candidate["signals"]) > 1 for candidate in candidates
    )
    high_confidence_candidate_count = sum(
        candidate["score"] >= 0.80 for candidate in candidates
    )
    payload = {
        "schema_version": BOUNDARY_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": duration_ms,
        "timeline_contract": {
            "unit": "milliseconds",
            "valid_range": {
                "exclusive_start_ms": 0,
                "exclusive_end_ms": duration_ms,
            },
            "floating_seconds_allowed": False,
            "timestamp_policy": "integer_ms_only",
        },
        "implemented_signals": list(SIGNAL_ORDER),
        "planned_signals": list(PLANNED_SIGNAL_ORDER),
        "config": asdict(config),
        "signal_availability": availability,
        "transcript_stats": transcript_stats,
        "warnings": warnings,
        "quality_metrics": {
            "raw_candidate_count": len(raw_candidates),
            "merged_candidate_count": len(candidates),
            "merge_tolerance_ms": config.merge_tolerance_ms,
            "multimodal_candidate_count": multimodal_candidate_count,
            "high_confidence_candidate_count": high_confidence_candidate_count,
            "signal_coverage_ratio": round(
                sum(count > 0 for count in signal_counts.values()) / len(SIGNAL_ORDER),
                4,
            ),
        },
        "candidate_count": len(candidates),
        "signal_counts": signal_counts,
        "candidates": candidates,
        "created_at": utc_now(),
    }
    write_json_atomic(output_path, payload)
    return payload
