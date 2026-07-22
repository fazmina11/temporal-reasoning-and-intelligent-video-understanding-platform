from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .atomic_spans import (
    AtomicSpanConfig,
    AtomicSpanError,
    build_atomic_spans,
    validate_atomic_spans,
)
from .boundary_signals import BoundaryConfig, extract_boundary_signals
from .media_manifest import load_manifest, save_manifest, utc_now


def run_chunking_foundation(
    *,
    repo_root: Path,
    video_id: str,
    boundary_config: BoundaryConfig | None = None,
    atom_config: AtomicSpanConfig | None = None,
) -> dict[str, Any]:
    """Run C3, C4, and C5 as one fail-closed pipeline stage."""
    boundaries = extract_boundary_signals(
        repo_root=repo_root,
        video_id=video_id,
        config=boundary_config,
    )
    atoms = build_atomic_spans(
        repo_root=repo_root,
        video_id=video_id,
        config=atom_config,
    )
    report = validate_atomic_spans(
        repo_root=repo_root,
        video_id=video_id,
        config=atom_config,
    )
    if not report["valid"]:
        raise AtomicSpanError(
            f"Atomic span validation failed with {len(report['errors'])} error(s)."
        )

    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    manifest.setdefault("artifact_metadata", {})["chunking_foundation"] = {
        "boundary_schema_version": boundaries["schema_version"],
        "boundary_candidate_count": boundaries["candidate_count"],
        "atom_schema_version": atoms["schema_version"],
        "atom_count": atoms["atom_count"],
        "validation_schema_version": report["schema_version"],
        "validation_passed": True,
        "completed_at": utc_now(),
    }
    manifest["updated_at"] = utc_now()
    save_manifest(repo_root=repo_root, manifest=manifest)
    return {"boundaries": boundaries, "atoms": atoms, "validation": report}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run chunking phases C3-C5.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
    )
    args = parser.parse_args()
    result = run_chunking_foundation(
        repo_root=Path(args.repo_root),
        video_id=args.video_id,
    )
    print(
        f"C3-C5 complete: {result['boundaries']['candidate_count']} candidates, "
        f"{result['atoms']['atom_count']} atoms, validation passed."
    )


if __name__ == "__main__":
    main()
