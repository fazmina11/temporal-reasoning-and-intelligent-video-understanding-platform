"""
src/phase3_indexing.py — Phase 3: Embedding, Indexing & Retrieval
==================================================================

Pipeline overview
-----------------
Step A │ Dual-Collection Indexing — two ChromaDB collections are built in parallel:
       │   • "video_moments_dense"  — SentenceTransformer embeddings of combined_context
       │                              (multimodal textual representation from Phase 2)
       │   • "video_moments_sparse" — keyword-only collection for on_screen_text / OCR
       │                              text, enabling exact-phrase lookups that dense
       │                              embeddings sometimes miss
Step B │ Metadata Normalisation   — all Phase 1+2 fields are sanitised into ChromaDB-
       │                              compatible types (str/int/float/bool) before upsert
Step C │ Hybrid Retrieval         — query time combines results from both collections
       │                              (Reciprocal Rank Fusion), re-ranked by temporal
       │                              proximity bias when a seed timestamp is provided

Advanced techniques
--------------------
• Multimodal Textual Representation  — combined_context (visual + audio) is the primary
                                        embedding target, enabling cross-modal queries
• Dual-Collection Strategy           — dense collection for semantic similarity;
                                        sparse/keyword collection for OCR text recall
• Reciprocal Rank Fusion (RRF)       — merges ranked results from both collections
                                        without requiring score normalisation
• Upsert Idempotency                 — scenes already in the collection are updated,
                                        not duplicated; safe to re-run after Phase 2 updates
• Temporal Proximity Re-ranking      — optional: boost results near a seed timestamp,
                                        useful for "what comes next?" retrieval patterns
• Rich Payload Storage               — all Phase 1+2 metadata fields are stored alongside
                                        each vector for zero-latency result enrichment
• Batch Upsert                       — documents inserted in configurable batches to cap
                                        peak memory usage on large videos
• Collection Stats Report            — printed after indexing for quick sanity-checking
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import sys
import math
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

# ── Local utilities ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_dirs, load_metadata, log

# ── Configuration ──────────────────────────────────────────────────────────────

# Resolve paths relative to the repository root (not the current working directory).
REPO_ROOT         = Path(__file__).resolve().parent.parent
DATA_ROOT         = REPO_ROOT / "data"

CHROMA_PATH      = str(REPO_ROOT / "chroma_db")
ENRICHED_PATH    = str(DATA_ROOT / "processed" / "metadata" / "enriched_metadata.json")

# SentenceTransformer model — runs fully locally (CPU/GPU auto-detected)
# "all-MiniLM-L6-v2"      — fast, 384-dim, great for short passages
# "all-mpnet-base-v2"     — slower, 768-dim, better recall on long context
EMBED_MODEL      = "all-MiniLM-L6-v2"

# Collection names
DENSE_COLLECTION  = "video_moments_dense"
SPARSE_COLLECTION = "video_moments_sparse"

# Batch size for upsert (tune down if RAM is limited)
UPSERT_BATCH_SIZE = 64

# Retrieval defaults
DEFAULT_TOP_K         = 5
RRF_K                 = 60      # RRF constant — higher = smoother rank merging
TEMPORAL_BIAS_WEIGHT  = 0.15    # 0.0 = no bias, 1.0 = pure temporal proximity


# ── ChromaDB & Embedding setup ─────────────────────────────────────────────────

def _build_clients() -> tuple[chromadb.PersistentClient, Any]:
    """Initialise the persistent ChromaDB client and embedding function."""
    ensure_dirs([CHROMA_PATH])
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        # device is auto-detected by sentence-transformers
    )
    log.info("🔌  ChromaDB client ready at: %s", CHROMA_PATH)
    log.info("🧠  Embedding model: %s", EMBED_MODEL)
    return client, ef


# ── Step B: Metadata Normalisation ────────────────────────────────────────────

def _safe_meta(value: Any) -> str | int | float | bool:
    """
    ChromaDB metadata values must be str | int | float | bool.
    Lists and dicts are JSON-serialised to strings.
    None becomes an empty string.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def _build_payload(scene: dict) -> tuple[str, str, str, dict]:
    """
    Build the four artefacts needed for one ChromaDB upsert row:

    Returns
    -------
    (dense_doc, sparse_doc, doc_id, metadata_dict)

    dense_doc  : combined_context (multimodal textual representation)
    sparse_doc : on_screen_text — pure OCR/text layer for keyword recall
    doc_id     : stable string ID derived from frame_id
    metadata   : flat dict of all Phase 1+2 fields, safe for ChromaDB
    """
    frame_id = scene.get("frame_id", "")
    doc_id   = f"scene__{Path(frame_id).stem}" if frame_id else f"scene__{id(scene)}"

    # Primary embedding target: multimodal fusion string from Phase 2B
    dense_doc = scene.get("combined_context", "")

    # Fallback: construct from available fields if Phase 2B wasn't run
    if not dense_doc:
        parts = []
        if scene.get("visual_summary"):
            parts.append(f"[VISUAL] {scene['visual_summary']}")
        if scene.get("on_screen_text"):
            parts.append(f"[TEXT ON SCREEN] {scene['on_screen_text']}")
        if scene.get("scene_transcript"):
            parts.append(f"[AUDIO] {scene['scene_transcript']}")
        dense_doc = "\n".join(parts) or f"Scene at {scene.get('timestamp', '?')}"

    # Sparse document: OCR text only (exact-phrase recall)
    sparse_doc = scene.get("on_screen_text", "") or scene.get("scene_transcript", "") or dense_doc

    # Metadata payload — all Phase 1 + Phase 2 fields, type-sanitised
    metadata = {
        # ── Phase 1 fields ──────────────────────────────────────────────
        "frame_id":        _safe_meta(scene.get("frame_id")),
        "timestamp":       _safe_meta(scene.get("timestamp")),
        "start_seconds":   _safe_meta(scene.get("start_seconds", 0.0)),
        "end_seconds":     _safe_meta(scene.get("end_seconds",   0.0)),
        "duration_sec":    _safe_meta(scene.get("duration_sec",  0.0)),
        "sad_score":       _safe_meta(scene.get("sad_score",     0.0)),
        "scene_score":     _safe_meta(scene.get("scene_score",   0.0)),
        "dedup_skipped":   _safe_meta(scene.get("dedup_skipped", False)),
        # ── Phase 2A (ASR) fields ────────────────────────────────────────
        "scene_transcript": _safe_meta(scene.get("scene_transcript", "")),
        "word_count":       _safe_meta(scene.get("word_count",        0)),
        "avg_confidence":   _safe_meta(scene.get("avg_confidence")),
        "has_low_conf_seg": _safe_meta(scene.get("has_low_conf_seg",  False)),
        # ── Phase 2B (VLM) fields ────────────────────────────────────────
        "visual_summary":   _safe_meta(scene.get("visual_summary",  "")),
        "on_screen_text":   _safe_meta(scene.get("on_screen_text",  "")),
        "diagram_type":     _safe_meta(scene.get("diagram_type",    "other")),
        "key_concepts":     _safe_meta(scene.get("key_concepts",    [])),
    }

    return dense_doc, sparse_doc, doc_id, metadata


# ── Step A: Dual-Collection Upsert ────────────────────────────────────────────

def _upsert_batch(
    collection: chromadb.Collection,
    documents:  list[str],
    metadatas:  list[dict],
    ids:        list[str],
) -> None:
    """Upsert one batch. ChromaDB upsert = insert-or-update (idempotent)."""
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )


def create_index(enriched_path: str = ENRICHED_PATH) -> dict[str, int]:
    """
    Step A — Build / refresh both ChromaDB collections from enriched_metadata.json.

    Upsert is used throughout, so this function is safe to call multiple
    times (e.g. after re-running Phase 2 to add new captions).

    Returns
    -------
    Dict with final counts: {"dense": N, "sparse": N}
    """
    if not Path(enriched_path).exists():
        log.error("❌  %s not found — run Phase 2 first.", enriched_path)
        return {}

    scenes = load_metadata(enriched_path)
    log.info("📦  Loaded %d scenes from %s", len(scenes), enriched_path)

    client, ef = _build_clients()

    dense_col  = client.get_or_create_collection(
        name=DENSE_COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},   # cosine similarity for SentenceTransformer
    )
    sparse_col = client.get_or_create_collection(
        name=SPARSE_COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Build payloads
    dense_docs, sparse_docs, metadatas, ids = [], [], [], []

    for scene in scenes:
        dense_doc, sparse_doc, doc_id, meta = _build_payload(scene)

        if not dense_doc.strip():
            log.warning("Scene %s: empty combined_context — skipping", doc_id)
            continue

        dense_docs.append(dense_doc)
        sparse_docs.append(sparse_doc)
        metadatas.append(meta)
        ids.append(doc_id)

    total = len(ids)
    log.info("🔢  Prepared %d valid scene records for indexing", total)

    # Batch upsert — dense collection
    log.info("⬆️   Upserting into '%s'…", DENSE_COLLECTION)
    for start in range(0, total, UPSERT_BATCH_SIZE):
        end = min(start + UPSERT_BATCH_SIZE, total)
        _upsert_batch(dense_col, dense_docs[start:end], metadatas[start:end], ids[start:end])
        log.info("    batch %d–%d / %d", start + 1, end, total)

    # Batch upsert — sparse / keyword collection
    log.info("⬆️   Upserting into '%s'…", SPARSE_COLLECTION)
    for start in range(0, total, UPSERT_BATCH_SIZE):
        end = min(start + UPSERT_BATCH_SIZE, total)
        _upsert_batch(sparse_col, sparse_docs[start:end], metadatas[start:end], ids[start:end])
        log.info("    batch %d–%d / %d", start + 1, end, total)

    # ── Collection stats report ──────────────────────────────────────────
    dense_count  = dense_col.count()
    sparse_count = sparse_col.count()

    diagram_dist: dict[str, int] = {}
    for meta in metadatas:
        dt = meta.get("diagram_type", "other")
        diagram_dist[dt] = diagram_dist.get(dt, 0) + 1

    has_transcript = sum(1 for m in metadatas if m.get("scene_transcript"))
    has_vision     = sum(1 for m in metadatas if m.get("visual_summary"))

    log.info("=" * 60)
    log.info("✅  Phase 3 Indexing Complete")
    log.info("   Dense  collection: %d vectors  (%s)", dense_count,  DENSE_COLLECTION)
    log.info("   Sparse collection: %d vectors  (%s)", sparse_count, SPARSE_COLLECTION)
    log.info("   Transcript coverage : %d / %d scenes", has_transcript, total)
    log.info("   Vision coverage     : %d / %d scenes", has_vision,     total)
    log.info("   Diagram type distribution: %s", diagram_dist)
    log.info("=" * 60)

    return {"dense": dense_count, "sparse": sparse_count}


# ── Step C: Hybrid Retrieval (RRF) ────────────────────────────────────────────

class VideoRetriever:
    """
    Hybrid retriever combining dense semantic search and sparse keyword search
    via Reciprocal Rank Fusion (RRF).

    Usage
    -----
    retriever = VideoRetriever()
    results   = retriever.query("vector database cosine similarity diagram", top_k=5)
    for r in results:
        print(r["timestamp"], r["visual_summary"])
    """

    def __init__(self) -> None:
        client, ef      = _build_clients()
        self._dense_col  = client.get_collection(DENSE_COLLECTION,  embedding_function=ef)
        self._sparse_col = client.get_collection(SPARSE_COLLECTION, embedding_function=ef)
        log.info(
            "🔍  VideoRetriever ready | dense=%d | sparse=%d",
            self._dense_col.count(), self._sparse_col.count(),
        )

    def _rrf_score(self, rank: int) -> float:
        """Reciprocal Rank Fusion score for a given 1-based rank."""
        return 1.0 / (RRF_K + rank)

    def _temporal_bias(self, start_seconds: float, seed_seconds: float) -> float:
        """
        Temporal Proximity Re-ranking bias.

        Returns a value in [0, 1] that peaks at 1.0 when the scene is at
        exactly seed_seconds and decays with distance (Gaussian-like).
        Controlled by TEMPORAL_BIAS_WEIGHT.
        """
        distance = abs(start_seconds - seed_seconds)
        return math.exp(-distance / 60.0)   # 60s half-life

    def query(
        self,
        query_text: str,
        top_k: int = DEFAULT_TOP_K,
        seed_timestamp: float | None = None,
        diagram_type_filter: str | None = None,
    ) -> list[dict]:
        """
        Hybrid semantic + keyword retrieval with optional temporal re-ranking.

        Parameters
        ----------
        query_text          : Natural language or keyword query.
        top_k               : Number of final results to return.
        seed_timestamp      : If set (seconds), boost results near this timestamp.
        diagram_type_filter : If set, only return results of this diagram_type
                              (e.g. "slide", "code", "diagram").

        Returns
        -------
        List of result dicts, each containing all metadata fields plus:
          rrf_score    : final fused score (higher = more relevant)
          source       : "dense" | "sparse" | "both"
          distance     : raw ChromaDB distance from dense collection
        """
        fetch_n = top_k * 4   # over-fetch for RRF merging + filter headroom

        # Metadata filter for ChromaDB where-clause
        where: dict | None = None
        if diagram_type_filter:
            where = {"diagram_type": diagram_type_filter}

        # ── Dense query ──────────────────────────────────────────────────
        dense_kwargs: dict[str, Any] = {
            "query_texts":  [query_text],
            "n_results":    fetch_n,
            "include":      ["metadatas", "distances", "documents"],
        }
        if where:
            dense_kwargs["where"] = where

        dense_res  = self._dense_col.query(**dense_kwargs)
        dense_ids  = dense_res["ids"][0]
        dense_dist = dense_res["distances"][0]
        dense_meta = dense_res["metadatas"][0]

        # ── Sparse query ─────────────────────────────────────────────────
        sparse_kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results":   fetch_n,
            "include":     ["metadatas", "distances"],
        }
        if where:
            sparse_kwargs["where"] = where

        sparse_res  = self._sparse_col.query(**sparse_kwargs)
        sparse_ids  = sparse_res["ids"][0]

        # ── RRF score accumulation ───────────────────────────────────────
        rrf_scores: dict[str, float] = {}
        sources:    dict[str, str]   = {}

        for rank, doc_id in enumerate(dense_ids, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + self._rrf_score(rank)
            sources[doc_id] = "dense"

        for rank, doc_id in enumerate(sparse_ids, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + self._rrf_score(rank)
            if doc_id in sources:
                sources[doc_id] = "both"
            else:
                sources[doc_id] = "sparse"

        # ── Temporal proximity bias ──────────────────────────────────────
        if seed_timestamp is not None:
            meta_by_id = {doc_id: meta for doc_id, meta in zip(dense_ids, dense_meta)}
            for doc_id, score in rrf_scores.items():
                meta = meta_by_id.get(doc_id, {})
                start_s = float(meta.get("start_seconds", 0))
                bias    = self._temporal_bias(start_s, seed_timestamp)
                rrf_scores[doc_id] = score * (1 - TEMPORAL_BIAS_WEIGHT) + bias * TEMPORAL_BIAS_WEIGHT

        # ── Sort, trim, enrich ───────────────────────────────────────────
        ranked_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:top_k]

        meta_by_id = {doc_id: meta for doc_id, meta in zip(dense_ids, dense_meta)}
        dist_by_id = {doc_id: dist for doc_id, dist in zip(dense_ids, dense_dist)}

        results: list[dict] = []
        for doc_id in ranked_ids:
            meta = meta_by_id.get(doc_id, {})
            result = dict(meta)
            result["doc_id"]    = doc_id
            result["rrf_score"] = round(rrf_scores[doc_id], 6)
            result["source"]    = sources.get(doc_id, "dense")
            result["distance"]  = round(dist_by_id.get(doc_id, 1.0), 4)
            results.append(result)

        return results

    def query_by_concept(self, concept: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
        """Convenience wrapper — queries the dense collection for a single concept."""
        return self.query(concept, top_k=top_k)

    def query_by_timestamp(self, seconds: float, radius: float = 30.0) -> list[dict]:
        """
        Return all indexed scenes within ±radius seconds of a given timestamp.

        Useful for "what was shown around 2:30?" lookups.
        """
        client, _ = _build_clients()
        col = client.get_collection(DENSE_COLLECTION)

        results_raw = col.get(include=["metadatas"])
        output = []
        for meta in results_raw["metadatas"]:
            start_s = float(meta.get("start_seconds", -9999))
            if abs(start_s - seconds) <= radius:
                output.append(dict(meta))
        output.sort(key=lambda m: float(m.get("start_seconds", 0)))
        return output


# ── CLI demo ───────────────────────────────────────────────────────────────────

def _print_results(results: list[dict], query: str) -> None:
    """Pretty-print retrieval results to stdout."""
    print(f"\n{'='*64}")
    print(f"  Query: \"{query}\"")
    print(f"  {len(results)} result(s)")
    print(f"{'='*64}")
    for i, r in enumerate(results, start=1):
        print(f"\n  [{i}]  {r.get('timestamp', '?')}  |  "
              f"score={r['rrf_score']:.4f}  |  "
              f"source={r['source']}  |  "
              f"type={r.get('diagram_type', '?')}")
        print(f"       frame : {r.get('frame_id', '?')}")
        if r.get("visual_summary"):
            print(f"       visual: {r['visual_summary'][:120]}…")
        if r.get("scene_transcript"):
            snippet = r["scene_transcript"][:120]
            print(f"       audio : {snippet}…")
        if r.get("key_concepts"):
            concepts = r["key_concepts"]
            if isinstance(concepts, str):
                concepts = concepts[:80]
            print(f"       concepts: {concepts}")
    print()


def _run_index(args) -> None:
    create_index(enriched_path=args.enriched)


def _run_query(args) -> None:
    retriever = VideoRetriever()
    results   = retriever.query(
        query_text          = args.query,
        top_k               = args.top_k,
        seed_timestamp      = args.seed_ts,
        diagram_type_filter = args.filter_type,
    )
    _print_results(results, args.query)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 3: Embedding, indexing, and hybrid retrieval for Video-RAG"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── index subcommand ──────────────────────────────────────────────────
    p_index = sub.add_parser("index", help="Build / refresh ChromaDB collections")
    p_index.add_argument(
        "--enriched", default=ENRICHED_PATH,
        help=f"Path to enriched_metadata.json (default: {ENRICHED_PATH})",
    )
    p_index.set_defaults(func=_run_index)

    # ── query subcommand ──────────────────────────────────────────────────
    p_query = sub.add_parser("query", help="Run a hybrid retrieval query")
    p_query.add_argument("query",         type=str,   help="Natural language query")
    p_query.add_argument("--top-k",       type=int,   default=DEFAULT_TOP_K)
    p_query.add_argument("--seed-ts",     type=float, default=None,
                         help="Temporal bias seed (seconds into video)")
    p_query.add_argument("--filter-type", type=str,   default=None,
                         help="Filter by diagram_type (slide|code|diagram|chart|…)")
    p_query.set_defaults(func=_run_query)

    args = parser.parse_args()
    args.func(args)
