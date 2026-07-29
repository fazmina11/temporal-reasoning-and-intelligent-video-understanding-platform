import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { buildWorkspaceViewModel } from "@/api/artifact-adapters";
import { ChatWindow } from "@/features/chat/chat-components";
import { EvidenceInspector } from "@/features/evidence/evidence-components";
import { OcrExplorer } from "@/features/evidence/ocr-explorer";
import { Timeline } from "@/features/timeline/timeline-components";
import { TranscriptExplorer } from "@/features/transcript/transcript-components";
import { useVideos } from "@/hooks/api/use-videos";
import { useWorkspace } from "@/hooks/api/use-workspace";
import {
  WorkspaceLayout,
  WorkspaceToolbar,
  TabNavigation,
  type WorkspaceTab
} from "@/features/workspace/workspace-components";
import { VideoPlayer } from "@/features/workspace/video-player";

export function WorkspacePage() {
  const { videoId: routeVideoId } = useParams<{ videoId: string }>();
  const [searchParams] = useSearchParams();
  const containerRef = useRef<HTMLDivElement>(null);
  const initialSeekApplied = useRef(false);
  const { data: videosResponse } = useVideos();
  const videoId = routeVideoId || videosResponse?.videos[0]?.id;
  const { data: artifacts, isLoading, error } = useWorkspace(videoId);
  const viewModel = useMemo(
    () => artifacts ? buildWorkspaceViewModel(artifacts) : null,
    [artifacts]
  );

  const [activeTab, setActiveTab] = useState<WorkspaceTab>("timeline");
  const [searchQuery, setSearchQuery] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [playheadSec, setPlayheadSec] = useState(0);
  const [seekRequestSec, setSeekRequestSec] = useState<number | null>(null);

  const handleSeek = useCallback((seconds: number) => {
    const bounded = Math.max(0, Math.min(seconds, viewModel?.durationSec || seconds));
    setSeekRequestSec(bounded);
    setPlayheadSec(bounded);
  }, [viewModel?.durationSec]);

  const handleTimeUpdate = useCallback((seconds: number) => {
    setPlayheadSec(seconds);
  }, []);

  useEffect(() => {
    if (initialSeekApplied.current || !viewModel) return;
    const requested = Number(searchParams.get("t"));
    if (Number.isFinite(requested) && requested >= 0) {
      handleSeek(requested);
    }
    initialSeekApplied.current = true;
  }, [handleSeek, searchParams, viewModel]);

  const handleToggleFullscreen = async () => {
    try {
      if (!document.fullscreenElement) {
        await containerRef.current?.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
      setIsFullscreen(Boolean(document.fullscreenElement));
    } catch {
      toast.error("Fullscreen mode is not available in this browser.");
    }
  };

  const title = artifacts?.manifest.original_filename
    || artifacts?.manifest.source_filename
    || videosResponse?.videos.find((video) => video.id === videoId)?.title
    || "Video workspace";

  if (!videoId) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-center">
        <div>
          <p className="text-sm font-semibold">No processed video is available.</p>
          <p className="mt-1 text-xs text-muted-foreground">Upload a video to open the evidence workspace.</p>
        </div>
      </div>
    );
  }

  if (isLoading || !viewModel || !artifacts) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-sm text-muted-foreground">
        {error ? "The backend artifacts could not be loaded." : "Loading canonical video evidence..."}
      </div>
    );
  }

  const tabContent = activeTab === "timeline"
    ? (
      <Timeline
        tracks={viewModel.tracks}
        chapters={viewModel.chapters}
        durationSec={viewModel.durationSec}
        playheadSec={playheadSec}
        onSeekToTimestamp={handleSeek}
      />
    )
    : activeTab === "transcript"
      ? <TranscriptExplorer blocks={viewModel.transcriptBlocks} onSeekToTimestamp={handleSeek} />
      : activeTab === "ocr"
        ? <OcrExplorer records={viewModel.ocrEvidence} onSeekToTimestamp={handleSeek} />
        : (
          <Timeline
            tracks={viewModel.tracks.filter((track) => track.id === "events" || track.id === "topics")}
            chapters={viewModel.chapters}
            durationSec={viewModel.durationSec}
            playheadSec={playheadSec}
            onSeekToTimestamp={handleSeek}
          />
        );

  return (
    <div ref={containerRef} className="mx-auto h-full max-w-[1700px] animate-fade-in">
      <WorkspaceLayout
        toolbar={
          <WorkspaceToolbar
            title={title}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            isFullscreen={isFullscreen}
            onToggleFullscreen={handleToggleFullscreen}
            onExport={() => toast.info("Workspace export will use the backend report endpoint in a later phase.")}
            onOpenSettings={() => toast.info("Workspace preferences are not configured yet.")}
          />
        }
        leftTop={
          <VideoPlayer
            videoId={videoId}
            title={title}
            seekRequestSec={seekRequestSec}
            onTimeUpdate={handleTimeUpdate}
          />
        }
        leftBottom={
          <div className="flex h-full flex-col overflow-hidden bg-card">
            <TabNavigation activeTab={activeTab} onTabChange={setActiveTab} />
            <div className="flex-1 overflow-hidden">{tabContent}</div>
          </div>
        }
        rightTop={
          <ChatWindow videoId={videoId} onJumpToVideo={handleSeek} />
        }
        rightBottom={
          <EvidenceInspector
            items={viewModel.evidenceItems}
            nodes={viewModel.graphNodes}
            edges={viewModel.graphEdges}
            durationSec={viewModel.durationSec}
            onSeekToTimestamp={handleSeek}
          />
        }
      />
    </div>
  );
}
