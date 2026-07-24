from __future__ import annotations
import os

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HIERARCHY_EMBED_MODEL", "BAAI/bge-base-en-v1.5")

import uuid
import shutil
import asyncio
import logging
import re
from functools import partial
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

# Import existing pipeline phases
from src.phase1_sampling import process_video as phase1_process
from src.phase2_audio import transcribe_video
from src.phase2_visual import run_phase2_visual as phase2_enrich
from src.phase3_indexing import create_index as phase3_index
from src.phase4_rag import VideoRAG
from src.pipeline.media_manifest import (
    ManifestError,
    create_media_manifest,
    load_manifest,
    update_manifest_status,
)
from src.pipeline.chunking_foundation import run_chunking_foundation
from src.pipeline.frame_extraction import (
    FrameExtractionConfig,
    run_frame_extraction,
)
from src.pipeline.evidence_foundation import run_evidence_foundation
from src.pipeline.hierarchy_indexing import index_hierarchy
from src.pipeline.hierarchy_rag import HierarchyVideoRAG
from src.pipeline.json_artifacts import read_json
from src.pipeline.media_assets import extract_normalized_audio
from src.pipeline.modality_foundation import run_modality_foundation
from src.pipeline.agentic.contracts import (
    AnswerQuality,
    AskRequest,
    AskResponse,
    Citation,
    Outcome,
    RetrievalTrace,
    SourceType,
    model_to_dict,
)
from src.pipeline.agentic.conversation_resolver import resolve_conversation_references
from src.pipeline.agentic.query_understanding import understand_query
from src.pipeline.agentic.scope_router import ScopeAction, route_scope
from src.pipeline.agentic.scope_profile import build_video_scope_profile
from src.pipeline.agentic.citation_registry import build_evidence_registry
from src.pipeline.agentic.trace_repository import TraceRepository
from src.pipeline.agentic.retrieval_planner import create_retrieval_plan
from src.pipeline.agentic.retrieval_orchestrator import RetrievalOrchestrator
from src.pipeline.agentic.candidate_fusion import fuse_candidates
from src.pipeline.agentic.reranker import rerank_candidates
from src.pipeline.agentic.temporal_deduplicator import deduplicate_temporal_candidates
from src.pipeline.agentic.evidence_verifier import verify_evidence
from src.pipeline.agentic.answerability_gate import evaluate_answerability
from src.pipeline.agentic.corrective_retrieval import create_corrective_plan, should_retry
from src.pipeline.agentic.temporal_reasoner import build_temporal_context
from src.pipeline.agentic.evidence_packet import build_evidence_packet
from src.pipeline.agentic.answer_generator import GroundedAnswerGenerator
from src.pipeline.agentic.claim_verifier import remove_unsupported_claims, verify_claims
from src.pipeline.agentic.confidence_calibrator import calibrate_confidence

app = FastAPI(title="VideoSceneRAG API")

# Enable CORS for all origins with credentials support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage configuration
UPLOAD_DIR = REPO_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Mount data directory for serving processed frames/metadata if needed
app.mount("/data", StaticFiles(directory="data"), name="data")

# Global state to track processing status
processing_status: Dict[str, Dict[str, Any]] = {}

class QueryRequest(AskRequest):
    pass


class QueryResponse(AskResponse):
    pass

@app.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    video_id = str(uuid.uuid4())
    # Keep the original extension
    orig_ext = Path(file.filename).suffix
    video_filename = f"{video_id}{orig_ext}"
    file_path = UPLOAD_DIR / video_filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        manifest = create_media_manifest(
            repo_root=REPO_ROOT,
            video_id=video_id,
            original_filename=file.filename or video_filename,
            video_path=file_path,
            upload_extension=orig_ext.replace(".", ""),
        )
    except ManifestError as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    
    processing_status[video_id] = {
        "status": manifest["processing"]["status"],
        "progress": manifest["processing"]["progress"],
        "phase": manifest["processing"]["current_phase"],
        "filename": manifest["original_filename"],
        "extension": orig_ext.replace(".", ""),
        "path": manifest["video_path"],
        "manifest_path": manifest["artifacts"]["manifest_path"],
        "source_sha256": manifest["source_sha256"],
        "duration_ms": manifest["duration_ms"],
        "duration_seconds": manifest["duration_seconds"],
        "fps": manifest["fps"],
        "frame_count": manifest["frame_count"],
        "resolution": manifest["resolution"],
        "video_codec": manifest["video_codec"],
        "audio_codec": manifest["audio_codec"],
        "audio_sample_rate": manifest["audio_sample_rate"],
        "has_audio": manifest["has_audio"],
        "timeline": manifest["timeline"],
        "audio_path": manifest["audio_path"],
        "pipeline_version": manifest["pipeline_version"],
    }
    
    # Start background processing
    background_tasks.add_task(process_pipeline, video_id, str(file_path))
    
    return {
        "video_id": video_id,
        "filename": file.filename,
        "extension": orig_ext.replace(".", ""),
        "manifest": manifest,
    }

@app.get("/status/{video_id}")
async def get_status(video_id: str):
    if video_id not in processing_status:
        try:
            manifest = load_manifest(repo_root=REPO_ROOT, video_id=video_id)
            return {
                "status": manifest["processing"]["status"],
                "progress": manifest["processing"]["progress"],
                "phase": manifest["processing"]["current_phase"],
                "filename": manifest["original_filename"],
                "manifest_path": manifest["artifacts"]["manifest_path"],
                "source_sha256": manifest["source_sha256"],
                "duration_ms": manifest["duration_ms"],
                "duration_seconds": manifest["duration_seconds"],
                "fps": manifest["fps"],
                "frame_count": manifest["frame_count"],
                "resolution": manifest["resolution"],
                "video_codec": manifest["video_codec"],
                "audio_codec": manifest["audio_codec"],
                "audio_sample_rate": manifest["audio_sample_rate"],
                "has_audio": manifest["has_audio"],
                "timeline": manifest["timeline"],
                "audio_path": manifest["audio_path"],
                "pipeline_version": manifest["pipeline_version"],
                "error": manifest["processing"].get("error"),
            }
        except ManifestError:
            pass
        raise HTTPException(status_code=404, detail="Video not found")
    return processing_status[video_id]

@app.get("/manifest/{video_id}")
async def get_manifest(video_id: str):
    try:
        return load_manifest(repo_root=REPO_ROOT, video_id=video_id)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

def _get_manifest_artifact(video_id: str, artifact_key: str):
    try:
        manifest = load_manifest(repo_root=REPO_ROOT, video_id=video_id)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    artifact_path = Path(manifest["artifacts"][artifact_key])
    if not artifact_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact is not available yet: {artifact_key}",
        )
    return read_json(artifact_path)

@app.get("/boundaries/{video_id}")
async def get_boundaries(video_id: str):
    return _get_manifest_artifact(video_id, "boundaries_path")

@app.get("/atoms/{video_id}")
async def get_atoms(video_id: str):
    return _get_manifest_artifact(video_id, "atoms_path")

@app.get("/atom-validation/{video_id}")
async def get_atom_validation(video_id: str):
    return _get_manifest_artifact(video_id, "atom_validation_path")

@app.get("/frames/{video_id}")
async def get_frames(video_id: str):
    return _get_manifest_artifact(video_id, "frame_index_path")

@app.get("/frame-validation/{video_id}")
async def get_frame_validation(video_id: str):
    return _get_manifest_artifact(video_id, "frame_validation_path")

@app.get("/visual-artifacts/{video_id}")
async def get_visual_artifacts(video_id: str):
    return _get_manifest_artifact(video_id, "visual_artifacts_path")

@app.get("/semantic-chunks/{video_id}")
async def get_semantic_chunks(video_id: str):
    return _get_manifest_artifact(video_id, "semantic_chunks_path")

@app.get("/chunk-validation/{video_id}")
async def get_chunk_validation(video_id: str):
    return _get_manifest_artifact(video_id, "chunk_validation_path")

@app.get("/events/{video_id}")
async def get_events(video_id: str):
    return _get_manifest_artifact(video_id, "events_path")

async def process_pipeline(video_id: str, video_path: str):
    try:
        # Phase 1: Sampling & Scene Detection
        processing_status[video_id]["status"] = "Phase 1: Scene Detection"
        processing_status[video_id]["progress"] = 10
        processing_status[video_id]["phase"] = "scene_detection"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=10,
            current_phase="scene_detection",
        )
        # We need to run this in a thread pool since it's CPU intensive
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, phase1_process, video_path)

        # Produce a video-scoped transcript for sentence and pause boundaries.
        manifest = load_manifest(repo_root=REPO_ROOT, video_id=video_id)
        if manifest.get("has_audio") is not False:
            processing_status[video_id]["status"] = "Normalized audio extraction"
            processing_status[video_id]["progress"] = 20
            processing_status[video_id]["phase"] = "audio_extraction"
            update_manifest_status(
                repo_root=REPO_ROOT,
                video_id=video_id,
                status="processing",
                progress=20,
                current_phase="audio_extraction",
            )
            audio_result = await loop.run_in_executor(
                None,
                partial(
                    extract_normalized_audio,
                    repo_root=REPO_ROOT,
                    video_id=video_id,
                ),
            )
            processing_status[video_id]["status"] = "Transcript extraction"
            processing_status[video_id]["progress"] = 30
            processing_status[video_id]["phase"] = "transcription"
            update_manifest_status(
                repo_root=REPO_ROOT,
                video_id=video_id,
                status="processing",
                progress=30,
                current_phase="transcription",
            )
            await loop.run_in_executor(
                None,
                partial(
                    transcribe_video,
                    audio_result["audio_path"],
                    transcript_path=manifest["artifacts"]["transcript_path"],
                ),
            )

        # Phases C3-C5: boundary evidence, canonical atoms, then validation.
        processing_status[video_id]["status"] = "Canonical timeline chunking"
        processing_status[video_id]["progress"] = 55
        processing_status[video_id]["phase"] = "chunking_foundation"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=55,
            current_phase="chunking_foundation",
        )
        chunking_result = await loop.run_in_executor(
            None,
            partial(
                run_chunking_foundation,
                repo_root=REPO_ROOT,
                video_id=video_id,
            ),
        )
        processing_status[video_id]["boundary_candidate_count"] = (
            chunking_result["boundaries"]["candidate_count"]
        )
        processing_status[video_id]["atom_count"] = (
            chunking_result["atoms"]["atom_count"]
        )
        processing_status[video_id]["atom_validation_passed"] = True

        # Extract clear frame evidence across every canonical atom.
        processing_status[video_id]["status"] = "Frame evidence extraction"
        processing_status[video_id]["progress"] = 70
        processing_status[video_id]["phase"] = "frame_extraction"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=70,
            current_phase="frame_extraction",
        )
        frame_result = await loop.run_in_executor(
            None,
            partial(
                run_frame_extraction,
                repo_root=REPO_ROOT,
                video_id=video_id,
                config=FrameExtractionConfig(
                    mode=os.getenv("FRAME_EXTRACTION_MODE", "atom_coverage"),
                    interval_ms=int(os.getenv("FRAME_INTERVAL_MS", "2000")),
                ),
            ),
        )
        processing_status[video_id]["extracted_frame_count"] = (
            frame_result["frame_index"]["extracted_frame_count"]
        )
        processing_status[video_id]["frame_validation_passed"] = True

        # Phases C6-C9: transcript, visual evidence, semantic chunks, validation.
        processing_status[video_id]["status"] = "Evidence foundation and semantic chunks"
        processing_status[video_id]["progress"] = 78
        processing_status[video_id]["phase"] = "evidence_foundation"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=78,
            current_phase="evidence_foundation",
        )
        evidence_result = await loop.run_in_executor(
            None,
            partial(
                run_evidence_foundation,
                repo_root=REPO_ROOT,
                video_id=video_id,
                create_clips=os.getenv("CREATE_ATOM_CLIPS", "true").lower()
                not in {"0", "false", "no"},
            ),
        )
        processing_status[video_id]["semantic_chunk_count"] = (
            evidence_result["semantic_chunks"]["chunk_count"]
        )
        processing_status[video_id]["chunk_validation_passed"] = True

        # Phases C10-C11: events and hierarchy-native Chroma indexing.
        processing_status[video_id]["status"] = "Events and hierarchy index"
        processing_status[video_id]["progress"] = 84
        processing_status[video_id]["phase"] = "hierarchy_indexing"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=84,
            current_phase="hierarchy_indexing",
        )
        index_result = await loop.run_in_executor(
            None,
            partial(
                index_hierarchy,
                repo_root=REPO_ROOT,
                video_id=video_id,
            ),
        )
        processing_status[video_id]["hierarchy_index_collections"] = (
            index_result["collections"]
        )

        processing_status[video_id]["status"] = "OCR, speaker, and audio quality artifacts"
        processing_status[video_id]["progress"] = 88
        processing_status[video_id]["phase"] = "modality_foundation"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=88,
            current_phase="modality_foundation",
        )
        modality_result = await loop.run_in_executor(
            None,
            partial(
                run_modality_foundation,
                repo_root=REPO_ROOT,
                video_id=video_id,
                skip_ocr=os.getenv("SKIP_OCR", "false").lower() in {"1", "true", "yes"},
                expected_speakers=(
                    int(os.getenv("EXPECTED_SPEAKERS"))
                    if os.getenv("EXPECTED_SPEAKERS")
                    else None
                ),
                allow_partial=True,
            ),
        )
        processing_status[video_id]["modality_status"] = modality_result["status"]
        processing_status[video_id]["modality_errors"] = modality_result["errors"]

        scope_profile = await loop.run_in_executor(
            None,
            partial(
                build_video_scope_profile,
                repo_root=REPO_ROOT,
                video_id=video_id,
            ),
        )
        processing_status[video_id]["scope_profile_path"] = (
            scope_profile.get("profile_path")
            or load_manifest(repo_root=REPO_ROOT, video_id=video_id)["artifacts"].get("scope_profile_path")
        )
        registry_result = await loop.run_in_executor(
            None,
            partial(
                build_evidence_registry,
                repo_root=REPO_ROOT,
                video_id=video_id,
            ),
        )
        processing_status[video_id]["evidence_registry_path"] = (
            registry_result.get("registry_path")
        )
        
        # Phase 2: Visual Enrichment
        processing_status[video_id]["status"] = "Phase 2: Visual Analysis (Gemini)"
        processing_status[video_id]["progress"] = 92
        processing_status[video_id]["phase"] = "visual_analysis"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=92,
            current_phase="visual_analysis",
        )
        await loop.run_in_executor(None, phase2_enrich)
        
        # Phase 3: Indexing
        processing_status[video_id]["status"] = "Phase 3: Building Vector Index"
        processing_status[video_id]["progress"] = 96
        processing_status[video_id]["phase"] = "indexing"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=94,
            current_phase="indexing",
        )
        await loop.run_in_executor(None, phase3_index)
        
        processing_status[video_id]["status"] = "completed"
        processing_status[video_id]["progress"] = 100
        processing_status[video_id]["phase"] = "completed"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="completed",
            progress=100,
            current_phase="completed",
        )
        logger.info(f"Successfully processed video {video_id}")
        
    except Exception as e:
        processing_status[video_id]["status"] = "failed"
        processing_status[video_id]["phase"] = "failed"
        processing_status[video_id]["error"] = str(e)
        try:
            update_manifest_status(
                repo_root=REPO_ROOT,
                video_id=video_id,
                status="failed",
                progress=processing_status[video_id].get("progress", 0),
                current_phase=processing_status[video_id].get("phase", "failed"),
                error=str(e),
            )
        except ManifestError:
            logger.warning("Could not update failed manifest for %s", video_id)
        logger.error(f"Error processing {video_id}: {e}", exc_info=True)

# Global RAG instances
rag_engine: Optional[VideoRAG] = None
hierarchy_rag_engine: Optional[HierarchyVideoRAG] = None

def get_rag():
    global rag_engine
    if rag_engine is None:
        try:
            rag_engine = VideoRAG()
        except Exception as e:
            logger.error(f"Failed to initialize VideoRAG: {e}")
            raise e
    return rag_engine

def get_hierarchy_rag():
    global hierarchy_rag_engine
    if hierarchy_rag_engine is None:
        hierarchy_rag_engine = HierarchyVideoRAG(repo_root=REPO_ROOT)
    return hierarchy_rag_engine


def _source_type(value: Any) -> SourceType:
    normalized = str(value or "").strip().lower()
    mapping = {
        "atom": SourceType.ATOM,
        "atomic_span": SourceType.ATOM,
        "chunk": SourceType.SEMANTIC_CHUNK,
        "semantic_chunk": SourceType.SEMANTIC_CHUNK,
        "visual_chunk": SourceType.VISUAL_CHUNK,
        "event": SourceType.EVENT,
        "ocr": SourceType.OCR,
        "speaker_turn": SourceType.SPEAKER_TURN,
        "audio_event": SourceType.AUDIO_EVENT,
        "general_knowledge": SourceType.GENERAL_KNOWLEDGE,
        "system": SourceType.SYSTEM,
    }
    return mapping.get(normalized, SourceType.UNKNOWN)


def _citation_from_result(raw: dict[str, Any], index: int, video_id: str) -> Citation:
    start_ms = raw.get("start_ms")
    end_ms = raw.get("end_ms")
    if start_ms is None and raw.get("start_seconds") is not None:
        start_ms = int(float(raw["start_seconds"]) * 1000)
    if end_ms is None and raw.get("end_seconds") is not None:
        end_ms = int(float(raw["end_seconds"]) * 1000)
    return Citation(
        citation_id=str(raw.get("citation_id") or raw.get("id") or f"S{index + 1}"),
        source_type=_source_type(raw.get("source_type")),
        source_id=str(
            raw.get("source_id")
            or raw.get("atom_id")
            or raw.get("chunk_id")
            or raw.get("event_id")
            or f"source_{index + 1}"
        ),
        video_id=str(raw.get("video_id") or video_id),
        start_ms=start_ms,
        end_ms=end_ms,
        start_seconds=raw.get("start_seconds"),
        end_seconds=raw.get("end_seconds"),
        timestamp=raw.get("timestamp"),
        text=raw.get("text") or raw.get("transcript_text") or raw.get("summary"),
        visual_summary=raw.get("visual_summary"),
        parent_chunk_id=raw.get("parent_chunk_id"),
        parent_event_id=raw.get("parent_event_id"),
        confidence=raw.get("confidence"),
    )


def _primary_timestamp(citations: list[Citation]) -> float:
    for citation in citations:
        if citation.start_seconds is not None:
            return float(citation.start_seconds)
        if citation.start_ms is not None:
            return citation.start_ms / 1000.0
    return 0.0


def _response_from_hierarchy_result(
    *,
    request: QueryRequest,
    result: dict[str, Any],
    trace_id: str,
    fallback_used: bool = False,
) -> QueryResponse:
    citations = [_citation_from_result(c, i, request.video_id) for i, c in enumerate(result.get("citations") or [])]
    timestamp = _primary_timestamp(citations)
    primary = citations[0] if citations else None
    confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0) or 0.0)))
    outcome = Outcome.GROUNDED_ANSWER if citations and confidence >= 0.35 else Outcome.VIDEO_EVIDENCE_NOT_FOUND
    if outcome == Outcome.VIDEO_EVIDENCE_NOT_FOUND and citations:
        outcome = Outcome.PARTIAL_ANSWER
    return QueryResponse(
        outcome=outcome,
        answer=result.get("answer") or "I could not find enough reliable evidence in this video to answer that question.",
        video_id=request.video_id,
        query=request.query,
        answer_mode=request.answer_mode,
        timestamp=timestamp,
        start_ms=primary.start_ms if primary else None,
        end_ms=primary.end_ms if primary else None,
        source_id=primary.source_id if primary else None,
        source_type=primary.source_type if primary else SourceType.UNKNOWN,
        parent_event_id=primary.parent_event_id if primary else None,
        confidence=confidence,
        citations=citations,
        answer_quality=AnswerQuality(
            grounded=bool(citations),
            has_timestamp=timestamp > 0,
            has_citations=bool(citations),
            uses_verified_evidence=bool(citations),
            fallback_used=fallback_used,
            low_confidence_reason=None if confidence >= 0.35 else "weak_or_missing_evidence",
            quality_score=confidence,
        ),
        trace_id=trace_id,
    )


def _response_from_agentic_generation(
    *,
    request: QueryRequest,
    trace_id: str,
    generation: dict[str, Any],
    evidence_packet: dict[str, Any],
    temporal_context: dict[str, Any],
    claim_verification: dict[str, Any],
    confidence: dict[str, Any],
    answerability: dict[str, Any],
) -> QueryResponse:
    cited_ids = set(re.findall(r"\bS\d+\b", str(generation.get("answer") or "")))
    packet_citations = evidence_packet.get("citations", [])
    if cited_ids:
        packet_citations = [
            item for item in packet_citations if item.get("citation_id") in cited_ids
        ]
    elif packet_citations:
        packet_citations = packet_citations[:1]
    citations = [
        Citation(
            citation_id=item["citation_id"],
            evidence_id=item.get("evidence_id"),
            source_type=_source_type(item.get("source_type")),
            canonical_source_type=item.get("canonical_source_type"),
            source_id=str(item["source_id"]),
            video_id=item.get("video_id") or request.video_id,
            start_ms=item.get("start_ms"),
            end_ms=item.get("end_ms"),
            start_seconds=(item.get("start_ms") or 0) / 1000,
            end_seconds=(item.get("end_ms") or 0) / 1000,
            parent_chunk_id=item.get("parent_chunk_id"),
            parent_event_id=item.get("parent_event_id"),
            evidence_anchor=item.get("evidence_anchor") or {},
            answer_context_window=item.get("answer_context_window") or {},
            citation_interval=item.get("citation_interval") or {},
            quality_score=item.get("quality_score"),
            text=next(
                (
                    evidence.get("text")
                    for evidence in evidence_packet.get("verified_evidence", [])
                    if evidence.get("citation_id") == item["citation_id"]
                ),
                None,
            ),
        )
        for item in packet_citations
    ]
    timestamp = _primary_timestamp(citations)
    primary = citations[0] if citations else None
    score = float(confidence.get("score", 0.0))
    unsupported = int(claim_verification.get("unsupported_claim_count", 0) or 0)
    decision = answerability.get("decision")
    outcome = Outcome.GROUNDED_ANSWER
    if decision == "partial_answer" or unsupported:
        outcome = Outcome.PARTIAL_ANSWER
    if not citations:
        outcome = Outcome.VIDEO_EVIDENCE_NOT_FOUND
    return QueryResponse(
        outcome=outcome,
        answer=generation.get("answer", ""),
        video_id=request.video_id,
        query=request.query,
        answer_mode=request.answer_mode,
        timestamp=timestamp,
        start_ms=primary.start_ms if primary else None,
        end_ms=primary.end_ms if primary else None,
        source_id=primary.source_id if primary else None,
        source_type=primary.source_type if primary else SourceType.UNKNOWN,
        parent_event_id=primary.parent_event_id if primary else None,
        confidence=max(0.0, min(1.0, score)),
        citations=citations,
        answer_quality=AnswerQuality(
            grounded=bool(citations) and claim_verification.get("passed", False),
            has_timestamp=timestamp > 0,
            has_citations=bool(citations),
            uses_verified_evidence=bool(citations),
            fallback_used=bool(generation.get("fallback_used")),
            low_confidence_reason=confidence.get("low_confidence_reason"),
            quality_score=max(0.0, min(1.0, score)),
        ),
        trace_id=trace_id,
        warnings=[
            warning
            for warning in [
                "claim_revision_used" if generation.get("revision_used") else None,
                "conflicting_evidence" if temporal_context.get("conflicts") else None,
            ]
            if warning
        ],
    )


def _policy_response(
    *,
    request: QueryRequest,
    trace_id: str,
    outcome: Outcome,
    answer: str,
    confidence: float,
    warning: str | None = None,
) -> QueryResponse:
    return QueryResponse(
        outcome=outcome,
        answer=answer,
        video_id=request.video_id,
        query=request.query,
        answer_mode=request.answer_mode,
        timestamp=0.0,
        confidence=max(0.0, min(1.0, confidence)),
        citations=[],
        answer_quality=AnswerQuality(
            grounded=False,
            has_timestamp=False,
            has_citations=False,
            uses_verified_evidence=False,
            low_confidence_reason=outcome.value,
            quality_score=max(0.0, min(1.0, confidence)),
        ),
        trace_id=trace_id,
        warnings=[warning] if warning else [],
    )


def _agentic_prelude(request: QueryRequest) -> tuple[RetrievalTrace, dict[str, Any], dict[str, Any], dict[str, Any]]:
    resolved = resolve_conversation_references(
        raw_query=request.query,
        conversation_context=request.conversation_context,
    )
    understanding = understand_query(
        raw_query=request.query,
        standalone_query=resolved["standalone_query"],
        conversation_resolution=resolved,
    )
    scope = route_scope(
        repo_root=REPO_ROOT,
        video_id=request.video_id,
        query_understanding=understanding,
        answer_mode=request.answer_mode,
    )
    trace = RetrievalTrace(
        request=model_to_dict(request),
        conversation_resolution=resolved,
        query_understanding=understanding,
        scope_decision=scope,
    )
    return trace, resolved, understanding, scope


def _execute_plan_stage(
    *,
    request: QueryRequest,
    trace: RetrievalTrace,
    plan: Any,
    query_understanding: dict[str, Any],
    scope_decision: dict[str, Any],
) -> dict[str, Any]:
    trace.plans.append(model_to_dict(plan))
    orchestrator = RetrievalOrchestrator(REPO_ROOT)
    retrieval = orchestrator.execute(
        video_id=request.video_id,
        plan=plan,
        query_understanding=query_understanding,
    )
    trace.retrieval_attempts.extend(retrieval["attempts"])
    trace.warnings.extend(retrieval.get("warnings", []))

    fusion = fuse_candidates(
        candidates=retrieval["candidates"],
        plan=model_to_dict(plan),
        query_understanding=query_understanding,
    )
    reranked = rerank_candidates(
        candidates=fusion["candidates"],
        query_understanding=query_understanding,
    )
    deduped = deduplicate_temporal_candidates(candidates=reranked["candidates"])
    verification = verify_evidence(
        repo_root=REPO_ROOT,
        video_id=request.video_id,
        candidates=deduped["candidates"],
        query_understanding=query_understanding,
    )
    verification["retrieval_warnings"] = retrieval.get("warnings", [])
    verification["retrieval_attempts"] = retrieval.get("attempts", [])
    answerability = evaluate_answerability(
        verified_evidence=verification["verified_evidence"],
        query_understanding=query_understanding,
        scope_decision=scope_decision,
        verification_summary=verification,
    )
    return {
        "plan": plan,
        "retrieval": retrieval,
        "fusion": fusion,
        "reranked": reranked,
        "deduped": deduped,
        "verification": verification,
        "answerability": answerability,
    }


def _run_retrieval_gate(
    *,
    request: QueryRequest,
    trace: RetrievalTrace,
    query_understanding: dict[str, Any],
    scope_decision: dict[str, Any],
) -> dict[str, Any]:
    plan = create_retrieval_plan(
        query_understanding=query_understanding,
        answer_mode=request.answer_mode,
    )
    stage = _execute_plan_stage(
        request=request,
        trace=trace,
        plan=plan,
        query_understanding=query_understanding,
        scope_decision=scope_decision,
    )
    corrective_attempts = []
    attempt = 0
    while should_retry(stage["answerability"], attempt, plan.max_corrective_attempts):
        corrective_plan = create_corrective_plan(
            original_plan=plan,
            query_understanding=query_understanding,
            answerability=stage["answerability"],
            attempt=attempt,
        )
        attempt += 1
        corrective_stage = _execute_plan_stage(
            request=request,
            trace=trace,
            plan=corrective_plan,
            query_understanding=query_understanding,
            scope_decision=scope_decision,
        )
        corrective_attempts.append(
            {
                "attempt": attempt,
                "strategy": corrective_plan.strategy,
                "reason": corrective_plan.corrective_reason,
                "actions": corrective_plan.corrective_actions,
                "decision": corrective_stage["answerability"]["decision"],
                "score": corrective_stage["answerability"]["score"],
            }
        )
        stage = corrective_stage

    trace.candidate_fusion = {
        key: value
        for key, value in stage["fusion"].items()
        if key != "candidates"
    }
    trace.reranking = {
        key: value
        for key, value in stage["reranked"].items()
        if key != "candidates"
    }
    trace.reranking["deduplication"] = {
        key: value
        for key, value in stage["deduped"].items()
        if key != "candidates"
    }
    verification = stage["verification"]
    trace.verification = {
        key: value
        for key, value in verification.items()
        if key not in {"verified_evidence", "rejected_evidence"}
    }
    trace.verification["top_verified_source_ids"] = [
        item["source_id"]
        for item in verification["verified_evidence"][:5]
    ]
    trace.verification["rejected_evidence"] = verification["rejected_evidence"][:20]
    trace.answerability = stage["answerability"]
    stage["corrective_attempts"] = corrective_attempts
    return stage


def _run_agentic_answer_pipeline(
    *,
    request: QueryRequest,
    trace: RetrievalTrace,
    retrieval_gate: dict[str, Any],
    query_understanding: dict[str, Any],
) -> QueryResponse:
    temporal_context = build_temporal_context(
        repo_root=REPO_ROOT,
        video_id=request.video_id,
        verified_evidence=retrieval_gate["verification"]["verified_evidence"],
        retrieval_plan=model_to_dict(retrieval_gate["plan"]),
        query_understanding=query_understanding,
    )
    trace.temporal_reasoning = {
        key: value
        for key, value in temporal_context.items()
        if key != "expanded_atoms"
    }
    evidence_packet = build_evidence_packet(
        request=model_to_dict(request),
        outcome_candidate=retrieval_gate["answerability"]["decision"],
        verified_evidence=retrieval_gate["verification"]["verified_evidence"],
        temporal_context=temporal_context,
        answerability=retrieval_gate["answerability"],
        repo_root=REPO_ROOT,
        query_understanding=query_understanding,
    )
    trace.evidence_packet_summary = {
        "citation_count": len(evidence_packet["citations"]),
        "citation_validation": evidence_packet.get("citation_validation"),
        "verified_evidence_count": len(evidence_packet["verified_evidence"]),
        "primary_moment": evidence_packet["temporal_context"].get("primary_moment"),
        "missing_evidence_notes": evidence_packet.get("missing_evidence_notes", []),
    }

    generator = GroundedAnswerGenerator()
    generation = generator.generate(evidence_packet)
    claim_verification = verify_claims(generation["answer"], evidence_packet)
    if not claim_verification["passed"] and claim_verification.get("can_revise"):
        revised = generator.revise(evidence_packet, claim_verification)
        revised["revision_used"] = True
        revised_verification = verify_claims(revised["answer"], evidence_packet)
        generation = revised
        claim_verification = revised_verification
    if not claim_verification["passed"]:
        cleaned_answer = remove_unsupported_claims(generation["answer"], claim_verification)
        if cleaned_answer:
            generation = {
                **generation,
                "answer": cleaned_answer,
                "claim_filter_used": True,
                "citation_preserving": True,
            }
            claim_verification = verify_claims(cleaned_answer, evidence_packet)

    confidence = calibrate_confidence(
        retrieval_gate=retrieval_gate,
        temporal_context=temporal_context,
        evidence_packet=evidence_packet,
        claim_verification=claim_verification,
        generation=generation,
    )
    trace.generation = generation
    trace.claim_verification = claim_verification
    trace.confidence = confidence
    return _response_from_agentic_generation(
        request=request,
        trace_id=trace.trace_id,
        generation=generation,
        evidence_packet=evidence_packet,
        temporal_context=temporal_context,
        claim_verification=claim_verification,
        confidence=confidence,
        answerability=retrieval_gate["answerability"],
    )


@app.post("/ask")
async def ask_question(request: QueryRequest):
    trace_repo = TraceRepository(REPO_ROOT)
    trace: RetrievalTrace | None = None
    try:
        trace, resolved, understanding, scope = _agentic_prelude(request)
        if scope["policy_action"] == ScopeAction.PROCESSING_INCOMPLETE:
            response = _policy_response(
                request=request,
                trace_id=trace.trace_id,
                outcome=Outcome.PROCESSING_INCOMPLETE,
                answer="This video is not ready for reliable question answering yet. Please finish processing and indexing it first.",
                confidence=0.0,
                warning="processing_incomplete",
            )
        elif scope["policy_action"] == ScopeAction.ABSTAIN_UNRELATED:
            response = _policy_response(
                request=request,
                trace_id=trace.trace_id,
                outcome=Outcome.UNRELATED_TO_VIDEO,
                answer="That question appears to be outside the selected video, so I cannot answer it with video citations in strict video mode.",
                confidence=float(scope.get("confidence", 0.0)),
            )
        elif scope["policy_action"] == ScopeAction.CLARIFY:
            response = _policy_response(
                request=request,
                trace_id=trace.trace_id,
                outcome=Outcome.AMBIGUOUS_QUERY,
                answer="Do you want the answer from this selected video, or a general explanation?",
                confidence=float(scope.get("confidence", 0.0)),
            )
        elif scope["policy_action"] == ScopeAction.GENERAL_ANSWER:
            response = _policy_response(
                request=request,
                trace_id=trace.trace_id,
                outcome=Outcome.UNRELATED_TO_VIDEO,
                answer="This question looks unrelated to the selected video. Hybrid general-answer generation will be added in the next retrieval phase, so I am not attaching video citations.",
                confidence=float(scope.get("confidence", 0.0)),
            )
        else:
            retrieval_gate = _run_retrieval_gate(
                request=request,
                trace=trace,
                query_understanding=understanding,
                scope_decision=scope,
            )
            decision = retrieval_gate["answerability"]["decision"]
            if decision in {"answer", "partial_answer"}:
                response = _run_agentic_answer_pipeline(
                    request=request,
                    trace=trace,
                    retrieval_gate=retrieval_gate,
                    query_understanding=understanding,
                )
            elif decision == "processing_incomplete":
                response = _policy_response(
                    request=request,
                    trace_id=trace.trace_id,
                    outcome=Outcome.PROCESSING_INCOMPLETE,
                    answer="The requested evidence depends on processing that is incomplete or unavailable for this video.",
                    confidence=float(retrieval_gate["answerability"].get("score", 0.0)),
                    warning="processing_incomplete",
                )
            elif decision == "corrective_retrieval":
                response = _policy_response(
                    request=request,
                    trace_id=trace.trace_id,
                    outcome=Outcome.VIDEO_EVIDENCE_NOT_FOUND,
                    answer="I found weak related evidence, but not enough verified support to answer safely after corrective retrieval.",
                    confidence=float(retrieval_gate["answerability"].get("score", 0.0)),
                    warning="corrective_retrieval_exhausted",
                )
            else:
                response = _policy_response(
                    request=request,
                    trace_id=trace.trace_id,
                    outcome=Outcome.VIDEO_EVIDENCE_NOT_FOUND,
                    answer="I could not find enough reliable evidence in this video to answer that question.",
                    confidence=float(retrieval_gate["answerability"].get("score", 0.0)),
                    warning=decision,
                )

        trace.final_response = model_to_dict(response)
        trace_repo.save(request.video_id, trace)
        return response
    except Exception as e:
        logger.error(f"RAG error in /ask: {e}", exc_info=True)
        trace_id = trace.trace_id if trace else "trace_error"
        response = _policy_response(
            request=request,
            trace_id=trace_id,
            outcome=Outcome.SYSTEM_ERROR,
            answer=f"Error: {str(e)}",
            confidence=0.0,
            warning="system_error",
        )
        if trace:
            trace.errors.append({"code": "system_error", "message": str(e)})
            trace.final_response = model_to_dict(response)
            trace_repo.save(request.video_id, trace)
        return response


@app.post("/ask-debug")
async def ask_question_debug(request: QueryRequest):
    trace_repo = TraceRepository(REPO_ROOT)
    try:
        trace, resolved, understanding, scope = _agentic_prelude(request)
        result = {}
        retrieval_gate = {}
        if scope["policy_action"] == ScopeAction.RETRIEVE_VIDEO:
            retrieval_gate = _run_retrieval_gate(
                request=request,
                trace=trace,
                query_understanding=understanding,
                scope_decision=scope,
            )
            if retrieval_gate["answerability"]["decision"] in {"answer", "partial_answer"}:
                response = _run_agentic_answer_pipeline(
                    request=request,
                    trace=trace,
                    retrieval_gate=retrieval_gate,
                    query_understanding=understanding,
                )
                result = trace.generation
            elif retrieval_gate["answerability"]["decision"] == "processing_incomplete":
                response = _policy_response(
                    request=request,
                    trace_id=trace.trace_id,
                    outcome=Outcome.PROCESSING_INCOMPLETE,
                    answer="Debug route stopped because required modality processing is incomplete.",
                    confidence=float(retrieval_gate["answerability"].get("score", 0.0)),
                    warning="processing_incomplete",
                )
            else:
                response = _policy_response(
                    request=request,
                    trace_id=trace.trace_id,
                    outcome=Outcome.VIDEO_EVIDENCE_NOT_FOUND,
                    answer="Debug route stopped before generation because the evidence was not answerable.",
                    confidence=float(retrieval_gate["answerability"].get("score", 0.0)),
                    warning=retrieval_gate["answerability"]["decision"],
                )
        else:
            response = _policy_response(
                request=request,
                trace_id=trace.trace_id,
                outcome=Outcome.AMBIGUOUS_QUERY if scope["policy_action"] == ScopeAction.CLARIFY else Outcome.UNRELATED_TO_VIDEO,
                answer="Debug route stopped before retrieval because the scope policy did not select video retrieval.",
                confidence=float(scope.get("confidence", 0.0)),
            )
        trace.final_response = model_to_dict(response)
        trace_repo.save(request.video_id, trace)
        return {
            "trace": model_to_dict(trace),
            "response": model_to_dict(response),
            "retrieval_gate": retrieval_gate,
            "hierarchy_result": result,
        }
    except Exception as e:
        logger.error(f"RAG error in /ask-debug: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
