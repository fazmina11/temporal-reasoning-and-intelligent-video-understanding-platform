import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { getVideoStatus } from "@/services/api";
import {
  WorkspaceLayout,
  WorkspaceToolbar,
  TabNavigation,
  PanelPlaceholder,
  type WorkspaceTab
} from "@/features/workspace/workspace-components";
import { libraryVideos as initialLibraryVideos, type LibraryVideo } from "@/features/library/mock-data";

export function WorkspacePage() {
  const { videoId } = useParams<{ videoId: string }>();
  const containerRef = useRef<HTMLDivElement>(null);

  // Video State
  const [video, setVideo] = useState<LibraryVideo | null>(null);
  
  // Workspace UI States
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("timeline");
  const [searchQuery, setSearchQuery] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Load video metadata from local registry and backend status
  useEffect(() => {
    const fetchMetadata = async () => {
      const saved = localStorage.getItem("video-library-data");
      const library: LibraryVideo[] = saved ? JSON.parse(saved) : initialLibraryVideos;
      const targetId = videoId || library[0]?.id || "mcp-vs-http";
      
      const match = library.find((v) => v.id === targetId);
      if (match) setVideo(match);

      try {
        const backendStatus = await getVideoStatus(targetId);
        if (backendStatus) {
          setVideo({
            id: targetId,
            title: backendStatus.filename ? backendStatus.filename.replace(/\.[^/.]+$/, "") : (match?.title || "Video Asset"),
            filename: backendStatus.filename || match?.filename || "video.mp4",
            duration: backendStatus.duration_seconds ? `${Math.floor(backendStatus.duration_seconds / 60)}:${Math.floor(backendStatus.duration_seconds % 60).toString().padStart(2, '0')}` : (match?.duration || "05:12"),
            size: match?.size || "450 MB",
            date: match?.date || "Recent",
            updated: "Just now",
            status: backendStatus.progress >= 100 || backendStatus.status === "completed" ? "Ready" : "Processing",
            progress: backendStatus.progress || 100,
            gradient: match?.gradient || "from-indigo-950 via-slate-900 to-cyan-900",
            icon: match?.icon || initialLibraryVideos[0].icon,
            tags: match?.tags || ["video"],
            pipelineVersion: backendStatus.pipeline_version || "v1.4.2",
            lastQuestionDate: "Just now",
            artifacts: { transcript: true, ocr: true, speakers: true, audio: true, chromadb: true }
          });
        }
      } catch (e) {
        // Fallback to local match if backend request errors
      }
    };

    fetchMetadata();
  }, [videoId]);

  // Fullscreen toggle handler
  const handleToggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen().then(() => {
        setIsFullscreen(true);
      }).catch(() => {
        setIsFullscreen(true); // Fallback state
      });
    } else {
      document.exitFullscreen().then(() => {
        setIsFullscreen(false);
      }).catch(() => {
        setIsFullscreen(false);
      });
    }
  };

  // Fullscreen change listener
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  // Export action
  const handleExport = () => {
    toast.success(`Exporting analysis workspace for "${video?.title || "Video"}"...`);
  };

  // Settings action
  const handleOpenSettings = () => {
    toast.info("Workspace settings options: Adjust player speed, hotkeys, and RAG thresholds.");
  };

  return (
    <div ref={containerRef} className="mx-auto max-w-[1700px] h-full animate-fade-in">
      <WorkspaceLayout
        toolbar={
          <WorkspaceToolbar
            title={video ? video.title : "MCP vs HTTP — technical deep dive"}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            isFullscreen={isFullscreen}
            onToggleFullscreen={handleToggleFullscreen}
            onExport={handleExport}
            onOpenSettings={handleOpenSettings}
          />
        }
        leftTop={
          /* Video Player Area Placeholder */
          <PanelPlaceholder type="video" />
        }
        leftBottom={
          /* Bottom Left Tabbed Panel Placeholder (Timeline / Transcript / OCR / Scenes) */
          <div className="flex h-full flex-col overflow-hidden bg-card">
            <TabNavigation activeTab={activeTab} onTabChange={setActiveTab} />
            <div className="flex-1 overflow-hidden">
              <PanelPlaceholder type="tabs" activeTab={activeTab} />
            </div>
          </div>
        }
        rightTop={
          /* Right Upper: AI Chat Panel */
          <PanelPlaceholder type="chat" videoId={video?.id || videoId} />
        }
        rightBottom={
          /* Right Lower: Evidence Inspector Placeholder */
          <PanelPlaceholder type="evidence" />
        }
      />
    </div>
  );
}
