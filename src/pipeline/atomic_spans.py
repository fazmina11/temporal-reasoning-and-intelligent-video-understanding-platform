from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .boundary_signals import BOUNDARY_SCHEMA_VERSION
from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, utc_now, validate_manifest_timeline

ATOM_SCHEMA_VERSION = "atomic-spans-v1"
ATOM_VALIDATION_SCHEMA_VERSION = "atom-validation-v1"


class AtomicSpanError(RuntimeError):
    """Raised when canonical atomic spans cannot be built or validated."""


@dataclass(frozen=True)
class AtomicSpanConfig:
    minimum_duration_ms: int = 3_000
    target_duration_ms: int = 8_000
    maximum_duration_ms: int = 15_000
    hard_maximum_duration_ms: int = 20_000
    boundary_score_weight: float = 0.75
    target_proximity_weight: float = 0.25

    def validate(self) -> None:
        durations = (
            self.minimum_duration_ms,
            self.target_duration_ms,
            self.maximum_duration_ms,
            self.hard_maximum_duration_ms,
        )
        if any(not isinstance(value, int) or value <= 0 for value in durations):
            raise AtomicSpanError("All atomic duration settings must be positive integers.")
        if not (
            self.minimum_duration_ms
            <= self.target_duration_ms
            <= self.maximum_duration_ms
            <= self.hard_maximum_duration_ms
        ):
            raise AtomicSpanError(
                "Atomic durations must satisfy minimum <= target <= maximum <= hard maximum."
            )
        if self.boundary_score_weight < 0 or self.target_proximity_weight < 0:
            raise AtomicSpanError("Boundary selection weights must not be negative.")
        if self.boundary_score_weight + self.target_proximity_weight <= 0:
            raise AtomicSpanError("At least one boundary selection weight must be positive.")


def _load_boundaries(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        raise AtomicSpanError(f"Boundary artifact does not exist: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise AtomicSpanError("Boundary artifact must be a JSON object.")
    if payload.get("schema_version") != BOUNDARY_SCHEMA_VERSION:
        raise AtomicSpanError(
            f"Unsupported boundary schema: {payload.get('schema_version')}"
        )
    if payload.get("video_id") != manifest["video_id"]:
        raise AtomicSpanError("Boundary video_id does not match the manifest.")
    if payload.get("source_sha256") != manifest["source_sha256"]:
        raise AtomicSpanError("Boundary source hash does not match the manifest.")
    if payload.get("duration_ms") != manifest["duration_ms"]:
        raise AtomicSpanError("Boundary duration does not match the manifest timeline.")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise AtomicSpanError("Boundary artifact candidates must be a list.")
    return payload


def _candidate_utility(
    candidate: dict[str, Any],
    cursor_ms: int,
    config: AtomicSpanConfig,
) -> float:
    timestamp_ms = candidate["timestamp_ms"]
    distance = abs((timestamp_ms - cursor_ms) - config.target_duration_ms)
    proximity = max(0.0, 1.0 - distance / config.target_duration_ms)
    total_weight = config.boundary_score_weight + config.target_proximity_weight
    return (
        config.boundary_score_weight * float(candidate.get("score", 0.0))
        + config.target_proximity_weight * proximity
    ) / total_weight


def _choose_boundary(
    candidates: list[dict[str, Any]],
    cursor_ms: int,
    duration_ms: int,
    config: AtomicSpanConfig,
) -> dict[str, Any]:
    lower_bound = cursor_ms + config.minimum_duration_ms
    upper_bound = min(
        cursor_ms + config.maximum_duration_ms,
        duration_ms - config.minimum_duration_ms,
    )
    eligible = [
        candidate
        for candidate in candidates
        if lower_bound <= candidate.get("timestamp_ms", -1) <= upper_bound
    ]
    if eligible:
        selected = max(
            eligible,
            key=lambda item: (
                _candidate_utility(item, cursor_ms, config),
                float(item.get("score", 0.0)),
                -abs(
                    (item["timestamp_ms"] - cursor_ms)
                    - config.target_duration_ms
                ),
                -item["timestamp_ms"],
            ),
        )
        return {
            "timestamp_ms": selected["timestamp_ms"],
            "reasons": list(selected.get("signals") or ["candidate_boundary"]),
            "confidence": round(float(selected.get("score", 0.0)), 4),
            "boundary_id": selected.get("boundary_id"),
            "forced": False,
        }

    timestamp_ms = min(cursor_ms + config.target_duration_ms, upper_bound)
    if timestamp_ms < lower_bound:
        timestamp_ms = upper_bound
    if timestamp_ms <= cursor_ms:
        raise AtomicSpanError(
            f"Could not create a valid boundary after {cursor_ms} ms."
        )
    return {
        "timestamp_ms": timestamp_ms,
        "reasons": ["forced_target_duration"],
        "confidence": 1.0,
        "boundary_id": None,
        "forced": True,
    }


def _frame_interval(
    start_ms: int,
    end_ms: int,
    fps: float,
    frame_count: int,
) -> tuple[int | None, int | None]:
    if fps <= 0 or frame_count <= 0:
        return None, None
    start_frame = min(frame_count - 1, int(math.floor(start_ms * fps / 1000)))
    end_frame = min(
        frame_count - 1,
        max(start_frame, int(math.ceil(end_ms * fps / 1000)) - 1),
    )
    return start_frame, end_frame


def _duration_metrics(atoms: list[dict[str, Any]]) -> dict[str, Any]:
    durations: list[int] = []
    for atom in atoms:
        try:
            duration_ms = int(atom["duration_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if duration_ms >= 0:
            durations.append(duration_ms)
    if not durations:
        return {
            "minimum_atom_duration_ms": 0,
            "maximum_atom_duration_ms": 0,
            "average_atom_duration_ms": 0,
        }
    return {
        "minimum_atom_duration_ms": min(durations),
        "maximum_atom_duration_ms": max(durations),
        "average_atom_duration_ms": round(sum(durations) / len(durations), 2),
    }


def build_atomic_spans(
    *,
    repo_root: Path,
    video_id: str,
    config: AtomicSpanConfig | None = None,
) -> dict[str, Any]:
    """Run Phase C4 and persist one canonical, exact-cover atomic timeline."""
    config = config or AtomicSpanConfig()
    config.validate()
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    duration_ms = manifest["duration_ms"]
    if duration_ms <= 0:
        raise AtomicSpanError("Atomic span construction requires a positive duration.")

    boundaries_path = Path(manifest["artifacts"]["boundaries_path"])
    boundary_payload = _load_boundaries(boundaries_path, manifest)
    candidates = sorted(
        boundary_payload["candidates"], key=lambda item: item.get("timestamp_ms", -1)
    )

    selected_boundaries: list[dict[str, Any]] = []
    cursor_ms = 0
    while duration_ms - cursor_ms > config.maximum_duration_ms:
        selected = _choose_boundary(
            candidates, cursor_ms, duration_ms, config
        )
        selected_boundaries.append(selected)
        cursor_ms = selected["timestamp_ms"]

    cuts = [0, *[item["timestamp_ms"] for item in selected_boundaries], duration_ms]
    end_boundary_lookup = {
        item["timestamp_ms"]: item for item in selected_boundaries
    }
    atoms: list[dict[str, Any]] = []
    fps = float(manifest.get("fps") or 0.0)
    frame_count = int(manifest.get("frame_count") or 0)

    for index, (start_ms, end_ms) in enumerate(zip(cuts, cuts[1:]), start=1):
        atom_id = f"atom_{index:06d}"
        previous_atom_id = f"atom_{index - 1:06d}" if index > 1 else None
        next_atom_id = f"atom_{index + 1:06d}" if index < len(cuts) - 1 else None
        if index == 1:
            start_boundary = {
                "reasons": ["timeline_start"],
                "confidence": 1.0,
                "boundary_id": None,
                "forced": True,
            }
        else:
            start_boundary = end_boundary_lookup[start_ms]
        if end_ms == duration_ms:
            end_boundary = {
                "reasons": ["timeline_end"],
                "confidence": 1.0,
                "boundary_id": None,
                "forced": True,
            }
        else:
            end_boundary = end_boundary_lookup[end_ms]

        source_frame_start, source_frame_end = _frame_interval(
            start_ms, end_ms, fps, frame_count
        )
        atoms.append(
            {
                "video_id": video_id,
                "atom_id": atom_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": end_ms - start_ms,
                "previous_atom_id": previous_atom_id,
                "next_atom_id": next_atom_id,
                "boundary_start_reasons": list(start_boundary["reasons"]),
                "boundary_end_reasons": list(end_boundary["reasons"]),
                "boundary_confidence": round(
                    float(end_boundary["confidence"]), 4
                ),
                "start_boundary_id": start_boundary.get("boundary_id"),
                "end_boundary_id": end_boundary.get("boundary_id"),
                "end_boundary_forced": bool(end_boundary.get("forced")),
                "transcript_word_ids": [],
                "source_frame_start": source_frame_start,
                "source_frame_end": source_frame_end,
                "pipeline_version": manifest["pipeline_version"],
            }
        )

    payload = {
        "schema_version": ATOM_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": duration_ms,
        "timeline_contract": {
            "unit": "milliseconds",
            "coverage": "exact",
            "overlap_policy": "forbidden",
            "gap_policy": "forbidden",
            "identity_policy": "manifest_video_id_and_source_sha256",
        },
        "boundary_schema_version": boundary_payload["schema_version"],
        "boundary_artifact_path": str(boundaries_path),
        "boundary_signal_counts": boundary_payload.get("signal_counts", {}),
        "config": asdict(config),
        "atom_count": len(atoms),
        "forced_internal_boundary_count": sum(
            item["forced"] for item in selected_boundaries
        ),
        "quality_metrics": {
            **_duration_metrics(atoms),
            "target_duration_ms": config.target_duration_ms,
            "minimum_duration_ms": config.minimum_duration_ms,
            "maximum_duration_ms": config.maximum_duration_ms,
            "hard_maximum_duration_ms": config.hard_maximum_duration_ms,
            "candidate_boundary_count": len(candidates),
            "selected_internal_boundary_count": len(selected_boundaries),
            "natural_internal_boundary_count": sum(
                not item["forced"] for item in selected_boundaries
            ),
            "forced_internal_boundary_count": sum(
                item["forced"] for item in selected_boundaries
            ),
        },
        "selected_boundaries": selected_boundaries,
        "atoms": atoms,
        "created_at": utc_now(),
    }
    write_json_atomic(Path(manifest["artifacts"]["atoms_path"]), payload)
    return payload


def _issue(code: str, message: str, atom_id: str | None = None) -> dict[str, Any]:
    issue = {"code": code, "message": message}
    if atom_id is not None:
        issue["atom_id"] = atom_id
    return issue


def validate_atomic_spans(
    *,
    repo_root: Path,
    video_id: str,
    config: AtomicSpanConfig | None = None,
) -> dict[str, Any]:
    """Run Phase C5 and persist a detailed invariant report."""
    config = config or AtomicSpanConfig()
    config.validate()
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    validate_manifest_timeline(manifest)
    atoms_path = Path(manifest["artifacts"]["atoms_path"])
    if not atoms_path.is_file():
        raise AtomicSpanError(f"Atomic span artifact does not exist: {atoms_path}")
    payload = read_json(atoms_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("atoms"), list):
        raise AtomicSpanError("Atomic span artifact has an invalid structure.")

    atoms = payload["atoms"]
    duration_ms = manifest["duration_ms"]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    gap_count = 0
    overlap_count = 0
    max_gap_ms = 0
    max_overlap_ms = 0
    short_atom_count = 0
    hard_max_exceeded_count = 0

    if payload.get("schema_version") != ATOM_SCHEMA_VERSION:
        errors.append(_issue("schema_version", "Unsupported atomic span schema."))
    if payload.get("video_id") != video_id:
        errors.append(_issue("video_id", "Top-level video_id does not match."))
    if payload.get("source_sha256") != manifest["source_sha256"]:
        errors.append(_issue("source_sha256", "Source hash does not match manifest."))
    if payload.get("duration_ms") != duration_ms:
        errors.append(_issue("duration_ms", "Artifact duration does not match manifest."))
    if not atoms:
        errors.append(_issue("empty_atoms", "Atomic span list must not be empty."))

    atom_ids = [atom.get("atom_id") for atom in atoms if isinstance(atom, dict)]
    if len(atom_ids) != len(set(atom_ids)):
        errors.append(_issue("duplicate_atom_id", "Atom IDs must be unique."))

    for index, atom in enumerate(atoms):
        if not isinstance(atom, dict):
            errors.append(_issue("atom_type", f"Atom at index {index} is not an object."))
            continue
        atom_id = atom.get("atom_id")
        expected_id = f"atom_{index + 1:06d}"
        if atom_id != expected_id:
            errors.append(
                _issue("atom_order", f"Expected atom_id {expected_id}.", str(atom_id))
            )
        if atom.get("video_id") != video_id:
            errors.append(
                _issue("atom_video_id", "Atom belongs to another video.", atom_id)
            )
        if atom.get("pipeline_version") != manifest["pipeline_version"]:
            errors.append(
                _issue("pipeline_version", "Atom pipeline version differs.", atom_id)
            )

        start_ms = atom.get("start_ms")
        end_ms = atom.get("end_ms")
        atom_duration_ms = atom.get("duration_ms")
        if not isinstance(start_ms, int) or not isinstance(end_ms, int):
            errors.append(
                _issue("integer_timeline", "Atom timestamps must be integers.", atom_id)
            )
            continue
        if start_ms < 0 or end_ms < 0:
            errors.append(
                _issue("negative_timestamp", "Atom timestamps cannot be negative.", atom_id)
            )
        if start_ms >= end_ms:
            errors.append(
                _issue("invalid_interval", "Atom must satisfy start_ms < end_ms.", atom_id)
            )
        if end_ms > duration_ms:
            errors.append(
                _issue("past_duration", "Atom ends after the video duration.", atom_id)
            )
        if atom_duration_ms != end_ms - start_ms:
            errors.append(
                _issue("duration_mismatch", "Atom duration is inconsistent.", atom_id)
            )
        if end_ms - start_ms > config.hard_maximum_duration_ms:
            hard_max_exceeded_count += 1
            errors.append(
                _issue("hard_max_exceeded", "Atom exceeds hard maximum duration.", atom_id)
            )
        if (
            end_ms - start_ms < config.minimum_duration_ms
            and duration_ms >= config.minimum_duration_ms
        ):
            short_atom_count += 1
            warnings.append(
                _issue("short_atom", "Atom is shorter than the configured minimum.", atom_id)
            )

        expected_previous = atoms[index - 1].get("atom_id") if index > 0 else None
        expected_next = atoms[index + 1].get("atom_id") if index + 1 < len(atoms) else None
        if atom.get("previous_atom_id") != expected_previous:
            errors.append(
                _issue("previous_pointer", "previous_atom_id is invalid.", atom_id)
            )
        if atom.get("next_atom_id") != expected_next:
            errors.append(_issue("next_pointer", "next_atom_id is invalid.", atom_id))

        if index > 0 and isinstance(start_ms, int):
            previous_end = atoms[index - 1].get("end_ms")
            if isinstance(previous_end, int):
                delta_ms = start_ms - previous_end
                if delta_ms > 0:
                    gap_count += 1
                    max_gap_ms = max(max_gap_ms, delta_ms)
                    errors.append(
                        _issue("timeline_gap", f"Gap of {delta_ms} ms detected.", atom_id)
                    )
                elif delta_ms < 0:
                    overlap_count += 1
                    max_overlap_ms = max(max_overlap_ms, -delta_ms)
                    errors.append(
                        _issue(
                            "timeline_overlap",
                            f"Overlap of {-delta_ms} ms detected.",
                            atom_id,
                        )
                    )

    first_starts_at_zero = bool(atoms) and atoms[0].get("start_ms") == 0
    last_reaches_duration = bool(atoms) and atoms[-1].get("end_ms") == duration_ms
    if not first_starts_at_zero:
        errors.append(_issue("timeline_start", "First atom must start at 0 ms."))
    if not last_reaches_duration:
        errors.append(
            _issue("timeline_end", "Last atom must end at the video duration.")
        )

    checks = {
        "first_atom_starts_at_zero": first_starts_at_zero,
        "last_atom_reaches_duration": last_reaches_duration,
        "timestamps_are_non_negative": not any(
            issue["code"] == "negative_timestamp" for issue in errors
        ),
        "intervals_are_valid": not any(
            issue["code"] in {"invalid_interval", "past_duration"} for issue in errors
        ),
        "no_gaps": gap_count == 0,
        "no_overlaps": overlap_count == 0,
        "previous_next_pointers_are_valid": not any(
            issue["code"] in {"previous_pointer", "next_pointer"} for issue in errors
        ),
        "all_atoms_match_video_id": not any(
            issue["code"] == "atom_video_id" for issue in errors
        ),
        "hard_maximum_is_respected": not any(
            issue["code"] == "hard_max_exceeded" for issue in errors
        ),
    }
    report = {
        "schema_version": ATOM_VALIDATION_SCHEMA_VERSION,
        "video_id": video_id,
        "source_sha256": manifest["source_sha256"],
        "pipeline_version": manifest["pipeline_version"],
        "time_unit": "milliseconds",
        "duration_ms": duration_ms,
        "atoms_path": str(atoms_path),
        "config": asdict(config),
        "valid": len(errors) == 0,
        "checks": checks,
        "metrics": {
            "atom_count": len(atoms),
            "gap_count": gap_count,
            "overlap_count": overlap_count,
            "max_gap_ms": max_gap_ms,
            "max_overlap_ms": max_overlap_ms,
            "short_atom_count": short_atom_count,
            "hard_max_exceeded_count": hard_max_exceeded_count,
            "covered_duration_ms": sum(
                max(0, int(atom.get("duration_ms") or 0))
                for atom in atoms
                if isinstance(atom, dict)
            ),
            **_duration_metrics(
                [atom for atom in atoms if isinstance(atom, dict) and "duration_ms" in atom]
            ),
        },
        "errors": errors,
        "warnings": warnings,
        "validated_at": utc_now(),
    }
    report_path = Path(manifest["artifacts"]["atom_validation_path"])
    write_json_atomic(report_path, report)
    return report
