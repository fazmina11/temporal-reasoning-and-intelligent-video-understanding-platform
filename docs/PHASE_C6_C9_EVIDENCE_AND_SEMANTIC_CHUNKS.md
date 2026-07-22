# Phases C6-C9: Evidence Attachments and Semantic Chunks

## Outcome

These phases turn validated atomic spans into retrieval-ready evidence units.
C3-C5 decide the canonical timeline. C6-C9 attach transcript, frames, clips, and
semantic grouping without changing the atom boundaries.

Run after C3-C5:

```powershell
$env:FFMPEG_BIN_DIR="C:\Users\haris\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
python -m src.pipeline.evidence_foundation --video-id mcp_vs_api
```

For a faster metadata-only pass without atom clips:

```powershell
python -m src.pipeline.evidence_foundation --video-id mcp_vs_api --skip-clips
```

## Phase C6: Attach Transcript To Atomic Spans

C6 reads:

```text
data/processed/transcripts/{video_id}.json
data/processed/atoms/{video_id}.json
```

It updates every atom in:

```text
data/processed/atoms/{video_id}.json
```

Each atom receives:

```json
{
  "transcript_text": "He drew the blue graph to compare cats and dogs.",
  "word_ids": ["word_000421_000001", "word_000421_000002"],
  "segment_ids": ["segment_000421"],
  "speaker_ids": [],
  "asr_confidence": 0.9493
}
```

The IDs are stable within the transcript artifact. If diarization is not
available, `speaker_ids` remains an empty list instead of inventing speakers.
Words that cross atom boundaries may be referenced by more than one atom. This
preserves evidence rather than cutting a spoken word incorrectly.

## Phase C7: Frame And Clip Attachment

C7 refreshes frame evidence with atom-aware sampling:

```text
start frame
middle frame
end frame
highest visual-change frame
best OCR-readable frame approximation
```

It writes:

```text
data/processed/frames/{video_id}/frames.json
data/processed/clips/{video_id}/{atom_id}.mp4
data/processed/visual_artifacts/{video_id}.json
```

Each atom also receives:

```json
{
  "representative_frame_ids": ["frame_000000542", "frame_000000634"],
  "frame_timestamps_ms": [22606, 26443],
  "visual_evidence": {
    "frame_references": [],
    "clip": {
      "clip_start_ms": 22606,
      "clip_end_ms": 30240
    }
  }
}
```

The current OCR-readable frame is a deterministic quality estimate based on
sharpness, luminance, and black-pixel ratio. A later OCR phase can replace that
with real OCR confidence without changing the artifact shape.

## Phase C8: Semantic Chunk Builder

C8 groups atoms into coherent idea-level chunks:

```text
data/processed/semantic_chunks/{video_id}.json
```

Atomic spans remain precise evidence. Semantic chunks are larger retrieval units
that carry complete explanations. The current base builder merges neighboring
atoms until a meaningful split appears or the chunk reaches a duration limit.

Split signals:

```text
scene_cut
visual_difference
pause
forced_atomic_boundary
maximum_chunk_duration
```

Each chunk stores:

```json
{
  "chunk_id": "chunk_000052",
  "atom_ids": ["atom_000140", "atom_000141"],
  "start_ms": 9676200,
  "end_ms": 9712400,
  "title": "Cats vs dogs graph comparison",
  "transcript_text": "...",
  "representative_frame_ids": []
}
```

## Phase C9: Semantic Chunk Validation

C9 writes:

```text
data/processed/reports/{video_id}_chunk_validation.json
```

It checks:

- every semantic chunk references valid atoms;
- every atom belongs to exactly one semantic chunk;
- each chunk start equals the first atom start;
- each chunk end equals the last atom end;
- atoms inside a chunk are contiguous;
- chunk intervals do not conflict;
- first chunk starts at 0 ms;
- final chunk reaches the video duration.

If validation fails, the semantic stage raises an error and should not be used
for Chroma indexing.

## Verified Output For `mcp_vs_api`

```text
Atoms updated: 81
Transcript segments attached: 250
Transcript words attached: 1701
Atoms with transcript text: 79
Atoms with no speech text: 2
Average ASR confidence: 0.9493
Visual artifact records: 81
Atom clips: 81
Semantic chunks: 18
Chunk validation: passed
Missing atom assignments: 0
Duplicate atom assignments: 0
```

The generated clips occupy about 87 MB for this 12-minute video.

## API Endpoints

```text
GET /atoms/{video_id}
GET /visual-artifacts/{video_id}
GET /semantic-chunks/{video_id}
GET /chunk-validation/{video_id}
```

## Current Boundary

C6-C9 prepare retrieval-ready structure, but they still do not create advanced
Chroma records or agentic retrieval. The next phase should index semantic chunks
and atom evidence into Chroma with metadata fields for `video_id`, `chunk_id`,
`atom_ids`, `start_ms`, `end_ms`, transcript text, frame IDs, clip paths, and
source hash.
