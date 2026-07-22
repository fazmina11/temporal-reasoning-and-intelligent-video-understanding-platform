from __future__ import annotations

import os
import subprocess
import wave
from pathlib import Path
from typing import Any

from .media_manifest import (
    calculate_sha256,
    load_manifest,
    save_manifest,
    utc_now,
)
from .media_tools import MediaToolError, resolve_media_tool


class MediaAssetError(RuntimeError):
    """Raised when a normalized media artifact cannot be created safely."""


def extract_normalized_audio(
    *,
    repo_root: Path,
    video_id: str,
    sample_rate: int = 16_000,
    channels: int = 1,
) -> dict[str, Any]:
    """Extract one PCM WAV optimized for ASR and record it in the manifest."""
    if sample_rate <= 0 or channels <= 0:
        raise MediaAssetError("Audio sample rate and channel count must be positive.")

    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    audio_path = Path(manifest["artifacts"]["audio_path"])
    result: dict[str, Any]

    if manifest.get("has_audio") is False:
        result = {
            "status": "skipped",
            "reason": "source_has_no_audio_stream",
            "audio_path": str(audio_path),
            "created_at": utc_now(),
        }
    else:
        try:
            ffmpeg = resolve_media_tool("ffmpeg")
        except MediaToolError as exc:
            raise MediaAssetError(str(exc)) from exc
        if ffmpeg is None:
            raise MediaAssetError(
                "FFmpeg is required for normalized audio extraction."
            )

        audio_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = audio_path.with_suffix(".tmp.wav")
        command = [
            str(ffmpeg),
            "-v",
            "error",
            "-y",
            "-i",
            manifest["video_path"],
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(temporary_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=7_200,
                check=False,
            )
            if completed.returncode != 0:
                raise MediaAssetError(
                    "FFmpeg audio extraction failed: "
                    + completed.stderr.strip()
                )

            with wave.open(str(temporary_path), "rb") as wav_file:
                actual_channels = wav_file.getnchannels()
                actual_sample_rate = wav_file.getframerate()
                sample_width_bytes = wav_file.getsampwidth()
                sample_count = wav_file.getnframes()
            audio_duration_ms = int(
                sample_count * 1000 / actual_sample_rate + 0.5
            )
            if actual_channels != channels or actual_sample_rate != sample_rate:
                raise MediaAssetError(
                    "Normalized WAV properties do not match the requested settings."
                )
            if abs(audio_duration_ms - manifest["duration_ms"]) > 2_000:
                raise MediaAssetError(
                    "Normalized audio duration differs from the video by more than 2 seconds."
                )

            os.replace(temporary_path, audio_path)
        finally:
            temporary_path.unlink(missing_ok=True)

        result = {
            "status": "completed",
            "audio_path": str(audio_path),
            "audio_path_relative": str(audio_path.relative_to(repo_root)),
            "codec": "pcm_s16le",
            "container": "wav",
            "sample_rate": actual_sample_rate,
            "channels": actual_channels,
            "sample_width_bytes": sample_width_bytes,
            "sample_count": sample_count,
            "duration_ms": audio_duration_ms,
            "file_size_bytes": audio_path.stat().st_size,
            "sha256": calculate_sha256(audio_path),
            "created_at": utc_now(),
        }

    manifest.setdefault("artifact_metadata", {})["normalized_audio"] = result
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return result
