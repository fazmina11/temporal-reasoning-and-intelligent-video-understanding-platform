# VideoSceneRAG Advanced Roadmap

VideoSceneRAG is a multimodal video understanding system. The current project
already has a working prototype: video upload, scene extraction, transcription,
Gemini-based visual enrichment, ChromaDB indexing, FastAPI endpoints, and a
Next.js chat UI.

This README defines the target base architecture for turning the prototype into
an advanced, industry-style video RAG system where a user can ask questions from
any timeline, refer to vague memories, compare distant moments, and receive
grounded answers with temporal evidence.

The project should evolve from "scene captions in a vector DB" into a
hierarchical video memory system:

```text
Video
  -> Audio track, frames, clips, OCR, motion, transcript
  -> Atomic chunks
  -> Semantic events
  -> Chapters
  -> Entity/action/world memory
  -> Multi-index ChromaDB collections
  -> Agentic retrieval and temporal reasoning
  -> Grounded answer with citations and confidence
```

## Current Runtime Fixes

### 1. Deprecated Gemini package warning

The old package:

```text
google.generativeai
```

is deprecated. The project should use:

```text
google-genai
```

Install dependencies:

```powershell
pip install -r requirement.txt
```

The main RAG engine now uses the supported SDK import style:

```python
from google import genai
```

Required environment variables:

```env
GEMINI_API_KEY=your_new_key_here
GEMINI_MODEL=gemini-3-flash-preview
```

If your API key was reported as leaked, generate a new Gemini API key and replace
the old value in `.env`.

### Implemented chunking foundation

Phases C0/C1 and C3-C5 are now implemented. Each upload has a mature manifest,
integer-millisecond timeline, merged multimodal boundary candidates, canonical
non-overlapping atomic spans, and a fail-closed validation report.

Run the chunking foundation for an existing manifest:

```powershell
python -m src.pipeline.chunking_foundation --video-id <video_id>
```

Run transcript attachment, visual artifacts, atom clips, semantic chunks, and
chunk validation after C3-C5:

```powershell
python -m src.pipeline.evidence_foundation --video-id <video_id>
```

Run event building and hierarchy-native Chroma indexing:

```powershell
python -m src.pipeline.hierarchy_indexing --video-id <video_id>
```

Verify the full base hierarchy after indexing:

```powershell
python -m src.pipeline.hierarchy_validation --video-id <video_id>
```

Hierarchy retrieval uses Hugging Face SentenceTransformer embeddings through
ChromaDB. The default model is:

```text
BAAI/bge-base-en-v1.5
```

Override it with:

```powershell
$env:HIERARCHY_EMBED_MODEL="BAAI/bge-base-en-v1.5"
```

Implementation details, schemas, defaults, API routes, and verification commands
are documented in:

```text
docs/PHASE_C0_C1_MANIFEST_AND_TIMELINE.md
docs/PHASE_C3_C5_BOUNDARIES_AND_ATOMS.md
docs/PHASE_C6_AUDIO_AND_FRAME_EVIDENCE.md
docs/PHASE_C6_C9_EVIDENCE_AND_SEMANTIC_CHUNKS.md
docs/PHASE_C10_C12_EVENTS_INDEXING_RETRIEVAL.md
docs/PHASE_C13_C25_PRODUCTION_AGENTIC_RETRIEVAL_AND_ANSWER_QUALITY.md
```

Frame evidence defaults to a 2-second timeline interval, with an atom-midpoint
fallback only when a custom interval would otherwise leave an atom uncovered.
This gives every atom clear visual evidence without exporting tens of thousands
of near-duplicate source frames. Full archival extraction remains
available with:

```powershell
python -m src.pipeline.frame_extraction --video-id <video_id> --all-frames
```

### 2. Port already in use: WinError 10048

This error means another process is already using the port:

```text
Only one usage of each socket address is normally permitted
```

Check the port:

```powershell
netstat -ano | findstr :8001
```

Stop the process:

```powershell
taskkill /PID <PID_FROM_NETSTAT> /F
```

The frontend should use one backend port. Default local backend:

```text
http://localhost:8001
```

Optional frontend override:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
```

## How To Run Locally

Open Terminal 1 for the backend:

```powershell
cd "C:\SideQuest\CN Project\RAG-Enhanced-Video-Scene-Understanding"
$env:PYTHONUTF8="1"
$env:TRANSFORMERS_NO_TF="1"
$env:USE_TF="0"
$env:PORT="8001"
python -m uvicorn api:app --host 127.0.0.1 --port 8001
```

Open Terminal 2 for the frontend:

```powershell
cd "C:\SideQuest\CN Project\RAG-Enhanced-Video-Scene-Understanding\web"
npm.cmd install
npm.cmd run dev -- -p 3000
```

Open the app:

```text
http://127.0.0.1:3000/RAG-Enhanced-Video-Scene-Understanding
```

CLI mode:

```powershell
cd "C:\SideQuest\CN Project\RAG-Enhanced-Video-Scene-Understanding"
$env:PYTHONUTF8="1"
$env:TRANSFORMERS_NO_TF="1"
$env:USE_TF="0"
python src\main.py
```

## Why The Current Chunking Is Not Enough

The current system mostly uses detected scenes and selected center frames. This
is useful for a prototype, but it is weak for serious video understanding.

Main limitations:

- Visual cut detection does not equal semantic event segmentation.
- One frame cannot represent motion, actions, gestures, or temporal change.
- Transcript and visual content are not always aligned at word-level precision.
- ChromaDB stores only simple scene records instead of hierarchical memory.
- Retrieval is mostly one-pass instead of planner-driven and evidence verified.
- Vague memory queries are hard because the user may not know the timestamp,
  topic, slide number, or exact words.

The advanced system must support questions like:

```text
"I remember he drew a blue graph but forgot why."
"He compared cats and dogs. Where was that?"
"What changed between the first architecture diagram and the final one?"
"What did he say after explaining the loss curve?"
"Summarize all moments where he talks about attention, even if he uses different wording."
```

## Target Product Vision

The final system should act like a memory recovery and video reasoning assistant.

User input can be:

- exact timestamp
- topic name
- vague memory
- object description
- visual clue
- spoken phrase
- event sequence
- comparison request
- follow-up question

The system should respond with:

- answer
- exact or approximate timestamp range
- supporting clips/scenes
- citations
- confidence score
- reasoning trace from the agents
- warning if evidence is weak

## Target Architecture

```text
Upload Video
  |
  v
Media Ingestion
  - validate video
  - normalize codec
  - extract audio
  - create media manifest
  |
  v
Multimodal Chunking
  - scored multimodal boundary candidates
  - canonical non-overlapping atomic spans
  - semantic events and chapters
  - dynamic context expansion during retrieval
  |
  v
Multimodal Understanding
  - ASR transcript
  - OCR
  - keyframes
  - short clip VLM analysis
  - objects/actions/interactions
  - visual changes over time
  |
  v
World Memory Construction
  - entities
  - actions
  - relationships
  - temporal links
  - chapter summaries
  |
  v
Vector and Metadata Storage
  - ChromaDB dense indexes
  - sparse text index
  - entity/action index
  - timeline graph metadata
  |
  v
Agentic Query Pipeline
  - Planner Agent
  - Retriever Agent
  - Evidence Verifier
  - Temporal Reasoner
  - Answer Generator
  - Confidence Evaluator
  |
  v
Grounded Answer
```

## Data Storage Philosophy

Do not store only captions. Store a structured memory of the video.

Every chunk must have:

- identity
- parent video
- time range
- transcript words
- visual observations
- OCR text
- objects
- actions
- entities
- relationships
- previous/next links
- parent chapter
- source artifacts
- embeddings
- confidence

The project should separate raw artifacts from derived indexes:

```text
data/
  input_videos/
  uploads/
  processed/
    audio/
    frames/
    clips/
    transcripts/
    ocr/
    chunks/
    events/
    chapters/
    world_memory/
  logs/

chroma_db/
  persistent vector database

schemas/
  chunk.schema.json
  event.schema.json
  chapter.schema.json
  world_memory.schema.json
```

## Canonical Chunk Schema

Every chunk should eventually look like this:

```json
{
  "video_id": "video_001",
  "chunk_id": "video_001_chunk_000042",
  "chunk_type": "atomic | event | chapter",
  "parent_id": "video_001_event_000010",
  "start_seconds": 245.2,
  "end_seconds": 259.8,
  "duration_seconds": 14.6,
  "source": {
    "video_path": "data/uploads/video_001.mp4",
    "audio_path": "data/processed/audio/video_001.wav",
    "clip_path": "data/processed/clips/video_001_chunk_000042.mp4",
    "frame_paths": [
      "data/processed/frames/video_001_chunk_000042_kf_001.jpg"
    ]
  },
  "audio": {
    "transcript": "The model compares cats and dogs using a simple feature table.",
    "words": [
      {"text": "model", "start": 246.1, "end": 246.5, "confidence": 0.91}
    ],
    "speaker": "speaker_1",
    "asr_confidence": 0.88
  },
  "vision": {
    "ocr_text": "Cats vs Dogs",
    "objects": ["blue graph", "table", "slide"],
    "actions": ["draws a graph", "points to comparison"],
    "scene_description": "A slide compares cats and dogs with a blue graph on the right.",
    "motion_summary": "The presenter highlights the graph, then switches to a table."
  },
  "world_memory": {
    "entities": ["cats", "dogs", "blue graph"],
    "concepts": ["classification", "feature comparison"],
    "relations": [
      {"subject": "cats", "relation": "compared_with", "object": "dogs"}
    ],
    "event_summary": "The lecturer uses cats and dogs to explain feature-based comparison."
  },
  "retrieval_text": "Visual: blue graph, cats vs dogs slide. Audio: feature comparison...",
  "confidence": {
    "asr": 0.88,
    "vision": 0.82,
    "alignment": 0.79
  }
}
```

## ChromaDB Collection Design

Use multiple collections instead of one overloaded collection.

### 1. `video_chunks_text`

Purpose:

- semantic transcript search
- topic search
- concept search

Document text:

```text
transcript + summary + concepts + OCR
```

Metadata:

- video_id
- chunk_id
- chunk_type
- start_seconds
- end_seconds
- parent_event_id
- chapter_id
- speaker
- confidence

### 2. `video_chunks_vision`

Purpose:

- visual memory retrieval
- "blue graph", "whiteboard", "diagram", "cat/dog table"

Document text:

```text
clip VLM summary + objects + actions + OCR + visual changes
```

Metadata:

- video_id
- chunk_id
- frame_paths
- clip_path
- visual_confidence
- objects
- actions
- diagram_type

### 3. `video_chunks_audio`

Purpose:

- spoken phrase search
- speaker-aware retrieval
- timeline grounding from transcript

Document text:

```text
word-level transcript + speaker + nearby transcript context
```

Metadata:

- video_id
- chunk_id
- start_seconds
- end_seconds
- word_count
- asr_confidence
- speaker

### 4. `video_entities`

Purpose:

- cross-timeline memory
- entity recurrence
- vague memory resolution

Document text:

```text
entity name + aliases + related events + descriptions
```

Metadata:

- video_id
- entity_id
- entity_type
- first_seen_seconds
- last_seen_seconds
- chunk_ids
- aliases

### 5. `video_events`

Purpose:

- semantic event retrieval
- chapter-level answers
- timeline reasoning

Document text:

```text
event summary + causal links + participating entities + transcript summary
```

Metadata:

- video_id
- event_id
- start_seconds
- end_seconds
- child_chunk_ids
- previous_event_id
- next_event_id

### 6. `video_world_memory`

Purpose:

- higher-level reasoning across the whole video
- "how did the explanation evolve?"
- "where does he return to the same idea?"

Document text:

```text
chapter memory + recurring ideas + temporal evolution + relations
```

Metadata:

- video_id
- memory_id
- chapter_ids
- entity_ids
- timeline_ranges

## Advanced Chunking Strategy

The final system should use hierarchical chunking:

### Level 1: Atomic windows

Small canonical, non-overlapping spans used as precise evidence anchors.

Recommended:

- 3 second minimum
- 8 second target
- 15 second maximum, with a 20 second hard maximum
- align boundaries to transcript, pause, scene, and visual evidence

Example:

```text
atom_000001: 00:00.000-00:07.200
atom_000002: 00:07.200-00:14.800
atom_000003: 00:14.800-00:23.100
```

Why:

- supports exact timestamp answers
- prevents duplicate evidence and unstable citations
- works even when scene detection fails
- allows neighboring context to be assembled dynamically for each query

### Level 2: Semantic events

Events group atomic chunks by meaning.

Signals:

- topic shift in transcript
- slide/visual change
- speaker transition
- object/action change
- VLM-detected activity change
- embedding distance spike

Example:

```text
event_010: 02:41:08-02:43:22
summary: "Cats vs dogs comparison using blue graph and feature table."
children: chunk_122, chunk_123, chunk_124
```

### Level 3: Chapters

Chapters group events into larger explanation units.

Recommended:

- 2 to 8 minutes per chapter
- generated after all events are known
- includes recurring entities and key ideas

### Level 4: World memory

World memory connects repeated ideas across distant parts of the video.

Example:

```text
blue graph appears at 02:41:16
same concept returns at 02:58:40
final summary appears at 03:04:12
```

## Memory Recovery AI

Memory Recovery AI handles vague user memory instead of exact search.

Example:

```text
User: I remember he drew a blue graph but forgot why.
```

Pipeline:

```text
1. Extract memory clues
   - blue graph
   - drew
   - unknown topic

2. Search visual memory
   - video_chunks_vision
   - video_entities
   - video_events

3. Expand clues
   - blue graph -> chart, plot, curve, line graph
   - drew -> sketch, annotate, highlight

4. Retrieve candidates
   - top visual chunks
   - nearby transcript chunks
   - parent events

5. Temporal reconstruction
   - what happened before
   - what happened during
   - what happened after

6. Answer with uncertainty
   - "This is likely the moment at 02:41:16..."
   - include why the system believes that
```

The answer should include:

- best timestamp
- evidence clips
- why it matched the memory
- surrounding explanation
- confidence

## Agentic Video Understanding

Do not use a single retrieval pass for complex questions.

Target agent pipeline:

```text
Question
  -> Planner Agent
  -> Query Rewriter
  -> Retriever Agent
  -> Evidence Verifier
  -> Temporal Reasoner
  -> Answer Generator
  -> Confidence Evaluator
```

### Planner Agent

Role:

- classify query type
- decide which indexes to search
- decide whether the query is vague, timestamped, visual, audio, comparative, or follow-up

Output:

```json
{
  "query_type": "memory_recovery",
  "needs": ["vision_search", "nearby_transcript", "temporal_reasoning"],
  "search_terms": ["blue graph", "drawn graph", "comparison"],
  "expected_evidence": ["clip", "ocr", "transcript"]
}
```

### Retriever Agent

Role:

- query multiple Chroma collections
- perform hybrid retrieval
- collect parent and neighboring chunks

Searches:

- text chunks
- visual chunks
- audio chunks
- events
- entities
- world memory

### Evidence Verifier

Role:

- reject weak matches
- verify that answer claims are grounded
- check retrieved timestamp range

Questions:

- Does the visual evidence match the user clue?
- Does the transcript support the explanation?
- Are there multiple candidate moments?

### Temporal Reasoner

Role:

- connect before/during/after chunks
- explain how concepts evolve
- compare distant timeline ranges

Examples:

- "The graph appears at 02:41:16, but the reason is explained from 02:40:52 to 02:42:30."
- "He returns to the same idea at 02:58:40."

### Answer Generator

Role:

- generate final answer
- cite timestamps
- include concise explanation

### Confidence Evaluator

Role:

- combine retrieval score, visual match score, audio confidence, temporal coherence, and verifier score

Output:

```json
{
  "confidence": 0.82,
  "reason": "Visual clue matched blue graph and transcript explains comparison nearby.",
  "weaknesses": ["OCR confidence was low"]
}
```

## Video-Language Model Upgrade

Current prototype uses selected frames. Advanced system should use short clips.

Frame captioning sees:

```text
one image
```

Clip VLM sees:

```text
motion, action, gesture, transition, temporal change
```

Candidate models:

- Qwen2.5-VL
- Video-LLaMA
- LLaVA-Video

Implementation rule:

- Phase 1 can keep frame captioning as fallback.
- Phase 2 must add clip-level analysis.
- Store both frame summaries and clip summaries.
- Retrieval should prefer clip summaries for action and motion queries.

## Video World Model

The project should build a lightweight world model from extracted evidence.

It does not need to be a huge neural world model at first. Start with structured
latent memory:

```json
{
  "entities": ["blue graph", "cats", "dogs"],
  "actions": ["draws graph", "compares examples"],
  "interactions": ["cats compared with dogs"],
  "temporal_evolution": [
    "introduces comparison",
    "draws graph",
    "explains why graph matters",
    "returns to concept later"
  ]
}
```

This supports:

- vague visual memory
- long-range timeline relations
- chapter-level summaries
- event causality

## Event Segmentation Transformer

The current prototype uses visual cut detection. The advanced version should add
semantic event segmentation.

Start simple:

- transcript embedding shifts
- OCR title changes
- VLM summary shifts
- speaker pause boundaries
- visual similarity changes

Later upgrade:

- train or fine-tune a transformer boundary detector
- input: transcript tokens, frame embeddings, clip embeddings, OCR
- output: semantic event boundary probability per second

The first production-ready base does not need training. It should create the
data structure so a transformer can replace the heuristic boundary detector
without rewriting the whole project.

## Development Phases

### Phase 0: Stabilize the current project

Owner: Developer A

Tasks:

- replace deprecated Gemini SDK usage
- use one backend port
- make `.env.example`
- document port-kill commands
- confirm backend starts
- confirm frontend starts

Done when:

- no `google.generativeai` warning appears from the RAG path
- only port `8001` is required for backend
- `/docs` opens
- `/upload` and `/chat` point to the same backend

### Phase 1: Define contracts and folder structure

Owner: Developer A

Files:

```text
schemas/chunk.schema.json
schemas/event.schema.json
schemas/chapter.schema.json
schemas/world_memory.schema.json
src/contracts/
```

Tasks:

- define chunk schema
- define event schema
- define Chroma metadata schema
- define stable IDs
- define artifact paths

Developer B should not start UI assumptions until this phase is pushed and
pulled.

Push point:

```powershell
git checkout -b backend/phase-1-contracts
git add schemas src/contracts README.md
git commit -m "Define advanced video memory contracts"
git push -u origin backend/phase-1-contracts
```

After merge, Developer B pulls:

```powershell
git checkout main
git pull origin main
```

### Phase 2: Media ingestion and manifest

Owner: Developer A

Files:

```text
src/pipeline/ingest.py
src/pipeline/media_manifest.py
data/processed/manifests/
```

Tasks:

- validate uploaded video
- assign `video_id`
- normalize path handling
- extract metadata: fps, duration, resolution, codec
- create `media_manifest.json`
- extract full audio track

Done when:

- every uploaded video gets a manifest
- downstream phases never guess file paths

### Phase 3: Audio and transcript base

Owner: Developer A

Files:

```text
src/pipeline/audio.py
src/pipeline/transcription.py
data/processed/transcripts/
```

Tasks:

- run Faster-Whisper
- store word-level timestamps
- store segment-level timestamps
- preserve ASR confidence
- support transcript-only retrieval

Done when:

- transcript is searchable by time
- every word has start/end timestamp when available

### Phase 4: Atomic chunker

Owner: Developer A

Files:

```text
src/pipeline/boundary_signals.py
src/pipeline/atomic_spans.py
src/pipeline/chunking_foundation.py
data/processed/boundaries/
data/processed/atoms/
data/processed/reports/
```

Tasks:

- extract duration, sentence, pause, scene-cut, and visual-difference signals
- merge nearby evidence into scored boundary candidates
- create canonical non-overlapping atomic spans
- preserve boundary reasons and stable `atom_id` pointers
- validate exact timeline coverage before downstream indexing

Done when:

- every video has one canonical atom list
- the first atom starts at 0 and the last reaches the manifest duration
- there are no gaps or overlaps
- all previous/next pointers are valid
- the machine-readable validation report has `valid: true`

### Phase 5: Semantic event builder

Owner: Developer A

Files:

```text
src/pipeline/events.py
data/processed/events/
```

Tasks:

- group atomic chunks into events
- detect topic shifts
- detect visual/OCR shifts
- connect previous/next event links
- store parent-child relationships

Done when:

- every chunk belongs to an event
- events have start/end timestamps
- event summaries can be indexed

### Phase 6: Clip-level visual understanding

Owner: Developer A

Files:

```text
src/pipeline/clip_vlm.py
data/processed/clips/
```

Tasks:

- generate short clips per chunk
- run clip-level VLM
- extract objects, actions, interactions, OCR, visual changes
- store fallback frame captions

Done when:

- visual queries can match actions, not just static frames
- every visual output is tied to a chunk_id

### Phase 7: ChromaDB multi-index storage

Owner: Developer A

Files:

```text
src/indexing/chroma_store.py
src/indexing/embeddings.py
src/indexing/index_pipeline.py
```

Tasks:

- create collections listed above
- upsert text chunks
- upsert visual chunks
- upsert audio chunks
- upsert events
- upsert entities
- support idempotent re-indexing

Done when:

- re-running indexing does not duplicate records
- collection counts match chunk/event counts
- retrieval can return chunk, event, and neighboring context

### Phase 8: Agentic retrieval base

Owner: Developer B

Files:

```text
src/agents/planner.py
src/agents/retriever_agent.py
src/agents/evidence_verifier.py
src/agents/temporal_reasoner.py
src/agents/answer_generator.py
src/agents/confidence_evaluator.py
```

Tasks:

- create agent interfaces
- define agent input/output JSON
- make planner choose retrieval route
- make verifier reject weak evidence
- make temporal reasoner fetch before/after chunks

Done when:

- one query produces an explainable trace
- each agent output is inspectable

### Phase 9: Memory Recovery AI

Owner: Developer B

Files:

```text
src/retrieval/memory_recovery.py
src/retrieval/query_expansion.py
```

Tasks:

- detect vague memory queries
- expand visual clues
- search visual, entity, and event indexes
- retrieve surrounding transcript
- rank candidates by multimodal evidence

Done when:

- vague query returns likely moments
- answer includes why the match was selected

### Phase 10: API upgrade

Owner: Developer B

Files:

```text
api.py
src/api_models.py
```

Tasks:

- add `/videos`
- add `/videos/{video_id}/status`
- add `/videos/{video_id}/ask`
- add `/videos/{video_id}/timeline`
- add `/videos/{video_id}/evidence/{query_id}`
- stream progress events

Done when:

- frontend never directly reads backend internals
- API returns stable JSON contracts

### Phase 11: Frontend upgrade

Owner: Developer B

Files:

```text
web/src/app/*
web/src/components/*
web/src/lib/api.ts
```

Tasks:

- upload view
- processing timeline view
- video player with timestamp jumps
- chat view
- evidence panel
- confidence panel
- agent trace view

Done when:

- user can see why an answer was chosen
- citations are clickable
- vague memory answers show candidate moments

### Phase 12: Evaluation suite

Owner: Developer B

Files:

```text
tests/
eval/
```

Tasks:

- create sample videos
- create timestamp QA set
- create vague memory QA set
- create visual clue QA set
- measure retrieval recall
- measure answer grounding

Done when:

- every major retrieval change can be tested
- no phase is considered complete without eval samples

## Two-Person Team Workflow

Use this workflow to avoid merge conflicts.

### Roles

Developer A owns:

```text
src/pipeline/
src/indexing/
src/retrieval/core retrievers
schemas/
data contracts
ChromaDB storage
```

Developer B owns:

```text
api.py
src/agents/
src/retrieval/memory_recovery.py
web/
tests/
eval/
```

Shared files:

```text
README.md
requirement.txt
.gitignore
```

Rule for shared files:

- edit only when needed
- announce before editing
- pull before editing
- keep changes small

### Branch rules

Never commit directly to `main`.

Use branches:

```text
backend/phase-1-contracts
backend/phase-4-chunking
backend/phase-7-chroma-index
agent/phase-8-agentic-retrieval
frontend/phase-11-evidence-ui
eval/phase-12-memory-recovery-tests
fix/gemini-sdk-and-port
```

### Daily start

Both developers must start with:

```powershell
git checkout main
git pull origin main
```

Then create or update your branch:

```powershell
git checkout -b backend/phase-4-chunking
```

If branch already exists:

```powershell
git checkout backend/phase-4-chunking
git merge main
```

### Before pushing

Run checks:

```powershell
python -m compileall src api.py
cd web
npm.cmd run build
```

Then push:

```powershell
git add <your_files_only>
git commit -m "Implement phase 4 atomic chunking"
git push -u origin backend/phase-4-chunking
```

### Pull timing between two developers

Use this dependency order:

1. Developer A pushes and merges schema/contracts first.
2. Developer B pulls main after schema merge.
3. Developer A builds chunking and indexing.
4. Developer B builds API and UI against the merged schemas.
5. Developer A merges retrieval core.
6. Developer B pulls retrieval core before building agents.

Developer B should not build API responses from guessed fields. Wait for A to
merge schema files first.

Developer A should not edit UI files. If backend needs a UI field, update the
schema and tell B.

### Merge conflict prevention

Avoid both editing these files at the same time:

```text
README.md
requirement.txt
api.py
web/src/lib/api.ts
```

If conflict happens:

```powershell
git status
git diff
```

Resolve manually, then:

```powershell
git add <resolved_files>
git commit
```

Do not use:

```powershell
git reset --hard
```

unless both developers agree, because it can delete local work.

### Commit size rule

Good commit:

```text
Implement atomic chunk schema
```

Bad commit:

```text
Update everything
```

Each commit should represent one idea.

## Suggested Build Order For This Team

Sprint 1:

- A: Phase 0 and Phase 1
- B: frontend API cleanup and basic UI polish after pulling A's contracts

Sprint 2:

- A: Phase 2, Phase 3, Phase 4
- B: upload/status UI and eval data format

Sprint 3:

- A: Phase 5, Phase 6, Phase 7
- B: agent interfaces and API response contracts

Sprint 4:

- A: retrieval expansion and temporal neighbor retrieval
- B: Memory Recovery AI and evidence panel

Sprint 5:

- A: optimize indexing and storage
- B: evaluation suite and demo workflow

## Definition Of Done For The Advanced Base

The base is complete when:

- each uploaded video gets a `video_id`
- full audio is extracted
- transcript has timestamped words
- canonical atoms cover the full video without gaps or overlaps
- events group chunks semantically
- ChromaDB has multiple collections
- each vector record has stable metadata
- retriever can fetch neighboring chunks
- vague memory query can retrieve visual candidates
- answer includes timestamp, evidence, and confidence
- frontend uses one backend port
- README and schemas are in sync

## References

Gemini API Python examples use the supported SDK:

- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/generate-content/get-started
