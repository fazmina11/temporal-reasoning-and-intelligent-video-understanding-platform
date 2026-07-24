from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .audio_event_detection import build_audio_event_artifacts
from .ocr_extraction import extract_ocr_artifacts
from .speaker_diarization import build_speaker_artifacts
from .modality_quality import write_quality_report


def run_modality_foundation(
    *,
    repo_root: Path,
    video_id: str,
    skip_ocr: bool = False,
    expected_speakers: int | None = None,
    allow_partial: bool = True,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, fn in [
        (
            "speakers",
            lambda: build_speaker_artifacts(
                repo_root=repo_root, video_id=video_id, expected_speakers=expected_speakers
            ),
        ),
        ("audio_events", lambda: build_audio_event_artifacts(repo_root=repo_root, video_id=video_id)),
    ]:
        try:
            results[name] = fn()
        except Exception as exc:
            if not allow_partial:
                raise
            errors[name] = str(exc)
            _write_failure_report(repo_root=repo_root, video_id=video_id, modality=_report_modality(name), error=str(exc))
    if not skip_ocr:
        try:
            results["ocr"] = extract_ocr_artifacts(repo_root=repo_root, video_id=video_id)
        except Exception as exc:
            if not allow_partial:
                raise
            errors["ocr"] = str(exc)
            _write_failure_report(repo_root=repo_root, video_id=video_id, modality="ocr", error=str(exc))
    results["errors"] = errors
    results["status"] = "partial" if errors else "completed"
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Build OCR, speaker, and audio-event evidence artifacts.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--expected-speakers", type=int)
    args = parser.parse_args()
    result = run_modality_foundation(
        repo_root=Path(args.repo_root),
        video_id=args.video_id,
        skip_ocr=args.skip_ocr,
        expected_speakers=args.expected_speakers,
    )
    print(
        "Modality artifacts complete: "
        f"{result.get('speakers', {}).get('speaker_count', 0)} speakers, "
        f"{result.get('audio_events', {}).get('event_count', 0)} audio events, "
        f"{result.get('ocr', {}).get('record_count', 0)} OCR records."
    )


def _write_failure_report(*, repo_root: Path, video_id: str, modality: str, error: str) -> None:
    write_quality_report(
        repo_root=repo_root,
        video_id=video_id,
        modality=modality,
        payload={
            "status": "failed",
            "error": error,
            "record_quality": {
                "count": 0,
                "mean_quality": 0.0,
                "low_quality_count": 0,
                "low_quality_ratio": 0.0,
            },
        },
    )


def _report_modality(name: str) -> str:
    return {"speakers": "speaker", "audio_events": "audio"}.get(name, name)


if __name__ == "__main__":
    main()
