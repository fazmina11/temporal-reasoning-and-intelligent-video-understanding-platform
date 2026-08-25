"""
src/pipeline/topic_summarization.py — LLM-based Topic Summarization
====================================================================

Replaces the naive "first N words" approach with actual LLM-generated
topic summaries for semantic chunks and events.

Uses the multi-provider client (providers.py) with automatic fallback:
  1. Groq  (qwen/qwen3.6-27b)     — 14,400 req/day, primary
  2. Gemini (gemini-2.5-flash)      — 1,500 req/day, fallback

Produces:
  - title: concise 5-8 word topic label
  - summary_text: 1-2 sentence topic summary
  - topics: list of key topic keywords

If LLM is unavailable, falls back to an extractive approach that
selects the most informative sentences from the transcript.
"""

from __future__ import annotations

import json
import re
import logging
from pathlib import Path
from typing import Any

from .json_artifacts import read_json, write_json_atomic
from .media_manifest import load_manifest, save_manifest, utc_now
from .providers import call_llm

logger = logging.getLogger("topic_summarization")


def _summarize_with_llm(texts: list[str], context: str = "video segment") -> dict[str, Any]:
    """Use the multi-provider LLM to generate a topic summary for a list of transcript texts."""
    combined = "\n".join(f"[Segment {i+1}] {t}" for i, t in enumerate(texts) if t.strip())
    if not combined.strip():
        return {"title": "Visual or silent segment", "summary_text": "", "topics": []}

    prompt = f"""Analyze this {context} transcript and produce a concise topic summary.

Transcript:
{combined}

Return ONLY a JSON object with these fields:
{{
  "title": "concise 5-8 word topic label",
  "summary_text": "1-2 sentence summary of what this segment is about",
  "topics": ["topic1", "topic2", "topic3"]
}}

Rules:
- Title should describe the TOPIC, not quote the transcript
- Summary should explain the SUBJECT MATTER, not repeat words
- Topics should be noun phrases for search indexing
- Be specific: "Samsung Galaxy Watch 9 health features" not just "health"
- Do NOT use <think> tags or any reasoning tokens.
"""

    result_text = call_llm(
        prompt=prompt,
        max_tokens=300,
        temperature=0.3,
    )

    if result_text:
        # Parse JSON from response
        # Strip thinking tags if any
        result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL)
        # Strip markdown fences
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r'^```\w*\s*\n?', '', result_text)
            result_text = re.sub(r'\n?```\s*$', '', result_text)

        json_match = re.search(r'\{[^{}]*\}', result_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                logger.info("LLM summarization succeeded: title=%s", result.get("title", "")[:50])
                return {
                    "title": result.get("title", "")[:100],
                    "summary_text": result.get("summary_text", "")[:500],
                    "topics": result.get("topics", [])[:10],
                }
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse LLM response: %s", e)

    return _extractive_summary(texts)


def _extractive_summary(texts: list[str]) -> dict[str, Any]:
    """Fallback: extractive summarization without LLM."""
    combined = " ".join(t.strip() for t in texts if t.strip())
    if not combined.strip():
        return {"title": "Visual or silent segment", "summary_text": "", "topics": []}

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', combined)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # Title: first meaningful phrase (first 8 content words)
    words = re.findall(r'[A-Za-z0-9][A-Za-z0-9\'-]+', combined)
    # Skip filler words
    fillers = {'um', 'uh', 'hmm', 'like', 'well', 'yeah', 'oh', 'hey', 'so', 'but'}
    content_words = [w for w in words if w.lower() not in fillers]
    title = " ".join(content_words[:8]) if content_words else "Video segment"

    # Summary: first 2 meaningful sentences
    summary = " ".join(sentences[:2]) if sentences else combined[:200]

    # Topics: extract noun phrases (simple heuristic)
    topic_words = [w for w in content_words if len(w) > 3]
    topics = list(dict.fromkeys(topic_words[:5]))  # unique, first 5

    return {
        "title": title[:100],
        "summary_text": summary[:500],
        "topics": topics,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def enrich_chunk_summaries(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Add LLM-based topic summaries to semantic chunks."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    chunks_path = Path(manifest["artifacts"]["semantic_chunks_path"])

    if not chunks_path.is_file():
        raise FileNotFoundError(f"Semantic chunks not found: {chunks_path}")

    payload = read_json(chunks_path)
    chunks = payload.get("chunks", [])

    enriched_count = 0
    for chunk in chunks:
        # Skip already-enriched chunks (have non-trivial topics)
        if chunk.get("topics") and len(chunk["topics"]) > 0:
            continue

        transcript = chunk.get("transcript_text", "")
        if not transcript.strip():
            chunk["title"] = "Visual or silent segment"
            chunk["summary_text"] = ""
            chunk["topics"] = []
            continue

        result = _summarize_with_llm(
            [transcript],
            context=f"semantic chunk ({chunk.get('duration_ms', 0)/1000:.0f}s video segment)"
        )
        chunk["title"] = result["title"]
        chunk["summary_text"] = result["summary_text"]
        chunk["topics"] = result["topics"]
        enriched_count += 1

    payload["updated_at"] = utc_now()
    write_json_atomic(chunks_path, payload)

    return {
        "video_id": video_id,
        "chunk_count": len(chunks),
        "enriched_count": enriched_count,
    }


def enrich_event_summaries(*, repo_root: Path, video_id: str) -> dict[str, Any]:
    """Add LLM-based topic summaries and labels to events."""
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root=repo_root, video_id=video_id)
    events_path = Path(manifest["artifacts"]["events_path"])

    if not events_path.is_file():
        raise FileNotFoundError(f"Events not found: {events_path}")

    payload = read_json(events_path)
    events = payload.get("events", [])

    enriched_count = 0
    for event in events:
        # Skip already-enriched
        if event.get("topics") and len(event["topics"]) > 0:
            continue

        transcript = event.get("transcript_text", "")
        if not transcript.strip():
            event["title"] = "Visual or silent event"
            event["summary_text"] = ""
            event["label"] = "visual"
            event["content"] = ""
            event["topics"] = []
            continue

        # Gather chunk transcripts for richer context
        chunk_ids = event.get("chunk_ids", [])
        chunks_path = Path(manifest["artifacts"]["semantic_chunks_path"])
        chunk_payload = read_json(chunks_path)
        chunk_map = {c["chunk_id"]: c for c in chunk_payload.get("chunks", [])}
        chunk_transcripts = [
            chunk_map[cid].get("transcript_text", "")
            for cid in chunk_ids
            if cid in chunk_map
        ]

        result = _summarize_with_llm(
            chunk_transcripts if chunk_transcripts else [transcript],
            context=f"video event ({event.get('duration_ms', 0)/1000:.0f}s)"
        )
        event["title"] = result["title"]
        event["summary_text"] = result["summary_text"]
        event["topics"] = result["topics"]
        # Label and content for the evidence pipeline
        event["label"] = result["title"]
        event["content"] = result["summary_text"]
        enriched_count += 1

    payload["updated_at"] = utc_now()
    write_json_atomic(events_path, payload)

    return {
        "video_id": video_id,
        "event_count": len(events),
        "enriched_count": enriched_count,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enrich chunk and event summaries with LLM")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--chunks-only", action="store_true")
    parser.add_argument("--events-only", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)

    if not args.events_only:
        chunk_result = enrich_chunk_summaries(repo_root=repo_root, video_id=args.video_id)
        print(f"Chunks: {chunk_result['enriched_count']}/{chunk_result['chunk_count']} enriched")

    if not args.chunks_only:
        event_result = enrich_event_summaries(repo_root=repo_root, video_id=args.video_id)
        print(f"Events: {event_result['enriched_count']}/{event_result['event_count']} enriched")


if __name__ == "__main__":
    main()
