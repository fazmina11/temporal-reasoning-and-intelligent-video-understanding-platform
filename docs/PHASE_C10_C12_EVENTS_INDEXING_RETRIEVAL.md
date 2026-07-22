# Phases C10-C12: Events, Chroma Indexing, and Dynamic Retrieval

## Outcome

These phases finish the base hierarchy:

```text
Video
 -> Manifest
 -> Normalized timeline
 -> Transcript
 -> Boundary candidates
 -> Atomic spans
 -> Semantic chunks
 -> Events
 -> Validated hierarchy
 -> ChromaDB indexes
 -> Retrieval with dynamic context expansion
```

The design does not store random permanent overlapping chunks. It indexes
canonical atoms, semantic chunks, visual chunk evidence, and events. Extra
context is fetched dynamically at query time.

## Phase C10: Event Builder

Run:

```powershell
python -m src.pipeline.hierarchy_indexing --video-id <video_id>
```

C10 writes:

```text
data/processed/events/{video_id}.json
```

Events group semantic chunks into full explanations or activities. Each event
stores:

```json
{
  "event_id": "event_000010",
  "chunk_ids": ["chunk_000052"],
  "atom_ids": ["atom_000140", "atom_000141"],
  "start_ms": 9652000,
  "end_ms": 9802000,
  "title": "The lecturer compares cats and dogs using a blue graph",
  "transcript_text": "...",
  "representative_frame_ids": []
}
```

The semantic chunk artifact is also updated so each chunk has a
`parent_event_id`.

## Phase C11: ChromaDB Chunk Indexing

C11 indexes only stable hierarchy units into these collections:

```text
video_atoms_text
video_chunks_text
video_chunks_visual
video_events
```

Every vector metadata record includes:

```text
video_id
pipeline_version
source_type
source_id
start_ms
end_ms
parent_chunk_id
parent_event_id
source_sha256
```

Additional metadata stores atom IDs, frame IDs, clip paths, word IDs, segment
IDs, and titles when available.

Manual command:

```powershell
cd "C:\SideQuest\CN Project\RAG-Enhanced-Video-Scene-Understanding"
python -m src.pipeline.hierarchy_indexing --video-id mcp_vs_api
```

The hierarchy indexer defaults to:

```text
BAAI/bge-base-en-v1.5
```

This is stronger than `all-MiniLM-L6-v2` for semantic retrieval while still
being practical on a local laptop. You can override it without changing code:

```powershell
$env:HIERARCHY_EMBED_MODEL="BAAI/bge-base-en-v1.5"
python -m src.pipeline.hierarchy_indexing --video-id mcp_vs_api
```

The code defaults to offline/cache mode so blocked internet does not cause long
Hugging Face retry delays. If the model is not already cached on a fresh
machine, allow internet once or unset:

```powershell
Remove-Item Env:\HF_HUB_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:\TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
python -m src.pipeline.hierarchy_indexing --video-id mcp_vs_api
```

## Phase C12: Retrieval Context Expansion

C12 queries the hierarchy collections, then expands each hit through JSON
artifacts:

```text
retrieved atom/chunk/event
 -> previous atom
 -> next atom
 -> parent semantic chunk
 -> parent event
 -> nearby transcript
 -> related visual evidence
 -> clip paths
```

This gives timeline-aware answers without duplicating overlapping chunks inside
Chroma.

## Full Base Validation

After C10-C12, run the full hierarchy validator:

```powershell
$env:HIERARCHY_EMBED_MODEL="BAAI/bge-base-en-v1.5"
python -m src.pipeline.hierarchy_validation --video-id mcp_vs_api
```

It writes:

```text
data/processed/reports/{video_id}_hierarchy_validation.json
```

The validator checks:

```text
atom validation passed
frame validation passed
semantic chunk validation passed
all atoms have semantic chunks
all atoms have visual evidence
all chunks have parent events
events cover every chunk once
events cover every atom
event timeline is contiguous
model-versioned Chroma collections are available
```

Smoke test:

```powershell
python - <<'PY'
from pathlib import Path
from src.pipeline.hierarchy_retrieval import HierarchyRetriever

r = HierarchyRetriever(repo_root=Path.cwd())
results = r.query("How is MCP different from APIs?", video_id="mcp_vs_api", top_k=3)
for item in results:
    print(item["source_type"], item["source_id"], item["timestamp"])
    print(item["parent_chunk_id"], item["parent_event_id"])
    print(item["neighbor_atom_ids"])
PY
```

## API Integration

Uploads now run:

```text
C0/C1 manifest
C3-C5 boundaries and atoms
C6-C9 transcript, visual evidence, semantic chunks
C10-C11 events and hierarchy Chroma indexing
C12 retrieval through /ask
```

New or relevant endpoints:

```text
GET /events/{video_id}
POST /ask
```

`POST /ask` now uses the request `video_id` and retrieves from the hierarchy
index with dynamic context expansion.

## Verified Output For `mcp_vs_api`

```text
events: 10
video_atoms_text__baai_bge_base_en_v1_5: 81
video_chunks_text__baai_bge_base_en_v1_5: 18
video_chunks_visual__baai_bge_base_en_v1_5: 18
video_events__baai_bge_base_en_v1_5: 10
embedding model: BAAI/bge-base-en-v1.5
retrieval smoke test: passed
top query result: chunk_000012 at 00:07:41, parent event_000007
full hierarchy validation: passed
hierarchy validation errors: 0
hierarchy validation warnings: 0
```
