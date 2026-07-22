# Phases C13-C25: Production Agentic Retrieval And Answer Quality

This document adapts `VideoSceneRAG_Production_Agentic_Retrieval_Architecture_v2.md` into implementation phases for the current project.

The key correction is this:

The system should not behave like a chatbot that performs one vector search. It should behave like an evidence-controlled video intelligence system that decides whether the question is answerable before generating the answer.

## Production Flow

```text
User Question
 -> Conversation Resolver
 -> Query Understanding
 -> Scope Router
 -> Retrieval Planner
 -> Parallel Multimodal Retrieval
 -> Candidate Fusion
 -> Reranking And Temporal Deduplication
 -> Evidence Verifier
 -> Answerability Gate
      -> sufficient: Temporal Reasoning
      -> uncertain: Corrective Retrieval
      -> absent: Video Evidence Not Found
      -> unrelated: Out Of Scope Policy
 -> Evidence Packet Builder
 -> Grounded Answer Generator
 -> Claim And Citation Verifier
      -> valid: Return Answer
      -> invalid: Revise Once Or Abstain
 -> Confidence Calibration
 -> API Response And Retrieval Trace
```

## Why The Phase Plan Changed

The previous C13-C20 plan had the right direction, but the production architecture requires additional safety layers:

- Conversation reference resolution must happen before query understanding.
- Scope routing must separate unrelated questions from video-related missing evidence.
- Evidence sufficiency must be checked before answer generation.
- Corrective retrieval must happen when retrieval is weak but possibly fixable.
- The final answer must be verified claim-by-claim.
- Confidence must be calibrated from evidence signals, not model confidence alone.
- Observability, security, and production hardening need their own phases.

## Target Outcomes

Every question must return exactly one primary outcome:

```text
grounded_answer
partial_answer
video_evidence_not_found
unrelated_to_video
ambiguous_query
conflicting_evidence
processing_incomplete
system_error
```

This is important because `low_confidence` is not specific enough. A question can fail because it is unrelated, missing from the video, ambiguous, blocked by incomplete processing, or contradicted by evidence.

## Target `/ask` Response Contract

```json
{
  "outcome": "grounded_answer",
  "answer": "The speaker explains MCP as a protocol layer that connects tools and context to model reasoning.",
  "video_id": "mcp_vs_api",
  "query": "What is MCP logic in the reasoning layer?",
  "answer_mode": "strict_video",
  "timestamp": 299.925,
  "start_ms": 299925,
  "end_ms": 335965,
  "source_id": "chunk_000008",
  "source_type": "semantic_chunk",
  "parent_event_id": "event_000004",
  "confidence": 0.82,
  "citations": [
    {
      "citation_id": "S1",
      "source_type": "semantic_chunk",
      "source_id": "chunk_000008",
      "start_ms": 299925,
      "end_ms": 335965,
      "text": "retrieved evidence text"
    }
  ],
  "answer_quality": {
    "grounded": true,
    "has_timestamp": true,
    "has_citations": true,
    "uses_verified_evidence": true,
    "low_confidence_reason": null
  },
  "trace_id": "trace_20260722_001530_ab12"
}
```

For non-grounded outcomes, the response must still follow a typed contract. It should not collapse into a raw exception or a plain string.

## System Modes

The API should support an `answer_mode` field:

```text
strict_video
hybrid_assistant
clarify_when_ambiguous
```

### Strict Video

Use video evidence only.

If the question is unrelated or unsupported, abstain clearly.

### Hybrid Assistant

Try video evidence first. If the query is clearly unrelated, answer from general knowledge with:

```text
source_type: general_knowledge
```

Do not attach video timestamps or video citations to general answers.

### Clarify When Ambiguous

Ask one focused clarification if the query may refer either to the selected video or general knowledge.

## Trace Artifacts

Each question should write a trace:

```text
data/processed/retrieval_traces/{video_id}/{trace_id}.json
```

Trace contents:

```json
{
  "trace_id": "trace_...",
  "request": {},
  "versions": {},
  "conversation_resolution": {},
  "query_understanding": {},
  "scope_decision": {},
  "plans": [],
  "retrieval_attempts": [],
  "candidate_fusion": {},
  "reranking": {},
  "verification": {},
  "answerability": {},
  "temporal_reasoning": {},
  "evidence_packet_summary": {},
  "generation": {},
  "claim_verification": {},
  "confidence": {},
  "final_response": {},
  "timings": {},
  "warnings": [],
  "errors": []
}
```

## Phase C13: Typed Contracts And Workflow State

Status: implemented.

### Purpose

Create the contract layer before adding more retrieval logic.

Without typed contracts, later phases will keep breaking response metadata, citations, and debug traces.

### Deliverables

- `AskRequest` schema.
- `AskResponse` schema.
- Outcome schemas.
- Citation schema.
- Candidate evidence schema.
- Retrieval plan schema.
- Agentic workflow state.
- Retrieval trace schema.

### Suggested Modules

```text
src/pipeline/agentic/contracts.py
src/pipeline/agentic/state.py
src/pipeline/agentic/trace_repository.py
```

Implemented files:

```text
src/pipeline/agentic/contracts.py
src/pipeline/agentic/state.py
src/pipeline/agentic/trace_repository.py
tests/test_agentic_contracts.py
```

### Done Criteria

- Every `/ask` response validates against a schema.
- Every outcome has required fields.
- Citation objects cannot be malformed.
- Trace objects can be saved and loaded.
- Unit tests cover schema validation failures.

## Phase C14: Conversation Resolver And Query Understanding

Status: implemented.

### Purpose

Resolve follow-up questions and classify the user's intent.

Example:

```text
Turn 1: Where does he explain MCP?
Turn 2: What does he say after that?
```

The second query must resolve to:

```text
What does the speaker say after the MCP explanation near 00:05:00?
```

### Query Type Taxonomy

Support multi-label classification:

```text
definition
concept
exact_quote
exact_timestamp
approximate_timestamp
visual_memory
action_memory
ocr_or_slide_text
speaker_question
before_after
cause_effect
comparison
repeated_concept
summary
chapter_summary
entity_tracking
follow_up
cross_video
system_or_help
unrelated_or_general
unsafe_or_disallowed
unknown
```

### Deliverables

- Conversation reference resolver.
- Deterministic timestamp parser.
- Deterministic quote parser.
- Rule-based visual, temporal, comparison, and summary cue detector.
- Optional bounded LLM classifier.
- Query understanding object stored in trace.

### Suggested Modules

```text
src/pipeline/agentic/conversation_resolver.py
src/pipeline/agentic/query_understanding.py
```

Implemented files:

```text
src/pipeline/agentic/conversation_resolver.py
src/pipeline/agentic/query_understanding.py
tests/test_agentic_query_understanding.py
```

### Done Criteria

- Follow-up references resolve when prior citations exist.
- Exact timestamps are parsed into integer milliseconds.
- Visual memory questions are detected.
- Before/after questions are detected.
- Unknown classification does not block retrieval.

## Phase C15: Scope Router And Out-Of-Scope Policy

Status: implemented.

### Purpose

Decide whether the question should be answered from the selected video.

This is the production architecture's most important safety layer.

### Required Distinction

These are not the same:

```text
unrelated_to_video
```

The question is about another subject.

```text
video_evidence_not_found
```

The question appears to concern the video, but enough supporting evidence was not found.

### Deliverables

- Pre-retrieval scope classifier.
- Lightweight probe retrieval over video summary, events, and entities.
- Strict video policy.
- Hybrid assistant policy.
- Clarification policy.
- Negative query tests.

### Suggested Module

```text
src/pipeline/agentic/scope_router.py
```

Implemented files:

```text
src/pipeline/agentic/scope_router.py
tests/test_agentic_scope_router.py
```

API integration:

```text
api.py
```

`/ask` now creates a retrieval trace, stores conversation resolution, stores query understanding, stores the scope decision, and returns a typed response outcome. `/ask-debug` returns the trace together with the typed response.

### Done Criteria

- Unrelated questions do not get fake video citations.
- Strict mode never answers from general knowledge.
- Hybrid mode labels general answers clearly.
- Ambiguous questions can request clarification.
- The scope decision is stored in the trace.

## Phase C16: Retrieval Planner And Retriever Adapters

Status: implemented.

### Purpose

Build a bounded executable retrieval plan.

The planner must return configured retrieval steps, not arbitrary agent actions.

### Plan Shape

```json
{
  "strategy": "visual_causal_memory_recovery",
  "retrieval_steps": [
    {
      "retriever": "visual_dense",
      "level": "atomic_span",
      "query": "blue graph being drawn",
      "top_k": 30,
      "weight": 1.5
    },
    {
      "retriever": "event_dense",
      "level": "event",
      "query": "reason for drawing a blue graph",
      "top_k": 15,
      "weight": 1.2
    }
  ],
  "context_policy": {
    "direction": "both",
    "max_previous_atoms": 3,
    "max_next_atoms": 4,
    "include_parent_event": true,
    "max_context_ms": 180000
  },
  "max_corrective_attempts": 2
}
```

### First Retriever Adapters

Implement using what the project already has:

- Exact timeline lookup.
- Dense transcript retrieval.
- Dense semantic chunk retrieval.
- Dense event retrieval.
- Visual chunk retrieval.

Then add:

- Sparse/BM25 retrieval.
- OCR retrieval.
- Speaker retrieval.
- Clip/action retrieval.
- Audio-event retrieval.
- Entity/world-memory retrieval.

### Suggested Modules

```text
src/pipeline/agentic/retrieval_planner.py
src/pipeline/agentic/retrievers/base.py
src/pipeline/agentic/retrievers/exact_timeline.py
src/pipeline/agentic/retrievers/chroma_dense.py
src/pipeline/agentic/retrievers/local_visual.py
```

Implemented files:

```text
src/pipeline/agentic/retrieval_planner.py
src/pipeline/agentic/retrievers/base.py
src/pipeline/agentic/retrievers/exact_timeline.py
src/pipeline/agentic/retrievers/chroma_dense.py
src/pipeline/agentic/retrievers/local_visual.py
src/pipeline/agentic/retrievers/local_sparse.py
```

Implemented retrievers:

- Exact timeline lookup.
- Dense transcript retrieval.
- Dense semantic chunk retrieval.
- Dense event retrieval.
- Visual chunk retrieval.
- Sparse local keyword retrieval.
- Working local OCR, speaker-turn, and audio-event retrievers backed by canonical timestamped artifacts.
- Clip/action and entity/world-memory adapter slots retain safe empty behavior until their model-backed indexes are built.

### OCR, Speaker, And Audio Artifact Foundation

The previously empty OCR, speaker, and audio-event adapters are now backed by ingestion artifacts:

```text
data/processed/ocr/{video_id}.json
data/processed/speakers/{video_id}.json
data/processed/audio_events/{video_id}.json
```

Build all three after C6-C10 has created frames, transcript atoms, semantic chunks, and events:

```powershell
python -m src.pipeline.modality_foundation --video-id <video_id>
```

For a known speaker count, provide it explicitly. This is recommended for lectures and interviews because it prevents acoustic over-segmentation:

```powershell
python -m src.pipeline.modality_foundation --video-id <video_id> --expected-speakers 1
```

OCR uses Tesseract at ingestion time and stores token boxes, confidence, frame IDs, integer timestamps, atom IDs, parent chunk IDs, and parent event IDs. Configure a non-standard executable with `TESSERACT_PATH`.

Speaker processing computes acoustic spectral features for timestamped ASR segments, clusters them into stable speaker IDs, limits turns to 30 seconds, aligns turns to chunks, and writes speaker IDs back into canonical atoms. `--expected-speakers` is the preferred control when the source format is known.

Audio-event processing uses overlapping analysis windows but emits canonical non-overlapping timeline intervals. Its deterministic baseline recognizes `speech`, `silence`, `transient_sound`, `music_or_tonal_audio`, and `background_audio`, and stores confidence plus acoustic measurements for later model upgrades.

The query-understanding and planner layers now route:

```text
slide/on-screen text -> ocr_sparse
speaker/lecturer questions -> speaker
music/silence/sound questions -> audio_event
```

These local retrievers normalize their output to `CandidateEvidence`, so fusion, reranking, verification, temporal reasoning, citations, claim verification, and confidence calibration work without a special answer path.

### Done Criteria

- The planner selects retrieval based on query type.
- Exact timestamp queries bypass unnecessary vector search.
- Visual memory queries include visual retrieval.
- Comparison questions retrieve evidence for both sides.
- Plans are bounded by top-k and context limits.

## Phase C17: Parallel Retrieval, Fusion, Reranking, And Deduplication

Status: implemented.

### Purpose

Run the retrieval plan across multiple evidence layers, normalize results, merge rankings, and remove duplicate timeline evidence.

### Candidate Evidence Schema

```json
{
  "candidate_id": "cand_000001",
  "video_id": "mcp_vs_api",
  "source_type": "semantic_chunk",
  "source_id": "chunk_000008",
  "start_ms": 299925,
  "end_ms": 335965,
  "parent_event_id": "event_000004",
  "text": "The speaker explains MCP as a protocol layer...",
  "visual_summary": "A protocol diagram is displayed.",
  "media_refs": {
    "frames": [],
    "clip": null
  },
  "retrieval": {
    "retriever": "transcript_dense",
    "raw_score": 0.76,
    "rank": 2,
    "query_variant": "MCP protocol reasoning"
  },
  "versions": {
    "pipeline": "2.0.0",
    "embedding": "BAAI/bge-base-en-v1.5"
  }
}
```

### Fusion Method

Start with weighted reciprocal rank fusion:

```text
fused_score += retriever_weight / (rank_constant + rank)
```

Then add:

- Entity overlap bonus.
- Exact phrase bonus.
- Visual hint bonus.
- Temporal hint bonus.
- Penalty for stale pipeline version.

### Deduplication

Use temporal IoU to collapse near-duplicate results:

```text
overlap_ms / union_ms
```

Keep the stronger candidate, but retain references to merged candidates in the trace.

### Suggested Modules

```text
src/pipeline/agentic/retrieval_orchestrator.py
src/pipeline/agentic/candidate_fusion.py
src/pipeline/agentic/reranker.py
src/pipeline/agentic/temporal_deduplicator.py
```

Implemented files:

```text
src/pipeline/agentic/retrieval_orchestrator.py
src/pipeline/agentic/candidate_fusion.py
src/pipeline/agentic/reranker.py
src/pipeline/agentic/temporal_deduplicator.py
```

The orchestrator now records per-retriever candidate counts and warnings. Fusion uses weighted reciprocal rank fusion plus exact-term, entity, visual, temporal, and stale-index signals. Deduplication collapses near-duplicate timeline windows using temporal IoU.

### Done Criteria

- Multiple retrievers can run for one query.
- All outputs normalize to one candidate schema.
- Fused rankings are traceable.
- Duplicate timeline windows collapse.
- Candidate counts and scores are written to the trace.

## Phase C18: Evidence Verifier And Answerability Gate

Status: implemented.

### Purpose

Verify candidate evidence before generation and decide whether answering is allowed.

This prevents the model from improvising when retrieval is weak.

### Evidence Verification Checks

- Correct `video_id`.
- Current pipeline and index version.
- Valid `start_ms` and `end_ms`.
- Source artifact exists.
- Parent event/chunk links are valid.
- Transcript or visual content is present.
- Media references exist when cited.
- Candidate is relevant to the query.
- Candidate covers required query aspects.

### Answerability Decisions

```text
answer
partial_answer
corrective_retrieval
video_evidence_not_found
ambiguous_query
conflicting_evidence
processing_incomplete
```

### Three-Zone Policy

```text
score >= answer_threshold
-> answer

uncertain_threshold <= score < answer_threshold
-> corrective_retrieval

score < uncertain_threshold
-> not found or unrelated, depending on scope decision
```

### Suggested Modules

```text
src/pipeline/agentic/evidence_verifier.py
src/pipeline/agentic/answerability_gate.py
```

Implemented files:

```text
src/pipeline/agentic/evidence_verifier.py
src/pipeline/agentic/answerability_gate.py
tests/test_agentic_retrieval_gate.py
```

API integration:

```text
api.py
```

`/ask` now runs the C16-C18 retrieval gate before answer generation. If evidence is not answerable, the API returns a typed not-found or policy response instead of asking the answer model to improvise.

### Done Criteria

- No answer generation happens without sufficient verified evidence.
- Missing visual/OCR indexes can produce `processing_incomplete`.
- Weak retrieval triggers corrective retrieval or abstention.
- Evidence rejection reasons are counted in the trace.

## Phase C19: Corrective Retrieval And Temporal Reasoning

Status: implemented.

### Purpose

Retry retrieval intelligently when evidence is close but incomplete, then reason across time.

### Corrective Retrieval

Corrective retrieval should:

- Run at most the configured number of attempts.
- Expand or rewrite the query without semantic drift.
- Add missing modality retrievers.
- Widen temporal context only within limits.
- Stop when evidence becomes sufficient or attempts are exhausted.

### Temporal Reasoning

The temporal reasoner should:

- Sort verified evidence by timeline.
- Identify the primary moment.
- Attach previous and next atoms when needed.
- Attach parent semantic chunk and parent event.
- Detect before/after relationships.
- Detect repeated concept appearances.
- Mark conflicting evidence.

### Suggested Modules

```text
src/pipeline/agentic/corrective_retrieval.py
src/pipeline/agentic/temporal_reasoner.py
```

Implemented files:

```text
src/pipeline/agentic/corrective_retrieval.py
src/pipeline/agentic/temporal_reasoner.py
tests/test_agentic_answer_pipeline.py
```

The retrieval gate now performs bounded corrective retrieval when answerability is uncertain. Temporal reasoning identifies the primary moment, expands previous/next atoms inside the configured context window, attaches parent chunk/event context, records repeated-concept signals, and exposes conflicting or distant evidence instead of hiding it.

### Done Criteria

- Uncertain retrieval can perform one safe corrective loop.
- Timeline context is contiguous when needed.
- Context expansion does not exceed video duration.
- Conflicting evidence is not hidden.

## Phase C20: Evidence Packet And Grounded Generation

Status: implemented.

### Purpose

Build a compact, verified evidence packet and generate the answer only from that packet.

### Evidence Packet

The answer generator should receive:

- User question.
- Outcome candidate.
- Verified evidence list.
- Citation IDs.
- Timeline context.
- Visual references.
- Missing evidence notes.
- Allowed answer style.

It should not receive raw unverified Chroma results.

### Generation Rules

- Answer directly.
- Include timestamps when video evidence is used.
- Cite evidence IDs.
- State limitations clearly.
- Do not answer unsupported parts.
- Do not expose filesystem paths in user-facing responses.
- Preserve metadata when Gemini fails and fallback is used.

### Suggested Modules

```text
src/pipeline/agentic/evidence_packet.py
src/pipeline/agentic/answer_generator.py
```

Implemented files:

```text
src/pipeline/agentic/evidence_packet.py
src/pipeline/agentic/answer_generator.py
tests/test_agentic_answer_pipeline.py
```

The answer generator now receives a compact evidence packet containing only verified evidence, citation IDs, visual references, temporal context, missing-evidence notes, and allowed answer style. Gemini failures fall back to a local grounded answer that preserves citations and metadata.

### Done Criteria

- Gemini 503 does not break response metadata.
- Fallback answers include citations when evidence exists.
- Not-found answers are clear and safe.
- Generated answer references only packet evidence.

## Phase C21: Claim Verifier And Answer Revision

Status: implemented.

### Purpose

Verify the final answer after generation.

Even with a good evidence packet, the model can add unsupported claims. This phase catches that.

### Claim Verification

Extract claims from the draft answer and label each one:

```text
supported
partially_supported
unsupported
contradicted
not_video_claim
```

### Revision Rule

If verification fails:

1. Revise once using verifier feedback.
2. Verify again.
3. If still unsupported, return a partial answer or abstain.

### Suggested Module

```text
src/pipeline/agentic/claim_verifier.py
```

Implemented files:

```text
src/pipeline/agentic/claim_verifier.py
tests/test_agentic_answer_pipeline.py
```

Generated answers are checked for citation validity, timestamp consistency, and unsupported claims. If verification fails, the generator performs one bounded revision using supported evidence; if it still fails, the response is downgraded through the typed answer-quality metadata.

### Done Criteria

- Every video claim maps to at least one citation.
- Unsupported claims are removed or trigger partial answer.
- Citation IDs in answer text match actual citation objects.
- Timestamp claims match citation windows.

## Phase C22: Confidence Calibration

Status: implemented.

### Purpose

Calculate confidence from measurable evidence signals.

Do not use only LLM self-confidence.

### Confidence Features

- Top fused retrieval score.
- Reranker score.
- Number of verified evidence items.
- Required aspect coverage.
- Citation coverage.
- Citation precision.
- Timeline consistency.
- Modality coverage.
- Corrective retrieval used.
- Claim verification result.
- Generator fallback used.

### Suggested Module

```text
src/pipeline/agentic/confidence_calibrator.py
```

Implemented files:

```text
src/pipeline/agentic/confidence_calibrator.py
tests/test_agentic_answer_pipeline.py
```

Confidence is now calculated from retrieval, reranking, verified evidence count, citation coverage, claim support, timeline consistency, modality coverage, corrective retrieval usage, and fallback usage. `/ask-debug` exposes these features in the retrieval trace.

### Done Criteria

- Confidence is explainable in `/ask-debug`.
- Low confidence has a reason.
- Unsupported or partial answers cannot receive high confidence.
- Calibration report can be generated from the QA set.

## Phase C23: Evaluation Harness

### Purpose

Build repeatable regression tests for retrieval, answer quality, abstention, and calibration.

### QA Dataset Location

```text
data/processed/evals/{video_id}_qa_set.json
```

### Required Question Categories

```text
exact timestamp
approximate timestamp
exact quote
concept definition
visual object
color/attribute memory
action
OCR/slide text
speaker
before/after
cause/effect
comparison
repeated concept
event summary
chapter summary
follow-up
ambiguous visual memory
partially answerable
video-related but absent
unrelated general question
adversarial keyword overlap
processing-incomplete case
```

### Metrics

Retrieval:

- Recall@1, @3, @5, @10.
- Mean reciprocal rank.
- Temporal IoU.
- Mean timestamp error.
- Required-aspect coverage.
- Modality-specific recall.

Answer quality:

- Groundedness.
- Claim support rate.
- Citation precision.
- Citation recall.
- Timestamp correctness.
- Partial-answer honesty.

Unanswerable and unrelated:

- Abstention precision.
- Abstention recall.
- False answer rate.
- Correct out-of-scope routing rate.

Calibration:

- Brier score.
- Expected calibration error.
- Overconfidence rate.

### Suggested Module

```text
src/pipeline/agentic/evaluation_harness.py
```

### Done Criteria

- Evaluation can run for `mcp_vs_api`.
- Report identifies failed questions.
- Contract tests cover all outcomes.
- Regression tests run before merging retrieval or prompt changes.

## Phase C24: Observability And Operations

### Purpose

Make the system debuggable and reliable under real use.

### Deliverables

- Structured logs.
- Request IDs.
- Trace IDs.
- Latency per workflow node.
- Model error tracking.
- Fallback rate.
- Corrective retrieval rate.
- Trace write failure handling.
- Circuit breaker for external model failures.

### Suggested Modules

```text
src/pipeline/agentic/observability.py
src/pipeline/agentic/circuit_breaker.py
```

### Done Criteria

- `/ask-debug` exposes trace ID and workflow timings.
- External model failures degrade gracefully.
- Index consistency is checked before retrieval.
- Partially built indexes are never queried.

## Phase C25: Security And Production Hardening

### Purpose

Protect video data, traces, prompts, and media references.

### Deliverables

- Access filtering by `video_id`.
- Sanitized uploaded filenames.
- No raw filesystem paths in public API responses.
- Protected media URLs or internal media IDs.
- Prompt-injection defense for transcript and OCR text.
- Trace redaction.
- Retention policy for videos, traces, and conversations.
- Processing job locks.
- Concurrent index mutation protection.

### Suggested Module

```text
src/pipeline/agentic/security.py
```

### Done Criteria

- User-facing responses do not expose private paths.
- Evidence text is treated as data, not instructions.
- Retrieval traces redact sensitive information.
- Concurrent requests cannot query a partially built index.

## Suggested Directory Layout

```text
src/pipeline/agentic/
  __init__.py
  contracts.py
  state.py
  workflow.py
  trace_repository.py
  conversation_resolver.py
  query_understanding.py
  scope_router.py
  retrieval_planner.py
  retrieval_orchestrator.py
  candidate_fusion.py
  reranker.py
  temporal_deduplicator.py
  evidence_verifier.py
  answerability_gate.py
  corrective_retrieval.py
  temporal_reasoner.py
  evidence_packet.py
  answer_generator.py
  claim_verifier.py
  confidence_calibrator.py
  evaluation_harness.py
  observability.py
  circuit_breaker.py
  security.py
```

`workflow.py` coordinates stages. It must not contain retrieval, verification, prompt, or scoring business logic.

## Recommended First Build Order

For the next implementation sprint, build in this order:

1. C13 typed contracts and response outcomes.
2. C14 conversation resolution and query understanding.
3. C15 scope router with strict and hybrid modes.
4. C16 deterministic retrieval planner.
5. C17 dense + event + visual retrieval fusion.
6. C18 evidence verifier and answerability gate.
7. C19 one corrective retrieval attempt and temporal reasoning.
8. C20 structured evidence packet and grounded generation.
9. C21 claim and citation verifier.
10. C23 evaluation harness with negative questions.

C22, C24, and C25 can start once the core answer path is stable, but they must be completed before calling the system production-ready.

## Two-Developer Ownership Plan

### Developer 1: Retrieval Intelligence

Owns:

```text
conversation_resolver.py
query_understanding.py
scope_router.py
retrieval_planner.py
retrieval_orchestrator.py
candidate_fusion.py
reranker.py
temporal_deduplicator.py
```

### Developer 2: Evidence And Answer Quality

Owns:

```text
evidence_verifier.py
answerability_gate.py
corrective_retrieval.py
temporal_reasoner.py
evidence_packet.py
answer_generator.py
claim_verifier.py
confidence_calibrator.py
evaluation_harness.py
```

### Shared Files

Only one developer should edit these at a time:

```text
src/pipeline/agentic/contracts.py
src/pipeline/agentic/state.py
src/pipeline/agentic/workflow.py
api.py
README.md
docs/
tests/
config/
```

Use small branches and merge often.

## Git Workflow

Before starting work:

```powershell
git checkout main
git pull origin main
git checkout -b feature/c13-agentic-contracts
```

Before pushing:

```powershell
python -m compileall -q api.py src\pipeline
python -m unittest discover -s tests -v
git status
git add .
git commit -m "Add production agentic retrieval contracts"
git push origin feature/c13-agentic-contracts
```

Before merging teammate work:

```powershell
git checkout main
git pull origin main
git checkout feature/your-branch
git merge main
python -m unittest discover -s tests -v
```

## Definition Of Done

The production agentic retrieval layer is complete when:

- Every query receives a typed outcome.
- Exact timestamp queries bypass unnecessary semantic retrieval.
- Vague visual questions search visual and temporal evidence.
- Follow-up references resolve correctly.
- Every video claim has a valid citation.
- The system distinguishes unrelated questions from video-related absent content.
- Strict mode never answers from general knowledge.
- Hybrid mode clearly labels general answers.
- Weak evidence triggers corrective retrieval or abstention.
- Unsupported claims are removed or cause a partial answer.
- Confidence is measured from evidence and calibrated on labeled queries.
- Retrieval traces explain every decision.
- Regressions are automatically measured.
- Model failures do not remove timestamps, citations, or metadata.
- Partially built indexes are never queried.
- All API outcomes pass contract tests.

## Final Architecture Decision

VideoSceneRAG should be described as:

> A timeline-aware, multimodal, evidence-controlled agentic retrieval system that searches hierarchical video memory, verifies evidence before generation, reasons across temporal context, produces claim-level cited answers, and explicitly handles missing or unrelated questions through calibrated abstention or a clearly separated general-assistant route.
