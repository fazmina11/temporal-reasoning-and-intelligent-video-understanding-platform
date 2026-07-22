# Phases C3-C5: Boundary Signals and Canonical Atomic Spans

## Outcome

These phases turn one normalized video timeline into a deterministic set of
non-overlapping atomic spans. They are the evidence anchors that later
transcript alignment, clip understanding, embeddings, ChromaDB records, events,
and citations must reference.

The implementation deliberately fails closed: an atom timeline is not marked
complete unless Phase C5 proves that it covers the video exactly.

## Prerequisites

- A C0/C1 manifest at `data/processed/manifests/{video_id}.json`.
- The source video referenced by that manifest.
- FFmpeg and FFprobe on `PATH`, or one of these environment settings:

```dotenv
FFMPEG_BIN_DIR=C:\ffmpeg\bin
# Or configure each executable separately:
FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
FFPROBE_PATH=C:\ffmpeg\bin\ffprobe.exe
```

- For sentence and pause evidence, a word-timestamp transcript at the manifest's
  `artifacts.transcript_path`. C3 still runs without it and records a warning.

Verify the media tools:

```powershell
ffmpeg -version
ffprobe -version
```

## Phase C3: Boundary Signal Extraction

Run:

```powershell
python -m src.pipeline.chunking_foundation --video-id <video_id>
```

C3 creates:

```text
data/processed/boundaries/{video_id}.json
```

Implemented signals:

| Signal | Source | Default behavior |
|---|---|---|
| `duration` | Normalized timeline | Candidate every 15,000 ms |
| `sentence_boundary` | Whisper words/segments | Terminal `.`, `!`, or `?` |
| `pause` | Consecutive timed words | Gap of at least 800 ms |
| `scene_cut` | PySceneDetect | Content threshold 27.0 |
| `visual_difference` | FFmpeg sampled grayscale frames | 1-second sampling, normalized difference threshold 0.08 |

Candidates within 350 ms are merged. The timestamp from the strongest signal is
kept, all contributing signals remain visible, and confidence is combined as a
bounded probability. A candidate therefore preserves both a simple retrieval
surface and detailed evidence:

```json
{
  "boundary_id": "boundary_000145",
  "timestamp_ms": 9676200,
  "signals": ["sentence_boundary", "pause"],
  "score": 0.9104,
  "signal_scores": {
    "sentence_boundary": 0.68,
    "pause": 0.72
  },
  "evidence": {}
}
```

The artifact also stores the source SHA-256, pipeline and schema versions,
effective configuration, signal availability, transcript counts, warnings, and
per-signal candidate counts. This prevents silent use of missing modalities.

The base implementation now also declares the full signal roadmap. The active
signals are:

```text
duration
sentence_boundary
pause
scene_cut
visual_difference
```

The planned signals are recorded as unavailable with an explicit `planned`
status:

```text
speaker_change
ocr_change
topic_embedding_shift
motion_change
audio_event_change
```

This is intentional. Downstream code can inspect `signal_availability` and know
whether a signal was truly available, skipped because an artifact was missing, or
not implemented yet. The boundary artifact also includes `quality_metrics`,
including raw candidate count, merged candidate count, multimodal candidate
count, high-confidence candidate count, and signal coverage ratio.

## Phase C4: Atomic Span Builder

C4 consumes only a boundary artifact whose `video_id`, source hash, and duration
match the manifest. It creates:

```text
data/processed/atoms/{video_id}.json
```

Defaults:

```text
minimum:       3,000 ms
target:        8,000 ms
maximum:      15,000 ms
hard maximum: 20,000 ms
```

At each position, the builder considers candidates that satisfy the minimum and
maximum duration constraints. Selection combines candidate confidence with
distance from the 8-second target. It reserves at least 3 seconds for the final
span, so a strong boundary near the end cannot create a tiny accidental tail.
When no candidate is available, it inserts a deterministic target-duration cut.

Every atom stores integer milliseconds, source frame bounds, boundary reasons,
confidence, source boundary IDs, pipeline version, and valid previous/next IDs.
The first and final anchors are always `timeline_start` and `timeline_end`.

The atom artifact also stores a timeline contract and quality metrics:

- exact coverage is required;
- gaps and overlaps are forbidden;
- identity must match the manifest `video_id` and `source_sha256`;
- selected internal boundaries are preserved for debugging;
- natural and forced internal boundary counts are reported;
- minimum, maximum, and average atom duration are reported.

## Phase C5: Atomic Span Validation

C5 creates:

```text
data/processed/reports/{video_id}_atom_validation.json
```

It verifies:

- first atom starts at `0`;
- last atom ends at `manifest.duration_ms`;
- all timestamps are integer, non-negative, and ordered;
- every interval satisfies `start_ms < end_ms`;
- no atom exceeds the video or hard maximum;
- consecutive atoms have exactly equal end/start timestamps;
- there are no gaps or overlaps;
- IDs are unique and monotonic;
- previous/next pointers match neighboring records;
- source hash, `video_id`, duration, and pipeline version match the manifest.

The report includes boolean checks, coverage metrics, structured errors, and
warnings. `run_chunking_foundation` raises an error and does not mark the manifest
stage complete when `valid` is false.

The validation metrics now include short atom count, hard maximum violations,
covered duration, duration distribution, gap count, overlap count, and maximum
gap/overlap size. This makes C5 useful as a gate before transcript-to-atom
attachment, clip generation, Chroma indexing, and retrieval citations.

## API Integration

Uploads now run in this order:

```text
manifest and FFprobe metadata
-> legacy scene/frame pass
-> per-video Faster-Whisper transcript when audio exists
-> C3 boundary extraction
-> C4 atomic span construction
-> C5 validation
-> visual enrichment
-> vector indexing
```

Artifacts can be inspected through:

```text
GET /manifest/{video_id}
GET /boundaries/{video_id}
GET /atoms/{video_id}
GET /atom-validation/{video_id}
```

## Verification

Run focused tests:

```powershell
python -m unittest discover -s tests -v
```

Run C3-C5 again for an existing manifest:

```powershell
python -m src.pipeline.chunking_foundation --video-id demo_video
```

For a Windows FFmpeg install that is not on `PATH`, set `FFMPEG_BIN_DIR` first:

```powershell
$env:FFMPEG_BIN_DIR="C:\Users\haris\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
python -m src.pipeline.chunking_foundation --video-id mcp_vs_api
```

The included demo verification produced 163 merged candidates and 66 atoms over
581,700 ms. Validation reported zero gaps, zero overlaps, valid pointers, and
complete coverage. Atom durations ranged from 3,000 to 13,930 ms.

The `mcp_vs_api` verification produced 209 merged candidates and 81 atoms over
744,786 ms. C5 validation passed with zero gaps, zero overlaps, zero short atoms,
zero hard-maximum violations, and complete coverage.

## Current Boundary

C3-C5 create the canonical timeline base only. They do not yet attach transcript
text to atoms, generate clip-level VLM descriptions, create semantic chunks or
events, or write vectors to ChromaDB. Those later phases must consume these atom
IDs rather than generating a second competing timeline.
