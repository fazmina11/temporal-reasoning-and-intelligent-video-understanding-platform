# Phase C6: Normalized Audio and Frame Evidence

## Why This Phase Exists

The original prototype did not provide complete visual coverage. It selected one
center frame for each detected scene, skipped visually duplicated scenes, and
wrote the remaining JPEGs into one global directory.

For the included demo:

```text
source video frames:          17,451
legacy JPEGs:                      5
JPEGs in manifest frames_dir:      0
```

That output cannot support reliable timeline retrieval and is unsafe when two
videos are processed concurrently.

Phase C6 creates video-scoped evidence derived from the validated atomic
timeline. It also creates one normalized audio artifact for ASR.

## Normalized Audio

FFmpeg extracts:

```text
data/processed/audio/{video_id}.wav
```

Default audio format:

```text
codec: pcm_s16le
sample rate: 16,000 Hz
channels: 1
sample width: 16 bit
```

The manifest records:

- extraction status;
- absolute and relative paths;
- codec and container;
- sample rate and channels;
- sample count and duration;
- byte size;
- SHA-256 checksum.

The extractor verifies that the WAV is readable, has the requested format, and
does not differ from the video duration by more than two seconds. Faster-Whisper
then reads this normalized WAV rather than repeatedly decoding compressed audio
from the source video.

## Frame Extraction Modes

### `atom_coverage` (default)

This is the production default. It extracts:

- one frame every 2,000 ms;
- the first timeline frame;
- the final decodable timeline frame;
- an atom midpoint only if a custom wider interval leaves an atom uncovered.

The minimum atom duration is 3,000 ms, so the default interval gives every atom
at least one representative image while also catching visual changes inside
longer atoms. The compact periodic FFmpeg selector remains constant-size as video
duration grows.

### `all_frames` (optional)

This exports every decoded source frame. Use it only for frame-by-frame research,
motion ground truth, or archival datasets.

```powershell
python -m src.pipeline.frame_extraction --video-id <video_id> --all-frames
```

It is not the default because a 45-minute 30 FPS video contains about 81,000
frames and can require many gigabytes of JPEG storage. Retrieval also becomes
slower if every near-duplicate frame is indexed independently.

## Frame Artifact Layout

```text
data/processed/frames/{video_id}/
  frame_000000000.jpg
  frame_000000060.jpg
  ...
  frames.json

data/processed/reports/{video_id}_frame_validation.json
```

`frames.json` stores for every extracted image:

- `video_id` and `frame_id`;
- integer `timestamp_ms`;
- source frame index;
- canonical `atom_id`;
- sampling reasons;
- related atom IDs;
- absolute and relative paths;
- width and height;
- byte size and SHA-256;
- sharpness, luminance, and black-pixel diagnostics;
- pipeline version.

The manifest points to both `frames_dir` and `frame_index_path`. Later OCR, VLM,
embedding, and retrieval stages must consume the frame index rather than scan a
shared directory.

## Validation

Frame validation fails the stage when:

- a frame file is missing or unreadable;
- timestamps are invalid or out of order;
- source identity differs from the manifest;
- a frame points to an unknown atom;
- any canonical atom has no frame evidence.

The report explicitly distinguishes these two facts:

```text
complete_atom_coverage: true
all_source_frames_exported: false
```

The first means the full video timeline is represented for retrieval. The second
means default sampling was used instead of an archival export.

## What Happens With A 30-45 Minute Video

For a constant 30 FPS source:

| Duration | Source frames | 2-second interval frames | Coverage fallbacks | Typical default total |
|---:|---:|---:|---:|---:|
| 30 minutes | 54,000 | 900 | normally 0 | about 900 |
| 45 minutes | 81,000 | 1,350 | normally 0 | about 1,350 |

Actual totals vary because duplicate target timestamps are merged.

Expected normalized WAV sizes:

| Duration | 16 kHz mono PCM WAV |
|---:|---:|
| 30 minutes | about 58 MB |
| 45 minutes | about 86 MB |

Based on the included 1280x720 demo, JPEG evidence is roughly 140 KB per frame.
A 30-45 minute lecture would therefore commonly require around 125-190 MB
for sampled frames. Resolution and visual complexity can move this estimate.

Exporting every source frame from the same videos could require roughly 8-12 GB
at that average JPEG size, which is why it is explicit rather than automatic.

## Long-Video Processing Sequence

```text
Upload source video
  -> stream file to data/uploads
  -> calculate source SHA-256
  -> FFprobe duration, FPS, streams, codec, resolution, frame count
  -> write normalized integer-millisecond manifest
  -> extract and validate 16 kHz mono WAV
  -> transcribe WAV with word timestamps
  -> extract boundary signals
  -> build and validate canonical atoms
  -> extract interval frames and any atom-coverage fallbacks in one FFmpeg decode
  -> write frame index and validation report
  -> continue to OCR, clip/VLM understanding, and indexing
```

The source video is never loaded completely into RAM. FFprobe reads metadata,
hashing streams the file in blocks, FFmpeg decodes audio/video sequentially, and
JSON artifacts are written atomically. Processing time grows approximately with
video duration, but memory use remains bounded.

## Commands

Default atom-aware extraction:

```powershell
python -m src.pipeline.frame_extraction --video-id <video_id>
```

Increase temporal density to one frame per second:

```powershell
python -m src.pipeline.frame_extraction --video-id <video_id> --interval-ms 1000
```

Every source frame:

```powershell
python -m src.pipeline.frame_extraction --video-id <video_id> --all-frames
```

API artifacts:

```text
GET /frames/{video_id}
GET /frame-validation/{video_id}
GET /manifest/{video_id}
```

## Demo Verification

The included 581.7-second demo now produces:

```text
source frames:              17,451
atom-coverage frames:          292
resolution:               1280x720
maximum sample gap:         2,000 ms
atoms with frame evidence:   66 / 66
missing files:                    0
unreadable files:                 0
JPEG storage:                 40.7 MB
frame validation:                PASS
```

Normalized audio:

```text
duration:                  581,660 ms
sample rate:                16,000 Hz
channels:                           1
size:                         18.6 MB
audio validation:                PASS
```
