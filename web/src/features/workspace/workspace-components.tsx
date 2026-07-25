import { useState, useRef, useEffect, type ReactNode, type ComponentType } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Maximize2,
  Minimize2,
  Download,
  Settings,
  Play,
  Clock,
  FileText,
  Layers,
  Video,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  GripVertical,
  GripHorizontal,
  ChevronRight,
  Send,
  HelpCircle,
  Database,
  ExternalLink
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { ChatWindow } from "@/features/chat/chat-components";
import { Timeline } from "@/features/timeline/timeline-components";
import { TranscriptExplorer } from "@/features/transcript/transcript-components";
import { EvidenceInspector } from "@/features/evidence/evidence-components";

// ----------------------------------------------------
// 1. Resizable SplitPanel Component
// ----------------------------------------------------
interface SplitPanelProps {
  direction?: "horizontal" | "vertical";
  initialSplit?: number; // 0 to 100 percentage
  minSize?: number;
  maxSize?: number;
  panel1: ReactNode;
  panel2: ReactNode;
  className?: string;
}

export function SplitPanel({
  direction = "horizontal",
  initialSplit = 50,
  minSize = 15,
  maxSize = 85,
  panel1,
  panel2,
  className
}: SplitPanelProps) {
  const [split, setSplit] = useState(initialSplit);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();

      let newPercentage = 50;
      if (direction === "horizontal") {
        const offset = e.clientX - rect.left;
        newPercentage = (offset / rect.width) * 100;
      } else {
        const offset = e.clientY - rect.top;
        newPercentage = (offset / rect.height) * 100;
      }

      const clamped = Math.max(minSize, Math.min(maxSize, newPercentage));
      setSplit(clamped);
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!containerRef.current || !e.touches[0]) return;
      const rect = containerRef.current.getBoundingClientRect();
      const touch = e.touches[0];

      let newPercentage = 50;
      if (direction === "horizontal") {
        const offset = touch.clientX - rect.left;
        newPercentage = (offset / rect.width) * 100;
      } else {
        const offset = touch.clientY - rect.top;
        newPercentage = (offset / rect.height) * 100;
      }

      const clamped = Math.max(minSize, Math.min(maxSize, newPercentage));
      setSplit(clamped);
    };

    const handleMouseUp = () => setIsDragging(false);

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("touchmove", handleTouchMove);
    document.addEventListener("touchend", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleMouseUp);
    };
  }, [isDragging, direction, minSize, maxSize]);

  const handleDoubleClick = () => {
    setSplit(initialSplit);
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative flex h-full w-full overflow-hidden select-none",
        direction === "horizontal" ? "flex-row" : "flex-col",
        className
      )}
    >
      {/* Panel 1 */}
      <div
        style={{
          [direction === "horizontal" ? "width" : "height"]: `${split}%`
        }}
        className="relative h-full overflow-hidden shrink-0 transition-all duration-75"
      >
        {panel1}
      </div>

      {/* Resizable Divider Handle */}
      <div
        onMouseDown={() => setIsDragging(true)}
        onTouchStart={() => setIsDragging(true)}
        onDoubleClick={handleDoubleClick}
        title="Drag to resize panel (Double-click to reset)"
        className={cn(
          "group relative z-30 flex shrink-0 items-center justify-center transition-colors hover:bg-primary/40 active:bg-primary",
          direction === "horizontal"
            ? "w-2.5 cursor-col-resize border-x border-border/40 bg-slate-100 dark:bg-slate-900"
            : "h-2.5 cursor-row-resize border-y border-border/40 bg-slate-100 dark:bg-slate-900",
          isDragging ? "bg-primary text-white" : ""
        )}
      >
        <div
          className={cn(
            "rounded bg-border transition-colors group-hover:bg-primary",
            direction === "horizontal" ? "h-6 w-1" : "h-1 w-6",
            isDragging ? "bg-primary" : ""
          )}
        />
      </div>

      {/* Panel 2 */}
      <div
        style={{
          [direction === "horizontal" ? "width" : "height"]: `${100 - split}%`
        }}
        className="relative h-full flex-1 overflow-hidden transition-all duration-75"
      >
        {panel2}
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 2. WorkspaceToolbar Component
// ----------------------------------------------------
interface WorkspaceToolbarProps {
  title: string;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onExport: () => void;
  onOpenSettings: () => void;
}

export function WorkspaceToolbar({
  title,
  searchQuery,
  onSearchChange,
  isFullscreen,
  onToggleFullscreen,
  onExport,
  onOpenSettings
}: WorkspaceToolbarProps) {
  return (
    <div className="flex h-13 items-center justify-between gap-4 border-b border-border/80 bg-card px-4 py-2 shrink-0 shadow-xs">
      {/* Title section */}
      <div className="flex items-center gap-2.5 min-w-0">
        <Badge variant="outline" className="h-6 px-2 text-[10px] font-bold bg-primary/10 text-primary border-primary/20 shrink-0">
          WORKSPACE
        </Badge>
        <h1 className="text-sm font-bold truncate text-foreground" title={title}>
          {title}
        </h1>
      </div>

      {/* Search & Actions */}
      <div className="flex items-center gap-2">
        {/* Search */}
        <div className="relative w-44 sm:w-64">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search timeline & transcript..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-8 h-8 text-xs bg-background/60 border-border/70 focus-ring"
          />
        </div>

        {/* Export Button */}
        <Button
          variant="outline"
          size="sm"
          onClick={onExport}
          className="h-8 gap-1 px-2.5 text-xs font-semibold hover:border-border"
          title="Export workspace analysis"
        >
          <Download className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="hidden md:inline">Export</span>
        </Button>

        {/* Fullscreen Button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleFullscreen}
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </Button>

        {/* Settings Button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onOpenSettings}
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          title="Workspace Settings"
        >
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 3. TabNavigation Component
// ----------------------------------------------------
export type WorkspaceTab = "timeline" | "transcript" | "ocr" | "scenes";

interface TabNavigationProps {
  activeTab: WorkspaceTab;
  onTabChange: (tab: WorkspaceTab) => void;
}

export function TabNavigation({ activeTab, onTabChange }: TabNavigationProps) {
  const tabs: { id: WorkspaceTab; label: string; icon: ComponentType<any> }[] = [
    { id: "timeline", label: "Timeline", icon: Clock },
    { id: "transcript", label: "Transcript", icon: FileText },
    { id: "ocr", label: "OCR Text", icon: Layers },
    { id: "scenes", label: "Scenes", icon: Video }
  ];

  return (
    <div className="flex items-center gap-1 border-b border-border/80 bg-slate-50/60 dark:bg-slate-900/40 px-3 py-1.5 shrink-0 overflow-x-auto">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;

        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-normal",
              isActive ? "text-primary font-bold" : "text-muted-foreground hover:text-foreground"
            )}
          >
            {isActive && (
              <motion.div
                layoutId="active-tab-pill"
                className="absolute inset-0 rounded-md bg-card shadow-xs border border-border/60"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-1.5">
              <Icon className={cn("h-3.5 w-3.5", isActive ? "text-primary" : "text-muted-foreground")} />
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ----------------------------------------------------
// 4. PanelPlaceholder Component
// ----------------------------------------------------
interface PanelPlaceholderProps {
  type: "video" | "tabs" | "chat" | "evidence";
  activeTab?: WorkspaceTab;
  videoId?: string;
}

export function PanelPlaceholder({ type, activeTab = "timeline", videoId }: PanelPlaceholderProps) {
  if (type === "video") {
    return (
      <div className="relative flex h-full w-full flex-col justify-between overflow-hidden bg-slate-950 p-4 text-white">
        {/* Top Overlay Badge */}
        <div className="flex items-center justify-between z-10">
          <Badge variant="outline" className="bg-slate-900/80 border-slate-700 text-white gap-1.5 text-[10px]">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            1080p · H.264
          </Badge>
          <span className="rounded bg-black/60 px-2 py-0.5 font-mono text-[10px]">00:00 / 42:18</span>
        </div>

        {/* Center Video Frame Graphics */}
        <div className="flex flex-col items-center justify-center my-auto space-y-3 z-10">
          <div className="group relative flex h-16 w-16 cursor-pointer items-center justify-center rounded-full bg-white/10 backdrop-blur border border-white/20 transition hover:scale-110 hover:bg-white/20">
            <Play className="h-7 w-7 text-white fill-current ml-1" />
          </div>
          <div className="text-center space-y-1">
            <p className="text-xs font-bold text-slate-200">Video Player Area Placeholder</p>
            <p className="text-[10px] text-slate-400">Interactive video controls will be mounted in Phase 10</p>
          </div>
        </div>

        {/* Bottom Mock Scrubber */}
        <div className="space-y-1 z-10">
          <div className="h-1 w-full rounded-full bg-white/20 overflow-hidden cursor-pointer">
            <div className="h-full w-1/3 bg-primary" />
          </div>
        </div>

        {/* Background Grid Accent */}
        <div className="absolute inset-0 opacity-15 [background-image:linear-gradient(rgba(255,255,255,.07)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.07)_1px,transparent_1px)] [background-size:1.5rem_1.5rem]" />
      </div>
    );
  }

  if (type === "tabs") {
    if (activeTab === "timeline") {
      return <Timeline />;
    }
    if (activeTab === "transcript") {
      return <TranscriptExplorer />;
    }
    return (
      <div className="flex h-full w-full flex-col overflow-y-auto p-4 text-left space-y-3 bg-card">
        {activeTab === "ocr" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 text-primary" /> OCR Visual Overlay Tokens Placeholder
              </span>
              <Badge variant="outline" className="text-[10px]">4,200 Words</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2 border rounded-lg bg-slate-50/50 dark:bg-slate-900/20">
                <span className="text-[9px] font-mono text-muted-foreground">Frame 01:24</span>
                <p className="font-bold text-foreground mt-0.5">"Model Context Protocol Architecture"</p>
              </div>
              <div className="p-2 border rounded-lg bg-slate-50/50 dark:bg-slate-900/20">
                <span className="text-[9px] font-mono text-muted-foreground">Frame 05:12</span>
                <p className="font-bold text-foreground mt-0.5">"JSON-RPC 2.0 Transport Adapters"</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === "scenes" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Video className="h-3.5 w-3.5 text-primary" /> Scene Detection Manifest Placeholder
              </span>
              <Badge variant="outline" className="text-[10px]">16 Scenes</Badge>
            </div>
            <div className="space-y-2 text-xs">
              <div className="p-2.5 border rounded-lg bg-slate-50/50 dark:bg-slate-900/20 flex justify-between items-center">
                <div>
                  <span className="font-bold text-foreground">Scene 1: Introduction</span>
                  <p className="text-[10px] text-muted-foreground">00:00 – 05:12 (1,240 frames)</p>
                </div>
                <Badge variant="secondary" className="text-[9px]">98% Conf</Badge>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  if (type === "chat") {
    return <ChatWindow videoId={videoId} />;
  }

  if (type === "evidence") {
    return <EvidenceInspector />;
  }

  return null;
}

// ----------------------------------------------------
// 5. WorkspaceLayout Component
// ----------------------------------------------------
interface WorkspaceLayoutProps {
  toolbar: ReactNode;
  leftTop: ReactNode;
  leftBottom: ReactNode;
  rightTop: ReactNode;
  rightBottom: ReactNode;
}

export function WorkspaceLayout({
  toolbar,
  leftTop,
  leftBottom,
  rightTop,
  rightBottom
}: WorkspaceLayoutProps) {
  return (
    <div className="flex h-[calc(100vh-4.5rem)] w-full flex-col overflow-hidden rounded-xl border border-border/80 bg-background shadow-elevated">
      {/* Top Toolbar */}
      {toolbar}

      {/* Main Multi-Panel Resizable Container */}
      <div className="flex-1 overflow-hidden">
        <SplitPanel
          direction="horizontal"
          initialSplit={64}
          minSize={30}
          maxSize={85}
          panel1={
            /* Left Column: Vertical Split (Player Top / Timeline Bottom) */
            <SplitPanel
              direction="vertical"
              initialSplit={58}
              minSize={25}
              maxSize={75}
              panel1={leftTop}
              panel2={leftBottom}
            />
          }
          panel2={
            /* Right Column: Vertical Split (AI Chat Top / Evidence Inspector Bottom) */
            <SplitPanel
              direction="vertical"
              initialSplit={55}
              minSize={25}
              maxSize={75}
              panel1={rightTop}
              panel2={rightBottom}
            />
          }
        />
      </div>
    </div>
  );
}
