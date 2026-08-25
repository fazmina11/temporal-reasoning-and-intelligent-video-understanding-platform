from __future__ import annotations

import os
import re
from typing import Any

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from src.pipeline.knowledge_reconstruction import is_explanatory_query


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")



class GroundedAnswerGenerator:
    def __init__(self) -> None:
        self.client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if genai is not None and genai_types is not None and api_key:
            self.client = genai.Client(api_key=api_key)

    def generate(self, evidence_packet: dict[str, Any]) -> dict[str, Any]:
        if not evidence_packet.get("verified_evidence"):
            return {
                "answer": "I could not find enough reliable evidence in this video to answer that question.",
                "fallback_used": True,
                "model": "local_no_evidence",
            }
        if self.client is None:
            return self._local_answer(
                evidence_packet,
                fallback_used=False,
                model="local_grounded",
                provider_fallback_used=False,
            )
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=self._prompt(evidence_packet),
                config=genai_types.GenerateContentConfig(
                    temperature=0.1, max_output_tokens=1200
                ),
            )
            answer = str(response.text or "").strip()
            if not answer:
                return self._local_answer(
                    evidence_packet,
                    fallback_used=False,
                    model="local_empty_model_response",
                    provider_fallback_used=True,
                )
            return {
                "answer": _strip_paths(answer),
                "fallback_used": False,
                "provider_fallback_used": False,
                "citation_preserving": True,
                "model": GEMINI_MODEL,
            }
        except Exception as exc:
            fallback = self._local_answer(
                evidence_packet,
                fallback_used=False,
                model="local_gemini_error",
                provider_fallback_used=True,
            )
            fallback["error"] = str(exc)
            return fallback

    def revise(self, evidence_packet: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        supported_ids = {claim.get("required_citation") for claim in verification.get("claims", []) if claim.get("label") == "supported"}
        if not supported_ids:
            return self._local_answer(
                evidence_packet,
                fallback_used=False,
                model="local_revision",
                provider_fallback_used=True,
            )
        evidence = [
            item
            for item in evidence_packet.get("verified_evidence", [])
            if item["citation_id"] in supported_ids
        ]
        revised_packet = {**evidence_packet, "verified_evidence": evidence}
        return self._local_answer(
            revised_packet,
            fallback_used=False,
            model="local_revision",
            provider_fallback_used=True,
        )

    def _prompt(self, packet: dict[str, Any]) -> str:
        """Build a rich prompt that encourages synthesizing multiple evidence items."""
        evidence_lines = []
        for item in packet.get("verified_evidence", []):
            ts = f"{format_ms(item['start_ms'])}-{format_ms(item['end_ms'])}"
            text_part = item.get("text", "") or ""
            visual_part = item.get("visual_summary", "") or ""
            ocr_part = ""
            if item.get("ocr_text"):
                ocr_part = " OCR: " + " ".join(item["ocr_text"])
            evidence_lines.append(
                f"[{item['citation_id']}] ({ts}) {text_part}"
                + (f" Visual: {visual_part}" if visual_part else "")
                + ocr_part
            )

        timeline = packet.get("temporal_context", {}).get("timeline_summary", "")
        # Build a compact timeline of evidence timestamps
        evidence_timeline = _build_evidence_timeline(
            packet.get("verified_evidence", [])
        )

        return (
            "You are answering a question about a video using ONLY the evidence below.\n\n"
            "INSTRUCTIONS:\n"
            "- Synthesize information from MULTIPLE evidence items to give a comprehensive answer.\n"
            "- Cover ALL relevant timestamps and moments, not just the first one.\n"
            "- Every factual claim MUST cite evidence IDs like [S1], [S2], etc.\n"
            "- Include timestamps for each key point (e.g., at 0:07, at 1:32).\n"
            "- If different evidence items describe different aspects, combine them into a complete picture.\n"
            "- If evidence is partial or contradictory, acknowledge it.\n"
            "- Do not mention filesystem paths.\n"
            "- Be specific and detailed. List individual items, timestamps, and values when available.\n\n"
            f"Question: {packet['question']}\n\n"
            f"Timeline context: {timeline}\n\n"
            f"Evidence timeline: {evidence_timeline}\n\n"
            "Evidence:\n"
            + "\n".join(evidence_lines)
        )

    def _local_answer(
        self,
        packet: dict[str, Any],
        *,
        fallback_used: bool,
        model: str,
        provider_fallback_used: bool = False,
    ) -> dict[str, Any]:
        """Build a comprehensive answer from multiple verified evidence items."""
        evidence = packet.get("verified_evidence", [])
        question = packet.get("question", "")

        if not evidence:
            return {
                "answer": "I could not find enough reliable evidence in this video to answer that question.",
                "fallback_used": fallback_used,
                "provider_fallback_used": provider_fallback_used,
                "citation_preserving": True,
                "model": model,
            }

        # If only one evidence item, use the simple path
        if len(evidence) == 1:
            return self._single_evidence_answer(
                evidence[0], packet, fallback_used=fallback_used,
                model=model, provider_fallback_used=provider_fallback_used,
            )

        # Multi-evidence synthesis
        answer_parts = []
        cited_ids = set()

        # Group evidence by source type for structured reporting
        by_type: dict[str, list[dict[str, Any]]] = {}
        for item in evidence:
            src_type = item.get("evidence_type") or item.get("source_type") or "unknown"
            by_type.setdefault(src_type, []).append(item)

        # Extract unique content points across all evidence
        content_points = _extract_content_points(evidence, question)
        
        # Build answer from content points
        for point in content_points:
            ts = format_ms(point["start_ms"])
            text = point["text"]
            citation = point["citation_id"]
            cited_ids.add(citation)
            answer_parts.append(f"At {ts}, {text} [{citation}]")

        # If we have visual-only evidence, add those descriptions
        for item in evidence:
            visual = item.get("visual_summary", "")
            if visual and item["citation_id"] not in cited_ids:
                ts = format_ms(item["start_ms"])
                cited_ids.add(item["citation_id"])
                answer_parts.append(f"At {ts}, visually: {visual[:200]} [{item['citation_id']}]")

        # If we didn't get enough from content points, fall back to best excerpts
        if len(answer_parts) < 2:
            for item in evidence[:5]:
                if item["citation_id"] not in cited_ids:
                    text = item.get("text") or item.get("visual_summary") or ""
                    if text:
                        excerpt = _best_supported_excerpt(text, question, limit=200)
                        if excerpt:
                            ts = format_ms(item["start_ms"])
                            answer_parts.append(
                                f"At {ts}: {excerpt} [{item['citation_id']}]"
                            )
                            cited_ids.add(item["citation_id"])

        answer = ". ".join(answer_parts) if answer_parts else _build_single_answer(evidence[0], question)

        # Add explanatory learning path for explanatory queries
        if question and is_explanatory_query(question):
            try:
                from src.pipeline.knowledge_reconstruction import reconstruct_knowledge
                reconstruction = reconstruct_knowledge(question, evidence)
                concepts = reconstruction.learning_path.ordered_concepts
                if len(concepts) > 1:
                    chain = " -> ".join(concepts)
                    answer = f"Prerequisite Learning Path: {chain}.\n\n{answer}"
            except Exception:
                pass

        notes = packet.get("missing_evidence_notes") or []
        if notes:
            answer += "\n\nLimitations: " + "; ".join(notes)

        return {
            "answer": _strip_paths(answer),
            "fallback_used": fallback_used,
            "provider_fallback_used": provider_fallback_used,
            "citation_preserving": True,
            "model": model,
        }

    def _single_evidence_answer(
        self,
        item: dict[str, Any],
        packet: dict[str, Any],
        *,
        fallback_used: bool,
        model: str,
        provider_fallback_used: bool = False,
    ) -> dict[str, Any]:
        """Handle the case where only one evidence item exists."""
        timestamp = format_ms(item["start_ms"])
        text = _best_supported_excerpt(
            item.get("text") or item.get("visual_summary") or "The retrieved evidence is available for this moment.",
            packet.get("question", ""),
        )
        text = _as_single_claim(text)
        answer = f"At around {timestamp}, the video evidence says: {text} [{item['citation_id']}]."

        question = packet.get("question", "")
        if question and is_explanatory_query(question):
            try:
                from src.pipeline.knowledge_reconstruction import reconstruct_knowledge
                reconstruction = reconstruct_knowledge(question, [item])
                concepts = reconstruction.learning_path.ordered_concepts
                if len(concepts) > 1:
                    chain = " -> ".join(concepts)
                    answer = f"Prerequisite Learning Path: {chain} [{item['citation_id']}].\n\n{answer}"
            except Exception:
                pass

        notes = packet.get("missing_evidence_notes") or []
        if notes:
            answer += "\n\nLimitations: " + "; ".join(notes)

        return {
            "answer": _strip_paths(answer),
            "fallback_used": fallback_used,
            "provider_fallback_used": provider_fallback_used,
            "citation_preserving": True,
            "model": model,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_evidence_timeline(evidence: list[dict[str, Any]]) -> str:
    """Build a compact timeline string from evidence items."""
    if not evidence:
        return ""
    entries = []
    for item in evidence[:10]:
        ts = format_ms(item["start_ms"])
        text = (item.get("text") or item.get("visual_summary") or "")[:80]
        entries.append(f"{item['citation_id']}@{ts}: {text}")
    return " | ".join(entries)


def _extract_content_points(
    evidence: list[dict[str, Any]], question: str
) -> list[dict[str, Any]]:
    """Extract the most relevant content points from evidence items."""
    terms = _answer_terms(question)
    points = []

    for item in evidence:
        # Combine all text sources
        all_text = " ".join(
            str(item.get(key, ""))
            for key in ("text", "visual_summary", "transcript")
            if item.get(key)
        )
        if not all_text.strip():
            continue

        # Score relevance to question
        normalized = all_text.lower()
        if terms:
            relevance = sum(1 for term in terms if term in normalized) / len(terms)
        else:
            relevance = 0.3  # Default relevance if no terms

        # Extract the most relevant excerpt
        excerpt = _best_supported_excerpt(all_text, question, limit=300)
        if not excerpt:
            continue

        points.append({
            "start_ms": item.get("start_ms", 0),
            "end_ms": item.get("end_ms", 0),
            "text": excerpt,
            "citation_id": item.get("citation_id", ""),
            "relevance": relevance,
            "source_type": item.get("source_type", "unknown"),
        })

    # Sort by relevance, then by timestamp for chronological order
    points.sort(key=lambda p: (-p["relevance"], p["start_ms"]))

    # Deduplicate: keep only the best excerpt per timestamp range
    deduped = []
    seen_ranges: set[tuple[int, int]] = set()
    for point in points:
        # Check if this timestamp range is already covered
        time_key = (point["start_ms"] // 5000, point["end_ms"] // 5000)
        if time_key not in seen_ranges or point["relevance"] > 0.5:
            deduped.append(point)
            seen_ranges.add(time_key)

    # Sort chronologically for the final answer
    deduped.sort(key=lambda p: p["start_ms"])
    return deduped


def _build_single_answer(item: dict[str, Any], question: str) -> str:
    """Build a single-evidence answer as last resort."""
    timestamp = format_ms(item.get("start_ms", 0))
    text = item.get("text") or item.get("visual_summary") or "evidence available"
    excerpt = _best_supported_excerpt(text, question, limit=300)
    citation = item.get("citation_id", "S1")
    if excerpt:
        return f"At {timestamp}: {excerpt} [{citation}]"
    return f"Evidence found at {timestamp} [{citation}]"


def format_ms(ms: int) -> str:
    seconds = max(0, int(ms // 1000))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _strip_paths(text: str) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^\s]+", "[media]", text)
    text = re.sub(r"data/processed/[^\s]+", "[media]", text)
    return text


def _sentence_stem(text: str) -> str:
    return str(text).strip().rstrip(" .!?;:")


def _first_supported_sentence(text: str, limit: int = 320) -> str:
    compact = " ".join(str(text).split())
    parts = re.split(r"(?<=[.!?])\s+", compact)
    sentence = parts[0] if parts and parts[0] else compact
    return _sentence_stem(sentence[:limit])


def _best_supported_excerpt(text: str, question: str, limit: int = 420) -> str:
    compact = " ".join(str(text).split())
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if part.strip()]
    if not sentences:
        return _first_supported_sentence(compact, limit=limit)

    terms = _answer_terms(question)
    if not terms:
        # No question terms — take the longest/most informative sentence
        best = max(sentences, key=len)
        clipped = best if len(best) <= limit else best[:limit].rsplit(" ", 1)[0]
        return _sentence_stem(clipped)

    comparison = bool(re.search(r"\b(?:compare|compared|comparison|versus|vs)\b", question, re.I))
    max_sentences = 3 if comparison else 2  # Allow up to 2 sentences for richer answers
    best: tuple[float, int, int] | None = None
    best_text = sentences[0]
    for start_index in range(len(sentences)):
        for size in range(1, min(max_sentences, len(sentences) - start_index) + 1):
            candidate_text = " ".join(sentences[start_index : start_index + size])
            normalized = candidate_text.lower()
            coverage = sum(_answer_term_present(term, normalized) for term in terms) / len(terms)
            density = coverage / max(1.0, len(candidate_text) / 180.0)
            candidate = (coverage + density * 0.12, -size, -start_index)
            if best is None or candidate > best:
                best = candidate
                best_text = candidate_text
    clipped = best_text if len(best_text) <= limit else best_text[:limit].rsplit(" ", 1)[0]
    return _sentence_stem(clipped)


def _answer_terms(text: str) -> set[str]:
    stop = {
        "what", "where", "when", "why", "how", "does", "did", "the", "and",
        "from", "that", "this", "with", "about", "tell", "video", "speaker",
        "compare", "compared", "comparison", "versus",
    }
    return {
        _answer_stem(term.lower())
        for term in re.findall(r"[A-Za-z0-9]{3,}", text)
        if term.lower() not in stop
    }


def _answer_term_present(term: str, text: str) -> bool:
    return any(
        _answer_stem(token.lower()) == term
        for token in re.findall(r"[A-Za-z0-9]{3,}", text)
    )


def _answer_stem(term: str) -> str:
    for suffix in ("ization", "ation", "ing", "ed", "es", "s"):
        if len(term) > len(suffix) + 3 and term.endswith(suffix):
            return term[: -len(suffix)]
    return term


def _as_single_claim(text: str) -> str:
    parts = [
        _sentence_stem(part)
        for part in re.split(r"(?<=[.!?])\s+", str(text).strip())
        if part.strip()
    ]
    return "; ".join(parts)
