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

SPEAKER_SCHEMA_VERSION = "speaker-artifacts-v2"
SPEAKER_MIN_TURN_QUALITY = 0.55
SPEAKER_MERGE_GAP_MS = 700
SPEAKER_MIN_TURN_MS = 500


class SpeakerDiarizationError(RuntimeError):
    pass


def build_speaker_artifacts(
    *, repo_root: Path, video_id: str, expected_speakers: int | None = None, max_speakers: int = 4
) -> dict[str, Any]:
    try:
        from scipy.io import wavfile
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise SpeakerDiarizationError("Speaker diarization requires scipy and scikit-learn.") from exc

    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    audio_path = Path(manifest["artifacts"]["audio_path"])
    transcript_path = Path(manifest["artifacts"]["transcript_path"])
    if not audio_path.is_file():
        raise SpeakerDiarizationError(f"Audio artifact does not exist: {audio_path}")
    if not transcript_path.is_file():
        raise SpeakerDiarizationError(f"Transcript artifact does not exist: {transcript_path}")

    sample_rate, raw_audio = wavfile.read(audio_path, mmap=True)
    audio = _mono_float(raw_audio)
    segments = []
    for index, row in enumerate(load_transcript_segments(transcript_path), start=1):
        normalized = normalized_segment(row, index)
        if normalized:
            segments.append(normalized)
    if not segments:
        raise SpeakerDiarizationError("Transcript has no valid timestamped segments.")

    features = np.vstack(
        [_voice_feature(audio, int(sample_rate), row["start_ms"], row["end_ms"]) for row in segments]
    )
    scaled = StandardScaler().fit_transform(features)
    speaker_count, labels, clustering_score = _choose_labels(
        scaled,
        expected_speakers=expected_speakers,
        max_speakers=max_speakers,
        clustering_cls=AgglomerativeClustering,
        silhouette_fn=silhouette_score,
    )
    stable_labels = _stable_speaker_labels(labels, segments)
    maps = hierarchy_maps(manifest)
    labeled_segments = []
    for row, speaker_id in zip(segments, stable_labels):
        midpoint = (row["start_ms"] + row["end_ms"]) // 2
        parents = timeline_parent_ids(row["start_ms"], row["end_ms"], maps)
        segment_quality = _segment_quality(row, clustering_score)
        labeled_segments.append(
            {
                "segment_id": row["segment_id"],
                "speaker_id": speaker_id,
                "start_ms": row["start_ms"],
                "end_ms": row["end_ms"],
                "text": row["text"],
                "duration_ms": row["end_ms"] - row["start_ms"],
                "quality_score": segment_quality,
                "quality_flags": _speaker_quality_flags(row["end_ms"] - row["start_ms"], segment_quality),
                **timeline_parents(midpoint, maps),
                **parents,
            }
        )
    turns = _merge_turns(labeled_segments)
    speakers = []
    for speaker_id in sorted(set(stable_labels)):
        own = [row for row in labeled_segments if row["speaker_id"] == speaker_id]
        speakers.append(
            {
                "speaker_id": speaker_id,
                "label": speaker_id.replace("_", " ").title(),
                "total_speech_ms": sum(row["end_ms"] - row["start_ms"] for row in own),
                "segment_count": len(own),
                "turn_count": sum(turn["speaker_id"] == speaker_id for turn in turns),
                "mean_quality": round(sum(row["quality_score"] for row in own) / max(1, len(own)), 4),
            }
        )

    quality_report_path = write_quality_report(
        repo_root=repo_root,
        video_id=video_id,
        modality="speaker",
        payload={
            "backend": "acoustic_spectral_clustering",
            "speaker_count": speaker_count,
            "clustering_confidence": round(clustering_score, 4),
            "segment_quality": quality_summary([row["quality_score"] for row in labeled_segments], minimum=SPEAKER_MIN_TURN_QUALITY),
            "turn_quality": quality_summary([row["quality_score"] for row in turns], minimum=SPEAKER_MIN_TURN_QUALITY),
            "turn_count": len(turns),
            "merge_gap_ms": SPEAKER_MERGE_GAP_MS,
        },
    )
    payload = {
        "schema_version": SPEAKER_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "backend": "acoustic_spectral_clustering",
        "config": {
            "merge_gap_ms": SPEAKER_MERGE_GAP_MS,
            "minimum_turn_ms": SPEAKER_MIN_TURN_MS,
            "minimum_turn_quality": SPEAKER_MIN_TURN_QUALITY,
        },
        "speaker_count": speaker_count,
        "clustering_confidence": round(clustering_score, 4),
        "speakers": speakers,
        "turn_count": len(turns),
        "turns": turns,
        "segments": labeled_segments,
        "quality_report_path": str(quality_report_path),
        "created_at": utc_now(),
    }
    output_path = Path(manifest["artifacts"]["speakers_path"])
    write_json_atomic(output_path, payload)
    _attach_speakers_to_atoms(manifest, labeled_segments)
    manifest.setdefault("artifact_metadata", {})["speakers"] = {
        "schema_version": SPEAKER_SCHEMA_VERSION,
        "speaker_count": speaker_count,
        "turn_count": len(turns),
        "backend": payload["backend"],
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
    peak = float(np.max(np.abs(data))) if data.size else 1.0
    return data / max(1.0, peak)


def _voice_feature(audio: np.ndarray, sample_rate: int, start_ms: int, end_ms: int) -> np.ndarray:
    start = max(0, round(start_ms * sample_rate / 1000))
    end = min(len(audio), round(end_ms * sample_rate / 1000))
    signal = np.asarray(audio[start:end], dtype=np.float32)
    target = max(512, min(len(signal), sample_rate * 6))
    if signal.size == 0:
        return np.zeros(34, dtype=np.float32)
    if signal.size > target:
        offset = (signal.size - target) // 2
        signal = signal[offset : offset + target]
    signal = signal - float(signal.mean())
    frame_size = max(256, round(sample_rate * 0.032))
    hop = max(128, frame_size // 2)
    frames = []
    for pos in range(0, max(1, len(signal) - frame_size + 1), hop):
        frame = signal[pos : pos + frame_size]
        if len(frame) < frame_size:
            frame = np.pad(frame, (0, frame_size - len(frame)))
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(frame_size))) ** 2
        bands = np.array_split(spectrum[1:], 16)
        frames.append(np.log1p([float(np.mean(band)) for band in bands]))
    matrix = np.asarray(frames, dtype=np.float32)
    rms = np.sqrt(float(np.mean(signal**2)) + 1e-9)
    zcr = float(np.mean(np.abs(np.diff(np.signbit(signal))))) if len(signal) > 1 else 0.0
    return np.concatenate([matrix.mean(axis=0), matrix.std(axis=0), [np.log1p(rms), zcr]])


def _choose_labels(features, *, expected_speakers, max_speakers, clustering_cls, silhouette_fn):
    count = len(features)
    if count < 4 or expected_speakers == 1:
        return 1, np.zeros(count, dtype=int), 1.0
    upper = min(max_speakers, count - 1)
    if expected_speakers:
        options = [max(1, min(int(expected_speakers), upper))]
    else:
        options = list(range(2, upper + 1))
    best = (0.0, np.zeros(count, dtype=int), 1)
    for speaker_count in options:
        if speaker_count == 1:
            return 1, np.zeros(count, dtype=int), 1.0
        labels = clustering_cls(n_clusters=speaker_count, linkage="ward").fit_predict(features)
        score = float(silhouette_fn(features, labels))
        if score > best[0]:
            best = (score, labels, speaker_count)
    if expected_speakers is None and best[0] < 0.28:
        return 1, np.zeros(count, dtype=int), round(max(0.0, 1.0 - best[0]), 4)
    return best[2], best[1], best[0]


def _stable_speaker_labels(labels: np.ndarray, segments: list[dict[str, Any]]) -> list[str]:
    first_seen = {}
    for label, segment in zip(labels.tolist(), segments):
        first_seen.setdefault(int(label), segment["start_ms"])
    mapping = {
        label: f"speaker_{index:02d}"
        for index, (label, _start) in enumerate(sorted(first_seen.items(), key=lambda item: item[1]))
    }
    return [mapping[int(label)] for label in labels.tolist()]


def _merge_turns(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns = []
    for segment in segments:
        segment_quality = float(segment.get("quality_score", 0.7))
        can_merge = (
            turns
            and turns[-1]["speaker_id"] == segment["speaker_id"]
            and segment["start_ms"] - turns[-1]["end_ms"] <= SPEAKER_MERGE_GAP_MS
            and segment["end_ms"] - turns[-1]["start_ms"] <= 30_000
            and turns[-1].get("parent_chunk_id") == segment.get("parent_chunk_id")
        )
        if can_merge:
            turns[-1]["end_ms"] = segment["end_ms"]
            turns[-1]["segment_ids"].append(segment["segment_id"])
            turns[-1]["parent_atom_ids"] = sorted(set(turns[-1].get("parent_atom_ids", [])) | set(segment.get("parent_atom_ids", [])))
            turns[-1]["quality_score"] = round(
                sum(segment_quality for segment_quality in [
                    *turns[-1].get("_segment_quality_values", []),
                    segment_quality,
                ])
                / (len(turns[-1].get("_segment_quality_values", [])) + 1),
                4,
            )
            turns[-1].setdefault("_segment_quality_values", []).append(segment_quality)
            turns[-1]["quality_flags"] = _speaker_quality_flags(turns[-1]["end_ms"] - turns[-1]["start_ms"], turns[-1]["quality_score"])
            turns[-1]["text"] = " ".join([turns[-1]["text"], segment["text"]]).strip()
            continue
        turns.append(
            {
                "turn_id": f"turn_{len(turns) + 1:06d}",
                "speaker_id": segment["speaker_id"],
                "start_ms": segment["start_ms"],
                "end_ms": segment["end_ms"],
                "duration_ms": segment["end_ms"] - segment["start_ms"],
                "segment_ids": [segment["segment_id"]],
                "text": segment["text"],
                "atom_id": segment.get("atom_id"),
                "parent_atom_ids": segment.get("parent_atom_ids", []),
                "parent_chunk_id": segment.get("parent_chunk_id"),
                "parent_event_id": segment.get("parent_event_id"),
                "quality_score": segment_quality,
                "quality_flags": _speaker_quality_flags(segment["end_ms"] - segment["start_ms"], segment_quality),
                "_segment_quality_values": [segment_quality],
            }
        )
    for turn in turns:
        turn["duration_ms"] = turn["end_ms"] - turn["start_ms"]
        turn.pop("_segment_quality_values", None)
    return turns


def _attach_speakers_to_atoms(manifest: dict[str, Any], segments: list[dict[str, Any]]) -> None:
    from .json_artifacts import read_json

    path = Path(manifest["artifacts"]["atoms_path"])
    payload = read_json(path)
    for atom in payload.get("atoms", []):
        atom["speaker_ids"] = sorted(
            {
                segment["speaker_id"]
                for segment in segments
                if overlap_ms(atom["start_ms"], atom["end_ms"], segment["start_ms"], segment["end_ms"]) > 0
            }
        )
    payload["speaker_attachment"] = {
        "schema_version": SPEAKER_SCHEMA_VERSION,
        "speakers_path": manifest["artifacts"]["speakers_path"],
        "completed_at": utc_now(),
    }
    payload["updated_at"] = utc_now()
    write_json_atomic(path, payload)


def _segment_quality(segment: dict[str, Any], clustering_score: float) -> float:
    duration_ms = segment["end_ms"] - segment["start_ms"]
    duration_score = min(1.0, duration_ms / 3000)
    text_score = min(1.0, len(segment.get("text", "").split()) / 10)
    cluster_score = max(0.0, min(1.0, float(clustering_score)))
    return round((0.45 * cluster_score) + (0.30 * duration_score) + (0.25 * text_score), 4)


def _speaker_quality_flags(duration_ms: int, quality_score: float) -> list[str]:
    flags = []
    if duration_ms < SPEAKER_MIN_TURN_MS:
        flags.append("short_turn")
    if quality_score < SPEAKER_MIN_TURN_QUALITY:
        flags.append("low_confidence")
    if duration_ms > 30_000:
        flags.append("long_merged_turn")
    return flags
