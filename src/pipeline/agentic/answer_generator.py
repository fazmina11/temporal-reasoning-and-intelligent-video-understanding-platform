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
            return self._local_answer(evidence_packet, fallback_used=True, model="local_grounded")
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=self._prompt(evidence_packet),
                config=genai_types.GenerateContentConfig(temperature=0.1, max_output_tokens=800),
            )
            answer = str(response.text or "").strip()
            if not answer:
                return self._local_answer(evidence_packet, fallback_used=True, model="local_empty_model_response")
            return {"answer": _strip_paths(answer), "fallback_used": False, "model": GEMINI_MODEL}
        except Exception as exc:
            fallback = self._local_answer(evidence_packet, fallback_used=True, model="local_gemini_error")
            fallback["error"] = str(exc)
            return fallback

    def revise(self, evidence_packet: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        supported_ids = {claim.get("required_citation") for claim in verification.get("claims", []) if claim.get("label") == "supported"}
        if not supported_ids:
            return self._local_answer(evidence_packet, fallback_used=True, model="local_revision")
        evidence = [
            item
            for item in evidence_packet.get("verified_evidence", [])
            if item["citation_id"] in supported_ids
        ]
        revised_packet = {**evidence_packet, "verified_evidence": evidence}
        return self._local_answer(revised_packet, fallback_used=True, model="local_revision")

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

    def _local_answer(self, packet: dict[str, Any], *, fallback_used: bool, model: str) -> dict[str, Any]:
        evidence = packet.get("verified_evidence", [])
        first = evidence[0]
        timestamp = format_ms(first["start_ms"])
        text = _first_supported_sentence(
            first.get("text") or first.get("visual_summary") or "The retrieved evidence is available for this moment."
        )
        answer = (
            f"At around {timestamp}, the video evidence says: {text} [{first['citation_id']}]."
        )
        if len(evidence) > 1:
            support = evidence[1]
            support_text = _first_supported_sentence(support.get("text") or support.get("visual_summary") or "")
            answer += f"\n\nA nearby supporting moment adds: {support_text[:350]} [{support['citation_id']}]."
        notes = packet.get("missing_evidence_notes") or []
        if notes:
            answer += "\n\nLimitations: " + "; ".join(notes)
        return {"answer": _strip_paths(answer), "fallback_used": fallback_used, "model": model}


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
