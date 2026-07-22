from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .audio_event_detection import build_audio_event_artifacts
from .ocr_extraction import extract_ocr_artifacts
from .speaker_diarization import build_speaker_artifacts


def run_modality_foundation(
    *, repo_root: Path, video_id: str, skip_ocr: bool = False, expected_speakers: int | None = None
) -> dict[str, Any]:
    results = {
        "speakers": build_speaker_artifacts(
            repo_root=repo_root, video_id=video_id, expected_speakers=expected_speakers
        ),
        "audio_events": build_audio_event_artifacts(repo_root=repo_root, video_id=video_id),
    }
    if not skip_ocr:
        results["ocr"] = extract_ocr_artifacts(repo_root=repo_root, video_id=video_id)
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
        f"{result['speakers']['speaker_count']} speakers, "
        f"{result['audio_events']['event_count']} audio events, "
        f"{result.get('ocr', {}).get('record_count', 0)} OCR records."
    )


if __name__ == "__main__":
    main()
