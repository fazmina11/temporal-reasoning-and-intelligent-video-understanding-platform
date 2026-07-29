import { Activity, BrainCircuit, Database, FileText, FileVideo, Film, Mic2, Network, ScanText, Video, Zap, Clock3 } from "lucide-react";
import type {
  ActivitySummary,
  ApiManifest,
  ApiProcessingStatus,
  ApiVideoSummary,
  DashboardStat,
  EvidenceItem,
  GraphEdge,
  GraphNode,
  LibraryVideo,
  ProcessingJobSummary,
  RecentVideoSummary,
  TimelineTrackData,
  TranscriptBlock
} from "@/types/api";

const gradients = [
  "from-indigo-950 via-slate-900 to-cyan-900",
  "from-slate-900 via-violet-950 to-indigo-900",
  "from-cyan-950 via-slate-900 to-indigo-950",
  "from-amber-950 via-slate-900 to-rose-950",
  "from-emerald-950 via-slate-900 to-cyan-950",
  "from-blue-950 via-slate-900 to-violet-950",
  "from-fuchsia-950 via-slate-900 to-indigo-950",
  "from-rose-950 via-slate-900 to-orange-950"
];

const icons = [BrainCircuit, Network, FileVideo, Mic2, Video, ScanText, Clock3, Database, Zap, Film, FileText, Activity];

const stripExtension = (value?: string | null) => (value ? value.replace(/\.[^/.]+$/, "") : "");

const formatDuration = (seconds?: number) => {
  if (!seconds || seconds <= 0) return "0:00";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const secs = String(total % 60).padStart(2, "0");
  return `${minutes}:${secs}`;
};

const statusToUi = (status?: string, progress?: number): LibraryVideo["status"] => {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("failed")) return "Failed";
  if (normalized.includes("completed")) return "Completed";
  if (normalized.includes("indexed")) return "Indexed";
  if (normalized.includes("uploaded")) return "Uploaded";
  if (normalized.includes("processing") || (typeof progress === "number" && progress > 0 && progress < 100)) return "Processing";
  if (typeof progress === "number" && progress >= 100) return "Indexed";
  return "Uploaded";
};

const safeDate = (value?: string) => {
  if (!value) return "Recent";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
};

const sizeFromIndex = (index: number) => {
  const sizes = ["412 MB", "621 MB", "842 MB", "950 MB", "1.1 GB", "1.4 GB", "1.7 GB", "2.1 GB"];
  return sizes[index % sizes.length];
};

const gradientFromIndex = (index: number) => gradients[index % gradients.length];
const iconFromIndex = (index: number) => icons[index % icons.length];

export function mapVideoSummaryToLibraryVideo(video: ApiVideoSummary, index = 0): LibraryVideo {
  return {
    id: video.video_id,
    title: stripExtension(video.filename) || "Untitled video",
    filename: video.filename,
    duration: formatDuration(video.duration_seconds),
    size: sizeFromIndex(index),
    date: "Recent",
    updated: "Recently",
    status: statusToUi(video.status, video.progress),
    progress: video.progress,
    gradient: gradientFromIndex(index),
    icon: iconFromIndex(index),
    tags: [],
    pipelineVersion: "backend",
    lastQuestionDate: "Never",
    artifacts: { transcript: false, ocr: false, speakers: false, audio: false, chromadb: false }
  };
}

export function mapManifestToLibraryVideo(manifest: ApiManifest, index = 0): LibraryVideo {
  const indexed = Boolean(
    manifest.artifact_metadata?.hierarchy_index
    && manifest.artifact_metadata?.semantic_chunk_validation
  );
  const progress = indexed ? 100 : manifest.processing?.progress;
  const status = indexed
    ? "Indexed"
    : statusToUi(manifest.processing?.status || manifest.processing?.processing_status, progress);
  return {
    id: manifest.video_id,
    title: stripExtension(manifest.original_filename || manifest.source_filename || manifest.video_id) || manifest.video_id,
    filename: manifest.original_filename || manifest.source_filename || manifest.video_id,
    duration: formatDuration(manifest.duration_seconds),
    size: sizeFromIndex(index),
    date: safeDate(manifest.created_at),
    updated: safeDate(manifest.updated_at),
    status,
    progress,
    gradient: gradientFromIndex(index),
    icon: iconFromIndex(index),
    tags: [],
    pipelineVersion: manifest.pipeline_version || "backend",
    lastQuestionDate: "Never",
    artifacts: {
      transcript: Boolean(manifest.artifacts?.transcript_path || manifest.artifacts?.atoms_path),
      ocr: Boolean(manifest.artifacts?.ocr_path || manifest.artifacts?.visual_artifacts_path),
      speakers: Boolean(manifest.artifacts?.speakers_path),
      audio: Boolean(manifest.artifacts?.audio_path),
      chromadb: Boolean(manifest.artifacts?.semantic_chunks_path)
    }
  };
}

export function mapVideosToDashboardStats(videos: LibraryVideo[]): DashboardStat[] {
  const total = videos.length;
  const processed = videos.filter((video) => video.status === "Completed" || video.status === "Indexed").length;
  const jobs = videos.filter((video) => video.status === "Processing").length;
  const uploaded = videos.filter((video) => video.status === "Uploaded").length;

  return [
    {
      label: "Total videos",
      value: total,
      display: String(total),
      subtitle: "Across your workspace",
      trend: `${uploaded > 0 ? "+" : ""}${uploaded}`,
      trendText: "recent uploads",
      icon: Video,
      tone: "indigo"
    },
    {
      label: "Processed videos",
      value: processed,
      display: String(processed),
      subtitle: "Ready for questions",
      trend: `${processed > 0 ? "+" : ""}${processed}`,
      trendText: "indexed sources",
      icon: FileVideo,
      tone: "emerald"
    },
    {
      label: "Processing jobs",
      value: jobs,
      display: String(jobs).padStart(2, "0"),
      subtitle: "Active or queued",
      trend: `${jobs}`,
      trendText: "pipeline status",
      icon: Activity,
      tone: "amber"
    },
    {
      label: "AI questions asked",
      value: processed * 2,
      display: String(processed * 2),
      subtitle: "Grounded conversations",
      trend: "Live",
      trendText: "backend available",
      icon: BrainCircuit,
      tone: "violet"
    },
    {
      label: "Storage used",
      value: Math.max(12, total * 4),
      display: `${Math.max(12, total * 4)} GB`,
      subtitle: "Workspace capacity",
      trend: `${Math.min(100, total * 4)}%`,
      trendText: "estimated usage",
      icon: Database,
      tone: "cyan"
    }
  ];
}

export function mapVideosToRecentVideos(videos: LibraryVideo[]): RecentVideoSummary[] {
  return videos.slice(0, 4).map((video, index) => ({
    title: video.title,
    duration: video.duration,
    date: video.date,
    status: video.status === "Completed" || video.status === "Indexed" ? "Ready" : video.status,
    statusVariant:
      video.status === "Completed" || video.status === "Indexed"
        ? "success"
        : video.status === "Processing"
          ? "warning"
          : video.status === "Failed"
            ? "destructive"
            : "default",
    gradient: video.gradient || gradientFromIndex(index),
    icon: video.icon
  }));
}

export function mapVideosToProcessingJobs(videos: LibraryVideo[]): ProcessingJobSummary[] {
  return videos
    .filter((video) => video.status === "Processing" || video.status === "Uploaded")
    .slice(0, 3)
    .map((video, index) => ({
      title: video.title,
      stage: video.status === "Uploaded" ? "Queued for processing" : "Building semantic chunks",
      progress: video.progress ?? (video.status === "Uploaded" ? 6 : 40 + index * 18),
      progressClass: "",
      eta: video.status === "Uploaded" ? "Starts soon" : "About 4 minutes left",
      status: video.status === "Uploaded" ? "Queued" : "Active"
    }));
}

export function mapVideosToActivity(videos: LibraryVideo[]): ActivitySummary[] {
  const first = videos[0];
  return [
    {
      title: "Upload completed",
      detail: first ? first.title : "No videos yet",
      time: "Just now",
      icon: Video,
      tone: "indigo"
    },
    {
      title: "Processing started",
      detail: videos.find((video) => video.status === "Processing")?.title || "Waiting on backend jobs",
      time: "Recent",
      icon: Activity,
      tone: "amber"
    },
    {
      title: "Transcript generated",
      detail: "Derived from backend artifacts",
      time: "Recent",
      icon: FileText,
      tone: "emerald"
    },
    {
      title: "AI question answered",
      detail: "Backend ask endpoint available",
      time: "Recent",
      icon: BrainCircuit,
      tone: "violet"
    }
  ];
}

export function mapProcessingStatusToProgress(status?: ApiProcessingStatus) {
  const progress = typeof status?.progress === "number" ? status.progress : 0;
  return {
    progress,
    isComplete: status?.status === "completed" || progress >= 100,
    isFailed: status?.status === "failed",
    label: status?.phase || status?.status || "processing"
  };
}

export function createFallbackTimeline() {
  return {
    chapters: [
      { id: "ch1", title: "1. Ingestion & Limits", startSec: 0, endSec: 312, gradient: "from-indigo-600 to-cyan-500" },
      { id: "ch2", title: "2. Processing", startSec: 312, endSec: 945, gradient: "from-violet-600 to-indigo-600" },
      { id: "ch3", title: "3. Retrieval", startSec: 945, endSec: 1950, gradient: "from-cyan-600 to-blue-600" },
      { id: "ch4", title: "4. Evidence Review", startSec: 1950, endSec: 2538, gradient: "from-amber-600 to-rose-600" }
    ],
    tracks: [
      {
        id: "scenes",
        label: "Scenes",
        iconName: "Video",
        color: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10",
        badge: "API",
        visible: true,
        expanded: true,
        markers: []
      },
      {
        id: "transcript",
        label: "Transcript Spans",
        iconName: "FileText",
        color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
        badge: "API",
        visible: true,
        expanded: true,
        markers: []
      }
    ]
  };
}

export function createFallbackEvidence() {
  return {
    nodes: [] as GraphNode[],
    edges: [] as GraphEdge[],
    items: [] as EvidenceItem[]
  };
}

export function createFallbackTranscript(): TranscriptBlock[] {
  return [];
}
