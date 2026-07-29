import type {
  ApiManifest,
  EvidenceItem,
  GraphEdge,
  GraphNode,
  OcrEvidenceView,
  OverviewChapter,
  TimelineMarkerData,
  TimelineTrackData,
  TranscriptBlock,
  VideoDetailScene,
  WorkspaceViewModel
} from "@/types/api";

type JsonRecord = Record<string, unknown>;

export interface WorkspaceArtifactBundle {
  manifest: ApiManifest;
  transcript: unknown;
  timeline: unknown;
  ocr: unknown;
  scenes: unknown;
  boundaries: unknown;
  frames: unknown;
  chunkValidation: unknown;
  visualArtifacts: unknown;
  speakers: unknown;
  audioEvents: unknown;
}

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://localhost:8001").replace(/\/+$/, "");
const timelineColors = {
  scenes: "bg-indigo-500",
  transcript: "bg-emerald-500",
  ocr: "bg-cyan-500",
  speakers: "bg-violet-500",
  audio: "bg-amber-500",
  topics: "bg-blue-500",
  events: "bg-rose-500"
} as const;
const gradients = [
  "from-indigo-600 to-cyan-500",
  "from-violet-600 to-indigo-600",
  "from-cyan-600 to-blue-600",
  "from-amber-600 to-rose-600",
  "from-emerald-600 to-cyan-600"
];
const frameGradients = [
  "from-indigo-950 via-slate-900 to-cyan-900",
  "from-slate-900 via-violet-950 to-indigo-900",
  "from-cyan-950 via-slate-900 to-indigo-950",
  "from-amber-950 via-slate-900 to-rose-950"
];

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function records(value: unknown, key?: string): JsonRecord[] {
  const source = key ? record(value)[key] : value;
  return Array.isArray(source) ? source.map(record) : [];
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function milliseconds(row: JsonRecord, prefix: "start" | "end"): number {
  const ms = numberValue(row[`${prefix}_ms`], Number.NaN);
  if (Number.isFinite(ms)) return Math.max(0, ms);
  return Math.max(0, numberValue(row[prefix], 0) * 1000);
}

function seconds(row: JsonRecord, prefix: "start" | "end"): number {
  return milliseconds(row, prefix) / 1000;
}

export function formatTimestamp(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${minutes}:${String(secs).padStart(2, "0")}`;
}

function rangeLabel(startSec: number, endSec: number): string {
  return `${formatTimestamp(startSec)} - ${formatTimestamp(endSec)}`;
}

function assetUrl(value: unknown): string | undefined {
  const source = text(value).replace(/\\/g, "/");
  if (!source) return undefined;
  if (/^https?:\/\//i.test(source)) return source;
  const normalized = source.startsWith("/") ? source : `/${source}`;
  return `${API_BASE_URL}${normalized}`;
}

function confidenceFromTranscript(row: JsonRecord): number {
  const words = records(row.words);
  if (words.length) {
    const total = words.reduce((sum, word) => sum + numberValue(word.prob, 0), 0);
    return Math.round((total / words.length) * 100);
  }
  const direct = numberValue(row.asr_confidence ?? row.confidence, Number.NaN);
  if (Number.isFinite(direct)) return Math.round((direct <= 1 ? direct * 100 : direct));
  const avgLogProbability = numberValue(row.avg_logprob, Number.NaN);
  return Number.isFinite(avgLogProbability)
    ? Math.round(Math.min(1, Math.exp(avgLogProbability)) * 100)
    : 0;
}

function overlap(startSec: number, endSec: number, row: JsonRecord): boolean {
  return seconds(row, "start") < endSec && seconds(row, "end") > startSec;
}

function makeMarker(
  row: JsonRecord,
  trackId: TimelineMarkerData["trackId"],
  index: number,
  options: {
    idKeys: string[];
    titleKeys: string[];
    summaryKeys: string[];
    speaker?: string;
    ocrText?: string;
  }
): TimelineMarkerData {
  const startSec = seconds(row, "start");
  const rawEndSec = seconds(row, "end");
  const endSec = Math.max(startSec + 0.25, rawEndSec);
  const id = options.idKeys.map((key) => text(row[key])).find(Boolean) || `${trackId}_${index + 1}`;
  const title = options.titleKeys.map((key) => text(row[key])).find(Boolean) || `${trackId} evidence`;
  const summary = options.summaryKeys.map((key) => text(row[key])).find(Boolean) || title;
  return {
    id,
    trackId,
    startSec,
    endSec,
    timeLabel: rangeLabel(startSec, endSec),
    title,
    summary,
    transcriptQuote: text(row.transcript_text ?? row.text) || undefined,
    ocrText: options.ocrText,
    color: timelineColors[trackId as keyof typeof timelineColors] || "bg-slate-500",
    gradient: frameGradients[index % frameGradients.length],
    speaker: options.speaker
  };
}

function buildOcrEvidence(ocrDocument: unknown): OcrEvidenceView[] {
  const source = records(ocrDocument, "tracks").length
    ? records(ocrDocument, "tracks")
    : records(ocrDocument, "records");

  return source
    .map((row, index) => {
      const references = records(row.frame_references);
      const reference = references[0] || row;
      const startSec = seconds(row, "start");
      const endSec = Math.max(startSec + 0.001, seconds(row, "end"));
      return {
        id: text(row.ocr_track_id ?? row.ocr_id, `ocr_${index + 1}`),
        text: text(row.text).trim(),
        startSec,
        endSec,
        timestamp: rangeLabel(startSec, endSec),
        confidence: numberValue(row.mean_confidence ?? row.confidence, 0),
        qualityScore: numberValue(row.quality_score, 0),
        frameId: text(reference.frame_id) || undefined,
        frameUri: assetUrl(reference.frame_uri ?? reference.frame_path_relative),
        parentChunkId: text(row.parent_chunk_id) || undefined,
        parentEventId: text(row.parent_event_id) || undefined
      };
    })
    .filter((item) => item.text.length >= 2 && item.qualityScore >= 0.45)
    .sort((left, right) => right.qualityScore - left.qualityScore);
}

function buildTranscriptBlocks(
  transcriptDocument: unknown,
  chunks: JsonRecord[],
  ocrEvidence: OcrEvidenceView[],
  speakerTurns: JsonRecord[]
): TranscriptBlock[] {
  const source = Array.isArray(transcriptDocument)
    ? records(transcriptDocument)
    : records(transcriptDocument, "atoms").length
      ? records(transcriptDocument, "atoms")
      : records(transcriptDocument, "items");

  return source.map((row, index) => {
    const startSec = seconds(row, "start");
    const endSec = Math.max(startSec + 0.001, seconds(row, "end"));
    const chunk = chunks.find((candidate) => overlap(startSec, endSec, candidate));
    const speakerTurn = speakerTurns.find((candidate) => overlap(startSec, endSec, candidate));
    const nearbyOcr = ocrEvidence.find(
      (candidate) => candidate.startSec < endSec && candidate.endSec > startSec
    );
    const speakerId = text(row.speaker_id ?? speakerTurn?.speaker_id, "speaker_unknown");
    return {
      id: text(row.atom_id ?? row.segment_id ?? row.id, `transcript_${index + 1}`),
      startSec,
      endSec,
      timestamp: rangeLabel(startSec, endSec),
      speakerId,
      speakerName: speakerId === "speaker_unknown" ? "Speaker" : speakerId.replace(/_/g, " "),
      speakerAvatar: speakerId === "speaker_unknown" ? "S" : speakerId.replace(/\D/g, "").slice(-2) || "S",
      speakerTone: ["indigo", "violet", "cyan", "emerald"][index % 4] as TranscriptBlock["speakerTone"],
      text: text(row.transcript_text ?? row.text).trim(),
      confidence: confidenceFromTranscript(row),
      language: "Detected speech",
      hasOcr: Boolean(nearbyOcr),
      ocrPreview: nearbyOcr?.text,
      hasVisualObject: Boolean(chunk),
      sceneTitle: text(chunk?.title) || undefined,
      sceneGradient: frameGradients[index % frameGradients.length],
      citationCount: 0,
      importanceScore: numberValue(chunk?.asr_confidence, confidenceFromTranscript(row) / 100),
      topicCluster: text(chunk?.title, "Unclustered evidence")
    };
  }).filter((item) => item.text.length > 0);
}

function buildTimelineTracks(
  events: JsonRecord[],
  chunks: JsonRecord[],
  transcriptBlocks: TranscriptBlock[],
  ocrEvidence: OcrEvidenceView[],
  speakerTurns: JsonRecord[],
  audioEvents: JsonRecord[]
): TimelineTrackData[] {
  const track = (
    id: TimelineTrackData["id"],
    label: string,
    iconName: string,
    markers: TimelineMarkerData[],
    color: string
  ): TimelineTrackData => ({
    id,
    label,
    iconName,
    color,
    badge: `${markers.length}`,
    visible: true,
    expanded: id === "events" || id === "topics" || id === "transcript",
    markers
  });

  const eventMarkers = events.map((row, index) => makeMarker(row, "events", index, {
    idKeys: ["event_id", "id"],
    titleKeys: ["title"],
    summaryKeys: ["summary_text", "transcript_text"]
  }));
  const topicMarkers = chunks.map((row, index) => makeMarker(row, "topics", index, {
    idKeys: ["chunk_id", "id"],
    titleKeys: ["title"],
    summaryKeys: ["summary_text", "transcript_text"]
  }));
  const transcriptMarkers = transcriptBlocks.map((block) => ({
    id: block.id,
    trackId: "transcript" as const,
    startSec: block.startSec,
    endSec: block.endSec,
    timeLabel: block.timestamp,
    title: block.speakerName,
    summary: block.text,
    transcriptQuote: block.text,
    color: timelineColors.transcript,
    speaker: block.speakerName
  }));
  const ocrMarkers = ocrEvidence.slice(0, 200).map((item) => ({
    id: item.id,
    trackId: "ocr" as const,
    startSec: item.startSec,
    endSec: Math.max(item.endSec, item.startSec + 0.25),
    timeLabel: item.timestamp,
    title: item.text,
    summary: `Visible text from ${item.frameId || "a timeline frame"}`,
    ocrText: item.text,
    color: timelineColors.ocr
  }));
  const speakerMarkers = speakerTurns.map((row, index) => makeMarker(row, "speakers", index, {
    idKeys: ["turn_id"],
    titleKeys: ["speaker_id"],
    summaryKeys: ["text"],
    speaker: text(row.speaker_id, "Speaker")
  }));
  const audioMarkers = audioEvents.map((row, index) => makeMarker(row, "audio", index, {
    idKeys: ["audio_event_id"],
    titleKeys: ["label", "event_type"],
    summaryKeys: ["label", "event_type"]
  }));

  return [
    track("events", "Explanation Events", "Sparkles", eventMarkers, "text-rose-400 border-rose-500/30 bg-rose-500/10"),
    track("topics", "Semantic Topics", "Layers", topicMarkers, "text-blue-400 border-blue-500/30 bg-blue-500/10"),
    track("transcript", "Transcript Spans", "FileText", transcriptMarkers, "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"),
    track("ocr", "OCR Text", "Database", ocrMarkers, "text-cyan-400 border-cyan-500/30 bg-cyan-500/10"),
    track("speakers", "Speaker Turns", "Mic", speakerMarkers, "text-violet-400 border-violet-500/30 bg-violet-500/10"),
    track("audio", "Audio Events", "Volume2", audioMarkers, "text-amber-400 border-amber-500/30 bg-amber-500/10")
  ].filter((item) => item.markers.length > 0);
}

function buildEvidence(
  videoId: string,
  chunks: JsonRecord[],
  ocrEvidence: OcrEvidenceView[]
): { items: EvidenceItem[]; nodes: GraphNode[]; edges: GraphEdge[] } {
  const chunkItems: EvidenceItem[] = chunks.slice(0, 12).map((row, index) => {
    const startSec = seconds(row, "start");
    const endSec = seconds(row, "end");
    const confidence = numberValue(row.asr_confidence, 0);
    return {
      id: text(row.chunk_id, `chunk_${index + 1}`),
      sourceId: text(row.chunk_id) || undefined,
      nodeId: `node_chunk_${index + 1}`,
      timestamp: rangeLabel(startSec, endSec),
      startSec,
      endSec,
      sourceType: "transcript",
      title: text(row.title, "Semantic topic"),
      rank: index + 1,
      confidence: Math.round(confidence * 100),
      quality: confidence >= 0.9 ? "verified" : "partial",
      transcriptQuote: text(row.transcript_text),
      sceneDescription: text(row.summary_text),
      explanation: "Canonical semantic chunk linked to the source timeline and parent event.",
      frameGradient: frameGradients[index % frameGradients.length],
      parentEventId: text(row.parent_event_id) || undefined
    };
  });
  const ocrItems: EvidenceItem[] = ocrEvidence.slice(0, 6).map((item, index) => ({
    id: item.id,
    sourceId: item.id,
    nodeId: `node_ocr_${index + 1}`,
    timestamp: item.timestamp,
    startSec: item.startSec,
    endSec: item.endSec,
    sourceType: "ocr",
    title: item.text,
    rank: chunkItems.length + index + 1,
    confidence: Math.round(item.qualityScore * 100),
    quality: item.qualityScore >= 0.7 ? "verified" : "partial",
    ocrText: item.text,
    explanation: `OCR evidence extracted from ${item.frameId || "a representative frame"}.`,
    frameGradient: frameGradients[index % frameGradients.length],
    frameUri: item.frameUri,
    parentEventId: item.parentEventId
  }));
  const items = [...chunkItems, ...ocrItems];
  const rootNode: GraphNode = {
    id: "video_root",
    label: videoId,
    type: "video",
    x: 50,
    y: 12,
    iconName: "Video",
    color: "text-indigo-300 border-indigo-500/40 bg-indigo-500/20",
    details: "Processed video evidence hierarchy"
  };
  const nodes = [
    rootNode,
    ...items.map((item, index): GraphNode => ({
      id: item.nodeId,
      label: item.title.slice(0, 48),
      type: item.sourceType === "ocr" ? "ocr" : "topic",
      x: 12 + (index % 4) * 25,
      y: 34 + Math.floor(index / 4) * 18,
      iconName: item.sourceType === "ocr" ? "Database" : "Layers",
      color: item.sourceType === "ocr"
        ? "text-cyan-300 border-cyan-500/40 bg-cyan-500/20"
        : "text-emerald-300 border-emerald-500/40 bg-emerald-500/20",
      details: item.explanation
    }))
  ];
  const edges = items.map((item, index): GraphEdge => ({
    id: `edge_${index + 1}`,
    sourceId: "video_root",
    targetId: item.nodeId,
    label: "contains"
  }));
  return { items, nodes, edges };
}

function buildDetails(
  manifest: ApiManifest,
  events: JsonRecord[],
  chunks: JsonRecord[],
  transcriptBlocks: TranscriptBlock[],
  ocrEvidence: OcrEvidenceView[],
  ocrDocument: unknown,
  framesDocument: unknown,
  speakersDocument: unknown,
  audioDocument: unknown,
  validationDocument: unknown
): WorkspaceViewModel["details"] {
  const uniqueTexts = [...new Set(ocrEvidence.map((item) => item.text))]
    .filter((value) => value.length >= 3)
    .slice(0, 12);
  const topics = [...new Set(chunks.map((row) => text(row.title)).filter(Boolean))].slice(0, 10);
  const scenes: VideoDetailScene[] = events.map((row, index) => {
    const startSec = seconds(row, "start");
    const endSec = seconds(row, "end");
    return {
      id: text(row.event_id, `event_${index + 1}`),
      index: index + 1,
      timeStart: formatTimestamp(startSec),
      timeEnd: formatTimestamp(endSec),
      title: text(row.title, `Event ${index + 1}`),
      description: text(row.summary_text ?? row.transcript_text),
      gradient: frameGradients[index % frameGradients.length],
      startSec
    };
  });
  const summaryParts = events
    .slice(0, 3)
    .map((row) => text(row.summary_text))
    .filter(Boolean);
  return {
    summary: summaryParts.join(" ") || `Processed evidence for ${manifest.original_filename || manifest.source_filename || manifest.video_id}.`,
    topics,
    visibleTexts: uniqueTexts,
    stats: {
      events: events.length,
      frames: numberValue(record(framesDocument).extracted_frame_count, records(framesDocument, "frames").length),
      ocrRecords: records(ocrDocument, "records").length || ocrEvidence.length,
      transcriptSpans: transcriptBlocks.length,
      speakers: records(speakersDocument, "speakers").length,
      audioEvents: records(audioDocument, "events").length,
      semanticChunks: chunks.length
    },
    scenes,
    validationPassed: typeof record(validationDocument).validation_passed === "boolean"
      ? record(validationDocument).validation_passed as boolean
      : null
  };
}

export function buildWorkspaceViewModel(bundle: WorkspaceArtifactBundle): WorkspaceViewModel {
  const events = records(bundle.timeline, "events");
  const chunks = records(bundle.scenes, "chunks");
  const speakerTurns = records(bundle.speakers, "turns");
  const audioEvents = records(bundle.audioEvents, "events");
  const ocrEvidence = buildOcrEvidence(bundle.ocr);
  const transcriptBlocks = buildTranscriptBlocks(
    bundle.transcript,
    chunks,
    ocrEvidence,
    speakerTurns
  );
  const durationSec = Math.max(
    0,
    numberValue(bundle.manifest.duration_ms, 0) / 1000,
    numberValue(bundle.manifest.duration_seconds, 0)
  );
  const chapters: OverviewChapter[] = events.map((row, index) => ({
    id: text(row.event_id, `chapter_${index + 1}`),
    title: text(row.title, `Event ${index + 1}`),
    startSec: seconds(row, "start"),
    endSec: seconds(row, "end"),
    gradient: gradients[index % gradients.length]
  }));
  const evidence = buildEvidence(bundle.manifest.video_id, chunks, ocrEvidence);

  return {
    durationSec,
    chapters,
    tracks: buildTimelineTracks(
      events,
      chunks,
      transcriptBlocks,
      ocrEvidence,
      speakerTurns,
      audioEvents
    ),
    transcriptBlocks,
    ocrEvidence,
    evidenceItems: evidence.items,
    graphNodes: evidence.nodes,
    graphEdges: evidence.edges,
    details: buildDetails(
      bundle.manifest,
      events,
      chunks,
      transcriptBlocks,
      ocrEvidence,
      bundle.ocr,
      bundle.frames,
      bundle.speakers,
      bundle.audioEvents,
      bundle.chunkValidation
    )
  };
}
