# Phase C0-C1: Mature Manifest And Timeline Normalization

This document defines the completed base contract for Phase C0 and Phase C1.

These phases must be finished before accurate chunking begins.

## Phase C0: Mature Manifest Foundation

Every uploaded video creates one manifest:

```text
data/processed/manifests/{video_id}.json
```

The manifest is the source of truth for every later phase.

Required stored fields:

```text
video_id
source_filename
source_path
source_sha256
duration_ms
duration_seconds
fps
frame_count
width
height
resolution
video_codec
audio_codec
audio_sample_rate
has_audio
probe_backend
probe_warnings
pipeline_version
processing.status
processing.progress
processing.current_phase
processing.started_at
processing.completed_at
processing.updated_at
created_at
updated_at
artifact paths
```

The source hash is critical. It prevents the system from accidentally reusing
chunks, vectors, transcripts, or events from a different uploaded file.

## Phase C1: Timeline Normalization

All internal processing must use integer milliseconds.

Canonical fields:

```text
start_ms
end_ms
duration_ms
```

Floating seconds may be stored only for display or backward compatibility.

The manifest stores:

```json
{
  "timeline": {
    "time_unit": "milliseconds",
    "start_ms": 0,
    "end_ms": 120000,
    "duration_ms": 120000,
    "normalized": true,
    "normalization_version": "timeline-v1",
    "source_start_offset_ms": 0,
    "audio_start_offset_ms": 0,
    "video_start_offset_ms": 0
  }
}
```

## Conflict Prevention Rules

The manifest validator enforces:

- `duration_ms` is an integer
- `timeline.start_ms` is an integer
- `timeline.end_ms` is an integer
- `timeline.duration_ms` is an integer
- no timeline value is negative
- normalized timeline starts at `0`
- `timeline.end_ms == duration_ms`
- `timeline.duration_ms == duration_ms`
- `frame_count >= 0`
- `fps >= 0`

These rules prevent later conflicts in:

- transcript alignment
- atomic span boundaries
- citation timestamps
- ChromaDB metadata filtering
- timeline UI jumps
- event and chapter construction

## Probe Strategy

The project uses two probe modes.

Preferred:

```text
ffprobe
```

This can detect:

```text
video codec
audio codec
audio sample rate
has_audio
duration
fps
frame count
resolution
```

Fallback:

```text
OpenCV
```

This can detect:

```text
duration
fps
frame count
resolution
video codec
```

If OpenCV fallback is used, audio metadata is stored as unknown:

```json
{
  "audio_codec": null,
  "audio_sample_rate": null,
  "has_audio": null,
  "probe_warnings": [
    "ffprobe was not available; audio metadata could not be inspected."
  ]
}
```

Do not invent audio fields when the machine cannot inspect them.

## Artifact Paths Reserved By The Manifest

The manifest reserves paths for later phases:

```text
manifest_path
audio_path
transcript_path
atoms_path
chunks_path
boundaries_path
semantic_chunks_path
frames_dir
clips_dir
events_path
chapters_path
timeline_validation_path
```

Later phases must read these paths from the manifest instead of constructing
their own independent paths.

## Phase C0-C1 Exit Criteria

This phase is complete when:

- upload writes `data/processed/manifests/{video_id}.json`
- manifest contains `source_sha256`
- manifest contains `duration_ms`
- manifest contains `timeline`
- timeline is validated before saving
- manifest records processing status
- manifest records artifact paths for future phases
- `/manifest/{video_id}` returns the manifest
- `/status/{video_id}` returns manifest-backed status when memory state is gone

