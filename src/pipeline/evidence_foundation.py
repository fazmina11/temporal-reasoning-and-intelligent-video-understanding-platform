from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .semantic_chunks import run_semantic_chunking
from .transcript_attachment import attach_transcript_to_atoms
from .visual_attachment import attach_visual_artifacts


def run_evidence_foundation(
    *,
    repo_root: Path,
    video_id: str,
    create_clips: bool = True,
) -> dict[str, Any]:
    """Run phases C6-C9 after C3-C5 has produced validated atoms."""
    transcript_atoms = attach_transcript_to_atoms(
        repo_root=repo_root,
        video_id=video_id,
    )
    visual_artifacts = attach_visual_artifacts(
        repo_root=repo_root,
        video_id=video_id,
        create_clips=create_clips,
    )
    semantic = run_semantic_chunking(
        repo_root=repo_root,
        video_id=video_id,
    )
    return {
        "atoms": transcript_atoms,
        "visual_artifacts": visual_artifacts,
        "semantic_chunks": semantic["chunks"],
        "chunk_validation": semantic["validation"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evidence phases C6-C9.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
    )
    parser.add_argument(
        "--skip-clips",
        action="store_true",
        help="Attach frames and semantic chunks without generating atom clips.",
    )
    args = parser.parse_args()
    result = run_evidence_foundation(
        repo_root=Path(args.repo_root),
        video_id=args.video_id,
        create_clips=not args.skip_clips,
    )
    print(
        "C6-C9 complete: "
        f"{result['atoms']['atom_count']} atoms updated, "
        f"{result['visual_artifacts']['clip_count']} clips, "
        f"{result['semantic_chunks']['chunk_count']} semantic chunks, "
        "chunk validation passed."
    )


if __name__ == "__main__":
    main()
