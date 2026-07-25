import { useState, useRef, useEffect, type ComponentType } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Video,
  FileText,
  Layers,
  Mic,
  ShieldCheck,
  Database,
  Sparkles,
  Eye,
  EyeOff,
  ChevronRight,
  ChevronDown,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Play,
  Clock,
  Compass,
  Layers3,
  Bookmark
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  type TimelineMarkerData,
  type TimelineTrackData,
  type OverviewChapter,
  OVERVIEW_CHAPTERS,
  INITIAL_TIMELINE_TRACKS,
  TOTAL_DURATION_SEC
} from "./mock-timeline-data";

// Helper icon mapper
const ICON_MAP: Record<string, ComponentType<any>> = {
  Video,
  FileText,
  Layers,
  Mic,
  ShieldCheck,
  Database,
  Sparkles
};

// ----------------------------------------------------
// 1. ZoomControls Component
// ----------------------------------------------------
interface ZoomControlsProps {
  zoom: number; // Percentage, e.g. 100, 200, 400
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetZoom: () => void;
}

export function ZoomControls({ zoom, onZoomIn, onZoomOut, onResetZoom }: ZoomControlsProps) {
  return (
    <div className="flex items-center gap-1 bg-slate-900/80 border border-slate-800 rounded-lg p-1 text-xs shrink-0 shadow-xs">
      <Button
        variant="ghost"
        size="icon"
        onClick={onZoomOut}
        disabled={zoom <= 50}
        className="h-6 w-6 text-slate-300 hover:text-white hover:bg-slate-800"
        title="Zoom Out (-)"
      >
        <ZoomOut className="h-3.5 w-3.5" />
      </Button>

      <span className="font-mono text-[10px] font-bold text-slate-300 px-1.5 select-none min-w-[3rem] text-center">
        {zoom}%
      </span>

      <Button
        variant="ghost"
        size="icon"
        onClick={onZoomIn}
        disabled={zoom >= 400}
        className="h-6 w-6 text-slate-300 hover:text-white hover:bg-slate-800"
        title="Zoom In (+)"
      >
        <ZoomIn className="h-3.5 w-3.5" />
      </Button>

      <Button
        variant="ghost"
        size="icon"
        onClick={onResetZoom}
        className="h-6 w-6 text-slate-300 hover:text-white hover:bg-slate-800 ml-1 border-l border-slate-800 pl-1"
        title="Fit / Reset Zoom"
      >
        <Maximize2 className="h-3 w-3" />
      </Button>
    </div>
  );
}

// ----------------------------------------------------
// 2. OverviewStrip Component
// ----------------------------------------------------
interface OverviewStripProps {
  chapters: OverviewChapter[];
  currentSec: number;
  onSeek: (sec: number) => void;
}

export function OverviewStrip({ chapters, currentSec, onSeek }: OverviewStripProps) {
  return (
    <div className="space-y-1.5 bg-slate-950 p-2.5 border-b border-slate-800 shrink-0">
      <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
        <span className="flex items-center gap-1.5 text-indigo-400">
          <Compass className="h-3.5 w-3.5" /> AI Chapter Breakdown & Density Strip
        </span>
        <span className="font-mono text-slate-400">42:18 Total Span</span>
      </div>

      {/* Chapters Strip Grid */}
      <div className="relative h-6 w-full rounded-md overflow-hidden bg-slate-900 border border-slate-800 flex items-center cursor-pointer">
        {chapters.map((ch) => {
          const widthPct = ((ch.endSec - ch.startSec) / TOTAL_DURATION_SEC) * 100;
          return (
            <div
              key={ch.id}
              onClick={() => onSeek(ch.startSec)}
              style={{ width: `${widthPct}%` }}
              className={cn(
                "h-full border-r border-slate-950/60 bg-gradient-to-r transition-opacity hover:opacity-90 flex items-center px-2 relative group",
                ch.gradient
              )}
              title={`${ch.title} (${Math.floor(ch.startSec / 60)}m – ${Math.floor(ch.endSec / 60)}m)`}
            >
              <span className="text-[9px] font-bold font-mono text-white truncate shadow-xs">
                {ch.title}
              </span>
            </div>
          );
        })}

        {/* Current Playhead Needle Marker */}
        <div
          style={{ left: `${(currentSec / TOTAL_DURATION_SEC) * 100}%` }}
          className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 z-10 shadow-[0_0_8px_rgba(34,211,238,0.8)] pointer-events-none"
        />
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 3. MiniMap Component
// ----------------------------------------------------
interface MiniMapProps {
  currentSec: number;
  onSeek: (sec: number) => void;
}

export function MiniMap({ currentSec, onSeek }: MiniMapProps) {
  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clickX / rect.width));
    onSeek(Math.floor(pct * TOTAL_DURATION_SEC));
  };

  return (
    <div
      onClick={handleClick}
      className="relative h-4 w-full bg-slate-950 border-t border-slate-800 cursor-pointer overflow-hidden flex items-center px-1 shrink-0"
      title="MiniMap Overview - Click to jump playback"
    >
      {/* Background visual waves */}
      <div className="absolute inset-0 opacity-20 bg-[radial-gradient(#6366f1_1px,transparent_1px)] [background-size:8px_8px]" />

      {/* Playhead Marker */}
      <div
        style={{ left: `${(currentSec / TOTAL_DURATION_SEC) * 100}%` }}
        className="absolute top-0 bottom-0 w-1 bg-cyan-400 z-10 shadow-[0_0_6px_rgba(34,211,238,1)]"
      />
    </div>
  );
}

// ----------------------------------------------------
// 4. TrackHeader Component
// ----------------------------------------------------
interface TrackHeaderProps {
  track: TimelineTrackData;
  onToggleExpand: () => void;
  onToggleVisible: () => void;
}

export function TrackHeader({ track, onToggleExpand, onToggleVisible }: TrackHeaderProps) {
  const Icon = ICON_MAP[track.iconName] || Video;

  return (
    <div className="w-48 sm:w-56 shrink-0 h-10 border-r border-slate-800/80 bg-slate-900/90 px-3 flex items-center justify-between text-xs select-none">
      <div className="flex items-center gap-2 min-w-0">
        <button
          onClick={onToggleExpand}
          className="text-slate-400 hover:text-white transition-colors"
          title={track.expanded ? "Collapse Track" : "Expand Track"}
        >
          {track.expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>

        <span className={cn("grid h-5 w-5 place-items-center rounded border shrink-0", track.color)}>
          <Icon className="h-3 w-3" />
        </span>

        <span className="font-semibold text-slate-200 truncate" title={track.label}>
          {track.label}
        </span>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <Badge variant="outline" className="h-4 px-1 text-[9px] font-mono text-slate-400 border-slate-800 bg-slate-950">
          {track.badge}
        </Badge>
        <button
          onClick={onToggleVisible}
          className="text-slate-500 hover:text-slate-300 transition-colors p-1"
          title={track.visible ? "Hide Track" : "Show Track"}
        >
          {track.visible ? <Eye className="h-3 w-3 text-cyan-400" /> : <EyeOff className="h-3 w-3" />}
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 5. HoverPreview Component
// ----------------------------------------------------
interface HoverPreviewProps {
  marker: TimelineMarkerData;
  position: { x: number; y: number };
}

export function HoverPreview({ marker, position }: HoverPreviewProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      style={{
        left: `${position.x}px`,
        top: `${position.y}px`
      }}
      className="fixed z-50 w-72 pointer-events-none transform -translate-x-1/2 -translate-y-full mb-3"
    >
      <Card className="p-3 border border-indigo-500/40 bg-slate-950/95 text-white shadow-elevated backdrop-blur-2xl space-y-2 text-left">
        <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-1.5">
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {marker.timeLabel}
          </Badge>
          {marker.badge && (
            <Badge variant="outline" className="h-4 px-1 text-[9px] font-mono text-cyan-400 border-cyan-500/30 bg-cyan-950/30">
              {marker.badge}
            </Badge>
          )}
        </div>

        {/* Thumbnail gradient preview */}
        <div className={cn("h-16 w-full rounded bg-gradient-to-br flex items-center justify-center text-[10px] font-mono font-bold text-white shadow-inner p-2 text-center", marker.gradient || "from-indigo-950 via-slate-900 to-cyan-900")}>
          <span>{marker.title}</span>
        </div>

        <div className="space-y-1 text-xs">
          <p className="font-bold text-slate-100 leading-tight">{marker.title}</p>
          <p className="text-[11px] text-slate-400 leading-normal line-clamp-2">{marker.summary}</p>
          {marker.transcriptQuote && (
            <p className="text-[10px] text-emerald-400 italic bg-emerald-950/30 p-1.5 rounded border border-emerald-500/20 line-clamp-2 mt-1">
              "{marker.transcriptQuote}"
            </p>
          )}
        </div>
      </Card>
    </motion.div>
  );
}

// ----------------------------------------------------
// 6. TimelineMarker Component
// ----------------------------------------------------
interface TimelineMarkerProps {
  marker: TimelineMarkerData;
  zoom: number;
  onHover: (marker: TimelineMarkerData | null, pos?: { x: number; y: number }) => void;
  onSelect: (marker: TimelineMarkerData) => void;
}

export function TimelineMarker({ marker, zoom, onHover, onSelect }: TimelineMarkerProps) {
  const leftPct = (marker.startSec / TOTAL_DURATION_SEC) * 100;
  const widthPct = Math.max(0.8, ((marker.endSec - marker.startSec) / TOTAL_DURATION_SEC) * 100);

  const handleMouseEnter = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    onHover(marker, { x: rect.left + rect.width / 2, y: rect.top });
  };

  return (
    <div
      onClick={() => onSelect(marker)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => onHover(null)}
      style={{
        left: `${leftPct}%`,
        width: `${widthPct}%`
      }}
      className={cn(
        "absolute h-6 rounded border cursor-pointer transition-all duration-fast flex items-center px-1.5 text-[10px] font-bold text-white truncate shadow-2xs hover:scale-y-110 hover:z-20 hover:border-cyan-400",
        marker.color
      )}
      title={marker.title}
    >
      <span className="truncate drop-shadow">{marker.title}</span>
    </div>
  );
}

// ----------------------------------------------------
// 7. TimelineTrack Component
// ----------------------------------------------------
interface TimelineTrackProps {
  track: TimelineTrackData;
  zoom: number;
  onToggleExpand: (id: string) => void;
  onToggleVisible: (id: string) => void;
  onHoverMarker: (marker: TimelineMarkerData | null, pos?: { x: number; y: number }) => void;
  onSelectMarker: (marker: TimelineMarkerData) => void;
}

export function TimelineTrack({
  track,
  zoom,
  onToggleExpand,
  onToggleVisible,
  onHoverMarker,
  onSelectMarker
}: TimelineTrackProps) {
  if (!track.visible) return null;

  return (
    <div className="flex border-b border-slate-800/60 bg-slate-950/60 group hover:bg-slate-900/40 transition-colors">
      <TrackHeader
        track={track}
        onToggleExpand={() => onToggleExpand(track.id)}
        onToggleVisible={() => onToggleVisible(track.id)}
      />

      <div className={cn("flex-1 relative overflow-hidden transition-all duration-normal flex items-center px-2", track.expanded ? "h-10" : "h-7 opacity-75")}>
        {track.markers.map((m) => (
          <TimelineMarker
            key={m.id}
            marker={m}
            zoom={zoom}
            onHover={onHoverMarker}
            onSelect={onSelectMarker}
          />
        ))}
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 8. Timeline Component (Main Orchestrator)
// ----------------------------------------------------
interface TimelineProps {
  onSeekToTimestamp?: (sec: number) => void;
}

export function Timeline({ onSeekToTimestamp }: TimelineProps) {
  const [tracks, setTracks] = useState<TimelineTrackData[]>(INITIAL_TIMELINE_TRACKS);
  const [zoom, setZoom] = useState(100);
  const [currentSec, setCurrentSec] = useState(312); // 05:12
  const [hoveredMarker, setHoveredMarker] = useState<TimelineMarkerData | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const handleZoomIn = () => setZoom((prev) => Math.min(400, prev + 50));
  const handleZoomOut = () => setZoom((prev) => Math.max(50, prev - 50));
  const handleResetZoom = () => setZoom(100);

  const handleToggleExpand = (id: string) => {
    setTracks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, expanded: !t.expanded } : t))
    );
  };

  const handleToggleVisible = (id: string) => {
    setTracks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, visible: !t.visible } : t))
    );
  };

  const handleSeek = (sec: number) => {
    setCurrentSec(sec);
    onSeekToTimestamp?.(sec);
  };

  const handleSelectMarker = (marker: TimelineMarkerData) => {
    handleSeek(marker.startSec);
  };

  const timeRulerTicks = [0, 300, 600, 900, 1200, 1500, 1800, 2100, 2400];

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-slate-950 text-slate-100 text-left select-none">
      {/* Background Neural Network Artwork Overlay */}
      <div className="absolute inset-0 opacity-10 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] [background-size:2rem_2rem] pointer-events-none" />

      {/* Top Overview & Zoom Controls Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-900/90 border-b border-slate-800 shrink-0 z-10">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-6 px-2 text-[10px] font-mono font-bold bg-indigo-500/10 text-indigo-400 border-indigo-500/20">
            AI SEMANTIC TIMELINE
          </Badge>
          <span className="text-xs font-bold text-slate-200">Interactive Memory Graph</span>
        </div>

        <ZoomControls
          zoom={zoom}
          onZoomIn={handleZoomIn}
          onZoomOut={handleZoomOut}
          onResetZoom={handleResetZoom}
        />
      </div>

      {/* Overview Chapters Strip */}
      <OverviewStrip chapters={OVERVIEW_CHAPTERS} currentSec={currentSec} onSeek={handleSeek} />

      {/* Main Track View Area */}
      <div className="flex-1 overflow-y-auto relative z-10 space-y-0.5">
        {/* Time Ruler Bar */}
        <div className="flex border-b border-slate-800 bg-slate-900/60 sticky top-0 z-20">
          <div className="w-48 sm:w-56 shrink-0 h-6 border-r border-slate-800 px-3 flex items-center text-[10px] font-bold font-mono text-slate-400 uppercase tracking-wider">
            Time Axis
          </div>
          <div className="flex-1 relative h-6 overflow-hidden flex items-center">
            {timeRulerTicks.map((tSec) => {
              const leftPct = (tSec / TOTAL_DURATION_SEC) * 100;
              const mins = Math.floor(tSec / 60);
              return (
                <div
                  key={tSec}
                  style={{ left: `${leftPct}%` }}
                  className="absolute flex flex-col items-start font-mono text-[9px] text-slate-400"
                >
                  <span className="h-2 w-px bg-slate-700 mb-0.5" />
                  <span>{mins.toString().padStart(2, "0")}:00</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 7 Expandable Track Rows */}
        {tracks.map((t) => (
          <TimelineTrack
            key={t.id}
            track={t}
            zoom={zoom}
            onToggleExpand={handleToggleExpand}
            onToggleVisible={handleToggleVisible}
            onHoverMarker={(m, pos) => {
              setHoveredMarker(m);
              if (pos) setHoverPos(pos);
            }}
            onSelectMarker={handleSelectMarker}
          />
        ))}
      </div>

      {/* MiniMap Overview Slider at Bottom */}
      <MiniMap currentSec={currentSec} onSeek={handleSeek} />

      {/* Hover Preview Floating Popover */}
      <AnimatePresence>
        {hoveredMarker && (
          <HoverPreview marker={hoveredMarker} position={hoverPos} />
        )}
      </AnimatePresence>
    </div>
  );
}
