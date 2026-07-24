# VideoSceneRAG — Phase N Production Blueprint

> Master Phase N plan. This document supersedes
> `docs/PHASE_N_BASELINE_AND_MODALITY_QUALITY_IMPLEMENTATION.md` and should be
> treated as the source of truth for evaluation repair, relevance gating,
> safe rejection, retrieval accuracy, and OCR/speaker/audio quality work.

## Evaluation Baseline Repair, Modality Evidence Quality, Relevance Detection, Safe Rejection, and Retrieval Accuracy

**Document status:** Implementation-ready architecture  
**Target project:** VideoSceneRAG  
**Primary goal:** Repair the evaluation baseline, improve OCR/speaker/audio evidence, retrieve the correct timeline evidence, and reject irrelevant or unsupported questions without rejecting valid video questions.  
**Implementation approach:** Deterministic orchestration, bounded agent components, typed contracts, calibrated thresholds, persistent traces, and regression-first development.

**Current implementation status:** N0 through N10 are implemented.

- N0 baseline freeze tooling is available in `src/pipeline/evaluation/baseline_manager.py`.
- N1 QA labels support richer Phase N fields while remaining backward-compatible with the existing QA set.
- N2 unresolved follow-up questions now carry explicit ambiguity metadata and route to clarification before retrieval.
- N3 video scope profiles are generated in `data/processed/scope_profiles/{video_id}.json` and used by the deterministic scope analyzer.
- N4 retrieval orchestration normalizes candidate metadata, records modality/index readiness, and exposes fusion/reranking margins.
- N5 answerability uses an explainable evidence-sufficiency gate and bounded corrective retrieval metadata.
- N6 timestamp and citation repair is implemented through `src/pipeline/agentic/citation_registry.py`, canonical evidence IDs, separate anchor/context/citation intervals, source-type compatibility checks, and citation validation in the evidence packet.
- N7 OCR quality is implemented through `src/pipeline/ocr_extraction.py` with frame-level provenance, token boxes, frame URI/path references, temporal OCR tracks, quality flags, and `data/processed/reports/{video_id}_ocr_quality.json`.
- N8 speaker quality is implemented through `src/pipeline/speaker_diarization.py` with smoothed speaker turns, segment provenance, parent atom links, turn quality scores, and `data/processed/reports/{video_id}_speaker_quality.json`.
- N9 audio quality is implemented through `src/pipeline/audio_event_detection.py` with speech/silence/audio-event labels, transition markers, parent atom links, event quality scores, and `data/processed/reports/{video_id}_audio_quality.json`.
- N10 calibration and regression release is implemented through `config/phase_n_thresholds.yaml` and `src/pipeline/evaluation/release_manager.py`. The release workflow snapshots thresholds, runs the QA set, compares with the latest baseline when available, checks production gates, writes release JSON/Markdown artifacts, and recommends the next repair focus. The MCP-vs-API 60-question release suite now passes every mandatory gate: outcome accuracy `1.00`, negative abstention `1.00`, timestamp hit rate `1.00`, citation presence/validity `1.00`, required-term coverage `1.00`, unsupported-claim rate `0.00`, fallback rate `0.00`, and execution failures `0`.

## N10 Citation, Timestamp, and Fallback Repair

The final N10 repair adds the following production behavior:

- Public citation windows use the primary evidence anchor, while the wider source interval and answer context remain available in the trace.
- Comparison questions can cite a bounded contiguous atomic window when the two sides of the comparison cross atom boundaries.
- OCR evidence carries extraction quality separately from retrieval relevance and preserves exact frame provenance.
- Local generation selects query-relevant evidence sentences and preserves citation IDs and timestamps when the configured provider is unavailable.
- Provider failure is traced separately from answer fallback, so a grounded deterministic answer is not mislabeled as an ungrounded fallback.
- Claim verification revises once, removes unsupported sentences, and re-verifies the remaining answer before response construction.
- API responses retain only citations that are actually referenced by the final answer.
- Modality quality warnings remain visible but do not block a release when every mandatory quality gate passes.

Final release artifacts:

```text
data/evaluation/releases/mcp_vs_api/
  n10_citation_timestamp_fallback_repair_release/
    phase_n_release_report.json
    phase_n_release_report.md
```

---

# 1. Executive Summary

The current VideoSceneRAG architecture already contains the essential pipeline:

```text
Video
 -> Manifest
 -> Timeline normalization
 -> Transcript
 -> Boundaries
 -> Atomic spans
 -> Semantic chunks
 -> Events
 -> OCR, speaker, and audio evidence
 -> ChromaDB indexes
 -> Agentic retrieval
 -> Evidence verification
 -> Temporal reasoning
 -> Grounded answer generation
 -> Evaluation reports
```

The next problem is not architectural completeness. It is **retrieval trustworthiness**.

The system currently risks:

- answering unrelated questions as though they came from the video;
- confusing “not in the video” with “unrelated to the video”;
- answering ambiguous follow-ups without enough conversation context;
- selecting a nearby but incorrect primary timestamp;
- returning citations whose source type or interval does not match the evidence;
- generating claims that are only topically related rather than directly supported;
- indexing OCR, speaker, and audio evidence without strong post-processing and quality controls.

Phase N should therefore introduce two major upgrades:

```text
A. Evaluation-driven retrieval repair
B. A relevance and answerability firewall
```

The relevance firewall must not reject a question after only one classifier or one failed vector search. Rejection is allowed only after a bounded sequence of checks:

```text
Resolve conversation references
 -> Analyze query intent and requested modality
 -> Compare query with the video scope profile
 -> Run multimodal retrieval
 -> Rerank and verify evidence
 -> Perform one corrective retrieval pass when needed
 -> Measure evidence sufficiency
 -> Select answer, partial answer, clarification, not-found, or unrelated outcome
```

The central rule is:

> **Scope classification and evidence answerability are different decisions.**

Examples:

| Question | Correct classification |
|---|---|
| “What is the capital of Japan?” asked about a Python lecture | `unrelated_to_video` |
| “Who invented Python?” when the video discusses Python but never mentions its creator | `video_evidence_not_found` |
| “Why did he draw it?” with no usable conversation reference | `ambiguous_query` |
| “What happens after the blue graph?” when OCR/visual processing failed | `processing_incomplete` |
| “What does the lecturer say about feature comparison?” with strong transcript evidence | `grounded_answer` |

This distinction is required for accurate evaluation and trustworthy user behavior.

---

# 2. Objectives

At the end of Phase N:

1. Unrelated questions in strict-video mode return `unrelated_to_video`.
2. Questions related to the video’s topic but unsupported by the video return `video_evidence_not_found`.
3. Ambiguous questions without usable context return `ambiguous_query`.
4. Valid questions are not rejected merely because one retriever fails.
5. Retrieval runs across the modalities required by the question.
6. Primary timestamps identify the best evidence anchor, not merely the highest-scoring broad chunk.
7. Citations are generated from verified source records and validated claim-by-claim.
8. OCR records are deduplicated, temporally merged, confidence-scored, and linked to atoms/chunks/events.
9. Speaker turns are smoothed, overlap-aware, confidence-scored, and linked to words and atoms.
10. Audio events distinguish speech, silence, pauses, transitions, and meaningful acoustic events.
11. Each modality produces a versioned quality report.
12. Evaluation reports compare the repaired system against a frozen baseline.
13. Thresholds are calibrated from validation data rather than permanently hard-coded.
14. Every rejection includes a machine-readable reason and an auditable retrieval trace.

---

# 3. Non-Goals

Phase N should not yet add:

- heavyweight video-language model inference over every clip;
- semantic event segmentation transformers;
- world-model memory;
- cross-video entity graphs;
- autonomous web search;
- long-running open-ended agents;
- model fine-tuning before evaluation labels are stable.

These features should be added only after retrieval, rejection, timestamping, and citation quality are measurable and stable.

---

# 4. Core Design Principles

## 4.1 Evidence before generation

The answer model receives only verified evidence. A high vector similarity score is not proof that the evidence answers the question.

## 4.2 Rejection is a pipeline decision

The answer LLM must not independently decide whether a query is irrelevant. Rejection is made by a deterministic policy using multiple signals.

## 4.3 Conservative early rejection

A pre-retrieval scope gate may immediately reject only extremely clear unrelated questions. Borderline queries must proceed to retrieval.

## 4.4 Corrective retrieval before abstention

When a question appears related but evidence is weak, perform one bounded corrective pass:

- rewrite the query;
- search exact terms;
- search a missing modality;
- expand the temporal window;
- search parent events/chapters;
- resolve speaker or entity aliases.

## 4.5 Distinguish relevance from support

A query can be topically relevant but unsupported by the video.

```text
Topic relevance != answer evidence
```

## 4.6 Modality-specific evidence

Do not collapse transcript, OCR, speaker, audio, visual, and event evidence into one uncontrolled caption.

## 4.7 Fine-grained citations

Every factual answer sentence or atomic claim must identify its supporting evidence IDs.

## 4.8 Trace every decision

Store:

- query resolution;
- scope signals;
- retrieval plan;
- raw candidates;
- reranking scores;
- verification decisions;
- corrective actions;
- answerability scores;
- citations;
- claim verification;
- final outcome.

---

# 5. Revised Outcome Taxonomy

Every request must end in exactly one primary outcome.

```text
grounded_answer
partial_answer
video_evidence_not_found
unrelated_to_video
ambiguous_query
conflicting_evidence
processing_incomplete
unsupported_query_type
system_error
```

## 5.1 `grounded_answer`

Use when verified evidence fully supports the requested answer.

Requirements:

- answer coverage is sufficient;
- at least one verified primary source exists;
- timestamp is valid when the question is temporal;
- citations support all factual claims;
- contradiction score is below threshold.

## 5.2 `partial_answer`

Use when the video supports only part of a multi-part question.

Example:

```text
The video explains why the graph was drawn, but it does not state who originally created the method.
```

## 5.3 `video_evidence_not_found`

Use when the query is related to the video or its topic, but the indexed content does not provide enough evidence.

Example:

```text
The video discusses Python, but I could not find a reliable moment that states who invented it.
```

## 5.4 `unrelated_to_video`

Use when the query is outside the selected video’s subject, entities, timeline, conversation, and retrievable evidence.

Example:

```text
That question does not appear to be related to the selected video.
```

## 5.5 `ambiguous_query`

Use when:

- pronouns cannot be resolved;
- multiple timeline moments are equally plausible;
- the user asks “why did he do that?” without prior context;
- the request is missing a required entity, speaker, object, or timestamp.

## 5.6 `conflicting_evidence`

Use when transcript, OCR, visual, speaker, or timeline evidence materially disagrees.

## 5.7 `processing_incomplete`

Use when the requested evidence depends on a modality that is missing, failed, stale, or below minimum quality.

Example:

```text
OCR processing is incomplete, so I cannot reliably identify the text shown on that slide.
```

---

# 6. Relevance and Answerability Firewall

The firewall is the most important new architecture component.

```text
Question
 -> Conversation Resolver
 -> Query Analyzer
 -> Required-Modality Detector
 -> Video Scope Matcher
 -> Retrieval Planner
 -> Multimodal Retrieval
 -> Candidate Reranker
 -> Evidence Verifier
 -> Corrective Retrieval Controller
 -> Evidence Sufficiency Gate
 -> Outcome Policy
```

The firewall uses four separate gates.

---

# 7. Gate 1 — Conversation and Reference Resolution

## Purpose

Convert the user’s message into a standalone query before relevance classification.

Example:

```text
Previous:
User: Where was the blue graph shown?
Assistant: Around 02:41:16.

Current:
User: Why did he draw it?
```

Resolved query:

```text
Why did the lecturer draw the blue graph shown around 02:41:16?
```

## Resolution output

```json
{
  "raw_query": "Why did he draw it?",
  "standalone_query": "Why did the lecturer draw the blue graph shown around 02:41:16?",
  "resolved_entities": ["blue graph", "lecturer"],
  "resolved_time_hints_ms": [9676000],
  "resolution_confidence": 0.94,
  "unresolved_references": []
}
```

## Ambiguity rule

Return `ambiguous_query` only when:

```text
unresolved_references exist
AND resolution_confidence < configured threshold
AND retrieval cannot disambiguate them
```

Do not reject a follow-up merely because it contains a pronoun.

---

# 8. Gate 2 — Video Scope Matching

## 8.1 Video Scope Profile

Create a compact profile after indexing each video.

```json
{
  "video_id": "video_001",
  "title": "MCP vs API",
  "language": "en",
  "duration_ms": 1250000,
  "chapter_titles": [
    "Introduction",
    "Model reasoning layer",
    "MCP and API comparison"
  ],
  "event_summaries": [
    "The speaker introduces model context",
    "The speaker compares MCP with direct API calls"
  ],
  "top_entities": [
    "MCP",
    "API",
    "model reasoning",
    "tools",
    "context"
  ],
  "speakers": ["speaker_00"],
  "ocr_vocabulary": [
    "Model",
    "Tools",
    "Context",
    "MCP"
  ],
  "audio_event_types": ["speech", "pause"],
  "topic_keywords": [
    "protocol",
    "integration",
    "reasoning",
    "API"
  ],
  "scope_summary": "A technical explanation comparing MCP and APIs in model-tool integration.",
  "scope_embedding_version": "scope_v2"
}
```

Store:

```text
data/processed/scope_profiles/{video_id}.json
```

## 8.2 Scope signals

Compute independent signals:

```text
scope_embedding_similarity
entity_overlap_score
keyword_overlap_score
chapter_event_match_score
conversation_reference_score
timestamp_reference_score
speaker_reference_score
visual_hint_match_score
```

## 8.3 Scope score

Initial formula:

```text
scope_score =
    0.35 * scope_embedding_similarity
  + 0.20 * entity_overlap_score
  + 0.10 * keyword_overlap_score
  + 0.15 * chapter_event_match_score
  + 0.10 * conversation_reference_score
  + 0.05 * timestamp_reference_score
  + 0.05 * visual_hint_match_score
```

These weights are starting values only. Calibrate them from the validation set.

## 8.4 High-confidence unrelated fast path

A query may be rejected before full retrieval only when all are true:

```text
scope_score < strict_unrelated_threshold
entity_overlap_score == 0
conversation_reference_score == 0
timestamp_reference_score == 0
query is not a system/help command
query is not ambiguous
```

Recommended initial threshold:

```yaml
strict_unrelated_threshold: 0.12
```

This fast path should be intentionally conservative.

## 8.5 Borderline scope

When:

```text
strict_unrelated_threshold <= scope_score < probable_related_threshold
```

do not reject. Run retrieval and let the evidence gate decide.

---

# 9. Gate 3 — Multimodal Retrieval and Evidence Verification

## 9.1 Required modality detection

Map the query to evidence requirements.

| Query clue | Required modality | Supporting modality |
|---|---|---|
| “said”, quote, explain | transcript | speaker, event |
| “slide”, “text”, “code”, “label” | OCR | visual, transcript |
| “who said” | speaker + transcript | event |
| “sound”, “music”, “applause”, “silence” | audio event | transcript |
| “graph”, “red object”, “diagram” | visual/OCR | transcript |
| “before”, “after”, “later” | temporal hierarchy | transcript/event |
| “summarize” | event/chapter | transcript |
| exact timestamp | timeline lookup | neighboring atoms |

## 9.2 Parallel retrievers

Run only the retrievers relevant to the plan, plus one fallback retriever.

```text
exact_timeline_retriever
dense_transcript_retriever
sparse_keyword_retriever
ocr_retriever
speaker_retriever
audio_event_retriever
visual_retriever
semantic_chunk_retriever
event_retriever
chapter_retriever
entity_retriever
```

## 9.3 Candidate normalization

Every retriever returns the same structure.

```json
{
  "candidate_id": "cand_000041",
  "video_id": "video_001",
  "source_id": "chunk_000008",
  "source_type": "semantic_chunk",
  "start_ms": 299925,
  "end_ms": 335965,
  "retrieval_source": "semantic_chunk_dense",
  "raw_score": 0.79,
  "normalized_score": 0.83,
  "rank": 1,
  "text": "The speaker explains MCP as a protocol layer...",
  "entity_matches": ["MCP", "protocol"],
  "evidence_modalities": ["transcript"],
  "parent_atom_ids": ["atom_000041", "atom_000042"],
  "parent_event_id": "event_000004",
  "pipeline_version": "2.1.0",
  "index_version": "index_20260724_01"
}
```

## 9.4 Fusion

Do not directly add raw cosine scores from different models.

Use weighted Reciprocal Rank Fusion:

```text
RRF(candidate) =
  sum over retrievers:
    retriever_weight / (rrf_k + rank)
```

Query-specific weights:

```yaml
visual_memory:
  visual: 1.5
  ocr: 1.2
  event: 1.0
  transcript: 0.8

exact_quote:
  sparse_transcript: 1.6
  dense_transcript: 1.2
  speaker: 0.8

speaker_question:
  speaker: 1.5
  transcript: 1.2
  event: 0.7

audio_question:
  audio_event: 1.6
  transcript: 0.7
  event: 0.6
```

## 9.5 Reranking

Rerank the fused top candidates with a query-candidate model or deterministic scoring layer.

Reranking inputs:

```text
query
candidate transcript
OCR text
visual summary
speaker label
audio event
event summary
time hints
entity matches
```

Reranking should output:

```json
{
  "candidate_id": "cand_000041",
  "query_relevance": 0.91,
  "answer_likelihood": 0.86,
  "entity_coverage": 1.0,
  "temporal_alignment": 0.88,
  "modality_match": 1.0,
  "rerank_score": 0.90
}
```

## 9.6 Evidence verification

Verification checks:

- requested `video_id` matches;
- timeline is valid;
- source artifact exists;
- pipeline/index versions are compatible;
- required modality is actually present;
- query entities are supported;
- evidence is not duplicate;
- evidence is not merely topically related;
- OCR/speaker/audio confidence meets minimum quality;
- parent relationships resolve;
- citation interval is within video duration.

Verification status:

```text
strong
moderate
weak
rejected
```

Explicit rejection reasons:

```text
wrong_video
stale_index
invalid_timeline
missing_source
missing_required_modality
weak_query_match
topic_only_no_answer
duplicate_candidate
low_ocr_confidence
low_speaker_confidence
low_audio_confidence
entity_mismatch
time_hint_mismatch
```

---

# 10. Gate 4 — Corrective Retrieval and Evidence Sufficiency

## 10.1 Why corrective retrieval is required

A weak first search does not prove that a query is irrelevant.

Possible reasons for weak retrieval:

- ASR spelling error;
- OCR normalization error;
- entity alias mismatch;
- wrong retrieval granularity;
- visual clue not present in transcript;
- answer spread across neighboring atoms;
- broad event retrieved instead of precise atom;
- speaker label missing;
- query requires a later repeated occurrence.

## 10.2 Corrective actions

Allow at most one normal corrective pass and one emergency exact-search pass.

```text
query rewrite
entity alias expansion
acronym expansion
exact keyword search
OCR-only search
speaker-filtered search
audio-event search
parent event expansion
neighbor atom expansion
chapter search
search repeated entity occurrences
```

## 10.3 Corrective plan object

```json
{
  "correction_required": true,
  "reason": "missing_required_visual_support",
  "actions": [
    "expand_visual_aliases",
    "search_ocr",
    "expand_neighbor_atoms"
  ],
  "max_additional_candidates": 20,
  "retry_number": 1
}
```

## 10.4 Evidence sufficiency score

Compute answerability from a set of verified evidence, not only the top result.

```text
evidence_sufficiency =
    0.22 * top_rerank_score
  + 0.15 * top_k_consensus
  + 0.15 * required_modality_coverage
  + 0.14 * entity_coverage
  + 0.12 * temporal_alignment
  + 0.10 * source_quality
  + 0.07 * evidence_diversity
  + 0.05 * retrieval_margin
  - contradiction_penalty
  - uncertainty_penalty
```

Supporting diagnostics:

```json
{
  "top_rerank_score": 0.91,
  "top_k_consensus": 0.80,
  "required_modality_coverage": 1.0,
  "entity_coverage": 1.0,
  "temporal_alignment": 0.88,
  "source_quality": 0.93,
  "evidence_diversity": 0.72,
  "retrieval_margin": 0.64,
  "contradiction_penalty": 0.0,
  "uncertainty_penalty": 0.03,
  "evidence_sufficiency": 0.87
}
```

## 10.5 Decision policy

Initial thresholds:

```yaml
answerable_threshold: 0.72
partial_threshold: 0.55
retry_threshold: 0.38
not_found_threshold: 0.24
```

Decision order:

```text
1. Required processing unavailable
   -> processing_incomplete

2. Unresolved references and no dominant interpretation
   -> ambiguous_query

3. Strong contradictory evidence
   -> conflicting_evidence

4. Evidence sufficiency >= answerable_threshold
   -> grounded_answer

5. Evidence covers only part of requested claims
   -> partial_answer

6. Scope appears related but evidence remains insufficient after correction
   -> video_evidence_not_found

7. Scope is very low and all retrievers produce no credible support
   -> unrelated_to_video

8. Otherwise
   -> ambiguous_query or video_evidence_not_found, whichever diagnostics support
```

## 10.6 Critical rejection rule

Return `unrelated_to_video` only when:

```text
scope_score is very low
AND no conversation/timestamp reference exists
AND no verified evidence exists
AND corrective retrieval does not find support
AND the query is not simply asking for absent information about a video topic
```

This rule prevents false rejection of valid but difficult questions.

---

# 11. Irrelevance Reason Classifier

Every rejected question must explain why it was rejected internally.

## 11.1 Reason codes

```text
OUTSIDE_VIDEO_TOPIC
NO_SHARED_ENTITIES
NO_TIMELINE_REFERENCE
NO_CONVERSATION_REFERENCE
NO_RETRIEVAL_SUPPORT
GENERAL_KNOWLEDGE_REQUEST
UNSUPPORTED_EXTERNAL_FACT
MISSING_REFERENCE
MULTIPLE_POSSIBLE_REFERENTS
REQUIRED_MODALITY_UNAVAILABLE
RELATED_TOPIC_NOT_STATED
CONTRADICTORY_EVIDENCE
```

## 11.2 Example internal result

```json
{
  "outcome": "unrelated_to_video",
  "reason_codes": [
    "OUTSIDE_VIDEO_TOPIC",
    "NO_SHARED_ENTITIES",
    "NO_RETRIEVAL_SUPPORT"
  ],
  "scope_score": 0.05,
  "best_verified_score": 0.09,
  "corrective_retrieval_used": true,
  "user_message": "That question does not appear to be related to the selected video."
}
```

## 11.3 Related but absent example

```json
{
  "outcome": "video_evidence_not_found",
  "reason_codes": [
    "UNSUPPORTED_EXTERNAL_FACT",
    "RELATED_TOPIC_NOT_STATED"
  ],
  "scope_score": 0.71,
  "best_verified_score": 0.18,
  "user_message": "The question is related to the video's topic, but I could not find reliable evidence that the video states this information."
}
```

---

# 12. Evaluation Baseline Repair

## 12.1 Freeze the baseline

Before changing behavior, save:

```text
data/evaluation/baselines/{date}/
```

Include:

- commit hash;
- configuration;
- model versions;
- index versions;
- QA set version;
- evaluation report;
- per-question traces.

## 12.2 Evaluation record contract

```json
{
  "question_id": "q_neg_001",
  "video_id": "mcp_vs_api",
  "query": "What is the capital of Japan?",
  "expected_outcome": "unrelated_to_video",
  "acceptable_outcomes": ["unrelated_to_video"],
  "forbidden_outcomes": ["grounded_answer"],
  "requires_timestamp": false,
  "requires_citation": false,
  "expected_source_types": [],
  "negative_category": "outside_domain",
  "notes": "Clearly unrelated general knowledge query."
}
```

## 12.3 Positive question labels

```json
{
  "question_id": "q_pos_001",
  "video_id": "mcp_vs_api",
  "query": "How does the speaker describe MCP?",
  "expected_outcome": "grounded_answer",
  "expected_time_windows": [
    {
      "start_ms": 299000,
      "end_ms": 336000
    }
  ],
  "acceptable_source_types": [
    "atomic_span",
    "semantic_chunk",
    "event"
  ],
  "required_concepts": [
    ["MCP"],
    ["protocol", "connection", "context"]
  ],
  "requires_timestamp": true,
  "requires_citation": true
}
```

## 12.4 Negative question categories

The QA set must contain:

```text
outside_domain
related_topic_but_absent
entity_not_in_video
wrong_video
false_presupposition
unresolved_pronoun
missing_timestamp_reference
unsupported_comparison
unsupported_causal_question
required_modality_missing
adversarial_keyword_overlap
general_knowledge_about_video_entity
```

## 12.5 Hard negatives

Hard negatives must share words with the video while remaining unsupported.

Example for a video about MCP:

```text
Which company patented the MCP protocol in 2018?
```

The words may overlap, but the claim may not exist in the video.

## 12.6 Contrastive question pairs

Use paired tests:

```text
Answerable:
"What does the speaker compare MCP with?"

Unanswerable:
"Which benchmark proves MCP is faster than every API?"
```

This checks whether the system distinguishes topical similarity from actual support.

---

# 13. Evaluation Metrics

## 13.1 Outcome metrics

```text
outcome_accuracy
macro_f1_by_outcome
negative_abstention_rate
unrelated_rejection_precision
unrelated_rejection_recall
not_found_precision
ambiguity_detection_accuracy
partial_answer_accuracy
false_rejection_rate
unsafe_answer_rate
```

The most important paired metrics are:

```text
Answerable coverage
Selective risk
```

A system that rejects every question has high abstention but no usefulness.

## 13.2 Retrieval metrics

```text
Recall@1
Recall@3
Recall@5
MRR
nDCG@5
top_k_evidence_coverage
retrieval_margin
modality_recall
```

## 13.3 Temporal metrics

```text
timestamp_hit_rate
mean_absolute_timestamp_error_ms
median_timestamp_error_ms
temporal_IoU
primary_anchor_accuracy
event_coverage
```

## 13.4 Citation metrics

```text
citation_presence_rate
citation_source_validity
citation_interval_validity
citation_entailment_rate
claim_citation_coverage
unsupported_claim_rate
citation_precision
citation_recall
```

## 13.5 Calibration metrics

```text
Brier score
Expected Calibration Error
risk-coverage curve
confidence by outcome
false-confidence rate
```

## 13.6 Modality quality metrics

OCR:

```text
OCR token precision
OCR token recall
duplicate OCR rate
stable-text merge accuracy
timeline-link accuracy
low-confidence rejection accuracy
```

Speaker:

```text
speaker turn purity
speaker confusion rate
word-to-speaker assignment accuracy
short-turn fragmentation rate
overlap detection accuracy
```

Audio:

```text
speech/silence F1
pause boundary accuracy
audio transition precision
event type precision/recall
false event rate per minute
```

---

# 14. Timestamp Repair Architecture

## 14.1 Separate three intervals

Every answer should distinguish:

```text
evidence_anchor
answer_context_window
citation_interval
```

Example:

```json
{
  "evidence_anchor": {
    "start_ms": 9676000,
    "end_ms": 9684000
  },
  "answer_context_window": {
    "start_ms": 9652000,
    "end_ms": 9802000
  },
  "citation_interval": {
    "start_ms": 9668000,
    "end_ms": 9692000
  }
}
```

The clickable timestamp should normally use the evidence anchor.

## 14.2 Primary timestamp selector

Select the anchor using:

```text
query-required modality
rerank score
claim support
entity/action occurrence
time-hint distance
source granularity
OCR/speaker/audio confidence
```

Do not use the beginning of a broad event as the answer timestamp if a precise atom exists.

## 14.3 Timestamp selection score

```text
timestamp_anchor_score =
    0.30 * claim_support
  + 0.20 * modality_match
  + 0.18 * rerank_score
  + 0.14 * entity_action_localization
  + 0.10 * time_hint_alignment
  + 0.08 * source_granularity
```

## 14.4 Citation interval rules

- Atomic span citation: exact atom interval.
- Semantic chunk citation: only when the complete chunk supports the claim.
- Event citation: use only for broad event-level claims.
- OCR citation: use the stabilized OCR occurrence interval.
- Speaker citation: use the linked transcript turn interval.
- Audio citation: use the detected event interval plus a small configured padding.

---

# 15. Citation Validity Repair

## 15.1 Canonical source registry

Create one registry for every evidence item.

```text
data/processed/evidence_registry/{video_id}.jsonl
```

Record:

```json
{
  "evidence_id": "E_OCR_000031",
  "source_type": "ocr_track",
  "source_id": "ocr_track_000031",
  "video_id": "video_001",
  "start_ms": 9671000,
  "end_ms": 9689000,
  "parent_atom_ids": ["atom_000145", "atom_000146"],
  "parent_chunk_id": "chunk_000052",
  "parent_event_id": "event_000010",
  "artifact_uri": "data/processed/ocr/video_001/ocr_tracks.json",
  "pipeline_version": "2.1.0",
  "quality_score": 0.91
}
```

## 15.2 Citation creation rule

The LLM never creates source IDs or timestamps.

It emits only allowed evidence IDs:

```text
[S1]
[S2]
```

The backend maps each ID to the canonical source registry.

## 15.3 Claim-level verification

Pipeline:

```text
generated answer
 -> split into atomic claims
 -> attach candidate citations
 -> run entailment/support verification
 -> remove or revise unsupported claims
 -> regenerate once if necessary
 -> abstain if support remains inadequate
```

Claim result:

```json
{
  "claim_id": "claim_02",
  "text": "The blue graph is used to explain feature separation.",
  "status": "supported",
  "supporting_evidence_ids": ["E_VIS_00014", "E_TXT_00052"],
  "entailment_score": 0.88
}
```

## 15.4 Source-type compatibility

Define allowed source types by claim type.

```yaml
claim_source_compatibility:
  spoken_statement:
    - transcript_turn
    - atomic_span
    - semantic_chunk
  visible_text:
    - ocr_track
    - frame_evidence
  speaker_identity:
    - speaker_turn
    - transcript_turn
  acoustic_event:
    - audio_event
  broad_summary:
    - event
    - chapter
  visual_action:
    - visual_evidence
    - clip_evidence
```

A visible-text claim should not be validated only by an event summary generated from transcript.

---

# 16. Required Concept Coverage Repair

Evaluation should not require exact wording when synonyms are valid.

Replace one flat `required_terms` list with concept groups.

```json
{
  "required_concepts": [
    ["MCP"],
    ["protocol", "connection layer", "integration layer"],
    ["tools", "context"]
  ]
}
```

Coverage score:

```text
matched_concept_groups / total_concept_groups
```

Do not force the answer generator to insert a term unsupported by evidence merely to pass evaluation.

---

# 17. OCR Evidence Quality Pipeline

## 17.1 OCR input selection

Run OCR on:

- slide-change frames;
- high-text-density frames;
- representative first/middle/last frames;
- frames where OCR layout changes;
- user-retrieved frames during corrective search.

Avoid OCR on every frame unless necessary.

## 17.2 Raw OCR record

```json
{
  "frame_id": "frame_000145_02",
  "timestamp_ms": 9676200,
  "text": "Feature Comparison",
  "normalized_text": "feature comparison",
  "bbox": [132, 54, 712, 130],
  "engine_confidence": 0.92,
  "frame_quality": 0.88,
  "text_size_score": 0.81,
  "language": "en"
}
```

## 17.3 OCR normalization

Normalize:

- Unicode;
- whitespace;
- line breaks;
- repeated punctuation;
- common OCR substitutions;
- case for search while preserving raw text;
- hyphenated line breaks;
- code and mathematical symbols carefully.

Keep both:

```text
raw_text
normalized_text
```

## 17.4 Temporal OCR tracking

Merge the same text across consecutive frames.

OCR track identity uses:

```text
normalized text similarity
bounding-box overlap
screen-region consistency
temporal proximity
font/size similarity when available
```

Example:

```json
{
  "ocr_track_id": "ocr_track_000031",
  "canonical_text": "Feature Comparison",
  "start_ms": 9669000,
  "end_ms": 9691000,
  "occurrence_count": 8,
  "mean_engine_confidence": 0.91,
  "stability_score": 0.94,
  "linked_atom_ids": ["atom_000145", "atom_000146"]
}
```

## 17.5 OCR quality score

```text
ocr_quality =
    0.35 * engine_confidence
  + 0.20 * temporal_stability
  + 0.15 * frame_quality
  + 0.10 * text_size_score
  + 0.10 * language_consistency
  + 0.10 * semantic_consistency
```

## 17.6 OCR deduplication

Suppress:

- identical tracks with high temporal overlap;
- watermark text repeated for the entire video;
- player controls;
- timestamps from the player UI;
- low-confidence single-frame noise;
- text outside configured content regions when appropriate.

Mark persistent overlays:

```text
watermark
subtitle
channel logo
player UI
```

These should be searchable only under explicit policy.

## 17.7 OCR report

Write:

```text
data/processed/reports/{video_id}_ocr_quality.json
```

Include:

```json
{
  "raw_detection_count": 1940,
  "normalized_detection_count": 1610,
  "stable_track_count": 142,
  "duplicate_suppression_rate": 0.71,
  "low_confidence_rejection_count": 88,
  "persistent_overlay_count": 4,
  "timeline_link_success_rate": 0.99,
  "mean_track_quality": 0.86
}
```

---

# 18. Speaker Evidence Quality Pipeline

## 18.1 Processing flow

```text
audio
 -> voice activity detection
 -> diarization segments
 -> transcription words
 -> temporal word-speaker alignment
 -> turn smoothing
 -> short-turn merging
 -> overlap handling
 -> atom/chunk/event linking
```

## 18.2 Speaker turn record

```json
{
  "speaker_turn_id": "speaker_turn_000081",
  "speaker_id": "speaker_00",
  "start_ms": 299925,
  "end_ms": 315200,
  "word_ids": ["word_01021", "word_01022"],
  "text": "MCP creates a common protocol layer...",
  "diarization_confidence": 0.88,
  "word_alignment_confidence": 0.93,
  "turn_quality": 0.90,
  "overlap_status": "none",
  "linked_atom_ids": ["atom_000041"]
}
```

## 18.3 Turn smoothing rules

Merge adjacent same-speaker turns when:

```text
gap <= same_speaker_merge_gap_ms
AND no strong speaker-change evidence
AND acoustic similarity remains high
```

Suppress micro-turns when:

```text
duration < minimum_turn_ms
AND word_count is very low
AND neighboring speaker confidence is stronger
```

Do not merge when:

- an interruption is meaningful;
- overlapping speech exists;
- a clear speaker transition occurs;
- the gap contains a long pause.

## 18.4 Speaker aliases

Allow user-defined names:

```json
{
  "speaker_00": {
    "display_name": "Lecturer",
    "aliases": ["speaker", "presenter", "teacher"]
  }
}
```

Never infer a real identity without evidence.

## 18.5 Speaker quality score

```text
speaker_turn_quality =
    0.35 * diarization_confidence
  + 0.25 * word_alignment_confidence
  + 0.15 * acoustic_consistency
  + 0.15 * turn_duration_quality
  + 0.10 * neighboring_turn_consistency
```

## 18.6 Overlap handling

Represent:

```text
none
possible_overlap
confirmed_overlap
```

For confirmed overlap, allow multiple speaker IDs over the same interval.

## 18.7 Speaker report

```text
data/processed/reports/{video_id}_speaker_quality.json
```

Include:

```json
{
  "speaker_count": 2,
  "raw_segment_count": 248,
  "smoothed_turn_count": 171,
  "short_turn_merge_count": 51,
  "possible_overlap_count": 6,
  "word_assignment_rate": 0.97,
  "mean_turn_quality": 0.88,
  "low_confidence_turn_count": 9
}
```

---

# 19. Audio Evidence Quality Pipeline

## 19.1 Audio evidence taxonomy

Core classes:

```text
speech
silence
short_pause
long_pause
music
applause
laughter
alarm
impact
footsteps
door
vehicle
environmental_noise
audio_transition
unknown
```

Start with reliable classes before adding a large event vocabulary.

## 19.2 Silence and pause definitions

Configure by video type.

Example lecture profile:

```yaml
short_pause_ms:
  min: 300
  max: 1200

long_pause_ms:
  min: 1200
```

Do not classify every VAD gap as a meaningful event.

## 19.3 Acoustic transition detection

Detect:

- music starts/stops;
- microphone change;
- scene audio transition;
- sudden energy change;
- background environment change.

Transition signals:

```text
spectral distance
energy change
embedding change
VAD state change
music probability change
```

## 19.4 Audio event record

```json
{
  "audio_event_id": "audio_event_000031",
  "event_type": "applause",
  "start_ms": 775200,
  "end_ms": 779600,
  "model_confidence": 0.89,
  "temporal_stability": 0.86,
  "context_consistency": 0.80,
  "quality_score": 0.86,
  "linked_atom_ids": ["atom_000112"],
  "linked_event_id": "event_000021"
}
```

## 19.5 Audio quality score

```text
audio_event_quality =
    0.45 * model_confidence
  + 0.20 * temporal_stability
  + 0.15 * context_consistency
  + 0.10 * signal_quality
  + 0.10 * neighboring_event_consistency
```

## 19.6 Audio deduplication

Merge adjacent same-type events when the gap is below a class-specific threshold.

Avoid indexing:

- tiny low-confidence events;
- repeated background hum;
- constant room noise;
- VAD fragments with no semantic value.

## 19.7 Audio report

```text
data/processed/reports/{video_id}_audio_quality.json
```

Include:

```json
{
  "speech_duration_ratio": 0.82,
  "silence_duration_ratio": 0.11,
  "pause_count": 86,
  "semantic_audio_event_count": 14,
  "suppressed_noise_event_count": 132,
  "transition_count": 9,
  "mean_event_quality": 0.84
}
```

---

# 20. Modality Readiness and Quality Gates

Create:

```text
data/processed/reports/{video_id}_modality_readiness.json
```

Example:

```json
{
  "transcript": {
    "status": "ready",
    "quality": 0.92
  },
  "ocr": {
    "status": "ready_with_warnings",
    "quality": 0.74,
    "warnings": ["high persistent overlay rate"]
  },
  "speaker": {
    "status": "ready",
    "quality": 0.86
  },
  "audio": {
    "status": "ready",
    "quality": 0.83
  },
  "visual": {
    "status": "ready",
    "quality": 0.80
  }
}
```

Allowed statuses:

```text
not_started
processing
ready
ready_with_warnings
failed
stale
```

The retrieval planner must inspect readiness before selecting a modality.

---

# 21. Agentic Retrieval Architecture for Phase N

Use bounded components, not unrestricted autonomous agents.

```text
QueryResolver
ScopeAnalyzer
RetrievalPlanner
RetrievalOrchestrator
CandidateFusion
EvidenceReranker
EvidenceVerifier
CorrectiveRetrievalController
AnswerabilityJudge
TemporalAnchorSelector
EvidencePacketBuilder
GroundedAnswerGenerator
ClaimCitationVerifier
ConfidenceCalibrator
ResponsePolicy
TraceWriter
```

## 21.1 State machine

```text
RECEIVED
 -> RESOLVED
 -> SCOPE_ANALYZED
 -> PLANNED
 -> RETRIEVED
 -> RERANKED
 -> VERIFIED
 -> CORRECTED (optional)
 -> ANSWERABILITY_DECIDED
 -> TEMPORALLY_GROUNDED
 -> GENERATED
 -> CLAIMS_VERIFIED
 -> CALIBRATED
 -> COMPLETED
```

Failure states:

```text
AMBIGUOUS
UNRELATED
NOT_FOUND
PROCESSING_INCOMPLETE
CONFLICTING
FAILED_SAFE
```

## 21.2 Typed workflow state

```json
{
  "trace_id": "trace_20260724_001",
  "video_id": "video_001",
  "query": {},
  "scope_analysis": {},
  "retrieval_plan": {},
  "raw_candidates": [],
  "fused_candidates": [],
  "verified_evidence": [],
  "corrective_actions": [],
  "answerability": {},
  "temporal_context": {},
  "generated_answer": {},
  "claim_verification": {},
  "confidence": {},
  "final_response": {}
}
```

---

# 22. Retrieval Trace Contract

Store:

```text
data/processed/retrieval_traces/{video_id}/{trace_id}.json
```

Required fields:

```json
{
  "trace_id": "trace_20260724_001",
  "video_id": "video_001",
  "query": "Who invented Python?",
  "resolved_query": "Who invented Python?",
  "query_types": ["external_fact_question"],
  "required_modalities": ["transcript"],
  "scope_analysis": {
    "scope_score": 0.71,
    "matched_entities": ["Python"]
  },
  "retrieval_attempts": [
    {
      "attempt": 1,
      "collections": ["timeline_text", "events"],
      "candidate_count": 20
    },
    {
      "attempt": 2,
      "reason": "related_topic_but_insufficient_support",
      "actions": ["exact_keyword_search", "chapter_expansion"],
      "candidate_count": 8
    }
  ],
  "best_verified_score": 0.19,
  "answerability": {
    "outcome": "video_evidence_not_found",
    "reason_codes": [
      "RELATED_TOPIC_NOT_STATED",
      "UNSUPPORTED_EXTERNAL_FACT"
    ]
  }
}
```

---

# 23. API Response Contract

## 23.1 Grounded answer

```json
{
  "outcome": "grounded_answer",
  "answer": "The speaker describes MCP as a protocol layer that connects tools and context to the model reasoning layer. [S1]",
  "video_id": "video_001",
  "primary_timestamp_ms": 299925,
  "primary_interval": {
    "start_ms": 299925,
    "end_ms": 315200
  },
  "citations": [
    {
      "citation_id": "S1",
      "evidence_id": "E_TXT_00041",
      "source_type": "transcript_turn",
      "start_ms": 299925,
      "end_ms": 315200
    }
  ],
  "confidence": {
    "overall": 0.88,
    "label": "high"
  },
  "trace_id": "trace_20260724_001"
}
```

## 23.2 Unrelated question

```json
{
  "outcome": "unrelated_to_video",
  "answer": "That question does not appear to be related to the selected video.",
  "video_id": "video_001",
  "primary_timestamp_ms": null,
  "citations": [],
  "confidence": {
    "overall": 0.94,
    "label": "high"
  },
  "reason_codes": [
    "OUTSIDE_VIDEO_TOPIC",
    "NO_SHARED_ENTITIES",
    "NO_RETRIEVAL_SUPPORT"
  ],
  "trace_id": "trace_20260724_002"
}
```

## 23.3 Related but absent

```json
{
  "outcome": "video_evidence_not_found",
  "answer": "The question is related to the video's topic, but I could not find reliable evidence that the video states this information.",
  "video_id": "video_001",
  "primary_timestamp_ms": null,
  "citations": [],
  "confidence": {
    "overall": 0.83,
    "label": "high"
  },
  "reason_codes": [
    "RELATED_TOPIC_NOT_STATED"
  ],
  "trace_id": "trace_20260724_003"
}
```

## 23.4 Ambiguous question

```json
{
  "outcome": "ambiguous_query",
  "answer": "I could not determine what “it” refers to. Please mention the object, topic, or approximate timestamp.",
  "video_id": "video_001",
  "citations": [],
  "clarification": {
    "missing_fields": ["referenced_entity"]
  },
  "trace_id": "trace_20260724_004"
}
```

---

# 24. Configuration

Create:

```text
config/phase_n_thresholds.yaml
```

Example:

```yaml
scope:
  strict_unrelated_threshold: 0.12
  probable_related_threshold: 0.34
  reference_resolution_threshold: 0.72

retrieval:
  dense_top_k: 25
  sparse_top_k: 25
  modality_top_k: 15
  rerank_top_k: 12
  final_evidence_k: 6
  rrf_k: 60

corrective_retrieval:
  max_normal_retries: 1
  allow_exact_search_fallback: true
  max_extra_candidates: 20

answerability:
  answerable_threshold: 0.72
  partial_threshold: 0.55
  retry_threshold: 0.38
  not_found_threshold: 0.24
  contradiction_threshold: 0.55

deduplication:
  merge_tiou_threshold: 0.70
  suppress_tiou_threshold: 0.85
  semantic_duplicate_threshold: 0.92

ocr:
  minimum_track_quality: 0.55
  persistent_overlay_ratio: 0.75
  temporal_merge_gap_ms: 800

speaker:
  minimum_turn_quality: 0.55
  same_speaker_merge_gap_ms: 700
  minimum_turn_ms: 500

audio:
  minimum_event_quality: 0.58
  merge_gap_ms: 500

citation:
  minimum_entailment_score: 0.70
  minimum_claim_coverage: 0.90

confidence:
  high_threshold: 0.80
  moderate_threshold: 0.55
```

All threshold values must appear in evaluation artifacts.

---

# 25. Suggested Repository Structure

```text
src/
├── query/
│   ├── conversation_resolver.py
│   ├── query_analyzer.py
│   ├── modality_detector.py
│   └── scope_analyzer.py
│
├── retrieval/
│   ├── planner.py
│   ├── orchestrator.py
│   ├── candidate_schema.py
│   ├── fusion.py
│   ├── reranker.py
│   ├── evidence_verifier.py
│   ├── corrective_retrieval.py
│   ├── answerability.py
│   └── temporal_anchor.py
│
├── modalities/
│   ├── ocr/
│   │   ├── extractor.py
│   │   ├── normalizer.py
│   │   ├── temporal_tracker.py
│   │   ├── quality.py
│   │   └── report.py
│   ├── speaker/
│   │   ├── diarization.py
│   │   ├── alignment.py
│   │   ├── turn_smoothing.py
│   │   ├── quality.py
│   │   └── report.py
│   └── audio/
│       ├── vad.py
│       ├── event_detection.py
│       ├── transition_detection.py
│       ├── quality.py
│       └── report.py
│
├── answering/
│   ├── evidence_packet.py
│   ├── grounded_generator.py
│   ├── claim_splitter.py
│   ├── citation_verifier.py
│   ├── confidence_calibrator.py
│   └── response_policy.py
│
├── evaluation/
│   ├── baseline_manager.py
│   ├── qa_loader.py
│   ├── outcome_metrics.py
│   ├── retrieval_metrics.py
│   ├── temporal_metrics.py
│   ├── citation_metrics.py
│   ├── calibration_metrics.py
│   ├── modality_metrics.py
│   └── regression_report.py
│
├── orchestration/
│   ├── phase_n_workflow.py
│   ├── workflow_state.py
│   └── trace_writer.py
│
└── schemas/
    ├── evidence.py
    ├── outcomes.py
    ├── modality_quality.py
    └── api_response.py

config/
├── phase_n_thresholds.yaml
├── retrieval_profiles.yaml
└── modality_profiles.yaml

tests/
├── unit/
├── integration/
├── regression/
├── negative_queries/
└── modality_quality/
```

---

# 26. Implementation Phases

## N0 — Baseline Freeze

Deliverables:

```text
baseline report
commit/config snapshot
per-question traces
known failure list
```

## N1 — QA Label Repair

Tasks:

- add exact expected outcomes;
- separate unrelated from related-but-absent;
- add acceptable source types;
- replace flat required terms with concept groups;
- label one or more acceptable time windows;
- add negative categories.

## N2 — Conversation Resolver and Ambiguity Gate

Tasks:

- resolve pronouns and follow-ups;
- store resolution confidence;
- detect missing references;
- add ambiguity regression tests.

## N3 — Video Scope Profile and Scope Analyzer

Tasks:

- generate scope profile;
- add scope embedding;
- calculate independent scope signals;
- implement conservative fast rejection;
- add hard-negative tests.

## N4 — Retrieval Orchestrator Repair

Tasks:

- normalize candidates;
- enforce metadata filtering;
- implement query-specific RRF;
- add reranking;
- add modality readiness checks;
- record retrieval margin.

## N5 — Corrective Retrieval and Answerability Gate

Tasks:

- implement bounded corrective actions;
- calculate evidence sufficiency;
- separate outcomes;
- calibrate thresholds;
- add rejection reason codes.

## N6 — Timestamp and Citation Repair

Tasks:

- separate anchor/context/citation intervals;
- create canonical evidence registry;
- implement source-type compatibility;
- validate claim citations;
- add temporal IoU evaluation.

## N7 — OCR Quality

Tasks:

- normalize OCR;
- track text temporally;
- suppress overlays and duplicates;
- link OCR tracks to hierarchy;
- emit OCR quality report.

## N8 — Speaker Quality

Tasks:

- align words to speakers;
- smooth turns;
- handle overlap;
- assign confidence;
- emit speaker quality report.

## N9 — Audio Quality

Tasks:

- improve VAD and pause handling;
- detect stable audio events;
- suppress noise;
- link events to hierarchy;
- emit audio quality report.

## N10 — Calibration and Regression Release

Tasks:

- tune thresholds on validation split;
- lock thresholds;
- run full QA regression;
- compare against baseline;
- publish improvement report;
- mark phase ready only when release gates pass.

---

# 27. Test Plan

## 27.1 Unit tests

Test:

- scope score calculation;
- pronoun resolution states;
- outcome policy;
- evidence sufficiency formula;
- timestamp anchor selection;
- citation registry lookup;
- OCR temporal merge;
- speaker turn merge;
- audio event merge.

## 27.2 Integration tests

Test:

```text
question
 -> scope
 -> retrieval
 -> correction
 -> answerability
 -> response
```

## 27.3 Regression tests

Every previous QA item must retain or improve:

```text
outcome correctness
timeline hit
citation validity
claim support
```

## 27.4 Adversarial tests

Include:

- unrelated query containing video keywords;
- false premise;
- prompt injection inside transcript or OCR;
- request to ignore video evidence;
- question with a fake timestamp;
- question naming an entity absent from video;
- malformed pronoun follow-up;
- query requiring a failed modality.

## 27.5 No-evidence honesty tests

A no-evidence response must:

- contain no video citation;
- contain no invented timestamp;
- not claim certainty about absent content;
- state the appropriate reason;
- preserve the trace ID.

---

# 28. Release Gates

Phase N is complete only when all mandatory gates pass.

## 28.1 Outcome gates

Suggested initial targets:

```text
overall outcome accuracy >= 0.90
negative abstention rate >= 0.95
unrelated rejection precision >= 0.95
false rejection rate on answerable questions <= 0.05
ambiguity detection accuracy >= 0.90
```

## 28.2 Retrieval gates

```text
Recall@5 >= 0.90
MRR >= 0.80
top-3 timeline hit rate >= 0.90
```

## 28.3 Temporal gates

```text
primary timestamp hit rate >= 0.85
median timestamp error <= configured target
citation interval validity >= 0.98
```

## 28.4 Answer gates

```text
claim citation coverage >= 0.95
unsupported claim rate <= 0.03
citation source validity >= 0.98
```

## 28.5 Modality gates

Set separate targets by dataset and video type. At minimum:

- quality reports exist;
- low-quality records are not silently indexed as strong evidence;
- timeline links validate;
- deduplication metrics are recorded;
- regression tests pass.

These targets should be adjusted only through a documented evaluation decision.

---

# 29. Recommended Development Rules

1. Do not change retrieval logic without running the QA set.
2. Do not tune thresholds on the test split.
3. Do not use the generator’s self-reported confidence as final confidence.
4. Do not reject after a single empty retriever.
5. Do not attach citations to unrelated or general-knowledge answers.
6. Do not let the LLM invent evidence IDs or timestamps.
7. Do not mark topical evidence as answer-supporting without verification.
8. Do not index low-quality modality records without a quality flag.
9. Do not merge speaker/OCR/audio records without preserving provenance.
10. Do not add heavier models until Phase N release gates pass.

---

# 30. Pseudocode for the Final Ask Workflow

```python
def ask_video_question(request: AskRequest) -> AskResponse:
    state = WorkflowState.start(request)

    state.query = resolve_conversation(
        raw_query=request.query,
        conversation=request.conversation
    )

    if state.query.requires_reference and not state.query.reference_resolved:
        return build_ambiguous_response(state)

    readiness = load_modality_readiness(request.video_id)
    query_analysis = analyze_query(state.query.standalone_query)
    required_modalities = detect_required_modalities(query_analysis)

    if readiness.blocks(required_modalities):
        return build_processing_incomplete_response(
            state=state,
            missing_modalities=readiness.missing(required_modalities)
        )

    scope = analyze_video_scope(
        video_id=request.video_id,
        query=state.query,
        query_analysis=query_analysis
    )
    state.scope_analysis = scope

    if scope.is_strictly_unrelated():
        return build_unrelated_response(state)

    plan = build_retrieval_plan(
        query=state.query,
        analysis=query_analysis,
        readiness=readiness,
        scope=scope
    )

    candidates = retrieve_candidates(plan)
    candidates = normalize_and_fuse(candidates, plan)
    candidates = rerank_candidates(candidates, state.query, plan)
    verified = verify_evidence(candidates, state.query, plan)

    sufficiency = evaluate_evidence_sufficiency(
        query=state.query,
        verified_evidence=verified,
        scope=scope,
        required_modalities=required_modalities
    )

    if sufficiency.requires_correction:
        correction = build_corrective_plan(
            query=state.query,
            previous_candidates=candidates,
            diagnostics=sufficiency
        )
        corrected = retrieve_candidates(correction)
        corrected = normalize_and_fuse(corrected, correction)
        corrected = rerank_candidates(corrected, state.query, correction)
        verified = merge_and_verify(verified, corrected)
        sufficiency = evaluate_evidence_sufficiency(
            query=state.query,
            verified_evidence=verified,
            scope=scope,
            required_modalities=required_modalities
        )

    outcome = decide_outcome(
        query=state.query,
        scope=scope,
        sufficiency=sufficiency,
        readiness=readiness
    )

    if outcome != "grounded_answer" and outcome != "partial_answer":
        return build_non_answer_response(state, outcome, sufficiency)

    temporal_context = select_temporal_evidence(
        query=state.query,
        verified_evidence=verified
    )

    evidence_packet = build_evidence_packet(
        query=state.query,
        temporal_context=temporal_context,
        verified_evidence=verified
    )

    draft = generate_grounded_answer(evidence_packet)
    claim_report = verify_claims_and_citations(draft, evidence_packet)

    if not claim_report.passes:
        draft = revise_answer_once(draft, claim_report, evidence_packet)
        claim_report = verify_claims_and_citations(draft, evidence_packet)

    if not claim_report.passes:
        return build_safe_abstention_from_failed_verification(
            state=state,
            diagnostics=claim_report
        )

    confidence = calibrate_confidence(
        scope=scope,
        sufficiency=sufficiency,
        claim_report=claim_report
    )

    response = build_grounded_response(
        state=state,
        draft=draft,
        evidence_packet=evidence_packet,
        confidence=confidence
    )

    write_trace(state, response)
    return response
```

---

# 31. Final Recommended Architecture

```text
User Question
 -> Resolve conversation and pronouns
 -> Detect intent, entities, time, and required modalities
 -> Check modality readiness
 -> Match query against video scope profile
 -> Conservatively reject only obvious unrelated questions
 -> Build query-specific retrieval plan
 -> Run parallel text/OCR/speaker/audio/visual/event retrieval
 -> Fuse using weighted RRF
 -> Rerank with answer-likelihood and modality alignment
 -> Verify provenance, quality, timeline, and relevance
 -> Perform bounded corrective retrieval when evidence is weak
 -> Measure set-level evidence sufficiency
 -> Choose:
      grounded answer
      partial answer
      related but not found
      unrelated
      ambiguous
      conflicting
      processing incomplete
 -> Select precise evidence anchor and context window
 -> Generate answer from structured evidence
 -> Verify every claim and citation
 -> Calibrate confidence
 -> Return answer, timestamps, citations, reasons, and trace ID
 -> Run regression evaluation
```

---

# 32. Research Foundations

The design is consistent with the following research directions:

1. **Corrective Retrieval-Augmented Generation (CRAG)** — retrieval quality evaluation and corrective actions when retrieved evidence is weak.
2. **Self-RAG** — adaptive retrieval and self-reflection instead of blindly retrieving a fixed context.
3. **UAEval4RAG** — explicit evaluation of unanswerable questions and the trade-off between answer accuracy and rejection behavior.
4. **SURE-RAG** — evidence sufficiency, uncertainty, disagreement, and selective answering.
5. **ReClaim / fine-grained attributed generation** — sentence- or claim-level grounding rather than coarse paragraph citations.
6. **Temporal sentence grounding and VideoQA research** — localizing relevant video moments before generating an answer.

Reference links:

- CRAG: https://arxiv.org/abs/2401.15884
- Self-RAG: https://arxiv.org/abs/2310.11511
- UAEval4RAG: https://arxiv.org/abs/2412.12300
- SURE-RAG: https://arxiv.org/abs/2605.03534
- ReClaim: https://arxiv.org/abs/2407.01796
- Temporal grounding survey: https://arxiv.org/abs/2201.08071

---

# 33. Definition of Done

Phase N is complete when:

- unrelated questions are rejected without fake citations;
- related-but-absent questions are not mislabeled as unrelated;
- ambiguous follow-ups request clarification only after reference resolution fails;
- valid questions survive a failed individual retriever;
- corrective retrieval is bounded and traceable;
- primary timestamps point to the strongest evidence anchor;
- citations are generated only from the canonical evidence registry;
- every factual claim is supported or removed;
- OCR, speaker, and audio records have quality scores and reports;
- low-quality modality evidence is filtered or downgraded;
- thresholds are calibrated on validation data;
- the evaluation report demonstrates improvement over the frozen baseline;
- all unit, integration, negative, modality, and regression tests pass.

The system should then be considered ready for the next research layer.
