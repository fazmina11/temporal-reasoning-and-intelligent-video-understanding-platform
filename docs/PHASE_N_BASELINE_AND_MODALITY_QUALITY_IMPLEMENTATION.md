# Phase N Companion Note

This file is no longer the master implementation plan.

Use this document as the master Phase N blueprint:

```text
docs/VideoSceneRAG_Phase_N_Evaluation_Repair_and_Relevance_Gating.md
```

## Why The Master Plan Changed

The newer blueprint is stronger because it does not treat evaluation repair as
only a metric cleanup task. It adds the production-critical layer that the
project needs next:

```text
relevance detection
safe rejection
answerability gating
corrective retrieval
evidence sufficiency
claim-level citation validation
modality readiness checks
```

The most important correction is:

```text
unrelated_to_video != video_evidence_not_found
```

A question can be related to the video's topic but still unsupported by the
actual video evidence. The system must not collapse those cases into the same
outcome.

## Master Phase N Focus

Follow the master blueprint for:

1. baseline freeze;
2. QA label repair;
3. conversation resolution and ambiguity gating;
4. video scope profiles and relevance analysis;
5. retrieval orchestrator repair;
6. corrective retrieval and answerability gating;
7. timestamp and citation repair;
8. OCR evidence quality;
9. speaker evidence quality;
10. audio evidence quality;
11. calibration and regression release.

## Implementation Rule

Do not begin implementation from this companion note. Start from:

```text
docs/VideoSceneRAG_Phase_N_Evaluation_Repair_and_Relevance_Gating.md
```

This companion exists only to prevent older references from pointing the team
at an outdated Phase N plan.
