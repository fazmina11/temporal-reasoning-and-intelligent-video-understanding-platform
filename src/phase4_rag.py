"""
src/phase4_rag.py — Phase 4: NLP-Powered RAG Answer Engine
===========================================================

Pipeline overview
-----------------
Step A │ NLP Query Understanding  — before retrieval, the raw user question is
       │                            analysed by an LLM to produce:
       │                              • intent classification (CONCEPT / TIMESTAMP /
       │                                COMPARE / SUMMARISE / FOLLOWUP / UNKNOWN)
       │                              • semantic rewrite (denoised, expanded query)
       │                              • extracted entities (topics, named items)
       │                              • temporal hint extraction (e.g. "around 2 mins")
Step B │ Adaptive Retrieval       — intent drives the retrieval strategy:
       │                              CONCEPT    → hybrid dense+sparse RRF
       │                              TIMESTAMP  → temporal window lookup
       │                              COMPARE    → two parallel sub-queries merged
       │                              SUMMARISE  → broad top-K sweep
       │                              FOLLOWUP   → re-uses last context + narrow query
Step C │ Grounded Answer Gen      — retrieved scenes are packed into a structured
       │                            prompt; Gemini generates an answer with mandatory
       │                            inline citations ([Scene @ HH:MM:SS])
Step D │ Multi-turn Conversation  — a ConversationMemory object stores the last
       │                            N turns; each new question receives prior context
       │                            so follow-up questions resolve correctly
Step E │ Answer Validation        — the generated answer is checked for hallucination
       │                            signals (claims not grounded in retrieved context)
       │                            and a confidence score is produced

Advanced techniques
--------------------
• NLP Intent Classification   — LLM-based query router avoids wasted retrieval
• Query Rewriting             — semantic expansion improves recall on vague questions
• Entity Extraction           — named entities from query guide filter application
• Multi-turn Memory           — sliding-window conversation buffer (configurable depth)
• Structured Citation Engine  — every factual claim pinned to a timestamp
• Hallucination Guard         — post-generation grounding check flags unsupported claims
• Confidence Scoring          — composite score from retrieval distance + grounding ratio
• Streaming Support           — optional token-by-token streaming for interactive UIs
• REPL Mode                   — interactive terminal loop with conversation history
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError as exc:
    raise ImportError(
        "google-genai is required. Install dependencies with: pip install -r requirement.txt"
    ) from exc
from dotenv import load_dotenv

load_dotenv()

# ── Local utilities & Phase 3 retriever ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import log

# Import Phase 3 retriever (lazy — allows phase4 to run standalone if needed)
try:
    from phase3_indexing import VideoRetriever, DEFAULT_TOP_K
    _RETRIEVER_AVAILABLE = True
except ImportError:
    _RETRIEVER_AVAILABLE = False
    DEFAULT_TOP_K = 5
    log.warning("phase3_indexing not found — retriever unavailable until indexed")

# ── Configuration ──────────────────────────────────────────────────────────────

GEMINI_MODEL          = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_TEMPERATURE    = 0.7      # valid range: 0.0 - 2.0
GEMINI_MAX_TOKENS     = 1024

# Multi-turn memory depth (number of past Q&A pairs kept in context)
MEMORY_DEPTH          = 6

# Retrieval
TOP_K_DEFAULT         = 5
TOP_K_SUMMARISE       = 10      # broader sweep for summarisation queries
CONFIDENCE_THRESHOLD  = 0.45    # below this → answer flagged as low-confidence

# Hallucination guard
GROUNDING_CHECK       = True    # set False to skip post-generation validation


# ── Gemini client ──────────────────────────────────────────────────────────────

class GeminiClient:
    """Small adapter around the supported google-genai SDK."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.config = genai_types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_TOKENS,
        )

    def generate_content(self, contents: Any, stream: bool = False):
        if stream:
            return self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=self.config,
            )
        return self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=self.config,
        )


def _get_gemini() -> GeminiClient:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        log.info("Using Gemini model via google-genai: %s", GEMINI_MODEL)
        return GeminiClient(api_key=api_key, model_name=GEMINI_MODEL)
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY not set — add it to .env or export it."
        )
    genai.configure(api_key=api_key)
    
    # Try different model names for 2026 compatibility
    model_names = ["gemini-3-flash-preview", "gemini-3-flash", "gemini-pro", "gemini-1.5-flash"]
    
    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            log.info("🤖  Using Gemini model: %s", model_name)
            return model
        except Exception as e:
            log.warning("Failed to load model %s: %s", model_name, e)
            continue
    
    raise RuntimeError(f"Failed to initialize any Gemini model from: {model_names}")


def _call_gemini(model: GeminiClient, prompt: str, stream: bool = False):
    """Unified Gemini call with optional streaming."""
    if stream:
        return model.generate_content(prompt, stream=True)
    response = model.generate_content(prompt)
    return response.text.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Step A: NLP Query Understanding
# ──────────────────────────────────────────────────────────────────────────────

class QueryIntent(str, Enum):
    CONCEPT    = "CONCEPT"      # "What is attention mechanism?"
    TIMESTAMP  = "TIMESTAMP"    # "What happens at 2 minutes?"
    COMPARE    = "COMPARE"      # "Compare RNN vs Transformer"
    SUMMARISE  = "SUMMARISE"    # "Summarise the entire video"
    FOLLOWUP   = "FOLLOWUP"     # "Can you explain that further?"
    UNKNOWN    = "UNKNOWN"


@dataclass
class ParsedQuery:
    """Structured output of the NLP query understanding step."""
    original:       str
    rewritten:      str                  # denoised, expanded query for retrieval
    intent:         QueryIntent
    entities:       list[str]            # key topics, named items
    temporal_hint:  float | None         # extracted timestamp in seconds, if any
    diagram_filter: str | None           # e.g. "slide", "code" — for metadata filter
    sub_queries:    list[str]            # for COMPARE intent — two parallel queries
    confidence:     float = 1.0


_QUERY_PARSE_PROMPT = """
You are an NLP preprocessing engine for a video search RAG system.

Analyse the user query and return ONLY a valid JSON object (no markdown, no preamble):

{{
  "intent":         "<CONCEPT | TIMESTAMP | COMPARE | SUMMARISE | FOLLOWUP | UNKNOWN>",
  "rewritten":      "<clean, expanded version of the query for semantic search>",
  "entities":       ["<key topic or named item>", ...],
  "temporal_hint":  <seconds as float, or null — extract from phrases like '2 minutes', 'around 1:30', 'near the end'>,
  "diagram_filter": "<slide | code | diagram | chart | whiteboard | null — only set if query explicitly targets a visual type>",
  "sub_queries":    ["<first comparison term>", "<second comparison term>"] // only for COMPARE intent, else []
}}

Intent definitions:
  CONCEPT    — user wants to understand a topic or concept from the video
  TIMESTAMP  — user asks about a specific time window ("what happened at X")
  COMPARE    — user explicitly asks to compare or contrast two things
  SUMMARISE  — user wants an overview of all or a large portion of the video
  FOLLOWUP   — query references the previous answer ("that", "it", "this approach", "explain further")
  UNKNOWN    — cannot determine intent

Conversation history (last {history_len} turns):
{history}

Current query: "{query}"

Return ONLY the JSON object.
""".strip()


def parse_query(
    raw_query: str,
    model: GeminiClient,
    history: list[dict] | None = None,
) -> ParsedQuery:
    """
    Step A — NLP Query Understanding.

    Sends the raw user query + conversation history to Gemini for:
      • Intent classification
      • Semantic rewriting (expands vague terms, fixes typos)
      • Entity extraction
      • Temporal hint parsing
      • Diagram type filter detection

    Falls back gracefully to a default ParsedQuery on parse errors.
    """
    history = history or []
    history_str = "\n".join(
        f"Q: {t['question']}\nA: {t['answer'][:200]}…" for t in history[-4:]
    ) or "(none)"

    prompt = _QUERY_PARSE_PROMPT.format(
        history_len=len(history),
        history=history_str,
        query=raw_query,
    )

    try:
        raw = _call_gemini(model, prompt)

        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)

        intent = QueryIntent(data.get("intent", "UNKNOWN"))
        return ParsedQuery(
            original       = raw_query,
            rewritten      = data.get("rewritten", raw_query),
            intent         = intent,
            entities       = data.get("entities", []),
            temporal_hint  = data.get("temporal_hint"),
            diagram_filter = data.get("diagram_filter"),
            sub_queries    = data.get("sub_queries", []),
        )

    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Query parse failed (%s) — using raw query as fallback", exc)
        return ParsedQuery(
            original      = raw_query,
            rewritten     = raw_query,
            intent        = QueryIntent.UNKNOWN,
            entities      = [],
            temporal_hint = None,
            diagram_filter= None,
            sub_queries   = [],
            confidence    = 0.5,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Step B: Adaptive Retrieval
# ──────────────────────────────────────────────────────────────────────────────

def retrieve(
    parsed: ParsedQuery,
    retriever: "VideoRetriever",
    last_context: list[dict] | None = None,
) -> list[dict]:
    """
    Step B — Intent-driven adaptive retrieval.

    Routing table:
      CONCEPT    → hybrid RRF query on rewritten text + entity injection
      TIMESTAMP  → temporal window lookup ± 45 s around extracted hint
      COMPARE    → two parallel sub-queries, merged and deduplicated
      SUMMARISE  → broad top-K sweep (TOP_K_SUMMARISE)
      FOLLOWUP   → narrow RRF query on rewritten text, seeded at last result ts
      UNKNOWN    → fallback to standard hybrid query
    """
    intent  = parsed.intent
    query   = parsed.rewritten

    # Enrich query with extracted entities for better recall
    if parsed.entities:
        entity_str = " ".join(parsed.entities)
        query = f"{query} {entity_str}".strip()

    # ── TIMESTAMP intent ──────────────────────────────────────────────────
    if intent == QueryIntent.TIMESTAMP and parsed.temporal_hint is not None:
        log.info("🕐  TIMESTAMP intent — window lookup at %.1fs", parsed.temporal_hint)
        results = retriever.query_by_timestamp(
            seconds=parsed.temporal_hint,
            radius=45.0,
        )
        # Supplement with a semantic query in case window is sparse
        if len(results) < 2:
            results += retriever.query(query, top_k=TOP_K_DEFAULT)
        return _deduplicate(results)[:TOP_K_DEFAULT]

    # ── COMPARE intent ────────────────────────────────────────────────────
    if intent == QueryIntent.COMPARE and len(parsed.sub_queries) >= 2:
        log.info("⚖️  COMPARE intent — dual sub-query: %s", parsed.sub_queries)
        results_a = retriever.query(parsed.sub_queries[0], top_k=3)
        results_b = retriever.query(parsed.sub_queries[1], top_k=3)
        merged = _interleave(results_a, results_b)
        return _deduplicate(merged)[:TOP_K_DEFAULT]

    # ── SUMMARISE intent ──────────────────────────────────────────────────
    if intent == QueryIntent.SUMMARISE:
        log.info("📋  SUMMARISE intent — broad sweep top-%d", TOP_K_SUMMARISE)
        return retriever.query(query, top_k=TOP_K_SUMMARISE)

    # ── FOLLOWUP intent ───────────────────────────────────────────────────
    if intent == QueryIntent.FOLLOWUP and last_context:
        seed_ts = float(last_context[0].get("start_seconds", 0))
        log.info("🔁  FOLLOWUP intent — seeded at %.1fs", seed_ts)
        return retriever.query(
            query,
            top_k=TOP_K_DEFAULT,
            seed_timestamp=seed_ts,
        )

    # ── CONCEPT / UNKNOWN — standard hybrid RRF ───────────────────────────
    log.info("🔍  %s intent — hybrid RRF query", intent.value)
    return retriever.query(
        query,
        top_k=TOP_K_DEFAULT,
        seed_timestamp=parsed.temporal_hint,
        diagram_type_filter=parsed.diagram_filter,
    )


def _deduplicate(results: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in results:
        key = r.get("doc_id", r.get("frame_id", ""))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _interleave(a: list[dict], b: list[dict]) -> list[dict]:
    """Alternate items from two ranked lists."""
    out: list[dict] = []
    for x, y in zip(a, b):
        out.extend([x, y])
    out.extend(a[len(b):])
    out.extend(b[len(a):])
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Step C: Grounded Answer Generation
# ──────────────────────────────────────────────────────────────────────────────

def _build_context_block(scenes: list[dict]) -> str:
    """
    Format retrieved scenes into a numbered context block.

    Each scene gets a reference tag [S1], [S2], … that the LLM
    is instructed to use as inline citations in its answer.
    """
    lines: list[str] = []
    for i, scene in enumerate(scenes, start=1):
        ts      = scene.get("timestamp", "?")
        start_s = scene.get("start_seconds", "?")
        end_s   = scene.get("end_seconds",   "?")
        v_sum   = scene.get("visual_summary",   "")
        ocr     = scene.get("on_screen_text",   "")
        audio   = scene.get("scene_transcript", "")
        d_type  = scene.get("diagram_type",     "")
        concepts= scene.get("key_concepts",     "")

        lines.append(f"[S{i}] Timestamp: {ts}  ({start_s}s → {end_s}s)  | type: {d_type}")
        if v_sum:
            lines.append(f"     Visual  : {v_sum}")
        if ocr:
            lines.append(f"     On-screen text: {ocr[:300]}")
        if audio:
            lines.append(f"     Audio   : {audio[:300]}")
        if concepts:
            lines.append(f"     Concepts: {concepts}")
        lines.append("")

    return "\n".join(lines)


_ANSWER_PROMPT = """
You are an expert video research assistant with deep comprehension ability.

Your job is to answer the user's question using ONLY the retrieved scene context below.
Never invent information not present in the context.

RULES:
1. Every factual claim MUST be followed by an inline citation: [S1], [S2], etc.
2. If the user asks "when", "at what time", or "where in the video", you MUST identify the specific scene(s) and include the timestamp in your explanation.
3. If the context doesn't contain enough information, say: "The video doesn't cover this clearly in the retrieved segments."
4. For COMPARE queries — structure your answer with clear sections for each side.
5. For SUMMARISE queries — write a structured narrative paragraph, not a list.
6. Always mention the timestamp when citing a specific scene.
7. Respond in the same language as the user's question.
8. Be concise but complete — target 150-300 words unless summarising.

────────────────────────────────────────────────
CONVERSATION HISTORY:
{history}
────────────────────────────────────────────────
RETRIEVED SCENE CONTEXT:
{context}
────────────────────────────────────────────────
DETECTED INTENT: {intent}
USER QUESTION: {question}
────────────────────────────────────────────────
ANSWER (with citations and timestamps):
""".strip()


def generate_answer(
    question:    str,
    parsed:      ParsedQuery,
    scenes:      list[dict],
    model:       GeminiClient,
    history:     list[dict] | None = None,
    stream:      bool = False,
) -> str | Iterator:
    """
    Step C — Grounded answer generation with mandatory citations.

    Parameters
    ----------
    question : Original user question.
    parsed   : ParsedQuery from Step A.
    scenes   : Retrieved scenes from Step B.
    model    : Gemini GenerativeModel.
    history  : Conversation history (list of {question, answer} dicts).
    stream   : If True, returns a streaming iterator instead of a string.

    Returns
    -------
    Answer string (or streaming iterator if stream=True).
    """
    history = history or []
    history_str = "\n".join(
        f"Q: {t['question']}\nA: {t['answer']}" for t in history[-(MEMORY_DEPTH // 2):]
    ) or "(no prior conversation)"

    context_block = _build_context_block(scenes)

    prompt = _ANSWER_PROMPT.format(
        history  = history_str,
        context  = context_block,
        intent   = parsed.intent.value,
        question = question,
    )

    if stream:
        return model.generate_content(prompt, stream=True)

    return _call_gemini(model, prompt)


# ──────────────────────────────────────────────────────────────────────────────
# Step D: Multi-turn Conversation Memory
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ConversationMemory:
    """
    Sliding-window conversation buffer.

    Stores the last `depth` Q&A turns. Each turn also records the retrieved
    scenes so FOLLOWUP queries can re-use the previous retrieval context.
    """
    depth:   int = MEMORY_DEPTH
    turns:   list[dict] = field(default_factory=list)

    def add(self, question: str, answer: str, scenes: list[dict]) -> None:
        self.turns.append({
            "question": question,
            "answer":   answer,
            "scenes":   scenes,
            "ts":       time.time(),
        })
        # Trim to window
        if len(self.turns) > self.depth:
            self.turns = self.turns[-self.depth:]

    def last_scenes(self) -> list[dict]:
        """Return the scene context from the most recent turn."""
        return self.turns[-1]["scenes"] if self.turns else []

    def as_history(self) -> list[dict]:
        """Return turns formatted for prompt injection."""
        return [{"question": t["question"], "answer": t["answer"]} for t in self.turns]

    def clear(self) -> None:
        self.turns.clear()
        log.info("🧹  Conversation memory cleared")


# ──────────────────────────────────────────────────────────────────────────────
# Step E: Answer Validation (Hallucination Guard)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_confidence(scenes: list[dict], answer: str) -> float:
    """
    Composite confidence score:
      • Retrieval signal : mean (1 - distance) across retrieved scenes
      • Grounding ratio  : fraction of answer sentences that contain a [Sn] citation
      • Blend            : 60% retrieval + 40% grounding

    Returns float in [0, 1].
    """
    # Retrieval signal
    distances = [float(s.get("distance", 1.0)) for s in scenes if "distance" in s]
    retrieval_score = float(sum(1 - d for d in distances) / len(distances)) if distances else 0.5

    # Grounding ratio
    sentences  = [s.strip() for s in re.split(r"[.!?]", answer) if len(s.strip()) > 20]
    cited      = sum(1 for s in sentences if re.search(r"\[S\d+\]", s))
    grounding  = cited / len(sentences) if sentences else 0.0

    return round(0.6 * retrieval_score + 0.4 * grounding, 3)


def validate_answer(answer: str, scenes: list[dict]) -> dict:
    """
    Step E — Post-generation hallucination guard.

    Checks:
      1. Does the answer cite at least one [Sn] reference?
      2. Are all cited [Sn] indices within the range of retrieved scenes?
      3. Composite confidence score.

    Returns
    -------
    Dict with keys: confidence, has_citations, invalid_refs, warning
    """
    cited_indices = [int(m) for m in re.findall(r"\[S(\d+)\]", answer)]
    valid_range   = set(range(1, len(scenes) + 1))
    invalid_refs  = [i for i in cited_indices if i not in valid_range]

    has_citations = len(cited_indices) > 0
    confidence    = _compute_confidence(scenes, answer)

    warning: str | None = None
    if not has_citations:
        warning = "⚠️  Answer contains no scene citations — may be unsupported."
    elif invalid_refs:
        warning = f"⚠️  Answer references non-existent scenes: {invalid_refs}"
    elif confidence < CONFIDENCE_THRESHOLD:
        warning = f"⚠️  Low confidence ({confidence:.2f}) — retrieved context may be insufficient."

    return {
        "confidence":    confidence,
        "has_citations": has_citations,
        "invalid_refs":  invalid_refs,
        "warning":       warning,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public API: VideoRAG
# ──────────────────────────────────────────────────────────────────────────────

class VideoRAG:
    """
    End-to-end Video RAG engine.

    Orchestrates Steps A → E for each user query.

    Usage
    -----
    rag = VideoRAG()
    result = rag.ask("What is the difference between LSTM and Transformer?")
    print(result["answer"])
    print(result["citations"])
    """

    def __init__(self) -> None:
        self._model     = _get_gemini()
        self._retriever = VideoRetriever() if _RETRIEVER_AVAILABLE else None
        self._memory    = ConversationMemory(depth=MEMORY_DEPTH)
        log.info("🚀  VideoRAG engine initialised (model=%s, memory_depth=%d)",
                 GEMINI_MODEL, MEMORY_DEPTH)

    def ask(
        self,
        question:     str,
        top_k:        int  = TOP_K_DEFAULT,
        stream:       bool = False,
    ) -> dict:
        """
        Full RAG pipeline for a single question.

        Parameters
        ----------
        question : User's natural language question.
        top_k    : Max scenes to retrieve.
        stream   : If True, the 'answer' field is a streaming iterator.

        Returns
        -------
        Dict with keys:
          question    : original question
          intent      : detected QueryIntent
          rewritten   : NLP-rewritten query used for retrieval
          entities    : extracted entities
          scenes      : list of retrieved scene metadata dicts
          answer      : generated answer string (or stream iterator)
          citations   : list of {ref, timestamp, visual_summary} dicts
          confidence  : float confidence score
          warning     : str or None
        """
        if not self._retriever:
            return {
                "question": question,
                "answer":   "❌  Retriever unavailable — run phase3_indexing.py index first.",
                "warning":  "no_index",
            }

        start_time = time.time()

        # ── Step A: Query Understanding ──────────────────────────────────
        log.info("📝  Parsing query: %r", question)
        parsed = parse_query(question, self._model, history=self._memory.as_history())
        log.info("   intent=%s | rewritten=%r | entities=%s | ts_hint=%s",
                 parsed.intent, parsed.rewritten, parsed.entities, parsed.temporal_hint)

        # ── Step B: Adaptive Retrieval ───────────────────────────────────
        scenes = retrieve(parsed, self._retriever, last_context=self._memory.last_scenes())
        log.info("   Retrieved %d scenes", len(scenes))

        if not scenes:
            answer = "I couldn't find any relevant moments in the video for that question."
            self._memory.add(question, answer, [])
            return {"question": question, "intent": parsed.intent, "answer": answer,
                    "scenes": [], "citations": [], "confidence": 0.0, "warning": "no_results"}

        # ── Step C: Answer Generation ────────────────────────────────────
        answer = generate_answer(
            question = question,
            parsed   = parsed,
            scenes   = scenes,
            model    = self._model,
            history  = self._memory.as_history(),
            stream   = stream,
        )

        if stream:
            # Caller is responsible for consuming the iterator
            return {
                "question": question, "intent": parsed.intent,
                "rewritten": parsed.rewritten, "entities": parsed.entities,
                "scenes": scenes, "answer": answer,
                "citations": [], "confidence": None, "warning": None,
            }

        # ── Step D: Memory update ────────────────────────────────────────
        self._memory.add(question, answer, scenes)

        # ── Step E: Validation ───────────────────────────────────────────
        validation = validate_answer(answer, scenes) if GROUNDING_CHECK else {}
        confidence = validation.get("confidence", 1.0)
        warning    = validation.get("warning")

        # Build citation list
        citations = _extract_citations(answer, scenes)

        elapsed = round(time.time() - start_time, 2)
        log.info("✅  Answer generated in %.2fs | confidence=%.2f", elapsed, confidence)
        if warning:
            log.warning(warning)

        return {
            "question":   question,
            "intent":     parsed.intent.value,
            "rewritten":  parsed.rewritten,
            "entities":   parsed.entities,
            "scenes":     scenes,
            "answer":     answer,
            "citations":  citations,
            "confidence": confidence,
            "warning":    warning,
            "elapsed_s":  elapsed,
        }

    def summarise_video(self) -> dict:
        """Generate a full structured summary of the indexed video."""
        return self.ask("Provide a comprehensive summary of the entire video, covering all major topics and transitions.")

    def clear_memory(self) -> None:
        self._memory.clear()


def _extract_citations(answer: str, scenes: list[dict]) -> list[dict]:
    """
    Build a structured citation list from [Sn] references in the answer.

    Returns list of {ref, timestamp, visual_summary, frame_id} dicts.
    """
    cited_indices = sorted(set(int(m) for m in re.findall(r"\[S(\d+)\]", answer)))
    citations = []
    for idx in cited_indices:
        scene_idx = idx - 1
        if 0 <= scene_idx < len(scenes):
            s = scenes[scene_idx]
            citations.append({
                "ref":           f"[S{idx}]",
                "timestamp":     s.get("timestamp", "?"),
                "start_seconds": s.get("start_seconds"),
                "frame_id":      s.get("frame_id", ""),
                "visual_summary": s.get("visual_summary", "")[:120],
                "diagram_type":  s.get("diagram_type", ""),
            })
    return citations


# ──────────────────────────────────────────────────────────────────────────────
# REPL — Interactive terminal loop
# ──────────────────────────────────────────────────────────────────────────────

_HELP_TEXT = """
Commands:
  /clear       — clear conversation memory
  /summary     — summarise the entire video
  /history     — show conversation history
  /citations   — show citations from last answer
  /quit        — exit
  /help        — show this message
""".strip()


def _print_answer(result: dict) -> None:
    """Pretty-print a RAG result to the terminal."""
    width = 70
    print(f"\n{'─' * width}")
    print(f"  🎯 Intent    : {result.get('intent', '?')}")
    if result.get("rewritten") != result.get("question"):
        print(f"  🔄 Rewritten : {result.get('rewritten', '')}")
    if result.get("entities"):
        print(f"  🏷️  Entities  : {', '.join(result['entities'])}")
    print(f"{'─' * width}")
    print()

    answer = result.get("answer", "")
    for line in textwrap.wrap(answer, width=width):
        print(f"  {line}")

    print()
    if result.get("citations"):
        print(f"  📌 Citations:")
        for c in result["citations"]:
            print(f"     {c['ref']}  {c['timestamp']}  — {c.get('diagram_type', '')}  {c['visual_summary'][:80]}")

    conf = result.get("confidence")
    if conf is not None:
        bar_len = int(conf * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"\n  Confidence : [{bar}] {conf:.0%}")

    if result.get("warning"):
        print(f"\n  {result['warning']}")

    elapsed = result.get("elapsed_s")
    if elapsed:
        print(f"  ⏱  {elapsed}s")
    print(f"{'─' * width}\n")


def run_repl() -> None:
    """Interactive REPL for multi-turn video Q&A."""
    rag = VideoRAG()
    last_result: dict | None = None

    print("\n╔══════════════════════════════════════════════╗")
    print("║     📽️  Video RAG — Interactive Assistant      ║")
    print("╚══════════════════════════════════════════════╝")
    print("  Type your question or /help for commands.\n")

    while True:
        try:
            raw = input("You › ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not raw:
            continue

        # ── Commands ──────────────────────────────────────────────────────
        if raw.lower() in ("/quit", "/exit", "/q"):
            print("Goodbye!")
            break

        if raw.lower() == "/help":
            print(_HELP_TEXT)
            continue

        if raw.lower() == "/clear":
            rag.clear_memory()
            last_result = None
            print("  ✅ Memory cleared.\n")
            continue

        if raw.lower() == "/summary":
            print("  Generating summary…")
            last_result = rag.summarise_video()
            _print_answer(last_result)
            continue

        if raw.lower() == "/history":
            hist = rag._memory.as_history()
            if not hist:
                print("  (no history)\n")
            else:
                for i, t in enumerate(hist, 1):
                    print(f"  [{i}] Q: {t['question']}")
                    print(f"       A: {t['answer'][:120]}…\n")
            continue

        if raw.lower() == "/citations":
            if last_result and last_result.get("citations"):
                for c in last_result["citations"]:
                    print(f"  {c['ref']}  {c['timestamp']}  {c['visual_summary'][:100]}")
            else:
                print("  (no citations from last answer)\n")
            continue

        # ── Regular question ──────────────────────────────────────────────
        print("  🤔 Thinking…")
        last_result = rag.ask(raw)
        _print_answer(last_result)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 4: NLP-Powered RAG Answer Engine"
    )
    subparsers = parser.add_subparsers(dest='command', required=False, metavar='COMMAND')
    
    subparsers.add_parser("repl", help="Interactive multi-turn Q&A (default)")
    subparsers.add_parser("summary", help="Print a full video summary and exit")
    p_ask = subparsers.add_parser("ask", help="Single question, print result, exit")
    p_ask.add_argument("question", type=str)
    p_ask.add_argument("--top-k", type=int, default=TOP_K_DEFAULT)
    
    args = parser.parse_args()
    
    # Default to repl if no command specified
    command = getattr(args, 'command', 'repl')
    
    if command == "ask":
        rag = VideoRAG()
        result = rag.ask(args.question, top_k=args.top_k)
        _print_answer(result)
    elif command == "summary":
        rag = VideoRAG()
        result = rag.summarise_video()
        _print_answer(result)
    else:
        run_repl()
