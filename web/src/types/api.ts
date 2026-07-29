import type { ComponentType } from "react";

export type ApiProcessingState = "processing" | "completed" | "failed" | "cancelled";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue | undefined;
}

export interface ApiVideoSummary {
  video_id: string;
  filename: string;
  status: ApiProcessingState | string;
  progress?: number;
  duration_seconds?: number;
  resolution?: string | { width: number; height: number };
}

export interface ApiProcessingStatus extends ApiVideoSummary {
  phase?: string;
  extension?: string;
  path?: string;
  manifest_path?: string;
  source_sha256?: string;
  duration_ms?: number;
  fps?: number;
  frame_count?: number;
  video_codec?: string;
  audio_codec?: string;
  audio_sample_rate?: number;
  has_audio?: boolean;
  timeline?: Record<string, unknown>;
  audio_path?: string;
  pipeline_version?: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
}

export interface ApiManifest {
  video_id: string;
  source_filename?: string;
  original_filename?: string;
  upload_extension?: string;
  source_path?: string;
  source_path_relative?: string;
  source_sha256?: string;
  video_path?: string;
  video_path_relative?: string;
  audio_path?: string;
  audio_path_relative?: string;
  duration_ms?: number;
  duration_seconds?: number;
  fps?: number;
  frame_count?: number;
  resolution?: string | { width: number; height: number };
  width?: number;
  height?: number;
  video_codec?: string;
  audio_codec?: string;
  audio_sample_rate?: number;
  has_audio?: boolean;
  codec?: string;
  probe_backend?: string;
  probe_warnings?: string[];
  timeline?: Record<string, unknown>;
  processing?: {
    status?: string;
    processing_status?: string;
    progress?: number;
    current_phase?: string;
    error?: string;
    started_at?: string;
    completed_at?: string;
    updated_at?: string;
  };
  artifacts?: Record<string, string>;
  pipeline_version?: string;
  created_at?: string;
  updated_at?: string;
  artifact_metadata?: Record<string, unknown>;
}

export interface ApiArtifactDocument extends JsonObject {
  video_id?: string;
  generated_at?: string;
  schema_version?: string;
}

export interface ApiTranscriptAtom extends JsonObject {
  atom_id?: string;
  id?: string;
  start_ms?: number;
  end_ms?: number;
  text?: string;
  speaker_id?: string;
}

export interface ApiTranscriptDocument extends ApiArtifactDocument {
  atoms?: ApiTranscriptAtom[];
  items?: ApiTranscriptAtom[];
}

export interface ApiTimelineEvent extends JsonObject {
  event_id?: string;
  id?: string;
  start_ms?: number;
  end_ms?: number;
  title?: string;
  summary?: string;
}

export interface ApiTimelineDocument extends ApiArtifactDocument {
  events?: ApiTimelineEvent[];
  items?: ApiTimelineEvent[];
}

export interface ApiVideoLifecycleResponse {
  video_id: string;
  status: string;
  message?: string;
}

export interface ApiHealthResponse {
  status: "ok" | "degraded";
  service: string;
  timestamp: string;
  details?: JsonObject;
}

export interface ApiAnalyticsOverview {
  total_videos: number;
  ready_videos: number;
  processing_videos: number;
  failed_videos: number;
  total_duration_seconds: number;
  total_storage_bytes: number;
  questions_asked: number;
  videos: ApiVideoSummary[];
}
export interface ApiUploadResponse {
  video_id: string;
  filename?: string;
  extension?: string;
  manifest?: ApiManifest;
}

export type ApiAnswerMode = "strict_video" | "hybrid_assistant" | "clarify_when_ambiguous";
export type ApiOutcome =
  | "grounded_answer"
  | "partial_answer"
  | "video_evidence_not_found"
  | "unrelated_to_video"
  | "ambiguous_query"
  | "conflicting_evidence"
  | "processing_incomplete"
  | "system_error";
export type ApiSourceType =
  | "atom"
  | "semantic_chunk"
  | "visual_chunk"
  | "event"
  | "ocr"
  | "speaker_turn"
  | "audio_event"
  | "general_knowledge"
  | "system"
  | "unknown";

export interface ApiCitation {
  citation_id: string;
  evidence_id?: string | null;
  source_type: ApiSourceType;
  canonical_source_type?: string | null;
  source_id: string;
  video_id?: string | null;
  start_ms?: number | null;
  end_ms?: number | null;
  start_seconds?: number | null;
  end_seconds?: number | null;
  timestamp?: string | null;
  text?: string | null;
  visual_summary?: string | null;
  evidence_anchor?: Record<string, unknown>;
  answer_context_window?: Record<string, unknown>;
  citation_interval?: Record<string, unknown>;
  quality_score?: number | null;
  parent_chunk_id?: string | null;
  parent_event_id?: string | null;
  confidence?: number | null;
}

export interface ApiAnswerQuality {
  grounded?: boolean;
  has_timestamp?: boolean;
  has_citations?: boolean;
  uses_verified_evidence?: boolean;
  requires_visual_followup?: boolean;
  fallback_used?: boolean;
  low_confidence_reason?: string | null;
  quality_score?: number;
}

export interface ApiAskRequest {
  video_id: string;
  query: string;
  answer_mode?: ApiAnswerMode;
  conversation_context?: Record<string, unknown>[];
  request_id?: string;
}

export interface ApiAskResponse {
  outcome: ApiOutcome;
  answer: string;
  video_id: string;
  query: string;
  answer_mode?: ApiAnswerMode;
  timestamp?: number;
  start_ms?: number | null;
  end_ms?: number | null;
  source_id?: string | null;
  source_type?: ApiSourceType;
  parent_event_id?: string | null;
  confidence?: number;
  citations?: ApiCitation[];
  answer_quality?: ApiAnswerQuality;
  trace_id?: string;
  warnings?: string[];
}

export interface LibraryVideo {
  id: string;
  title: string;
  filename: string;
  duration: string;
  size: string;
  date: string;
  updated: string;
  status: "Uploaded" | "Processing" | "Completed" | "Failed" | "Indexed";
  progress?: number;
  gradient: string;
  icon: ComponentType<any>;
  tags: string[];
  pipelineVersion: string;
  lastQuestionDate: string;
  artifacts: {
    transcript: boolean;
    ocr: boolean;
    speakers: boolean;
    audio: boolean;
    chromadb: boolean;
  };
}

export interface DashboardStat {
  label: string;
  value: number;
  display: string;
  subtitle: string;
  trend: string;
  trendText: string;
  icon: ComponentType<any>;
  tone: "indigo" | "emerald" | "amber" | "violet" | "cyan";
}

export interface RecentVideoSummary {
  title: string;
  duration: string;
  date: string;
  status: string;
  statusVariant: "success" | "warning" | "default" | "destructive";
  gradient: string;
  icon: ComponentType<any>;
}

export interface ProcessingJobSummary {
  title: string;
  stage: string;
  progress: number;
  progressClass: string;
  eta: string;
  status: string;
}

export interface ActivitySummary {
  title: string;
  detail: string;
  time: string;
  icon: ComponentType<any>;
  tone: "indigo" | "emerald" | "amber" | "violet" | "cyan";
}

export interface CitationItem {
  id: string;
  timestamp: string;
  timestampEnd: string;
  frameGradient: string;
  transcriptSnippet: string;
  ocrSnippet?: string;
  score: number;
  type: "transcript" | "ocr" | "scene";
}

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  confidenceScore?: number;
  retrievalStatus?: string;
  citations?: CitationItem[];
  bookmarked?: boolean;
}

export interface TranscriptBlock {
  id: string;
  startSec: number;
  endSec: number;
  timestamp: string;
  speakerId: string;
  speakerName: string;
  speakerAvatar: string;
  speakerTone: "indigo" | "violet" | "cyan" | "emerald";
  text: string;
  confidence: number;
  language: string;
  hasOcr: boolean;
  ocrPreview?: string;
  hasVisualObject: boolean;
  sceneTitle?: string;
  sceneGradient?: string;
  citationCount: number;
  importanceScore: number;
  topicCluster: string;
  bookmarked?: boolean;
}

export interface TimelineMarkerData {
  id: string;
  trackId: "scenes" | "transcript" | "ocr" | "speakers" | "audio" | "citations" | "topics" | "events";
  startSec: number;
  endSec: number;
  timeLabel: string;
  title: string;
  summary: string;
  transcriptQuote?: string;
  ocrText?: string;
  color: string;
  gradient?: string;
  speaker?: string;
  badge?: string;
}

export interface TimelineTrackData {
  id: "scenes" | "transcript" | "ocr" | "speakers" | "audio" | "citations" | "topics" | "events";
  label: string;
  iconName: string;
  color: string;
  badge: string;
  visible: boolean;
  expanded: boolean;
  markers: TimelineMarkerData[];
}

export interface OverviewChapter {
  id: string;
  title: string;
  startSec: number;
  endSec: number;
  gradient: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "video" | "scene" | "speaker" | "ocr" | "transcript" | "object" | "topic" | "question" | "answer" | "evidence";
  x: number;
  y: number;
  iconName: string;
  color: string;
  details: string;
}

export interface GraphEdge {
  id: string;
  sourceId: string;
  targetId: string;
  label: "mentions" | "contains" | "references" | "explains" | "supports" | "related";
}

export interface EvidenceItem {
  id: string;
  nodeId: string;
  timestamp: string;
  startSec: number;
  endSec: number;
  sourceType: "transcript" | "ocr" | "scene" | "visual";
  title: string;
  rank: number;
  confidence: number;
  quality: "grounded" | "verified" | "partial" | "weak" | "unavailable";
  transcriptQuote?: string;
  ocrText?: string;
  sceneDescription?: string;
  speaker?: string;
  explanation: string;
  frameGradient: string;
  frameUri?: string;
  sourceId?: string;
  parentEventId?: string;
}

export type VideoStatus = LibraryVideo["status"];

export interface OcrEvidenceView {
  id: string;
  text: string;
  startSec: number;
  endSec: number;
  timestamp: string;
  confidence: number;
  qualityScore: number;
  frameId?: string;
  frameUri?: string;
  parentChunkId?: string;
  parentEventId?: string;
}

export interface VideoDetailScene {
  id: string;
  index: number;
  timeStart: string;
  timeEnd: string;
  title: string;
  description: string;
  gradient: string;
  startSec: number;
}

export interface VideoDetailView {
  summary: string;
  topics: string[];
  visibleTexts: string[];
  stats: {
    events: number;
    frames: number;
    ocrRecords: number;
    transcriptSpans: number;
    speakers: number;
    audioEvents: number;
    semanticChunks: number;
  };
  scenes: VideoDetailScene[];
  validationPassed: boolean | null;
}

export interface WorkspaceViewModel {
  durationSec: number;
  chapters: OverviewChapter[];
  tracks: TimelineTrackData[];
  transcriptBlocks: TranscriptBlock[];
  ocrEvidence: OcrEvidenceView[];
  evidenceItems: EvidenceItem[];
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  details: VideoDetailView;
}



export interface ApiVideoQuestion extends ApiAskResponse {
  created_at?: string;
}

export interface ApiQuestionHistoryResponse {
  questions: ApiVideoQuestion[];
}

export interface ApiAskDebugResponse {
  trace: JsonObject;
  response: ApiAskResponse;
  retrieval_gate: JsonObject;
  hierarchy_result: JsonObject;
}

