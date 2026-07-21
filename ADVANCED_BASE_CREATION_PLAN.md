# Advanced Video RAG Base Creation Plan

This document is the base-building plan for upgrading this project from simple
scene chunking into an advanced video understanding platform.

Important scope note:

- This document does not implement Memory Recovery AI.
- This document does not implement agentic retrieval.
- This document does not implement Qwen2.5-VL, Video-LLaMA, LLaVA-Video, a Video
  World Model, or an Event Segmentation Transformer.
- This document defines the base architecture, storage contracts, project phases,
  team workflow, and Git discipline required so those features can be added later
  without rewriting the project.

The immediate goal is to build a strong foundation:

```text
Reliable video ingestion
  -> reliable audio extraction
  -> timestamped transcript
  -> timeline-safe chunking
  -> clip/frame artifacts
  -> structured metadata
  -> multi-collection ChromaDB indexing
  -> retrieval interfaces
  -> API contracts
  -> future-ready agent and memory interfaces
```

## 1. Problem With The Current Project

The current project is a useful prototype, but it is not yet an industry-level
video RAG base.

Current limitations:

- It depends too heavily on scene detection.
- Scene detection based on visual cuts does not equal semantic chunking.
- A center frame does not represent motion, drawing, gestures, transitions, or
  interactions.
- Audio, visual frames, OCR, and Chroma records are not tied together by a strong
  canonical chunk schema.
- Retrieval is mostly scene-level, not timeline-aware.
- ChromaDB storage is too simple for vague memory search.
- There is no clean separation between atomic chunks, semantic events, chapters,
  and long-range memory.
- There is no stable interface for later agents like Planner, Verifier, Temporal
  Reasoner, or Confidence Evaluator.

The advanced features you want require a better base first.

## 2. Target User Experience

The final system should support queries like:

```text
"What happened at 01:20:15?"
"What did he explain after the blue graph?"
"I remember he drew a blue graph but forgot why."
"He compared cats and dogs. Where was that?"
"Where does he return to the same idea later?"
"Compare the first explanation of transformers with the final summary."
"Summarize all places where he talks about loss curves."
```

For every answer, the system should return:

- timestamp range
- exact or approximate moment
- answer grounded in transcript and visual evidence
- citations
- neighboring timeline context
- confidence score
- explanation of why this moment was selected

To support that, the base must store more than captions.

## 3. Base Architecture

The base project should be organized as a pipeline with stable outputs at each
phase.

```text
Video Upload
  |
  v
Media Manifest
  |
  v
Audio Extraction
  |
  v
Transcript With Word Timestamps
  |
  v
Atomic Timeline Chunks
  |
  v
Frame And Clip Artifacts
  |
  v
Visual/OCR/Audio Metadata
  |
  v
Semantic Event Containers
  |
  v
Chapter Containers
  |
  v
ChromaDB Multi-Collection Index
  |
  v
Retrieval Interfaces
  |
  v
Future Agents And Memory Recovery
```

## 4. Project Folder Structure

Create this structure before advanced features are implemented.

```text
RAG-Enhanced-Video-Scene-Understanding/
  api.py
  requirement.txt
  README.md
  docs/
    ADVANCED_BASE_CREATION_PLAN.md
    API_CONTRACT.md
    CHROMA_SCHEMA.md
    TEAM_WORKFLOW.md

  schemas/
    media_manifest.schema.json
    transcript.schema.json
    chunk.schema.json
    event.schema.json
    chapter.schema.json
    world_memory.schema.json
    retrieval_result.schema.json

  src/
    pipeline/
      ingest.py
      media_manifest.py
      audio.py
      transcription.py
      chunking.py
      frame_sampling.py
      clip_sampling.py
      ocr.py
      visual_analysis.py
      event_builder.py
      chapter_builder.py

    indexing/
      embeddings.py
      chroma_store.py
      index_pipeline.py
      collection_names.py

    retrieval/
      base_retriever.py
      timeline_context.py
      hybrid_search.py
      memory_recovery_interface.py

    agents/
      interfaces.py
      planner_interface.py
      verifier_interface.py
      temporal_reasoner_interface.py
      confidence_interface.py

    models/
      api_models.py
      pipeline_models.py
      retrieval_models.py

    utils.py

  data/
    uploads/
    input_videos/
    processed/
      manifests/
      audio/
      transcripts/
      chunks/
      frames/
      clips/
      ocr/
      events/
      chapters/
      world_memory/
      indexing_reports/
    logs/

  chroma_db/
```

Rule:

Each pipeline phase must write a file artifact that the next phase reads. Do not
make later phases depend on hidden in-memory state.

## 5. Core Design Principles

### 5.1 Timeline Is The Primary Structure

Every object must have:

- `video_id`
- `start_seconds`
- `end_seconds`
- `duration_seconds`
- source path references
- confidence fields

No transcript, visual record, Chroma metadata, event, chapter, or answer should
exist without a timeline anchor.

### 5.2 Chunks Must Cover The Entire Video

Chunking should not depend only on scene detection.

The first reliable base should use:

- fixed windows
- overlap
- transcript alignment
- optional scene boundary hints

Recommended base:

```text
chunk size: 10 to 15 seconds
overlap: 2 to 4 seconds
minimum chunk: 5 seconds
maximum chunk: 30 seconds
```

Scene detection can help adjust boundaries, but it must not be the only chunking
strategy.

### 5.3 Store Raw Evidence And Derived Memory Separately

Raw evidence:

- transcript words
- frames
- clips
- OCR text
- audio confidence

Derived memory:

- summaries
- concepts
- entities
- actions
- relationships
- event summaries
- chapter summaries

Do not overwrite raw evidence with summaries.

### 5.4 Retrieval Must Return Context, Not Just Matches

When ChromaDB returns a matching chunk, the retriever must also be able to fetch:

- previous chunk
- next chunk
- parent event
- parent chapter
- related entities
- repeated concept occurrences

This is the base requirement for questions from any timeline.

### 5.5 Future Advanced Features Must Plug Into Interfaces

Do not hard-code future features directly into the pipeline.

Create interfaces for:

- memory recovery
- planner agent
- evidence verifier
- temporal reasoner
- confidence evaluator
- clip VLM analyzer
- semantic event segmenter

The first version of these interfaces can return placeholder results. The
important thing is that the project shape is ready.

## 6. Canonical IDs

Use stable IDs everywhere.

```text
video_id:    video_20260721_000001
chunk_id:    video_20260721_000001_chunk_000042
event_id:    video_20260721_000001_event_000010
chapter_id:  video_20260721_000001_chapter_000003
entity_id:   video_20260721_000001_entity_blue_graph
memory_id:   video_20260721_000001_memory_000012
```

Do not use Python `id()` or random IDs for deterministic artifacts.

## 7. Required Data Contracts

### 7.1 Media Manifest

File:

```text
data/processed/manifests/{video_id}.json
```

Purpose:

The manifest is the source of truth for one video.

Example:

```json
{
  "video_id": "video_20260721_000001",
  "original_filename": "lecture.mp4",
  "video_path": "data/uploads/video_20260721_000001.mp4",
  "duration_seconds": 10800.0,
  "fps": 30.0,
  "width": 1920,
  "height": 1080,
  "codec": "h264",
  "audio_path": "data/processed/audio/video_20260721_000001.wav",
  "created_at": "2026-07-21T00:00:00Z",
  "pipeline_version": "base-v1"
}
```

### 7.2 Transcript Contract

File:

```text
data/processed/transcripts/{video_id}.json
```

Required fields:

```json
{
  "video_id": "video_20260721_000001",
  "language": "en",
  "segments": [
    {
      "segment_id": "seg_000001",
      "start_seconds": 10.2,
      "end_seconds": 18.4,
      "text": "Today we compare cats and dogs using a graph.",
      "confidence": 0.91,
      "speaker": "speaker_1"
    }
  ],
  "words": [
    {
      "word_id": "word_000001",
      "text": "compare",
      "start_seconds": 12.1,
      "end_seconds": 12.5,
      "confidence": 0.88,
      "speaker": "speaker_1"
    }
  ]
}
```

### 7.3 Atomic Chunk Contract

File:

```text
data/processed/chunks/{video_id}.json
```

Example:

```json
{
  "video_id": "video_20260721_000001",
  "chunk_id": "video_20260721_000001_chunk_000042",
  "chunk_type": "atomic",
  "start_seconds": 245.0,
  "end_seconds": 260.0,
  "duration_seconds": 15.0,
  "previous_chunk_id": "video_20260721_000001_chunk_000041",
  "next_chunk_id": "video_20260721_000001_chunk_000043",
  "transcript_text": "The presenter compares cats and dogs with a blue graph.",
  "word_ids": ["word_000931", "word_000932"],
  "frame_ids": ["frame_000101", "frame_000102"],
  "clip_id": "clip_000042",
  "event_id": null,
  "chapter_id": null,
  "retrieval_text": "Audio: The presenter compares cats and dogs. Visual: blue graph.",
  "confidence": {
    "transcript": 0.88,
    "visual": null,
    "alignment": 0.9
  }
}
```

### 7.4 Visual Evidence Contract

File:

```text
data/processed/frames/{video_id}.json
data/processed/clips/{video_id}.json
```

Base frame record:

```json
{
  "frame_id": "frame_000101",
  "video_id": "video_20260721_000001",
  "chunk_id": "video_20260721_000001_chunk_000042",
  "timestamp_seconds": 251.0,
  "frame_path": "data/processed/frames/video_20260721_000001/frame_000101.jpg",
  "sampling_reason": "chunk_midpoint"
}
```

Base clip record:

```json
{
  "clip_id": "clip_000042",
  "video_id": "video_20260721_000001",
  "chunk_id": "video_20260721_000001_chunk_000042",
  "start_seconds": 245.0,
  "end_seconds": 260.0,
  "clip_path": "data/processed/clips/video_20260721_000001/clip_000042.mp4"
}
```

Future VLM output should attach to this contract:

```json
{
  "chunk_id": "video_20260721_000001_chunk_000042",
  "objects": ["blue graph", "slide", "presenter"],
  "actions": ["draws graph", "points to axis"],
  "interactions": ["presenter explains graph"],
  "motion_summary": "The presenter draws a blue curve and points at the labels.",
  "ocr_text": "Cats vs Dogs",
  "visual_summary": "A blue graph is used to compare cats and dogs.",
  "visual_confidence": 0.82
}
```

### 7.5 Event Contract

Events group chunks by meaning.

File:

```text
data/processed/events/{video_id}.json
```

Example:

```json
{
  "event_id": "video_20260721_000001_event_000010",
  "video_id": "video_20260721_000001",
  "start_seconds": 240.0,
  "end_seconds": 310.0,
  "child_chunk_ids": [
    "video_20260721_000001_chunk_000040",
    "video_20260721_000001_chunk_000041",
    "video_20260721_000001_chunk_000042"
  ],
  "event_summary": "The lecturer compares cats and dogs using a blue graph.",
  "key_entities": ["cats", "dogs", "blue graph"],
  "key_actions": ["compares examples", "draws graph"],
  "previous_event_id": "video_20260721_000001_event_000009",
  "next_event_id": "video_20260721_000001_event_000011",
  "chapter_id": null
}
```

### 7.6 Chapter Contract

Chapters group events into larger teaching units.

File:

```text
data/processed/chapters/{video_id}.json
```

Example:

```json
{
  "chapter_id": "video_20260721_000001_chapter_000003",
  "video_id": "video_20260721_000001",
  "start_seconds": 180.0,
  "end_seconds": 600.0,
  "event_ids": [
    "video_20260721_000001_event_000008",
    "video_20260721_000001_event_000009",
    "video_20260721_000001_event_000010"
  ],
  "chapter_title": "Feature comparison examples",
  "chapter_summary": "This section introduces feature comparisons using simple examples.",
  "recurring_entities": ["cats", "dogs", "feature table", "blue graph"]
}
```

## 8. ChromaDB Base Design

The base should use multiple Chroma collections. Do not put everything into one
collection.

### 8.1 Collection: `video_chunks_text`

Purpose:

- transcript search
- topic search
- concept search

Document:

```text
transcript_text + event summary + OCR + key concepts
```

Metadata:

```json
{
  "video_id": "video_20260721_000001",
  "chunk_id": "video_20260721_000001_chunk_000042",
  "chunk_type": "atomic",
  "start_seconds": 245.0,
  "end_seconds": 260.0,
  "event_id": "video_20260721_000001_event_000010",
  "chapter_id": "video_20260721_000001_chapter_000003",
  "source": "transcript"
}
```

### 8.2 Collection: `video_chunks_visual`

Purpose:

- vague visual memory search
- object search
- action search
- OCR search

Document:

```text
objects + actions + visual_summary + motion_summary + OCR
```

Metadata:

```json
{
  "video_id": "video_20260721_000001",
  "chunk_id": "video_20260721_000001_chunk_000042",
  "start_seconds": 245.0,
  "end_seconds": 260.0,
  "clip_id": "clip_000042",
  "frame_ids": "frame_000101,frame_000102",
  "source": "vision"
}
```

### 8.3 Collection: `video_chunks_audio`

Purpose:

- phrase retrieval
- speaker-aware search
- exact spoken content search

Document:

```text
full transcript chunk + nearby transcript context
```

Metadata:

```json
{
  "video_id": "video_20260721_000001",
  "chunk_id": "video_20260721_000001_chunk_000042",
  "start_seconds": 245.0,
  "end_seconds": 260.0,
  "speaker": "speaker_1",
  "asr_confidence": 0.88,
  "source": "audio"
}
```

### 8.4 Collection: `video_events`

Purpose:

- event-level retrieval
- timeline-level answers
- parent context for chunks

Document:

```text
event_summary + child chunk summaries + key entities + key actions
```

Metadata:

```json
{
  "video_id": "video_20260721_000001",
  "event_id": "video_20260721_000001_event_000010",
  "start_seconds": 240.0,
  "end_seconds": 310.0,
  "chapter_id": "video_20260721_000001_chapter_000003",
  "source": "event"
}
```

### 8.5 Collection: `video_entities`

Purpose:

- connect distant timelines
- find repeated concepts
- support Memory Recovery AI later

Document:

```text
entity name + aliases + descriptions + related events
```

Metadata:

```json
{
  "video_id": "video_20260721_000001",
  "entity_id": "video_20260721_000001_entity_blue_graph",
  "entity_name": "blue graph",
  "first_seen_seconds": 245.0,
  "last_seen_seconds": 610.0,
  "chunk_ids": "chunk_000042,chunk_000090",
  "source": "entity"
}
```

### 8.6 Collection: `video_world_memory`

Purpose:

- future long-range reasoning
- concept evolution
- repeated idea tracking

This collection can start as a placeholder in the base.

Document:

```text
chapter memory + entity evolution + related timestamps
```

Metadata:

```json
{
  "video_id": "video_20260721_000001",
  "memory_id": "video_20260721_000001_memory_000001",
  "start_seconds": 180.0,
  "end_seconds": 900.0,
  "source": "world_memory"
}
```

## 9. Base Retrieval Requirements

Before implementing agents, create simple retrieval interfaces that already
return the right shape.

Base retrieval result:

```json
{
  "query": "blue graph",
  "video_id": "video_20260721_000001",
  "matches": [
    {
      "match_type": "chunk",
      "chunk_id": "video_20260721_000001_chunk_000042",
      "start_seconds": 245.0,
      "end_seconds": 260.0,
      "score": 0.84,
      "source_collection": "video_chunks_visual",
      "evidence": {
        "transcript": "The presenter compares cats and dogs...",
        "visual_summary": "A blue graph is drawn on a slide.",
        "ocr_text": "Cats vs Dogs"
      },
      "neighbors": {
        "previous_chunk_id": "video_20260721_000001_chunk_000041",
        "next_chunk_id": "video_20260721_000001_chunk_000043",
        "event_id": "video_20260721_000001_event_000010",
        "chapter_id": "video_20260721_000001_chapter_000003"
      }
    }
  ]
}
```

This shape enables later Planner, Evidence Verifier, Temporal Reasoner, and
Memory Recovery AI.

## 10. Future Feature Readiness

### 10.1 Memory Recovery AI Readiness

Do not implement full Memory Recovery AI yet.

Base requirements:

- visual chunks are indexed
- entities are extracted or at least reserved
- events connect neighboring chunks
- retriever can search visual and text collections
- retriever can fetch before and after context

When the user later asks:

```text
"I remember he drew a blue graph but forgot why."
```

The future Memory Recovery AI can:

1. extract vague clues: `blue graph`, `drew`
2. search `video_chunks_visual`
3. expand query to `chart`, `plot`, `curve`, `diagram`
4. fetch transcript around top visual matches
5. fetch parent event
6. answer with likely timestamp and confidence

The base must make those steps possible.

### 10.2 Agentic Video Understanding Readiness

Do not implement full agents yet.

Create interfaces only:

```text
PlannerInput -> PlannerOutput
RetrieverInput -> RetrievalResult
VerifierInput -> VerifierOutput
TemporalReasonerInput -> TimelineContext
AnswerGeneratorInput -> Answer
ConfidenceInput -> ConfidenceReport
```

Agents should later plug into these interfaces.

### 10.3 Clip VLM Readiness

Do not integrate Qwen2.5-VL, Video-LLaMA, or LLaVA-Video yet.

Base requirements:

- create short clips per chunk
- store `clip_path`
- store `clip_id`
- define visual analysis output schema

The first version can use frame captions as fallback, but the data model must
support clip-level VLM output later.

### 10.4 Video World Model Readiness

Do not implement a neural world model yet.

Base requirements:

- store entities
- store actions
- store interactions
- store temporal evolution fields
- store cross-event links

The first base can populate these fields with simple extraction or empty arrays.
The important part is that the schema exists.

### 10.5 Event Segmentation Transformer Readiness

Do not train or integrate a transformer yet.

Base requirements:

- event builder should have a replaceable boundary detector interface
- current detector can be heuristic
- future transformer should return the same event contract

Interface:

```text
BoundaryDetector.detect(video_id, chunks) -> list[event_boundaries]
```

This allows a transformer to replace heuristic segmentation later.

## 11. Team Roles

Assume a two-person team:

```text
Developer A: backend pipeline, chunking, storage, indexing
Developer B: API, frontend, agents, evaluation
```

### Developer A Owns

```text
schemas/
src/pipeline/
src/indexing/
src/retrieval/base_retriever.py
src/retrieval/timeline_context.py
data contract docs
```

### Developer B Owns

```text
api.py
src/models/api_models.py
src/agents/
src/retrieval/memory_recovery_interface.py
web/
tests/
eval/
```

### Shared Files

```text
README.md
docs/
requirement.txt
.gitignore
```

Shared file rule:

Only one developer edits a shared file at a time. Announce before editing it.

## 12. Phase Plan

### Phase 0: Stabilize Current Runtime

Owner: Developer A

Goal:

Make the current project runnable and predictable.

Tasks:

- use `google-genai`
- remove old Gemini package dependency
- use one backend port
- add `.env.example`
- document port conflict fix
- verify backend startup
- verify frontend build

Developer B should:

- pull after Phase 0 is merged
- update frontend API base usage if needed
- avoid modifying backend pipeline files during this phase

Branch:

```text
fix/runtime-stability
```

Push:

```powershell
git checkout -b fix/runtime-stability
git add api.py requirement.txt src/phase2_visual.py src/phase4_rag.py web/src/app/chat/page.tsx web/src/app/upload/page.tsx .env.example
git commit -m "Stabilize Gemini SDK and local backend port"
git push -u origin fix/runtime-stability
```

### Phase 1: Schemas And Contracts

Owner: Developer A

Goal:

Create stable schemas before building code.

Tasks:

- create `schemas/media_manifest.schema.json`
- create `schemas/transcript.schema.json`
- create `schemas/chunk.schema.json`
- create `schemas/event.schema.json`
- create `schemas/chapter.schema.json`
- create `schemas/retrieval_result.schema.json`
- document Chroma metadata fields

Developer B should:

- wait for Phase 1 merge before building API response models
- review schemas for frontend needs

Branch:

```text
backend/phase-1-schemas
```

Push:

```powershell
git checkout -b backend/phase-1-schemas
git add schemas docs
git commit -m "Define video memory schemas"
git push -u origin backend/phase-1-schemas
```

After merge, both developers:

```powershell
git checkout main
git pull origin main
```

### Phase 2: Media Manifest And Ingestion

Owner: Developer A

Goal:

Every uploaded video gets a stable identity and manifest.

Tasks:

- create `src/pipeline/ingest.py`
- create `src/pipeline/media_manifest.py`
- assign stable `video_id`
- validate video path
- inspect duration, fps, resolution, codec
- write manifest JSON

Developer B should:

- build UI only against manifest fields from schema
- avoid changing ingestion code

Branch:

```text
backend/phase-2-ingestion
```

### Phase 3: Audio And Transcript Base

Owner: Developer A

Goal:

Create voice/audio foundation.

Tasks:

- extract full audio
- run Faster-Whisper
- write segment timestamps
- write word timestamps if available
- store ASR confidence
- map transcript to `video_id`

Output:

```text
data/processed/audio/{video_id}.wav
data/processed/transcripts/{video_id}.json
```

Developer B should:

- create transcript display components only after transcript schema is merged
- not change ASR pipeline files

Branch:

```text
backend/phase-3-audio-transcript
```

### Phase 4: Atomic Timeline Chunker

Owner: Developer A

Goal:

Build reliable chunk coverage for the whole video.

Tasks:

- create fixed overlapping chunks
- align transcript words into chunks
- add previous/next chunk IDs
- write chunk JSON
- guarantee no timeline gaps
- add chunking report

Output:

```text
data/processed/chunks/{video_id}.json
data/processed/indexing_reports/{video_id}_chunk_report.json
```

Done when:

- first chunk starts near 0
- last chunk reaches video duration
- every chunk has start/end seconds
- every chunk has previous/next links
- transcript text is attached when available

Branch:

```text
backend/phase-4-atomic-chunking
```

### Phase 5: Frame And Clip Artifact Base

Owner: Developer A

Goal:

Prepare for clip VLMs without integrating them yet.

Tasks:

- sample frames per chunk
- create short clip per chunk
- write frame manifest
- write clip manifest
- attach frame IDs and clip IDs to chunks

Output:

```text
data/processed/frames/{video_id}/
data/processed/clips/{video_id}/
data/processed/frames/{video_id}.json
data/processed/clips/{video_id}.json
```

Branch:

```text
backend/phase-5-visual-artifacts
```

### Phase 6: Event And Chapter Containers

Owner: Developer A

Goal:

Create semantic containers before advanced segmentation.

Tasks:

- group chunks into simple events
- add event IDs to chunks
- create chapter containers
- add previous/next event links
- make boundary detector replaceable

Base boundary method:

- transcript topic shift
- visual scene cut hints
- long pause
- OCR title change when available

Future boundary method:

- Event Segmentation Transformer

Branch:

```text
backend/phase-6-event-containers
```

### Phase 7: ChromaDB Multi-Collection Index

Owner: Developer A

Goal:

Create future-ready vector storage.

Tasks:

- create `src/indexing/collection_names.py`
- create `src/indexing/chroma_store.py`
- create `src/indexing/index_pipeline.py`
- upsert text chunks
- upsert visual chunks
- upsert audio chunks
- upsert events
- reserve entity and world memory collections
- make indexing idempotent

Collections:

```text
video_chunks_text
video_chunks_visual
video_chunks_audio
video_events
video_entities
video_world_memory
```

Done when:

- each collection can be created
- reindexing does not duplicate rows
- collection counts can be printed
- chunk IDs match metadata

Branch:

```text
backend/phase-7-chroma-index
```

### Phase 8: Retrieval Interface

Owner: Developer A

Goal:

Create retrieval output shape that agents can use later.

Tasks:

- implement base hybrid search interface
- retrieve from multiple collections
- fetch previous/next chunks
- fetch parent event
- return evidence fields

Do not implement full agentic reasoning yet.

Branch:

```text
backend/phase-8-retrieval-interface
```

### Phase 9: API Contract

Owner: Developer B

Goal:

Expose the new base pipeline safely to frontend.

Tasks:

- define API request/response models
- add video status endpoint
- add timeline endpoint
- add retrieval endpoint
- keep old `/ask` route working until replacement is stable

Suggested endpoints:

```text
POST /videos/upload
GET  /videos/{video_id}/status
GET  /videos/{video_id}/timeline
POST /videos/{video_id}/retrieve
POST /videos/{video_id}/ask
```

Branch:

```text
api/phase-9-contracts
```

Developer B must pull after Developer A merges Phase 7 and Phase 8:

```powershell
git checkout main
git pull origin main
git checkout -b api/phase-9-contracts
```

### Phase 10: Frontend Base

Owner: Developer B

Goal:

Make frontend work with stable backend contracts.

Tasks:

- upload page
- processing status
- video player
- timeline view
- basic chat
- source citations
- evidence panel placeholder

Do not implement full Memory Recovery UI yet.

Branch:

```text
frontend/phase-10-base-ui
```

### Phase 11: Agent Interface Skeletons

Owner: Developer B

Goal:

Prepare for agentic video understanding.

Tasks:

- create agent input/output models
- create placeholder Planner Agent
- create placeholder Evidence Verifier
- create placeholder Temporal Reasoner
- create placeholder Confidence Evaluator
- return trace object

No complex LLM agent logic yet.

Branch:

```text
agent/phase-11-interfaces
```

### Phase 12: Evaluation Base

Owner: Developer B

Goal:

Create test data before advanced features.

Tasks:

- create small QA set
- create timestamp QA set
- create vague memory QA set
- create expected retrieval timestamp ranges
- create evaluation script

Output:

```text
eval/questions.json
eval/expected_answers.json
tests/test_chunk_coverage.py
tests/test_chroma_counts.py
tests/test_retrieval_shape.py
```

Branch:

```text
eval/phase-12-base-evaluation
```

## 13. Pull And Push Rules

### 13.1 Golden Rule

Never work on stale `main`.

Before starting work:

```powershell
git checkout main
git pull origin main
```

Then create your branch:

```powershell
git checkout -b backend/phase-4-atomic-chunking
```

### 13.2 Who Pushes What

Developer A pushes:

```text
backend/*
fix/runtime-stability
```

Developer B pushes:

```text
api/*
frontend/*
agent/*
eval/*
```

Both push to:

```text
origin/<your-branch-name>
```

Do not push directly to:

```text
origin/main
```

### 13.3 Who Pulls From Whom

Normal workflow:

- Do not pull directly from teammate local machines.
- Do not build long-term work from teammate feature branches.
- Pull from `origin/main` after a teammate's pull request is merged.

Correct:

```powershell
git checkout main
git pull origin main
```

Only pull a teammate branch when reviewing or testing their work:

```powershell
git fetch origin
git checkout backend/phase-4-atomic-chunking
```

After review, return to main:

```powershell
git checkout main
git pull origin main
```

### 13.4 When Developer B Must Pull

Developer B must pull after these Developer A phases merge:

- Phase 1 schemas
- Phase 4 chunking
- Phase 7 ChromaDB indexing
- Phase 8 retrieval interface

Reason:

Frontend, API, and agent work must depend on real contracts, not guessed fields.

### 13.5 When Developer A Must Pull

Developer A must pull after these Developer B phases merge:

- Phase 9 API contracts
- Phase 11 agent interfaces
- Phase 12 evaluation base

Reason:

Backend pipeline and indexing should produce fields required by API, agents, and
evaluation.

## 14. Merge Conflict Prevention

### Developer A Should Avoid Editing

```text
web/
src/agents/
api.py except agreed API changes
```

### Developer B Should Avoid Editing

```text
src/pipeline/
src/indexing/
schemas/ unless agreed
```

### Shared Files Require Coordination

```text
README.md
docs/*.md
requirement.txt
.gitignore
```

Before editing shared files:

1. Tell teammate.
2. Pull latest main.
3. Make small edit.
4. Push quickly.

### Good Commit Examples

```text
Define chunk schema
Add media manifest writer
Implement atomic chunk coverage report
Add Chroma collection names
Create retrieval result model
```

### Bad Commit Examples

```text
Update files
Final changes
Backend stuff
Fix all
```

## 15. Recommended Branch Sequence

Use this order:

```text
fix/runtime-stability
backend/phase-1-schemas
backend/phase-2-ingestion
backend/phase-3-audio-transcript
backend/phase-4-atomic-chunking
backend/phase-5-visual-artifacts
backend/phase-6-event-containers
backend/phase-7-chroma-index
backend/phase-8-retrieval-interface
api/phase-9-contracts
frontend/phase-10-base-ui
agent/phase-11-interfaces
eval/phase-12-base-evaluation
```

Do not start Phase 10 UI before Phase 9 API contracts exist.

Do not start Memory Recovery AI before:

- visual chunks exist
- event containers exist
- Chroma multi-index exists
- retrieval interface returns neighboring context

Do not start Event Segmentation Transformer before:

- event contract exists
- boundary detector interface exists
- chunk coverage is reliable

## 16. Definition Of Done For The Base

The base is complete when:

- one uploaded video gets a stable `video_id`
- media manifest is written
- audio is extracted
- transcript has timestamps
- atomic chunks cover the full video
- chunks have overlap
- chunks link to previous and next chunks
- frames are sampled per chunk
- clips are created or at least reserved per chunk
- events group chunks
- chapters group events
- ChromaDB has multiple collections
- vector records include stable metadata
- reindexing is idempotent
- retrieval returns evidence plus neighboring context
- API returns stable JSON
- frontend uses one backend base URL
- agent interfaces exist as placeholders
- evaluation base exists

Only after this definition of done should the team implement:

- Memory Recovery AI
- Planner Agent
- Evidence Verifier
- Temporal Reasoner
- Confidence Evaluator
- Qwen2.5-VL or another clip VLM
- Video World Model
- Event Segmentation Transformer

## 17. First Implementation Step After This Document

Start with Phase 1.

Developer A:

```powershell
git checkout main
git pull origin main
git checkout -b backend/phase-1-schemas
```

Create:

```text
schemas/media_manifest.schema.json
schemas/transcript.schema.json
schemas/chunk.schema.json
schemas/event.schema.json
schemas/chapter.schema.json
schemas/retrieval_result.schema.json
```

Developer B:

```powershell
git checkout main
git pull origin main
```

Then wait for Phase 1 schema merge before building API/frontend against the new
base.

This keeps the project clean and prevents both developers from guessing
different data shapes.

