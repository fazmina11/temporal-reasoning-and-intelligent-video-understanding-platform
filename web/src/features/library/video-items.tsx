import { useState, useRef, useEffect, type ComponentType } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { MoreHorizontal, ExternalLink, Edit2, Trash2, Info, Play, Calendar, HardDrive, Cpu } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge, Thumbnail } from "@/features/library/library-primitives";
import type { LibraryVideo } from "@/types/api";

// Reusable action menu dropdown component
export function ActionMenu({
  video,
  onRename,
  onDelete,
  onViewDetails,
  align = "right"
}: {
  video: LibraryVideo;
  onRename: (video: LibraryVideo) => void;
  onDelete: (video: LibraryVideo) => void;
  onViewDetails: (video: LibraryVideo) => void;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [open]);

  return (
    <div className="relative" ref={menuRef}>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 hover:bg-slate-100 dark:hover:bg-slate-800"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(!open);
        }}
        aria-label={`Actions for ${video.title}`}
      >
        <MoreHorizontal className="h-4 w-4" />
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 5 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 5 }}
            transition={{ duration: 0.12 }}
            className={`absolute z-30 mt-1 w-44 rounded-lg border bg-card p-1 shadow-elevated focus:outline-none ${
              align === "right" ? "right-0" : "left-0"
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <Link
              to={`/videos/${video.id}`}
              className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors"
              onClick={() => setOpen(false)}
            >
              <Play className="h-3.5 w-3.5 text-muted-foreground" />
              <span>Open workspace</span>
            </Link>
            <button
              onClick={() => {
                setOpen(false);
                onViewDetails(video);
              }}
              className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors"
            >
              <Info className="h-3.5 w-3.5 text-muted-foreground" />
              <span>View details</span>
            </button>
            <button
              onClick={() => {
                setOpen(false);
                onRename(video);
              }}
              className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors"
            >
              <Edit2 className="h-3.5 w-3.5 text-muted-foreground" />
              <span>Rename</span>
            </button>
            <hr className="my-1 border-border" />
            <button
              onClick={() => {
                setOpen(false);
                onDelete(video);
              }}
              className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5 text-rose-500" />
              <span>Delete</span>
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface VideoItemProps {
  video: LibraryVideo;
  onRename: (video: LibraryVideo) => void;
  onDelete: (video: LibraryVideo) => void;
  onViewDetails: (video: LibraryVideo) => void;
}

export function VideoCard({ video, onRename, onDelete, onViewDetails }: VideoItemProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.22, ease: "easeInOut" }}
      className="h-full"
    >
      <Card className="group flex h-full flex-col overflow-hidden p-2 bg-card hover:shadow-soft border transition-shadow duration-normal">
        <div className="relative">
          {/* Card Thumbnail link */}
          <Link to={`/videos/${video.id}`} className="focus-ring block rounded-lg overflow-hidden">
            <Thumbnail gradient={video.gradient} icon={video.icon} duration={video.duration} />
            
            {/* Quick Progress overlay for thumbnail if processing */}
            {video.status === "Processing" && video.progress !== undefined && (
              <div className="absolute inset-x-3 bottom-3 h-1 overflow-hidden rounded-full bg-white/20">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${video.progress}%` }}
                  transition={{ duration: 0.8 }}
                  className="h-full rounded-full bg-cyan-300"
                />
              </div>
            )}
          </Link>

          {/* Hover Actions Glass Overlay */}
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-lg bg-slate-950/70 opacity-0 backdrop-blur-xs transition-opacity duration-normal group-hover:opacity-100">
            <Button size="sm" variant="primary" className="h-8 rounded-full px-4 text-xs font-semibold shadow-md" asChild>
              <Link to={`/videos/${video.id}`}>
                <Play className="mr-1 h-3 w-3 fill-current" /> Open
              </Link>
            </Button>
            <div className="flex items-center gap-1.5">
              <Button
                size="icon"
                variant="secondary"
                className="h-7 w-7 rounded-full border border-white/10 bg-white/10 text-white hover:bg-white/20 hover:text-white transition-colors"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onViewDetails(video);
                }}
                title="View Details"
              >
                <Info className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="icon"
                variant="secondary"
                className="h-7 w-7 rounded-full border border-white/10 bg-white/10 text-white hover:bg-white/20 hover:text-white transition-colors"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onRename(video);
                }}
                title="Rename"
              >
                <Edit2 className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="icon"
                variant="destructive"
                className="h-7 w-7 rounded-full border border-red-500/20 bg-red-500/20 text-red-100 hover:bg-red-500/40 hover:text-white transition-colors"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDelete(video);
                }}
                title="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Three-dot dropdown menu overlay (top-right, accessible) */}
          <div className="absolute right-2 top-2 z-25">
            <div className="rounded-md border border-white/10 bg-slate-950/60 text-white backdrop-blur shadow-sm hover:bg-slate-950/80 transition-colors">
              <ActionMenu
                video={video}
                onRename={onRename}
                onDelete={onDelete}
                onViewDetails={onViewDetails}
                align="right"
              />
            </div>
          </div>
        </div>

        {/* Card Body */}
        <div className="flex flex-1 flex-col p-2.5">
          <div className="flex items-start justify-between gap-2.5">
            <Link to={`/videos/${video.id}`} className="focus-ring min-w-0 flex-1 rounded-sm">
              <h3 className="line-clamp-2 text-sm font-semibold leading-5 text-card-foreground group-hover:text-primary transition-colors">
                {video.title}
              </h3>
            </Link>
          </div>

          {/* Filename & size */}
          <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground min-w-0">
            <span className="truncate max-w-[70%] font-mono" title={video.filename}>
              {video.filename}
            </span>
            <span className="shrink-0 flex items-center gap-1 font-medium">
              <HardDrive className="h-3 w-3" />
              {video.size}
            </span>
          </div>

          {/* Processing progress bar if active */}
          {video.status === "Processing" && video.progress !== undefined && (
            <div className="mt-2.5 space-y-1 rounded bg-slate-50 p-1.5 dark:bg-slate-900/40">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Cpu className="h-3 w-3 animate-spin text-amber-500" />
                  Processing...
                </span>
                <span className="font-semibold text-amber-500 dark:text-amber-400">{video.progress}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${video.progress}%` }}
                  transition={{ duration: 0.5 }}
                  className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-400"
                />
              </div>
            </div>
          )}

          {/* Spacer to push tags/details to bottom */}
          <div className="flex-1 min-h-[0.75rem]" />

          {/* Footer Metadata */}
          <div className="border-t border-border/60 pt-2.5 mt-2">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Calendar className="h-3 w-3" />
                {video.date}
              </span>
              <StatusBadge status={video.status} />
            </div>

            {/* Tags row */}
            <div className="mt-2.5 flex flex-wrap gap-1">
              {video.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="rounded-md border bg-slate-50/50 px-1.5 py-0.5 text-[10px] text-muted-foreground font-medium dark:bg-slate-900/30"
                >
                  #{tag}
                </span>
              ))}
              <span className="rounded-md border border-dashed px-1.5 py-0.5 text-[10px] text-muted-foreground/70 font-mono ml-auto">
                {video.pipelineVersion}
              </span>
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

export function VideoRow({ video, onRename, onDelete, onViewDetails }: VideoItemProps) {
  return (
    <motion.tr
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="group border-b border-border/80 last:border-0 hover:bg-slate-50/55 dark:hover:bg-slate-900/20 transition-colors"
    >
      {/* Small Preview Column */}
      <td className="py-3 pl-4 w-24">
        <Link to={`/videos/${video.id}`} className="focus-ring block rounded-md overflow-hidden relative group/row-thumb">
          <Thumbnail gradient={video.gradient} icon={video.icon} className="h-10 w-20 p-1.5" />
          
          {/* Subtle play indicator on row thumbnail hover */}
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/40 opacity-0 group-hover/row-thumb:opacity-100 transition-opacity">
            <Play className="h-3 w-3 text-white fill-current" />
          </div>
        </Link>
      </td>

      {/* Title & tags */}
      <td className="px-3 py-3 max-w-[18rem] md:max-w-[24rem]">
        <div className="flex flex-col min-w-0">
          <Link
            to={`/videos/${video.id}`}
            className="focus-ring block truncate font-semibold text-sm hover:text-primary transition-colors text-card-foreground"
            title={video.title}
          >
            {video.title}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground min-w-0">
            <span className="font-mono truncate max-w-[180px]" title={video.filename}>
              {video.filename}
            </span>
            <span>Â·</span>
            {video.tags.map((tag) => (
              <span key={tag} className="text-[10px] text-muted-foreground/80">
                #{tag}
              </span>
            ))}
          </div>
        </div>
      </td>

      {/* Duration */}
      <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground font-medium">
        {video.duration}
      </td>

      {/* Size */}
      <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground font-mono">
        {video.size}
      </td>

      {/* Status Badges with progress display if processing */}
      <td className="px-3 py-3 whitespace-nowrap">
        <div className="flex flex-col gap-1 items-start">
          <StatusBadge status={video.status} />
          {video.status === "Processing" && video.progress !== undefined && (
            <div className="flex items-center gap-1.5 w-20">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-amber-500"
                  style={{ width: `${video.progress}%` }}
                />
              </div>
              <span className="text-[9px] font-bold text-amber-500">{video.progress}%</span>
            </div>
          )}
        </div>
      </td>

      {/* Pipeline & Last updated info */}
      <td className="px-3 py-3">
        <div className="flex flex-col text-xs">
          <span className="text-muted-foreground font-medium">{video.updated}</span>
          <span className="text-[10px] text-muted-foreground/60 font-mono mt-0.5">{video.pipelineVersion}</span>
        </div>
      </td>

      {/* Row Actions column */}
      <td className="px-3 py-3 text-right">
        <div className="flex justify-end items-center gap-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Quick open workspace button */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-foreground"
            aria-label={`Open workspace for ${video.title}`}
            asChild
          >
            <Link to={`/videos/${video.id}`}>
              <Play className="h-3.5 w-3.5 fill-current" />
            </Link>
          </Button>

          {/* Dropdown Action menu */}
          <ActionMenu
            video={video}
            onRename={onRename}
            onDelete={onDelete}
            onViewDetails={onViewDetails}
            align="right"
          />
        </div>
      </td>
    </motion.tr>
  );
}

