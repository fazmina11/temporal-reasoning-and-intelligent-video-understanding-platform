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

class QueryRequest(BaseModel):
    video_id: str
    query: str

class QueryResponse(BaseModel):
    answer: str
    timestamp: float
    confidence: float
    citations: List[Dict[str, Any]]

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
        
        # Phase 2: Visual Enrichment
        processing_status[video_id]["status"] = "Phase 2: Visual Analysis (Gemini)"
        processing_status[video_id]["progress"] = 86
        processing_status[video_id]["phase"] = "visual_analysis"
        update_manifest_status(
            repo_root=REPO_ROOT,
            video_id=video_id,
            status="processing",
            progress=82,
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

@app.post("/ask")
async def ask_question(request: QueryRequest):
    try:
        rag = get_hierarchy_rag()
        result = rag.ask(request.query, video_id=request.video_id)
        
        # Extract all timestamps from citations for comprehensive references
        timestamps = []
        if result.get("citations"):
            for citation in result["citations"]:
                if "start_seconds" in citation and citation["start_seconds"] is not None:
                    timestamp = float(citation["start_seconds"])
                    ts_str = citation.get("timestamp", str(timestamp))
                    timestamps.append({
                        "timestamp": timestamp,
                        "formatted": ts_str,
                        "context": citation.get("visual_summary", "")[:100] + "..." if citation.get("visual_summary") else ""
                    })
                elif "timestamp" in citation:
                    # Parse timestamp like "00:01:23" to seconds
                    ts_str = citation["timestamp"]
                    try:
                        parts = ts_str.split(':')
                        if len(parts) == 3:
                            timestamp = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        elif len(parts) == 2:
                            timestamp = int(parts[0]) * 60 + int(parts[1])
                        else:
                            timestamp = float(ts_str)
                        timestamps.append({
                            "timestamp": timestamp,
                            "formatted": ts_str,
                            "context": citation.get("visual_summary", "")[:100] + "..." if citation.get("visual_summary") else ""
                        })
                    except:
                        continue
        
        # Use the first timestamp for video jumping, but return all for frontend
        primary_timestamp = timestamps[0]["timestamp"] if timestamps else 0.0
        
        return QueryResponse(
            answer=result.get("answer", "❌  Retriever unavailable or processing failed."),
            timestamp=primary_timestamp,
            confidence=result.get("confidence", 0.0),
            citations=result.get("citations", [])
        )
    except Exception as e:
        logger.error(f"RAG error in /ask: {e}", exc_info=True)
        # Return a valid QueryResponse even on internal error to avoid 500
        return QueryResponse(
            answer=f"❌  Error: {str(e)}",
            timestamp=0.0,
            confidence=0.0,
            citations=[]
        )

@app.post("/ask-debug")
async def ask_question_debug(request: QueryRequest):
    try:
        rag = get_hierarchy_rag()
        return rag.ask(request.query, video_id=request.video_id)
    except Exception as e:
        logger.error(f"RAG error in /ask-debug: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
