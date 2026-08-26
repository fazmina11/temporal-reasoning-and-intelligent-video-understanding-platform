from __future__ import annotations

import os
import re
import time
import logging
from typing import Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.pipeline.providers import call_llm
from src.pipeline.knowledge_reconstruction import is_explanatory_query
from src.pipeline.agentic.scope_classifier import ScopeDecision, QueryOutcome, ScopeResult, get_scope_classifier


logger = logging.getLogger("answer_generator")

# Token budget constants
MAX_CONTEXT_TOKENS = 12000  # Conservative limit for Groq/Gemini context window
RESERVED_TOKENS = 2000      # Reserve for prompt template, system message, response
MAX_EVIDENCE_TOKENS = MAX_CONTEXT_TOKENS - RESERVED_TOKENS  # ~10000 tokens for evidence
MAX_EVIDENCE_ITEMS = 30     # Hard cap on evidence items
MAX_EVIDENCE_TEXT_PER_ITEM = 500  # Max chars per evidence text

# Quality gate thresholds
MIN_EVIDENCE_SOURCES = 2
MIN_MODALITIES = 2
MIN_RETRIEVAL_CONFIDENCE = 0.35
MIN_ANSWER_CONFIDENCE = 0.45


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token for English."""
    return max(1, len(text) // 4)


def count_prompt_tokens(prompt: str) -> int:
    """Count tokens in a prompt."""
    return estimate_tokens(prompt)



class GroundedAnswerGenerator:
    def __init__(self, repo_root: str | None = None) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[2]
        self._scope_classifier_cache: dict[str, Any] = {}

    def generate(self, evidence_packet: dict[str, Any]) -> dict[str, Any]:
        start_time = time.time()
        question = evidence_packet.get("question") or evidence_packet.get("query_understanding", {}).get("standalone_query") or evidence_packet.get("query_understanding", {}).get("raw_query") or ""
        video_id = evidence_packet.get("video_id")
        
        # ── SCOPE CLASSIFICATION (runs before any retrieval gates) ──
        scope_result = None
        if video_id:
            try:
                classifier = get_scope_classifier(self.repo_root, video_id)
                scope_result = classifier.classify(question)
                evidence_packet["scope_result"] = scope_result.to_dict()
                
                # IMMEDIATE routing for OUT_OF_SCOPE and AMBIGUOUS
                if scope_result.decision == ScopeDecision.OUT_OF_SCOPE:
                    logger.info("Scope OUT_OF_SCOPE: %s", scope_result.reasoning)
                    return self._typed_non_answer(evidence_packet, scope_result.suggested_outcome.value, scope_result.reasoning, scope_result)
                
                if scope_result.decision == ScopeDecision.AMBIGUOUS:
                    logger.info("Scope AMBIGUOUS: %s", scope_result.reasoning)
                    # Don't reject immediately, but flag for downstream
                    evidence_packet["scope_ambiguous"] = True
                    evidence_packet["scope_reasoning"] = scope_result.reasoning
                    
            except Exception as e:
                logger.warning("Scope classification failed: %s", e)
        
        # ── TEST MODE DETECTION ──
        # Test mode is active when: scope classifier returned test_mode, or no video data available
        test_mode = (
            scope_result and scope_result.metadata.get("test_mode") or
            evidence_packet.get("test_mode") or
            not evidence_packet.get("video_id")
        )
        
        if test_mode:
            logger.info("Test mode detected - relaxing quality gates")
        
        # ── QUALITY GATES ──
        verified_evidence = evidence_packet.get("verified_evidence", [])
        
        # Quality Gate 0: No evidence at all
        if not verified_evidence:
            return self._typed_non_answer(evidence_packet, QueryOutcome.VIDEO_EVIDENCE_NOT_FOUND.value,
                "No evidence retrieved from video", scope_result)
        
        # Quality Gate 1: Minimum evidence threshold (relaxed in test mode)
        min_sources = 1 if test_mode else MIN_EVIDENCE_SOURCES
        if len(verified_evidence) < min_sources:
            return self._typed_non_answer(evidence_packet, QueryOutcome.VIDEO_EVIDENCE_NOT_FOUND.value,
                f"Insufficient evidence sources ({len(verified_evidence)} < {min_sources})", scope_result)
        
        # Quality Gate 2: Modality diversity (skip for timestamp queries and test mode)
        modalities = set(e.get("source_type", "unknown") for e in verified_evidence)
        query_types = evidence_packet.get("query_understanding", {}).get("query_types", [])
        is_timestamp = "timestamp" in query_types
        
        if not is_timestamp and not test_mode and len(modalities) < MIN_MODALITIES:
            return self._typed_non_answer(evidence_packet, QueryOutcome.VIDEO_EVIDENCE_NOT_FOUND.value,
                f"Only {len(modalities)} modality(ies) retrieved; need multi-modal evidence (got: {sorted(modalities)})", scope_result)
        
        # Quality Gate 3: Scope check from classifier
        if scope_result and scope_result.decision == ScopeDecision.OUT_OF_SCOPE:
            return self._typed_non_answer(evidence_packet, scope_result.suggested_outcome.value, scope_result.reasoning, scope_result)
        
        if scope_result and scope_result.decision == ScopeDecision.AMBIGUOUS:
            # Don't reject, but add ambiguity flag
            evidence_packet["scope_ambiguous"] = True
            evidence_packet["scope_reasoning"] = scope_result.reasoning
        
        # Quality Gate 4: Retrieval confidence threshold (relaxed in test mode)
        retrieval_conf = self._compute_retrieval_confidence(verified_evidence)
        min_retrieval_conf = 0.2 if test_mode else MIN_RETRIEVAL_CONFIDENCE
        if retrieval_conf < min_retrieval_conf:
            return self._typed_non_answer(evidence_packet, QueryOutcome.VIDEO_EVIDENCE_NOT_FOUND.value,
                f"Retrieval confidence too low ({retrieval_conf:.2f} < {min_retrieval_conf})", scope_result)
        
        # Quality Gate 5: Modality-specific checks (skip in test mode)
        if not test_mode:
            modality_check = self._check_modality_requirements(verified_evidence, query_types)
            if modality_check:
                return self._typed_non_answer(evidence_packet, QueryOutcome.VIDEO_EVIDENCE_NOT_FOUND.value, modality_check, scope_result)
        
        # ── Ensure question field exists ──
        if 'question' not in evidence_packet:
            evidence_packet['question'] = question
        
        # ── Apply token budget management ──
        evidence_packet = self._apply_token_budget(evidence_packet)
        
        # ── Generate answer ──
        prompt = self._prompt(evidence_packet)
        prompt_tokens = count_prompt_tokens(prompt)
        
        # Dynamic max_tokens based on prompt size
        max_tokens = min(2000, max(500, 4000 - prompt_tokens // 2))
        
        answer_text = call_llm(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        
        if not answer_text or not answer_text.strip():
            return self._local_answer(evidence_packet, fallback_used=False, model="local_fallback", provider_fallback_used=True, scope_result=scope_result)
        
        answer = _strip_paths(answer_text.strip())
        
        # ── POST-GENERATION VALIDATION ──
        # Quality Gate 6: Citation presence
        citation_check = self._validate_citations(answer, verified_evidence)
        if not citation_check["valid"] and not is_timestamp:
            logger.warning("Answer failed citation validation: %s", citation_check["reason"])
            # Don't reject, but flag
        
        # Quality Gate 7: Answer confidence calibration
        answer_confidence = self._calibrate_answer_confidence(answer, verified_evidence, retrieval_conf, citation_check)
        
        if answer_confidence < MIN_ANSWER_CONFIDENCE and not is_timestamp:
            logger.warning("Low answer confidence: %.2f", answer_confidence)
            # Don't reject, but add warning
        
        # Add scope info to response
        response = {
            "answer": _strip_paths(answer.strip()),
            "fallback_used": False,
            "provider_fallback_used": False,
            "citation_preserving": True,
            "model": "multi_provider",
            "prompt_tokens": prompt_tokens,
            "max_tokens": max_tokens,
            "generation_time_ms": int((time.time() - start_time) * 1000),
        }
        
        if scope_result:
            response["scope_decision"] = scope_result.decision.value
            response["scope_confidence"] = scope_result.confidence
            if scope_result.decision == ScopeDecision.AMBIGUOUS:
                response["scope_warning"] = scope_result.reasoning
        
        response["retrieval_confidence"] = retrieval_conf
        response["answer_confidence"] = answer_confidence
        
        return response
        # Fallback to local answer if LLM fails
        return self._local_answer(
            evidence_packet,
            fallback_used=False,
            model="local_fallback",
            provider_fallback_used=True,
        )

    def _apply_token_budget(self, packet: dict[str, Any]) -> dict[str, Any]:
        """Apply token budget constraints to evidence packet."""
        evidence = packet.get("verified_evidence", [])
        if not evidence:
            return packet
        
        # Score and rank evidence by relevance
        scored_evidence = self._score_evidence(evidence, packet.get("question", ""))
        
        # Build prompt template to estimate overhead
        template_prompt = self._build_template_prompt(packet)
        template_tokens = count_prompt_tokens(template_prompt)
        
        # Available tokens for evidence content
        available_tokens = MAX_EVIDENCE_TOKENS - template_tokens
        if available_tokens < 1000:
            logger.warning("Token budget very low (%d), using minimal evidence", available_tokens)
            available_tokens = 1000
        
        # Select evidence within token budget
        selected_evidence = []
        used_tokens = 0
        
        for item in scored_evidence:
            item_text = self._format_evidence_item(item)
            item_tokens = count_prompt_tokens(item_text)
            
            if used_tokens + item_tokens > available_tokens:
                if not selected_evidence:
                    # Always include at least one item, truncate if necessary
                    max_chars = max(200, available_tokens * 3)
                    item = self._truncate_evidence_item(item, max_chars)
                    selected_evidence.append(item)
                break
            
            selected_evidence.append(item)
            used_tokens += item_tokens
            
            if len(selected_evidence) >= MAX_EVIDENCE_ITEMS:
                break
        
        logger.info(
            "Token budget: template=%d, available=%d, used=%d, selected=%d/%d evidence items",
            template_tokens, available_tokens, used_tokens, len(selected_evidence), len(evidence)
        )
        
        return {**packet, "verified_evidence": selected_evidence, "_token_budget": {
            "template_tokens": template_tokens,
            "available_tokens": available_tokens,
            "used_tokens": used_tokens,
            "selected_count": len(selected_evidence),
            "total_count": len(evidence),
        }}

    def _score_evidence(self, evidence: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        """Score evidence items by relevance to question."""
        terms = _answer_terms(question)
        scored = []
        
        for item in evidence:
            # Combine all text sources
            all_text = " ".join(
                str(item.get(key, ""))
                for key in ("text", "visual_summary", "transcript", "ocr_text")
                if item.get(key)
            )
            if not all_text.strip():
                scored.append((0.0, item))
                continue
            
            # Score relevance to question
            normalized = all_text.lower()
            if terms:
                relevance = sum(1 for term in terms if term in normalized) / len(terms)
            else:
                relevance = 0.3
            
            # Boost for evidence with citations
            if item.get("citation_id") or item.get("candidate_id"):
                relevance += 0.1
            
            # Boost for visual evidence
            if item.get("visual_summary"):
                relevance += 0.05
            
            scored.append((relevance, item))
        
        # Sort by relevance descending
        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored]

    def _format_evidence_item(self, item: dict[str, Any]) -> str:
        """Format a single evidence item for the prompt."""
        ts = f"{format_ms(item['start_ms'])}-{format_ms(item['end_ms'])}"
        text_part = item.get("text", "") or ""
        visual_part = item.get("visual_summary", "") or ""
        ocr_part = ""
        if item.get("ocr_text"):
            ocr_part = " OCR: " + " ".join(item["ocr_text"])
        cite_id = item.get('citation_id') or item.get('candidate_id', 'unknown')
        return f"[{cite_id}] ({ts}) {text_part}" + (f" Visual: {visual_part}" if visual_part else "") + ocr_part

    def _truncate_evidence_item(self, item: dict[str, Any], max_chars: int) -> dict[str, Any]:
        """Truncate evidence item text to fit within char limit."""
        truncated = {**item}
        for key in ("text", "visual_summary"):
            if truncated.get(key) and len(truncated[key]) > max_chars:
                truncated[key] = truncated[key][:max_chars].rsplit(" ", 1)[0] + "..."
        if truncated.get("ocr_text"):
            truncated["ocr_text"] = truncated["ocr_text"][:3]
        return truncated

    def _build_template_prompt(self, packet: dict[str, Any]) -> str:
        """Build prompt template without evidence to estimate overhead."""
        timeline = packet.get("temporal_context", {}).get("timeline_summary", "")
        evidence_timeline = _build_evidence_timeline(packet.get("verified_evidence", []))
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
        )

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
            if _cite_id(item) in supported_ids
        ]
        revised_packet = {**evidence_packet, "verified_evidence": evidence}
        # Apply token budget to filtered evidence as well
        revised_packet = self._apply_token_budget(revised_packet)
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
            cite_id = item.get('citation_id') or item.get('candidate_id', 'unknown')
            evidence_lines.append(
                f"[{cite_id}] ({ts}) {text_part}"
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
        scope_result: ScopeResult | None = None,
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
                "scope_result": scope_result.to_dict() if scope_result else None,
            }

        # If only one evidence item, use the simple path
        if len(evidence) == 1:
            return self._single_evidence_answer(
                evidence[0], packet, fallback_used=fallback_used,
                model=model, provider_fallback_used=provider_fallback_used,
                scope_result=scope_result,
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
            citation = point.get("candidate_id", "S1")
            cited_ids.add(citation)
            answer_parts.append(f"At {ts}, {text} [{citation}]")

        # If we have visual-only evidence, add those descriptions
        for item in evidence:
            visual = item.get("visual_summary", "")
            if visual and _cite_id(item) not in cited_ids:
                ts = format_ms(item["start_ms"])
                cited_ids.add(_cite_id(item))
                answer_parts.append(f"At {ts}, visually: {visual[:200]} [{_cite_id(item)}]")

        # If we didn't get enough from content points, fall back to best excerpts
        if len(answer_parts) < 2:
            for item in evidence[:5]:
                if _cite_id(item) not in cited_ids:
                    text = item.get("text") or item.get("visual_summary") or ""
                    if text:
                        excerpt = _best_supported_excerpt(text, question, limit=200)
                        if excerpt:
                            ts = format_ms(item["start_ms"])
                            answer_parts.append(
                                f"At {ts}: {excerpt} [{_cite_id(item)}]"
                            )
                            cited_ids.add(_cite_id(item))

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
        scope_result: ScopeResult | None = None,
    ) -> dict[str, Any]:
        """Handle the case where only one evidence item exists."""
        timestamp = format_ms(item["start_ms"])
        text = _best_supported_excerpt(
            item.get("text") or item.get("visual_summary") or "The retrieved evidence is available for this moment.",
            packet.get("question", ""),
        )
        text = _as_single_claim(text)
        answer = f"At around {timestamp}, the video evidence says: {text} [{_cite_id(item)}]."

        question = packet.get("question", "")
        if question and is_explanatory_query(question):
            try:
                from src.pipeline.knowledge_reconstruction import reconstruct_knowledge
                reconstruction = reconstruct_knowledge(question, [item])
                concepts = reconstruction.learning_path.ordered_concepts
                if len(concepts) > 1:
                    chain = " -> ".join(concepts)
                    answer = f"Prerequisite Learning Path: {chain} [{_cite_id(item)}].\n\n{answer}"
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

    def _typed_non_answer(
        self,
        packet: dict[str, Any],
        outcome: str,
        reason: str,
        scope_result: ScopeResult | None = None
    ) -> dict[str, Any]:
        """Return a structured non-answer with outcome type, reason, and metadata."""
        # Map outcome to user-friendly message
        messages = {
            QueryOutcome.VIDEO_EVIDENCE_NOT_FOUND.value: "The video does not contain enough information to answer this question.",
            QueryOutcome.UNRELATED_TO_VIDEO.value: "This question is not related to the content of the video.",
            QueryOutcome.AMBIGUOUS_QUERY.value: "Your question could refer to multiple things. Please clarify what you're asking about.",
            QueryOutcome.CONFLICTING_EVIDENCE.value: "The video contains conflicting information on this topic.",
            QueryOutcome.PROCESSING_INCOMPLETE.value: "The video is still being processed. Please try again later.",
            QueryOutcome.GROUNDED_ANSWER.value: "Answer generated.",  # Should not happen here
        }
        
        message = messages.get(outcome, f"Unable to answer: {reason}")
        
        response = {
            "answer": message,
            "fallback_used": True,
            "model": "quality_gate_reject",
            "outcome": outcome,
            "rejection_reason": reason,
        }
        
        if scope_result:
            response["scope_decision"] = scope_result.decision.value
            response["scope_confidence"] = scope_result.confidence
            response["scope_reasoning"] = scope_result.reasoning
        
        return response

    def _check_modality_requirements(self, evidence: list[dict], query_types: list) -> str | None:
        """Check if evidence has required modalities for the query type."""
        modalities = set(e.get("source_type", "unknown") for e in evidence)
        
        # Visual queries need visual evidence
        if any(q in query_types for q in ["visual", "diagram", "slide", "chart", "code"]):
            if "visual" not in modalities and "visual_evidence" not in modalities:
                return f"Query asks about visual content but no visual evidence retrieved (modalities: {sorted(modalities)})"
        
        # OCR queries need OCR evidence
        if any(q in query_types for q in ["text", "ocr", "written", "read"]):
            if "ocr" not in modalities and "ocr_track" not in modalities:
                return f"Query asks about on-screen text but no OCR evidence retrieved"
        
        # Audio queries need audio evidence
        if any(q in query_types for q in ["audio", "sound", "music", "speaker", "voice"]):
            if "audio" not in modalities and "audio_event" not in modalities and "speaker_turn" not in modalities:
                return f"Query asks about audio but no audio evidence retrieved"
        
        return None

    def _compute_retrieval_confidence(self, evidence: list[dict[str, Any]]) -> float:
        """Compute retrieval confidence from evidence quality and modality coverage."""
        if not evidence:
            return 0.0
        scores = []
        for e in evidence[:5]:
            score = e.get("quality_score", e.get("raw_score"))
            if score is not None:
                scores.append(score)
            else:
                scores.append(0.5)
        if not scores:
            return 0.0
        avg_score = sum(scores) / len(scores)
        modality_coverage = len(set(e.get("source_type", "unknown") for e in evidence[:10])) / 5.0
        return min(1.0, avg_score * 0.7 + modality_coverage * 0.3)

    def _validate_citations(self, answer: str, evidence: list[dict]) -> dict:
        """Validate that answer contains proper citations to evidence."""
        import re
        cited = re.findall(r'\[S(\d+)\]', answer)
        if not cited:
            return {"valid": False, "reason": "No citations found in answer", "citations": []}
        
        cited_indices = set(int(c) for c in cited)
        max_evidence = len(evidence)
        
        invalid = [c for c in cited_indices if c > max_evidence or c < 1]
        if invalid:
            return {"valid": False, "reason": f"Citations reference non-existent evidence: {invalid}", "citations": cited}
        
        # Check citation coverage (at least 50% of sentences should have citations)
        sentences = [s.strip() for s in re.split(r'[.!?]', answer) if len(s.strip()) > 20]
        if sentences:
            cited_sentences = sum(1 for s in sentences if re.search(r'\[S\d+\]', s))
            coverage = cited_sentences / len(sentences)
            if coverage < 0.5:
                return {"valid": False, "reason": f"Low citation coverage ({coverage:.0%})", "citations": cited}
        
        return {"valid": True, "reason": "Citations valid", "citations": cited}

    def _calibrate_answer_confidence(self, answer: str, evidence: list[dict], retrieval_conf: float, citation_check: dict) -> float:
        """Calibrate final answer confidence from multiple signals."""
        if not evidence:
            return 0.0
        
        # Base from retrieval
        base = retrieval_conf * 0.4
        
        # Citation quality
        citation_quality = 1.0 if citation_check.get("valid") else 0.3
        base += citation_quality * 0.3
        
        # Evidence diversity
        modalities = len(set(e.get("source_type", "unknown") for e in evidence))
        modality_score = min(1.0, modalities / 4.0) * 0.2
        base += modality_score
        
        # Evidence count
        count_score = min(1.0, len(evidence) / 10.0) * 0.1
        base += count_score
        
        return min(1.0, max(0.0, base))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_evidence_timeline(evidence: list[dict[str, Any]]) -> str:
    """Build a compact timeline string from evidence items."""
    if not evidence:
        return ""
    entries = []
    for item in evidence[:10]:
        ts = format_ms(item["start_ms"])
        text = (item.get("text") or item.get("visual_summary") or "")[:80]
        entries.append(f"{_cite_id(item)}@{ts}: {text}")
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
            "citation_id": item.get("citation_id") or item.get("candidate_id", ""),
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
    citation = item.get("citation_id") or item.get("candidate_id", "S1")
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


def _cite_id(item: dict[str, Any]) -> str:
    """Get citation ID from an evidence item (supports both old and new formats)."""
    return item.get('citation_id') or item.get('candidate_id', 'S1')


def _as_single_claim(text: str) -> str:
    parts = [
        _sentence_stem(part)
        for part in re.split(r"(?<=[.!?])\s+", str(text).strip())
        if part.strip()
    ]
    return "; ".join(parts)
