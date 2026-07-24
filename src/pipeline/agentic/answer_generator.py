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
                config=genai_types.GenerateContentConfig(temperature=0.1, max_output_tokens=800),
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
        evidence_lines = []
        for item in packet.get("verified_evidence", []):
            evidence_lines.append(
                f"[{item['citation_id']}] {format_ms(item['start_ms'])}-{format_ms(item['end_ms'])}: "
                f"{item.get('text', '')} Visual: {item.get('visual_summary', '')}"
            )
        return (
            "Answer the video question using only the evidence below.\n"
            "Every factual video claim must cite one or more evidence IDs like [S1].\n"
            "Include the most useful timestamp. If evidence is partial, say so.\n"
            "Do not mention filesystem paths.\n\n"
            f"Question: {packet['question']}\n"
            f"Timeline context: {packet.get('temporal_context', {}).get('timeline_summary', '')}\n\n"
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
        evidence = packet.get("verified_evidence", [])
        first = evidence[0]
        timestamp = format_ms(first["start_ms"])
        text = _best_supported_excerpt(
            first.get("text") or first.get("visual_summary") or "The retrieved evidence is available for this moment.",
            packet.get("question", ""),
        )
        text = _as_single_claim(text)
        answer = (
            f"At around {timestamp}, the video evidence says: {text} [{first['citation_id']}]."
        )
        question = packet.get("question", "")
        if question and is_explanatory_query(question):
            try:
                from src.pipeline.knowledge_reconstruction import reconstruct_knowledge

                reconstruction = reconstruct_knowledge(question, evidence)
                concepts = reconstruction.learning_path.ordered_concepts
                if len(concepts) > 1:
                    chain = " -> ".join(concepts)
                    answer = (
                        f"Prerequisite Learning Path: {chain} [{first['citation_id']}].\n\n"
                        + answer
                    )
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
        return _first_supported_sentence(compact, limit=limit)
    comparison = bool(re.search(r"\b(?:compare|compared|comparison|versus|vs)\b", question, re.I))
    max_sentences = 3 if comparison else 1
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
