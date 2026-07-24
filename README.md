# VideoSceneRAG

## Temporal Reasoning and Intelligent Video Understanding Platform

VideoSceneRAG converts long videos into structured, searchable timeline memory.
It combines transcription, visual evidence, OCR, speaker and audio analysis,
hierarchical chunking, ChromaDB retrieval, temporal reasoning, and verified
answer generation.

Instead of treating a video as a collection of unrelated screenshots or
overlapping text chunks, VideoSceneRAG builds a canonical hierarchy:

```text
Video
 -> Manifest and normalized timeline
 -> Transcript and multimodal boundary signals
 -> Atomic evidence spans
 -> Semantic topic chunks
 -> Explanation/activity events
 -> OCR, speaker, audio, frame, and clip evidence
 -> Hierarchical ChromaDB indexes
 -> Agentic retrieval and temporal reasoning
 -> Grounded answer with timestamp, citations, and confidence
```

The project is designed for questions such as:

- "What is MCP?"
- "When did the speaker compare MCP with HTTP?"
- "What text appeared on the opening slide?"
- "What happened after the server was introduced?"
- "I remember a diagram about tools and context. Why was it shown?"

---

## Current Status

The repository contains a working research-grade end-to-end base:

- mature media manifests and integer-millisecond timelines;
- boundary extraction and validated non-overlapping atomic spans;
- transcript, frame, clip, OCR, speaker, and audio attachment;
- semantic chunks and events;
- hierarchy-native ChromaDB indexing;
- planner-driven multimodal retrieval;
- fusion, reranking, temporal deduplication, and corrective retrieval;
- evidence verification and answerability gating;
- citation-aligned grounded generation;
- unsupported-claim removal;
- calibrated confidence and persistent retrieval traces;
- FastAPI upload, artifact, question, and debug endpoints;
- Next.js upload and chat prototype;
- automated Phase N evaluation and release gates.

The `mcp_vs_api` N10 release suite currently passes all mandatory gates:

| Metric | Result |
| --- | ---: |
| Outcome accuracy | 1.00 |
| Negative-question abstention | 1.00 |
| Timestamp hit rate | 1.00 |
| Citation presence | 1.00 |
| Citation validity | 1.00 |
| Required-term coverage | 1.00 |
| Unsupported-claim rate | 0.00 |
| Fallback rate | 0.00 |
| Execution failures | 0 |

These results cover the repository's labeled 60-question MCP-vs-API validation
set. They are not a claim of perfect performance on every video or question.

---

## Why This Project Is Different

### Canonical timeline evidence

All internal time values use integer milliseconds. Atomic spans:

- do not overlap;
- cover the video timeline;
- have valid previous/next links;
- preserve transcript and multimodal evidence;
- act as the precise unit for citations.

### Hierarchical memory

Atomic spans preserve precision. Semantic chunks preserve coherent ideas.
Events preserve full explanations or activities. Retrieval can search each
level and expand context dynamically without permanently indexing random
overlapping windows.

### Multimodal retrieval

The retrieval planner can use:

- exact timeline lookup;
- dense transcript retrieval;
- semantic chunk retrieval;
- event retrieval;
- sparse lexical retrieval;
- visual evidence;
- OCR text;
- speaker turns;
- audio events;
- memory-recovery candidates.

### Agentic but bounded

The system uses distinct deterministic and bounded stages:

```mermaid
flowchart LR
    Q["Question"] --> C["Conversation resolver"]
    C --> U["Query understanding"]
    U --> S["Scope router"]
    S --> P["Retrieval planner"]
    P --> R["Parallel retrievers"]
    R --> F["Fusion and reranking"]
    F --> V["Evidence verifier"]
    V --> G["Answerability gate"]
    G --> T["Temporal reasoner"]
    T --> E["Evidence packet"]
    E --> A["Answer generator"]
    A --> CV["Claim verifier"]
    CV --> CF["Confidence calibrator"]
    CF --> O["Typed response"]
```

The planner selects configured retrievers and bounded context policies. It does
not execute arbitrary model-generated actions.

### Evidence-first answers

Every grounded response can include:

- exact evidence anchor;
- start and end milliseconds;
- canonical source ID;
- source type;
- parent topic/event;
- citations;
- evidence quality;
- calibrated confidence;
- trace ID.

If evidence is insufficient, unrelated, ambiguous, conflicting, or still being
processed, the system returns a typed non-answer outcome instead of inventing a
video citation.

---

## Main Features

### Video processing

- upload and source hashing;
- FFprobe media inspection with OpenCV fallback;
- duration, FPS, frame count, resolution, codec, and audio metadata;
- normalized audio extraction;
- Faster Whisper transcription;
- scene and visual-change detection;
- sentence and pause boundaries;
- canonical atom generation and validation;
- representative frames and short clips;
- semantic chunks and events.

### Modality evidence

- frame-level OCR text;
- OCR token boxes and confidence;
- temporal OCR tracks;
- frame provenance;
- speaker segments and smoothed turns;
- parent atom/chunk/event links;
- speech, silence, transition, and audio events;
- modality quality reports.

### Retrieval and reasoning

- BAAI `bge-base-en-v1.5` embeddings;
- persistent ChromaDB hierarchy collections;
- exact, dense, sparse, visual, OCR, speaker, and audio adapters;
- weighted reciprocal-rank fusion;
- query-aware reranking;
- temporal overlap deduplication;
- bounded corrective retrieval;
- previous/next context expansion;
- parent chunk and event expansion;
- repeated-concept and before/after reasoning.

### Answer quality

- strict-video scope policy;
- unrelated-question rejection;
- ambiguity clarification;
- evidence sufficiency scoring;
- processing-readiness checks;
- citation registry;
- primary-anchor citation windows;
- citation-preserving local generation when Gemini is unavailable;
- unsupported-claim filtering;
- measurable confidence.

### Evaluation

- typed QA schemas;
- 60-question `mcp_vs_api` set;
- definitions, concepts, timestamps, visual memory, unrelated, and ambiguous
  categories;
- baseline freezing;
- report generation;
- regression comparison;
- release thresholds;
- modality-quality gates;
- JSON and Markdown release reports.

---

## Technology Stack

| Layer | Technology |
| --- | --- |
| API | FastAPI, Uvicorn, Pydantic |
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS |
| Video/audio | FFmpeg, FFprobe, OpenCV, PySceneDetect |
| Transcription | Faster Whisper |
| OCR | Tesseract, pytesseract |
| Embeddings | Hugging Face SentenceTransformers |
| Vector database | ChromaDB |
| Generation | Google GenAI SDK with grounded local fallback |
| Data | Versioned JSON artifacts and JSON Schema |
| Evaluation | unittest, pytest, custom QA/release tooling |

---

## Repository Structure

```text
.
├── api.py
├── config/
│   └── phase_n_thresholds.yaml
├── data/
│   └── evaluation/
│       └── qa_sets/
├── docs/
├── schemas/
├── src/
│   ├── phase1_sampling.py
│   ├── phase2_audio.py
│   ├── phase2_visual.py
│   ├── phase3_indexing.py
│   ├── phase4_rag.py
│   └── pipeline/
│       ├── agentic/
│       ├── evaluation/
│       ├── knowledge_reconstruction/
│       ├── memory_recovery/
│       ├── atomic_spans.py
│       ├── boundary_signals.py
│       ├── chunking_foundation.py
│       ├── evidence_foundation.py
│       ├── hierarchy_indexing.py
│       ├── media_manifest.py
│       ├── modality_foundation.py
│       └── ...
├── tests/
├── web/
│   └── src/
└── requirement.txt
```

Large media, generated artifacts, model caches, Chroma data, traces, and secrets
are intentionally excluded from Git.

---

## Prerequisites

### Required

- Python 3.11 or 3.12;
- Node.js 20+;
- FFmpeg and FFprobe;
- Tesseract OCR;
- Git.

### Optional

- Gemini API key;
- NVIDIA GPU;
- CUDA-compatible PyTorch environment.

The current base works on CPU. A GPU improves transcription and future local
video-language-model processing. An RTX 3050 6 GB is suitable for development
with smaller models and conservative settings, but large clip-native VLMs need
more VRAM or a hosted provider.

### Verify external tools

```powershell
ffmpeg -version
ffprobe -version
tesseract --version
```

If FFmpeg is installed outside `PATH`, configure:

```env
FFMPEG_BIN_DIR=C:\path\to\ffmpeg\bin
FFMPEG_PATH=C:\path\to\ffmpeg\bin\ffmpeg.exe
FFPROBE_PATH=C:\path\to\ffmpeg\bin\ffprobe.exe
```

Tesseract can be configured with:

```env
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
```

---

## Installation

```powershell
git clone https://github.com/fazmina11/temporal-reasoning-and-intelligent-video-understanding-platform.git
cd temporal-reasoning-and-intelligent-video-understanding-platform

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirement.txt
```

Frontend:

```powershell
cd web
npm.cmd install
cd ..
```

Create `.env` from `.env.example` and set only the values needed for your
environment:

```env
GEMINI_API_KEY=replace_with_your_key
GEMINI_MODEL=gemini-3-flash-preview
PORT=8001
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
FRAME_EXTRACTION_MODE=atom_coverage
FRAME_INTERVAL_MS=2000
HIERARCHY_EMBED_MODEL=BAAI/bge-base-en-v1.5
```

Never expose `GEMINI_API_KEY` in the browser or commit `.env`.

---

## Run Locally

### 1. Start the backend

```powershell
cd "C:\SideQuest\CN Project\RAG-Enhanced-Video-Scene-Understanding"

$env:PYTHONUTF8="1"
$env:TRANSFORMERS_NO_TF="1"
$env:USE_TF="0"

python -m uvicorn api:app --host 127.0.0.1 --port 8001
```

API documentation:

```text
http://127.0.0.1:8001/docs
```

### 2. Start the frontend

```powershell
cd web
npm.cmd run dev -- -p 3000
```

Open:

```text
http://127.0.0.1:3000/RAG-Enhanced-Video-Scene-Understanding
```

### Port conflict

If port `8001` is occupied:

```powershell
Get-NetTCPConnection -LocalPort 8001
```

Stop the existing process or start the API on another port and update
`NEXT_PUBLIC_API_BASE_URL`.

---

## Ask Questions About the Processed Demo

The repository's development QA target uses:

```text
video_id = mcp_vs_api
```

```powershell
$body = @{
    video_id = "mcp_vs_api"
    query = "How is MCP compared to HTTP standardization?"
    answer_mode = "strict_video"
} | ConvertTo-Json

$result = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/ask" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

$result | ConvertTo-Json -Depth 10
```

Inspect citations:

```powershell
$result.citations |
    Format-Table citation_id, source_type, source_id, start_ms, end_ms, quality_score
```

Inspect the agentic trace:

```powershell
$debug = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/ask-debug" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

$debug.trace | ConvertTo-Json -Depth 12
```

The first question may take longer while the embedding model loads.

---

## Upload and Process a Video

### Web interface

1. Start backend and frontend.
2. Open the web URL.
3. Select a video.
4. Wait for processing to reach `completed`.
5. Ask questions in the video workspace.

### API

```powershell
$videoPath = "C:\path\to\video.mp4"

$upload = curl.exe -s `
    -X POST `
    -F "file=@$videoPath" `
    "http://127.0.0.1:8001/upload" |
    ConvertFrom-Json

$videoId = $upload.video_id
```

Monitor:

```powershell
do {
    $status = Invoke-RestMethod "http://127.0.0.1:8001/status/$videoId"
    Write-Host "$($status.progress)% - $($status.phase) - $($status.status)"
    if ($status.status -notin @("completed", "failed")) {
        Start-Sleep -Seconds 5
    }
} while ($status.status -notin @("completed", "failed"))
```

Ask:

```powershell
$body = @{
    video_id = $videoId
    query = "Summarize the main explanation."
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/ask" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body |
    ConvertTo-Json -Depth 10
```

---

## Processing Pipeline

| Progress | Phase | Output |
| ---: | --- | --- |
| 0 | Upload and manifest | Source identity and media metadata |
| 10 | Scene detection | Visual-change and scene signals |
| 20 | Audio extraction | Normalized audio |
| 30 | Transcription | Timestamped transcript |
| 55 | Chunking foundation | Boundaries and canonical atoms |
| 70 | Frame extraction | Timeline frame evidence |
| 78 | Evidence foundation | Attached evidence and semantic chunks |
| 84 | Hierarchy indexing | Events and Chroma collections |
| 88 | Modality foundation | OCR, speaker, and audio artifacts |
| 92 | Visual enrichment | Additional visual descriptions |
| 96 | Final indexing | Compatibility search index |
| 100 | Completed | Ready for retrieval |

Each phase writes artifacts recorded by the video manifest. Validation reports
prevent malformed timelines or hierarchy references from silently entering
retrieval.

---

## API

### Video and processing

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/upload` | Upload and process a video |
| `GET` | `/status/{video_id}` | Processing progress |
| `GET` | `/manifest/{video_id}` | Video profile and artifacts |

### Artifact inspection

| Method | Endpoint |
| --- | --- |
| `GET` | `/boundaries/{video_id}` |
| `GET` | `/atoms/{video_id}` |
| `GET` | `/atom-validation/{video_id}` |
| `GET` | `/frames/{video_id}` |
| `GET` | `/frame-validation/{video_id}` |
| `GET` | `/visual-artifacts/{video_id}` |
| `GET` | `/semantic-chunks/{video_id}` |
| `GET` | `/chunk-validation/{video_id}` |
| `GET` | `/events/{video_id}` |

### Retrieval

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/ask` | Typed grounded answer |
| `POST` | `/ask-debug` | Answer plus retrieval trace |

### Ask outcomes

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

`strict_video` mode intentionally refuses unsupported or unrelated questions.

---

## Run Pipeline Phases Manually

For an existing manifest:

```powershell
python -m src.pipeline.chunking_foundation --video-id <video_id>
python -m src.pipeline.frame_extraction --video-id <video_id>
python -m src.pipeline.evidence_foundation --video-id <video_id>
python -m src.pipeline.hierarchy_indexing --video-id <video_id>
python -m src.pipeline.modality_foundation --video-id <video_id> --expected-speakers 1
python -m src.pipeline.hierarchy_validation --video-id <video_id>
```

All-frame extraction is available but storage intensive:

```powershell
python -m src.pipeline.frame_extraction --video-id <video_id> --all-frames
```

---

## Generated Artifacts

```text
data/processed/manifests/{video_id}.json
data/processed/transcripts/{video_id}.json
data/processed/boundaries/{video_id}.json
data/processed/atoms/{video_id}.json
data/processed/semantic_chunks/{video_id}.json
data/processed/events/{video_id}.json
data/processed/frames/{video_id}/
data/processed/clips/{video_id}/
data/processed/visual_artifacts/{video_id}.json
data/processed/ocr/{video_id}.json
data/processed/speakers/{video_id}.json
data/processed/audio_events/{video_id}.json
data/processed/reports/
data/processed/retrieval_traces/{video_id}/
chroma_db/
```

Runtime media and artifacts are not committed to Git.

---

## Testing

### Full unit suite

```powershell
python -m unittest discover -s tests -v
```

### Evaluation integration

```powershell
python -m pytest tests\test_evaluation_integration.py -q
```

### Validate the QA dataset

```powershell
python -m src.pipeline.evaluation.validate_dataset `
    --file data\evaluation\qa_sets\mcp_vs_api_qa.json
```

### Run the N10 release gate

```powershell
python -m src.pipeline.evaluation.release_manager `
    --video-id mcp_vs_api `
    --qa-dataset data\evaluation\qa_sets\mcp_vs_api_qa.json `
    --baseline-mode auto `
    --release-id manual_verification
```

Expected:

```text
Phase N release decision: pass
```

### Compile check

```powershell
python -m compileall -q api.py src\pipeline
```

---

## Frontend Direction

The production frontend should make backend work visible:

- truthful processing phases;
- artifact counters;
- video profile;
- evidence timeline;
- transcript, topic, event, OCR, speaker, and audio tracks;
- citation-to-video seeking;
- answer outcomes and confidence;
- optional retrieval trace inspector.

The complete frontend implementation brief is:

[Frontend Product and Backend Visibility Specification](docs/FRONTEND_PRODUCT_AND_BACKEND_VISIBILITY_SPEC.md)

---

## Deployment

The current runtime is suitable for local development and controlled
single-machine demonstrations.

Before public multi-user deployment, the project needs:

- durable worker jobs;
- persistent job/video metadata;
- authentication and tenant ownership;
- protected object storage;
- signed media URLs;
- Chroma service configuration;
- production health checks;
- configurable CORS;
- rate limits, quotas, backup, and monitoring;
- reproducible dependency locks and containers.

See:

[Production Deployment Runbook](docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md)

---

## Chrome Extension

A future Manifest V3 Chrome extension can provide a VideoSceneRAG side panel on
YouTube, look up the active video, ask grounded questions, and seek the player
to citation timestamps.

The first release should operate on already authorized/processed videos. Any
YouTube ingestion workflow requires policy, privacy, permission, and content
rights review.

See:

[Chrome Extension Future Architecture](docs/CHROME_EXTENSION_FUTURE_ARCHITECTURE.md)

---

## Documentation

### Product and operations

- [Frontend Product and Backend Visibility Specification](docs/FRONTEND_PRODUCT_AND_BACKEND_VISIBILITY_SPEC.md)
- [Production Deployment Runbook](docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md)
- [Chrome Extension Future Architecture](docs/CHROME_EXTENSION_FUTURE_ARCHITECTURE.md)
- [Project Process Flow](docs/PROJECT_PROCESS_FLOW.md)
- [Next Focus and Phase Roadmap](docs/NEXT_FOCUS_AND_PHASE_ROADMAP.md)

### Processing architecture

- [C0-C1 Manifest and Timeline](docs/PHASE_C0_C1_MANIFEST_AND_TIMELINE.md)
- [C3-C5 Boundaries and Atoms](docs/PHASE_C3_C5_BOUNDARIES_AND_ATOMS.md)
- [C6 Audio and Frame Evidence](docs/PHASE_C6_AUDIO_AND_FRAME_EVIDENCE.md)
- [C6-C9 Evidence and Semantic Chunks](docs/PHASE_C6_C9_EVIDENCE_AND_SEMANTIC_CHUNKS.md)
- [C10-C12 Events, Indexing, and Retrieval](docs/PHASE_C10_C12_EVENTS_INDEXING_RETRIEVAL.md)

### Agentic retrieval and evaluation

- [C13-C25 Agentic Retrieval and Answer Quality](docs/PHASE_C13_C25_PRODUCTION_AGENTIC_RETRIEVAL_AND_ANSWER_QUALITY.md)
- [Phase N Evaluation Repair and Relevance Gating](docs/VideoSceneRAG_Phase_N_Evaluation_Repair_and_Relevance_Gating.md)
- [Production Agentic Retrieval Architecture v2](docs/VideoSceneRAG_Production_Agentic_Retrieval_Architecture_v2.md)

---

## Roadmap

### Near term

- production frontend implementation;
- durable job and artifact storage;
- Docker deployment;
- authentication and video ownership;
- larger multi-video evaluation set;
- evidence-debug explorer;
- dependency locking and CI.

### Research

- clip-native VLM adapters such as Qwen-VL/Video-LLaMA/LLaVA-Video;
- learned semantic event segmentation;
- entity and world memory;
- repeated-concept and cross-video reasoning;
- richer memory recovery;
- Chrome extension integration.

---

## Known Limitations

- current processing runs in the API process;
- current status storage is partly in memory;
- current frontend API types predate the full typed answer contract;
- local `/data` serving is development-oriented;
- user authentication and tenant isolation are not implemented;
- artifact storage is local;
- Chroma is local/embedded by default;
- dependency versions need a production lock;
- large VLMs are not part of the base runtime;
- evaluation is currently strongest on the MCP-vs-API fixture.

These limitations are documented so deployment work does not mistake a
successful local demo for a complete public-production architecture.

---

## Contributing

Recommended workflow:

1. create a focused branch;
2. pull the latest `main`;
3. keep backend, frontend, and documentation changes scoped;
4. add or update tests;
5. run compile, unit, integration, and relevant evaluation checks;
6. open a pull request with artifact/schema impact noted;
7. merge only after the release gates relevant to the change pass.

Do not commit:

- `.env`;
- API keys;
- uploaded videos;
- extracted frames/audio/clips;
- Chroma data;
- model caches;
- retrieval traces containing user data.

---

## License

No open-source license has been declared in this repository yet. Add an
appropriate `LICENSE` file before public redistribution or third-party reuse.
