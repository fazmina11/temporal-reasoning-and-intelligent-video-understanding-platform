# Next Focus And Phase Roadmap

This document defines what the project should focus on next after the current
base implementation.

The project already has the core foundation:

```text
Video
 -> Manifest
 -> Normalized timeline
 -> Transcript
 -> Boundary candidates
 -> Atomic spans
 -> Semantic chunks
 -> Events
 -> OCR, speaker, and audio-event artifacts
 -> ChromaDB indexes
 -> Agentic retrieval
 -> Grounded answer response with citations, confidence, and trace metadata
```

The next goal is to turn this working research-grade base into a stronger,
more reliable, measurable, and user-friendly Memory Recovery AI platform.

## Main Next Focus

The next focus should be:

```text
Evaluation, reliability, better evidence quality, and user-facing observability.
```

Do not immediately jump into heavier video-language models or transformer event
segmentation. Those are important, but they should come after the current system
can prove answer quality with tests, metrics, and clear debug traces.

The recommended priority order is:

1. Build a strong question-answer evaluation set.
2. Add answer quality scoring and regression reports.
3. Improve OCR, speaker, audio, and visual evidence quality.
4. Add user-facing timeline citations and debug inspection.
5. Add async processing jobs for longer videos.
6. Add production-safe storage and index lifecycle management.
7. Add advanced VLM clip understanding.
8. Add semantic event segmentation and world-memory research features.

## Why This Order Matters

The project is now structurally ready, but advanced models alone will not make
it reliable. If a user asks:

```text
"I remember he drew a blue graph but forgot why."
```

the system must prove four things:

- It retrieved the correct timeline moment.
- It used the right evidence type, such as transcript, OCR, frame, clip, or event.
- It avoided unsupported claims.
- It returned citations and confidence that can be inspected.

That requires evaluation and observability first.

## Phase N1: Golden QA Evaluation Set

### Purpose

Create a labeled benchmark for the project so every retrieval or generation
change can be measured.

Without this phase, the team will not know whether retrieval is improving or
silently becoming worse.

### Deliverables

- A local QA dataset for each processed video.
- Questions grouped by query type.
- Expected answer notes.
- Expected timestamp windows.
- Expected citation source IDs when known.
- Negative questions that should not be answered from video evidence.
- Ambiguous questions that should trigger clarification.

### Suggested Files

```text
data/evaluation/qa_sets/{video_id}_qa.json
data/evaluation/qa_sets/mcp_vs_api_qa.json
src/pipeline/evaluation/qa_schema.py
src/pipeline/evaluation/qa_loader.py
```

### QA Types To Include

```text
definition
concept
exact_timestamp
visual_memory
ocr_or_slide_text
speaker_question
before_after
comparison
summary
repeated_concept
unrelated_or_general
video_evidence_not_found
ambiguous_query
```

### Example Record

```json
{
  "question_id": "qa_000001",
  "video_id": "mcp_vs_api",
  "query": "Where does he explain MCP?",
  "expected_outcome": "grounded_answer",
  "expected_start_ms_min": 280000,
  "expected_start_ms_max": 340000,
  "required_terms": ["MCP", "protocol"],
  "forbidden_terms": [],
  "expected_source_types": ["semantic_chunk", "event", "atom"],
  "notes": "The answer should cite the MCP explanation moment."
}
```

### Done Criteria

- At least 50 labeled questions exist for `mcp_vs_api`.
- At least 10 negative questions are included.
- At least 10 vague memory questions are included.
- At least 10 timestamp or before-after questions are included.
- The dataset can be loaded without running the API server.

## Phase N2: Automated Retrieval And Answer Evaluation

### Purpose

Create a repeatable command that runs the QA set against the `/ask` pipeline and
produces a quality report.

### Deliverables

- Evaluation runner.
- Metrics calculator.
- JSON report.
- Markdown summary report.
- Regression comparison between two runs.

### Suggested Files

```text
src/pipeline/evaluation/evaluate_ask.py
src/pipeline/evaluation/metrics.py
src/pipeline/evaluation/report_writer.py
data/evaluation/reports/{video_id}_{run_id}.json
data/evaluation/reports/{video_id}_{run_id}.md
```

### Required Metrics

```text
outcome_accuracy
timestamp_hit_rate
citation_presence_rate
citation_validity_rate
required_term_coverage
unsupported_claim_rate
negative_question_abstention_rate
average_confidence
low_confidence_reason_coverage
fallback_rate
average_latency_ms
```

### Example Command

```powershell
python -m src.pipeline.evaluation.evaluate_ask --video-id mcp_vs_api
```

### Done Criteria

- The command runs without the frontend.
- Each QA item records pass/fail details.
- Timestamp answers are checked with a tolerance window.
- Unrelated questions are expected to return `unrelated_to_video`.
- Video-related missing evidence is expected to return `video_evidence_not_found`.
- Reports are easy to compare before and after retrieval changes.

## Phase N3: Evidence Quality Upgrade

### Purpose

Improve the quality of the evidence artifacts before adding heavier reasoning.

The current OCR, speaker, and audio-event foundation is useful, but it should be
made more accurate and easier to trust.

### OCR Upgrade

Focus on:

- Better frame preprocessing.
- OCR confidence filtering.
- Deduplication of repeated slide text.
- Slide-region detection for lecture videos.
- Stable OCR IDs linked to frame IDs and atoms.

Suggested files:

```text
src/pipeline/ocr_extraction.py
src/pipeline/ocr_postprocessing.py
tests/test_ocr_postprocessing.py
```

Output:

```text
data/processed/ocr/{video_id}.json
data/processed/reports/{video_id}_ocr_quality.json
```

### Speaker Upgrade

Focus on:

- Speaker turn smoothing.
- Handling unknown speaker count.
- Linking speaker turns to transcript segments.
- Speaker confidence.
- Avoiding very tiny fragmented turns.

Suggested files:

```text
src/pipeline/speaker_diarization.py
src/pipeline/speaker_postprocessing.py
tests/test_speaker_postprocessing.py
```

Output:

```text
data/processed/speakers/{video_id}.json
data/processed/reports/{video_id}_speaker_quality.json
```

### Audio Event Upgrade

Focus on:

- Silence detection.
- Music/noise/speech markers.
- Long pause events.
- Audio event links to boundary candidates.
- Audio event confidence.

Suggested files:

```text
src/pipeline/audio_event_detection.py
src/pipeline/audio_event_postprocessing.py
tests/test_audio_event_postprocessing.py
```

Output:

```text
data/processed/audio_events/{video_id}.json
data/processed/reports/{video_id}_audio_event_quality.json
```

### Done Criteria

- OCR records contain confidence, text, frame ID, timestamp, and atom/chunk links.
- Speaker turns contain speaker ID, start/end ms, confidence, and transcript links.
- Audio events contain event type, start/end ms, confidence, and boundary links.
- Low-quality records are filtered or marked clearly.
- Quality reports are generated for each modality.

## Phase N4: User-Facing Timeline Evidence UI

### Purpose

Make the system explain itself to the user.

The API already returns metadata, but the user experience should clearly show
where the answer came from.

### Deliverables

- Timeline citation panel.
- Clickable citation timestamps.
- Evidence cards for transcript, OCR, visual, speaker, and audio.
- Clip preview for cited moments.
- Confidence explanation.
- Outcome-specific UI states.
- Ask-debug view for development mode.

### Suggested Areas

```text
web/
api.py
src/pipeline/agentic/contracts.py
```

### UI Behavior

For grounded answers, show:

```text
answer
timestamp
confidence
citations
source type
clip/frame references
```

For not-found answers, show:

```text
what was searched
why evidence was insufficient
what the user can ask instead
```

For unrelated answers in hybrid mode, show:

```text
general answer
no video timestamp
source_type: general_knowledge
```

### Done Criteria

- Users can see timestamps for every cited video claim.
- Users can inspect the supporting transcript/OCR/visual evidence.
- The UI does not display raw filesystem paths.
- Development mode can show trace details.
- Production mode hides internal trace details unless explicitly enabled.

## Phase N5: Long Video Processing And Job System

### Purpose

Support 30 to 180 minute videos without blocking the API or corrupting partial
indexes.

### Why This Is Needed

Long videos produce many artifacts:

- Thousands of sampled frames.
- Long transcripts.
- Hundreds or thousands of atoms.
- Many semantic chunks and events.
- OCR, speaker, and audio-event records.
- Multiple Chroma collections.

This should run as a controlled processing job, not as a single request that may
timeout.

### Deliverables

- Job manifest.
- Step-level processing status.
- Resume support.
- Failure recovery.
- Job locks.
- Progress API.
- Processing queue.

### Suggested Files

```text
src/pipeline/jobs/job_contracts.py
src/pipeline/jobs/job_repository.py
src/pipeline/jobs/processor.py
src/pipeline/jobs/locks.py
src/pipeline/jobs/progress.py
```

### Processing States

```text
pending
probing
transcribing
extracting_frames
extracting_boundaries
building_atoms
attaching_evidence
building_chunks
building_events
indexing
validating
completed
failed
cancelled
```

### Done Criteria

- A long video can be processed step by step.
- A failed job can resume from the last valid artifact.
- Chroma indexes are not queried while incomplete.
- The UI can show progress.
- Each processing step writes a report.

## Phase N6: Storage, Versioning, And Index Lifecycle

### Purpose

Make artifacts and indexes stable across code changes.

The project already stores pipeline versions in metadata. The next step is to
manage rebuilds, stale artifacts, and index compatibility cleanly.

### Deliverables

- Artifact registry.
- Index registry.
- Pipeline version compatibility checks.
- Rebuild command.
- Cleanup command for one video.
- Backup/export command for processed metadata.

### Suggested Files

```text
src/pipeline/storage/artifact_registry.py
src/pipeline/storage/index_registry.py
src/pipeline/storage/rebuild.py
src/pipeline/storage/cleanup.py
```

### Example Commands

```powershell
python -m src.pipeline.storage.rebuild --video-id mcp_vs_api --from-step chunks
python -m src.pipeline.storage.cleanup --video-id mcp_vs_api --keep-source-video
python -m src.pipeline.storage.index_registry --check --video-id mcp_vs_api
```

### Done Criteria

- The system can detect stale artifacts.
- The system can rebuild a video from a selected phase.
- The system can clean generated artifacts without deleting source videos.
- Chroma collection metadata records index version and embedding model.
- Retrieval rejects incompatible indexes.

## Phase N7: Advanced Clip-Level Video-Language Model Layer

### Purpose

Move beyond single-frame captions and understand short clips with motion,
actions, and temporal changes.

This is the start of the stronger research direction.

### Candidate Models

```text
Qwen2.5-VL
LLaVA-Video
Video-LLaMA
Gemini video input, when available through the selected API path
```

### Deliverables

- Clip sampler.
- VLM adapter interface.
- Local/offline adapter option.
- Cloud adapter option.
- Clip-level visual summaries.
- Action and object timeline records.
- VLM confidence and failure metadata.

### Suggested Files

```text
src/pipeline/vlm/base.py
src/pipeline/vlm/clip_sampler.py
src/pipeline/vlm/qwen_adapter.py
src/pipeline/vlm/gemini_video_adapter.py
src/pipeline/vlm/clip_understanding.py
```

### Output

```text
data/processed/vlm_clips/{video_id}.json
data/processed/reports/{video_id}_vlm_quality.json
```

### GPU Guidance

Your RTX 3050 6GB can support lightweight local experiments, smaller VLMs, and
quantized models, but it is not ideal for large video-language models over long
clips.

Recommended approach:

- Use CPU/GPU hybrid processing for the current base.
- Use small or quantized models locally.
- Keep cloud adapters available for heavier VLM runs.
- Cache every clip result so expensive model calls are not repeated.

### Done Criteria

- The project can process clips, not just frames.
- Motion/action questions use clip evidence.
- Clip summaries link back to atoms, chunks, and events.
- Retrieval can search clip-level visual memory.
- Expensive VLM calls are cached and resumable.

## Phase N8: Semantic Event Segmentation Research Layer

### Purpose

Replace simple rule-based event grouping with learned or model-assisted semantic
event boundaries.

This should happen after the base evaluation framework exists, because the team
must measure whether the new segmentation actually improves retrieval.

### Deliverables

- Event boundary training/evaluation dataset.
- Transformer or model-assisted segmenter adapter.
- Boundary confidence.
- Comparison against current rule-based segmentation.
- Regression report on QA quality.

### Suggested Files

```text
src/pipeline/event_segmentation/base.py
src/pipeline/event_segmentation/rule_based.py
src/pipeline/event_segmentation/model_based.py
src/pipeline/event_segmentation/evaluate_boundaries.py
```

### Done Criteria

- Model-generated event boundaries are validated before use.
- Boundary changes do not break atom/chunk hierarchy.
- Event segmentation quality is compared against the current baseline.
- Retrieval quality improves or the model-based segmenter stays optional.

## Phase N9: Video World Model And Memory Graph

### Purpose

Build a higher-level memory layer that stores objects, entities, actions,
relationships, and temporal evolution.

This is where the project becomes more novel.

### Memory Objects

```text
entities
objects
slides
concepts
actions
comparisons
claims
questions
relationships
repeated appearances
```

### Example

```json
{
  "memory_id": "mem_000145",
  "video_id": "mcp_vs_api",
  "type": "concept",
  "label": "Model Context Protocol",
  "aliases": ["MCP"],
  "first_seen_ms": 299925,
  "last_seen_ms": 440120,
  "evidence_ids": ["chunk_000008", "event_000004"],
  "relationships": [
    {
      "type": "explains",
      "target": "tool connection layer",
      "evidence_id": "chunk_000009"
    }
  ]
}
```

### Suggested Files

```text
src/pipeline/world_model/memory_schema.py
src/pipeline/world_model/memory_builder.py
src/pipeline/world_model/entity_linker.py
src/pipeline/world_model/relation_extractor.py
src/pipeline/world_model/memory_retriever.py
```

### Done Criteria

- Concepts and entities can be tracked across the full video.
- Repeated concept questions can search the memory graph.
- Memory records always link back to timeline evidence.
- The answer generator cannot cite memory records unless evidence citations exist.

## Phase N10: Production Hardening

### Purpose

Make the system safer and easier to run repeatedly.

### Deliverables

- Configuration validation.
- Startup health checks.
- Dependency checks for FFmpeg, FFprobe, Tesseract, ChromaDB, and model cache.
- Clear error messages.
- Rate limiting for generation calls.
- Gemini fallback handling.
- Local-only retrieval fallback.
- Processing locks.
- Trace redaction.

### Suggested Files

```text
src/config/settings.py
src/config/health_checks.py
src/pipeline/agentic/circuit_breaker.py
src/pipeline/agentic/security.py
tests/test_health_checks.py
tests/test_security_contracts.py
```

### Done Criteria

- Missing dependencies are reported before processing starts.
- Gemini 503 or quota failures do not remove metadata from responses.
- The API can answer from retrieved evidence using fallback generation.
- No public response exposes local file paths.
- Concurrent processing does not corrupt artifacts or Chroma collections.

## Two-Person Team Execution Plan

The team should work in parallel only when file ownership is clearly separated.

### Developer 1: Evaluation And Retrieval Quality

Owns:

```text
src/pipeline/evaluation/
src/pipeline/agentic/retrieval_planner.py
src/pipeline/agentic/retrieval_orchestrator.py
src/pipeline/agentic/candidate_fusion.py
src/pipeline/agentic/reranker.py
src/pipeline/agentic/temporal_deduplicator.py
tests/test_evaluation_*.py
tests/test_agentic_retrieval_*.py
```

Primary phases:

```text
N1
N2
retrieval improvements from N3
```

### Developer 2: Evidence Artifacts And Processing

Owns:

```text
src/pipeline/ocr_extraction.py
src/pipeline/ocr_postprocessing.py
src/pipeline/speaker_diarization.py
src/pipeline/speaker_postprocessing.py
src/pipeline/audio_event_detection.py
src/pipeline/audio_event_postprocessing.py
src/pipeline/jobs/
src/pipeline/storage/
tests/test_ocr_*.py
tests/test_speaker_*.py
tests/test_audio_*.py
tests/test_jobs_*.py
```

Primary phases:

```text
N3
N5
N6
```

### Shared Work

Only one developer should edit these at a time:

```text
api.py
README.md
docs/
src/pipeline/agentic/contracts.py
src/pipeline/agentic/state.py
src/pipeline/agentic/workflow.py
web/
requirement.txt
```

For shared files, create a short coordination message before starting:

```text
I am editing api.py for progress endpoints. Please avoid api.py until I push.
```

## Branching And Merge Workflow

### Start Of Day

Both developers:

```powershell
git checkout main
git pull origin main
```

### Create Feature Branch

Developer 1 examples:

```powershell
git checkout -b feature/n1-n2-evaluation-harness
git checkout -b feature/retrieval-quality-metrics
```

Developer 2 examples:

```powershell
git checkout -b feature/n3-evidence-quality-upgrade
git checkout -b feature/n5-processing-jobs
```

### Before Pushing A Branch

Run:

```powershell
python -m compileall -q api.py src\pipeline
python -m unittest discover -s tests -v
git status
```

Then:

```powershell
git add .
git commit -m "Add evaluation harness foundation"
git push origin feature/n1-n2-evaluation-harness
```

### Before Merging Main Into Your Branch

Run:

```powershell
git checkout main
git pull origin main
git checkout feature/your-branch-name
git merge main
python -m unittest discover -s tests -v
```

### Merge Order

Recommended merge order:

1. Evaluation schema and QA loader.
2. Evidence postprocessing improvements.
3. Evaluation runner and reports.
4. UI/debug timeline citation work.
5. Processing job system.
6. Storage and index lifecycle.
7. VLM clip understanding.
8. Event segmentation research.
9. World-memory graph.

## Immediate Next Sprint

The next sprint should be small and measurable.

### Sprint Goal

```text
Create the evaluation harness and use it to measure current answer quality.
```

### Sprint Tasks

1. Add `data/evaluation/qa_sets/mcp_vs_api_qa.json`.
2. Add QA schema and loader.
3. Add evaluation runner.
4. Add metrics report writer.
5. Run the evaluation against the current `mcp_vs_api` processed artifacts.
6. Save the first baseline report.
7. Fix the top three failure categories only after seeing the report.

### Sprint Done Criteria

- The team can run one command to evaluate the current system.
- The report shows timestamp accuracy, citation validity, and abstention quality.
- Future retrieval changes can be compared against this baseline.

## Definition Of Next Milestone Done

The next milestone is complete when:

- A 50+ question QA set exists for `mcp_vs_api`.
- Evaluation reports are generated automatically.
- OCR, speaker, and audio quality reports exist.
- The UI shows citation timestamps and evidence cards.
- Long video processing has resumable job state.
- Stale indexes are detected before retrieval.
- Gemini/model failures keep response metadata intact.
- The project can prove answer quality improvement with numbers.

## Final Recommendation

Build the next milestone around measurement first.

The strongest version of this project is not just a system that answers video
questions. It is a system that can show exactly why it answered, where the
evidence lives on the timeline, how confident it is, and whether a new change
made the answers better or worse.
