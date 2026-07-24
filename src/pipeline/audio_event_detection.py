from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .json_artifacts import write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now
from .modality_common import (
    hierarchy_maps,
    load_transcript_segments,
    normalized_segment,
    overlap_ms,
    timeline_parent_ids,
    timeline_parents,
)
from .modality_quality import quality_summary, write_quality_report

AUDIO_EVENT_SCHEMA_VERSION = "audio-events-v2"
AUDIO_MIN_EVENT_QUALITY = 0.58
AUDIO_MERGE_GAP_MS = 500


class AudioEventDetectionError(RuntimeError):
    pass


def build_audio_event_artifacts(
    *, repo_root: Path, video_id: str, window_ms: int = 2000, hop_ms: int = 1000
) -> dict[str, Any]:
    try:
        from scipy.io import wavfile
    except ImportError as exc:
        raise AudioEventDetectionError("Audio event extraction requires scipy.") from exc

    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    audio_path = Path(manifest["artifacts"]["audio_path"])
    if not audio_path.is_file():
        raise AudioEventDetectionError(f"Audio artifact does not exist: {audio_path}")
    sample_rate, raw = wavfile.read(audio_path, mmap=True)
    audio = _mono_float(raw)
    duration_ms = min(int(manifest["duration_ms"]), round(len(audio) * 1000 / sample_rate))
    transcript_path = Path(manifest["artifacts"]["transcript_path"])
    speech_segments = []
    if transcript_path.is_file():
        for index, row in enumerate(load_transcript_segments(transcript_path), start=1):
            normalized = normalized_segment(row, index)
            if normalized:
                speech_segments.append(normalized)

    windows = []
    previous_spectrum = None
    for start_ms in range(0, duration_ms, hop_ms):
        analysis_end_ms = min(duration_ms, start_ms + window_ms)
        end_ms = min(duration_ms, start_ms + hop_ms)
        start = round(start_ms * sample_rate / 1000)
        end = round(analysis_end_ms * sample_rate / 1000)
        signal = np.asarray(audio[start:end], dtype=np.float32)
        features, spectrum = _features(signal, int(sample_rate), previous_spectrum)
        previous_spectrum = spectrum
        speech_overlap = sum(
            overlap_ms(start_ms, analysis_end_ms, row["start_ms"], row["end_ms"])
            for row in speech_segments
        ) / max(1, analysis_end_ms - start_ms)
        windows.append({"start_ms": start_ms, "end_ms": end_ms, "speech_overlap": min(1.0, speech_overlap), **features})

    if not windows:
        raise AudioEventDetectionError("Audio artifact contains no samples.")
    db_values = np.asarray([row["rms_dbfs"] for row in windows])
    silence_threshold = float(min(-42.0, np.percentile(db_values, 20) + 3.0))
    flux_threshold = float(np.percentile([row["spectral_flux"] for row in windows], 92))
    for row in windows:
        row["label"], row["confidence"] = _classify(row, silence_threshold, flux_threshold)

    maps = hierarchy_maps(manifest)
    events = _merge_windows(windows, maps)
    quality_report_path = write_quality_report(
        repo_root=repo_root,
        video_id=video_id,
        modality="audio",
        payload={
            "backend": "deterministic_acoustic_features_v1",
            "event_quality": quality_summary([row["quality_score"] for row in events], minimum=AUDIO_MIN_EVENT_QUALITY),
            "event_count": len(events),
            "label_counts": {label: sum(event["label"] == label for event in events) for label in sorted({e["label"] for e in events})},
            "transition_count": sum(1 for event in events if event.get("is_transition")),
            "merge_gap_ms": AUDIO_MERGE_GAP_MS,
        },
    )
    payload = {
        "schema_version": AUDIO_EVENT_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "backend": "deterministic_acoustic_features_v1",
        "config": {
            "window_ms": window_ms,
            "hop_ms": hop_ms,
            "merge_gap_ms": AUDIO_MERGE_GAP_MS,
            "minimum_event_quality": AUDIO_MIN_EVENT_QUALITY,
            "silence_threshold_dbfs": round(silence_threshold, 3),
        },
        "event_count": len(events),
        "label_counts": {label: sum(event["label"] == label for event in events) for label in sorted({e["label"] for e in events})},
        "events": events,
        "quality_report_path": str(quality_report_path),
        "created_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["audio_events_path"]), payload)
    manifest.setdefault("artifact_metadata", {})["audio_events"] = {
        "schema_version": AUDIO_EVENT_SCHEMA_VERSION,
        "event_count": len(events),
        "label_counts": payload["label_counts"],
        "quality_report_path": str(quality_report_path),
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return payload


def _mono_float(audio: np.ndarray) -> np.ndarray:
    data = np.asarray(audio)
    if data.ndim > 1:
        data = data.astype(np.float32).mean(axis=1)
    else:
        data = data.astype(np.float32)
    if np.issubdtype(np.asarray(audio).dtype, np.integer):
        data /= max(1.0, float(np.iinfo(np.asarray(audio).dtype).max))
    return data


def _features(signal: np.ndarray, sample_rate: int, previous_spectrum: np.ndarray | None):
    if signal.size == 0:
        return {"rms_dbfs": -100.0, "zero_crossing_rate": 0.0, "spectral_centroid_hz": 0.0, "spectral_flatness": 0.0, "spectral_flux": 0.0}, np.zeros(257)
    rms = float(np.sqrt(np.mean(signal**2) + 1e-12))
    zcr = float(np.mean(np.abs(np.diff(np.signbit(signal))))) if len(signal) > 1 else 0.0
    fft_size = min(4096, max(512, 2 ** int(np.floor(np.log2(len(signal))))))
    spectrum = np.abs(np.fft.rfft(signal[:fft_size] * np.hanning(fft_size))) + 1e-10
    normalized = spectrum / spectrum.sum()
    frequencies = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    centroid = float(np.sum(frequencies * normalized))
    flatness = float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))
    flux = 0.0
    if previous_spectrum is not None:
        width = min(len(spectrum), len(previous_spectrum))
        current = spectrum[:width] / max(1e-9, float(np.linalg.norm(spectrum[:width])))
        previous = previous_spectrum[:width] / max(1e-9, float(np.linalg.norm(previous_spectrum[:width])))
        flux = float(np.linalg.norm(np.maximum(0.0, current - previous)))
    return {
        "rms_dbfs": round(20.0 * np.log10(max(rms, 1e-5)), 4),
        "zero_crossing_rate": round(zcr, 6),
        "spectral_centroid_hz": round(centroid, 3),
        "spectral_flatness": round(flatness, 6),
        "spectral_flux": round(flux, 6),
    }, spectrum


def _classify(row: dict[str, Any], silence_threshold: float, flux_threshold: float) -> tuple[str, float]:
    if row["rms_dbfs"] <= silence_threshold:
        return "silence", min(0.99, 0.65 + (silence_threshold - row["rms_dbfs"]) / 40.0)
    if row["speech_overlap"] >= 0.30:
        return "speech", min(0.99, 0.65 + 0.34 * row["speech_overlap"])
    if row["spectral_flux"] >= flux_threshold and row["rms_dbfs"] > silence_threshold + 8:
        return "transient_sound", 0.72
    if row["spectral_flatness"] < 0.12 and row["zero_crossing_rate"] < 0.18:
        return "music_or_tonal_audio", 0.62
    return "background_audio", 0.55


def _merge_windows(windows: list[dict[str, Any]], maps: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for row in windows:
        if (
            groups
            and groups[-1][-1]["label"] == row["label"]
            and row["start_ms"] - groups[-1][-1]["end_ms"] <= AUDIO_MERGE_GAP_MS
        ):
            groups[-1].append(row)
        else:
            groups.append([row])
    events = []
    for group_index, group in enumerate(groups):
        start_ms, end_ms = group[0]["start_ms"], group[-1]["end_ms"]
        midpoint = (start_ms + end_ms) // 2
        parents = timeline_parent_ids(start_ms, end_ms, maps)
        previous_label = groups[group_index - 1][0]["label"] if group_index > 0 else None
        next_label = groups[group_index + 1][0]["label"] if group_index + 1 < len(groups) else None
        confidence = round(float(np.mean([row["confidence"] for row in group])), 4)
        quality_score = _audio_quality(group, confidence)
        events.append(
            {
                "audio_event_id": f"audio_event_{len(events) + 1:06d}",
                "label": group[0]["label"],
                "event_type": group[0]["label"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": end_ms - start_ms,
                "confidence": round(float(np.mean([row["confidence"] for row in group])), 4),
                "quality_score": quality_score,
                "quality_flags": _audio_quality_flags(group[0]["label"], quality_score, end_ms - start_ms),
                "is_transition": bool(previous_label and previous_label != group[0]["label"]),
                "previous_label": previous_label,
                "next_label": next_label,
                "features": {
                    key: round(float(np.mean([row[key] for row in group])), 5)
                    for key in ["rms_dbfs", "zero_crossing_rate", "spectral_centroid_hz", "spectral_flatness", "spectral_flux", "speech_overlap"]
                },
                **timeline_parents(midpoint, maps),
                **parents,
            }
        )
    return events


def _audio_quality(group: list[dict[str, Any]], confidence: float) -> float:
    duration_ms = group[-1]["end_ms"] - group[0]["start_ms"]
    duration_score = min(1.0, duration_ms / 2500)
    stability_score = 1.0 if len({row["label"] for row in group}) == 1 else 0.6
    return round(min(1.0, (0.60 * confidence) + (0.25 * duration_score) + (0.15 * stability_score)), 4)


def _audio_quality_flags(label: str, quality_score: float, duration_ms: int) -> list[str]:
    flags = []
    if quality_score < AUDIO_MIN_EVENT_QUALITY:
        flags.append("low_confidence")
    if duration_ms < 300:
        flags.append("very_short_event")
    if label == "background_audio":
        flags.append("broad_background_label")
    return flags
