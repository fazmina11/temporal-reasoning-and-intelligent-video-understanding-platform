import { useMemo, useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Grid2X2, List, Plus, UploadCloud, RotateCcw, Info, Check, AlertCircle, HardDrive, Calendar, FileText, Cpu, Trash2, Film, Play, X, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { PageHeader } from "@/components/global/headers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription
} from "@/components/ui/dialog";

import type { LibraryVideo, VideoStatus } from "@/types/api";
import { useDeleteVideo, useVideos } from "@/hooks/api/use-videos";
import { FilterButton, FilterDrawer, SearchBar, type FilterState } from "@/features/library/library-controls";
import { Pagination } from "@/features/library/pagination";
import { VideoCard, VideoRow } from "@/features/library/video-items";
import { StatusBadge } from "@/features/library/library-primitives";

export function VideoLibraryPage() {
  // Persistence of View Mode
  const [view, setView] = useState<"grid" | "list">(() => {
    const saved = localStorage.getItem("video-library-view");
    return saved === "list" ? "list" : "grid";
  });

  useEffect(() => {
    localStorage.setItem("video-library-view", view);
  }, [view]);

  const { data: videosResponse } = useVideos();
  const deleteVideoMutation = useDeleteVideo();
  const videos = useMemo(() => videosResponse?.videos ?? [], [videosResponse]);

  // UI Control State
  const [filterOpen, setFilterOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("Recently updated");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState<FilterState>({
    status: "All statuses",
    dateRange: "Any time",
    duration: "Any duration",
    tag: "All tags",
    collection: "All collections"
  });

  // Dialog State
  const [activeVideo, setActiveVideo] = useState<LibraryVideo | null>(null);
  const [dialogType, setDialogType] = useState<"rename" | "delete" | "details" | null>(null);
  const [renameTitle, setRenameTitle] = useState("");

  const VideoIcon = activeVideo?.icon;

  // Pagination page resets on search/filter changes
  useEffect(() => {
    setPage(1);
  }, [searchQuery, activeFilters]);

  // Handle video action triggers
  const handleRenameTrigger = (video: LibraryVideo) => {
    setActiveVideo(video);
    setRenameTitle(video.title);
    setDialogType("rename");
  };

  const handleDeleteTrigger = (video: LibraryVideo) => {
    setActiveVideo(video);
    setDialogType("delete");
  };

  const handleDetailsTrigger = (video: LibraryVideo) => {
    setActiveVideo(video);
    setDialogType("details");
  };

  // Perform Actions
  const handleSaveRename = () => {
    if (!activeVideo) return;
    toast.info("Rename will be available once the backend exposes a video metadata update route.");
    setDialogType(null);
    setActiveVideo(null);
  };

  const handleConfirmDelete = async () => {
    if (!activeVideo) return;

    try {
      await deleteVideoMutation.mutateAsync(activeVideo.id);
      toast.success(`"${activeVideo.title}" has been deleted`);
      setDialogType(null);
      setActiveVideo(null);
    } catch (error) {
      toast.error("Could not delete this video from the backend.");
    }
  };

  const resetLibraryFilters = () => {
    setSearchQuery("");
    setActiveFilters({
      status: "All statuses",
      dateRange: "Any time",
      duration: "Any duration",
      tag: "All tags",
      collection: "All collections"
    });
    setPage(1);
  };

  // Active filters count
  const getActiveFiltersCount = () => {
    let count = 0;
    if (activeFilters.status !== "All statuses") count++;
    if (activeFilters.dateRange !== "Any time") count++;
    if (activeFilters.duration !== "Any duration") count++;
    if (activeFilters.tag !== "All tags") count++;
    if (activeFilters.collection !== "All collections") count++;
    return count;
  };

  // Client-side Search and Filter logic
  const filteredVideos = videos.filter((video) => {
    const matchesSearch =
      video.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      video.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
      video.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesStatus =
      activeFilters.status === "All statuses" || video.status === activeFilters.status;

    const matchesTag =
      activeFilters.tag === "All tags" ||
      video.tags.some((t) => t.toLowerCase() === activeFilters.tag.toLowerCase());

    // Other filters (duration, collection, dateRange) act as visuals for simulation
    return matchesSearch && matchesStatus && matchesTag;
  });

  // Client-side Sorting logic
  const sortedVideos = [...filteredVideos].sort((a, b) => {
    if (sort === "Name A-Z") {
      return a.title.localeCompare(b.title);
    }
    
    // Date conversions for mock timestamps
    const getTimestamp = (dateStr: string) => {
      if (dateStr.startsWith("Today")) return Date.now();
      if (dateStr.startsWith("Yesterday")) return Date.now() - 24 * 60 * 60 * 1000;
      return new Date(dateStr).getTime() || 0;
    };

    const getUpdatedTimestamp = (upStr: string) => {
      if (upStr.includes("min ago")) {
        const mins = parseInt(upStr) || 10;
        return Date.now() - mins * 60 * 1000;
      }
      if (upStr === "Yesterday") {
        return Date.now() - 24 * 60 * 60 * 1000;
      }
      return new Date(upStr).getTime() || 0;
    };

    if (sort === "Newest uploaded") {
      return getTimestamp(b.date) - getTimestamp(a.date);
    }
    if (sort === "Oldest uploaded") {
      return getTimestamp(a.date) - getTimestamp(b.date);
    }
    
    // Default "Recently updated"
    return getUpdatedTimestamp(b.updated) - getUpdatedTimestamp(a.updated);
  });

  // Slice for Pagination
  const ITEMS_PER_PAGE = 8;
  const pageVideos = sortedVideos.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const hasVideos = videos.length > 0;
  const hasFilteredVideos = sortedVideos.length > 0;

  return (
    <div className="mx-auto max-w-[1600px] space-y-7 animate-fade-in">
      {/* Page Header */}
      <PageHeader
        eyebrow="Asset management"
        title="Video library"
        description="Browse, organize, and inspect uploaded video sources. Connect context clues and evidence markers directly to transcripts."
        actions={
          <div className="flex items-center gap-2">
            <Button asChild className="shadow-sm">
              <Link to="/videos/new">
                <UploadCloud className="h-4 w-4" />
                Upload video
              </Link>
            </Button>
          </div>
        }
      />

      {/* Controls Bar */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between border-b pb-4 border-border/40">
        <div className="flex flex-1 flex-wrap items-center gap-2">
          <SearchBar value={searchQuery} onChange={setSearchQuery} />
          
          <FilterButton
            onClick={() => setFilterOpen(true)}
            active={getActiveFiltersCount() > 0}
            activeFiltersCount={getActiveFiltersCount()}
          />
          
          {searchQuery && (
            <Badge variant="secondary" className="gap-1.5 h-10 px-3 text-xs bg-slate-100 border border-slate-200 text-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800">
              Search: "{searchQuery}"
              <button onClick={() => setSearchQuery("")} className="hover:text-foreground focus:outline-none">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}

          {getActiveFiltersCount() > 0 && (
            <Badge variant="secondary" className="gap-1.5 h-10 px-3 text-xs bg-slate-100 border border-slate-200 text-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800">
              Filtered: {getActiveFiltersCount()} active
              <button
                onClick={() =>
                  setActiveFilters({
                    status: "All statuses",
                    dateRange: "Any time",
                    duration: "Any duration",
                    tag: "All tags",
                    collection: "All collections"
                  })
                }
                className="hover:text-foreground focus:outline-none"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}

          <Badge variant="outline" className="h-10 items-center px-4 text-xs font-semibold select-none ml-auto lg:ml-0 bg-card border shadow-xs text-muted-foreground">
            {filteredVideos.length} {filteredVideos.length === 1 ? "video" : "videos"} found
          </Badge>
        </div>

        {/* Sort & View modes */}
        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <span className="hidden sm:inline whitespace-nowrap">Sort by</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="focus-ring h-10 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground transition-all hover:bg-background/80"
            >
              <option>Recently updated</option>
              <option>Newest uploaded</option>
              <option>Oldest uploaded</option>
              <option>Name A-Z</option>
            </select>
          </label>

          {/* Grid/List View Toggles */}
          <div className="flex items-center rounded-lg border bg-card p-1 shadow-sm" role="group" aria-label="Video view mode">
            <Button
              variant={view === "grid" ? "secondary" : "ghost"}
              size="icon"
              className={`h-8 w-8 transition-all ${view === "grid" ? "bg-secondary text-primary dark:bg-slate-800 dark:text-primary-foreground" : "text-muted-foreground"}`}
              onClick={() => setView("grid")}
              aria-label="Grid view"
              aria-pressed={view === "grid"}
            >
              <Grid2X2 className="h-4 w-4" />
            </Button>
            <Button
              variant={view === "list" ? "secondary" : "ghost"}
              size="icon"
              className={`h-8 w-8 transition-all ${view === "list" ? "bg-secondary text-primary dark:bg-slate-800 dark:text-primary-foreground" : "text-muted-foreground"}`}
              onClick={() => setView("list")}
              aria-label="List view"
              aria-pressed={view === "list"}
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {hasVideos ? (
        hasFilteredVideos ? (
          <AnimatePresence mode="wait" initial={false}>
            {view === "grid" ? (
              /* Grid View layout (4-5 col desktop, 2-3 col tablet, 1 col mobile) */
              <motion.div
                key="grid"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="grid gap-5 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5"
              >
                {pageVideos.map((video) => (
                  <VideoCard
                    key={video.id}
                    video={video}
                    onRename={handleRenameTrigger}
                    onDelete={handleDeleteTrigger}
                    onViewDetails={handleDetailsTrigger}
                  />
                ))}
              </motion.div>
            ) : (
              /* List View layout */
              <motion.div
                key="list"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                <Card className="overflow-hidden border border-border/80 shadow-soft">
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[850px] text-left border-collapse">
                      <thead className="border-b bg-slate-50 dark:bg-slate-900/60">
                        <tr className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                          <th className="w-24 py-3.5 pl-4">Preview</th>
                          <th className="px-3 py-3.5">Title</th>
                          <th className="px-3 py-3.5">Duration</th>
                          <th className="px-3 py-3.5">Size</th>
                          <th className="px-3 py-3.5">Status</th>
                          <th className="px-3 py-3.5">Last updated</th>
                          <th className="px-4 py-3.5 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60">
                        {pageVideos.map((video) => (
                          <VideoRow
                            key={video.id}
                            video={video}
                            onRename={handleRenameTrigger}
                            onDelete={handleDeleteTrigger}
                            onViewDetails={handleDetailsTrigger}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        ) : (
          /* Empty Search Results State */
          <Card className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-border shadow-xs rounded-xl bg-card/60 min-h-[300px]">
            <div className="grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-muted-foreground dark:bg-slate-900 mb-4 border shadow-xs">
              <Info className="h-6 w-6 text-slate-500" />
            </div>
            <h3 className="text-base font-semibold text-foreground">No matches found</h3>
            <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
              We couldn't find any videos matching your search query or filters. Try adjusting your inputs.
            </p>
            <div className="mt-5 flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchQuery("");
                  setActiveFilters({
                    status: "All statuses",
                    dateRange: "Any time",
                    duration: "Any duration",
                    tag: "All tags",
                    collection: "All collections"
                  });
                }}
              >
                Clear all filters
              </Button>
            </div>
          </Card>
        )
      ) : (
        /* Empty Library State */
        <LibraryEmptyState />
      )}

      {/* Pagination Controls */}
      {hasFilteredVideos && (
        <Pagination
          page={page}
          totalItems={filteredVideos.length}
          itemsPerPage={ITEMS_PER_PAGE}
          onChange={setPage}
        />
      )}

      {/* Filter drawer sidebar */}
      <FilterDrawer
        open={filterOpen}
        onClose={() => setFilterOpen(false)}
        filters={activeFilters}
        onApplyFilters={setActiveFilters}
      />

      {/* MODAL 1: Rename Dialog */}
      <Dialog open={dialogType === "rename"} onOpenChange={(open) => !open && setDialogType(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold">Rename video</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Modify the display title for this asset. This does not change the source filename.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-3">
            <label className="text-xs font-semibold text-foreground/80 block">Video Title</label>
            <Input
              type="text"
              value={renameTitle}
              onChange={(e) => setRenameTitle(e.target.value)}
              placeholder="Enter a friendly title"
              className="h-10 text-sm focus-ring border border-border"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleSaveRename()}
            />
          </div>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button variant="ghost" size="sm" onClick={() => setDialogType(null)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleSaveRename}>
              Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* MODAL 2: Delete confirmation Dialog */}
      <Dialog open={dialogType === "delete"} onOpenChange={(open) => !open && setDialogType(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2 text-rose-600">
              <Trash2 className="h-5 w-5" />
              Delete video asset
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              This action cannot be undone and will erase all metadata.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-foreground">
              Are you sure you want to delete <span className="font-semibold text-foreground">"{activeVideo?.title}"</span>? This will permanently wipe all extracted video timelines, OCR, transcript indexes, and speaker clusters.
            </p>
            {activeVideo?.filename && (
              <div className="mt-3 rounded-lg border bg-slate-50 p-2.5 dark:bg-slate-900/50 flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                <span className="truncate">{activeVideo.filename}</span>
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button variant="ghost" size="sm" onClick={() => setDialogType(null)}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={handleConfirmDelete}>
              Confirm Delete
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* MODAL 3: Detailed Video Specs Dialog */}
      <Dialog open={dialogType === "details"} onOpenChange={(open) => !open && setDialogType(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader className="border-b pb-3">
            <DialogTitle className="text-base font-bold flex items-center gap-2 text-foreground">
              <Info className="h-5 w-5 text-primary" />
              Asset Metadata & Process Status
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Deep dive parameters of the video analysis pipeline.
            </DialogDescription>
          </DialogHeader>

          {activeVideo && (
            <div className="grid grid-cols-1 md:grid-cols-12 gap-5 py-4">
              {/* Left Column: Visual summary */}
              <div className="md:col-span-5 space-y-4">
                <div className="relative rounded-lg overflow-hidden border">
                  {/* Miniature Thumbnail */}
                  <div className={`h-28 w-full bg-gradient-to-br flex items-end p-3 ${activeVideo.gradient}`}>
                    <span className="grid h-7 w-7 place-items-center rounded bg-white/10 text-white backdrop-blur">
                      {VideoIcon && <VideoIcon className="h-4 w-4" />}
                    </span>
                    <span className="ml-auto rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">
                      {activeVideo.duration}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  <h4 className="font-semibold text-sm leading-tight text-foreground">{activeVideo.title}</h4>
                  <p className="text-xs font-mono text-muted-foreground break-all">{activeVideo.filename}</p>
                </div>
                <div className="pt-2">
                  <StatusBadge status={activeVideo.status} className="w-auto inline-flex" />
                  {activeVideo.status === "Processing" && activeVideo.progress !== undefined && (
                    <div className="mt-2 space-y-1">
                      <div className="flex justify-between text-[10px] text-muted-foreground font-semibold">
                        <span>Rebuilding Index...</span>
                        <span>{activeVideo.progress}%</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        <div
                          className="h-full bg-amber-500 rounded-full"
                          style={{ width: `${activeVideo.progress}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Key-Values and Artifacts list */}
              <div className="md:col-span-7 space-y-5">
                {/* Meta details list */}
                <div className="grid grid-cols-2 gap-3.5 border rounded-lg p-3 bg-slate-50/50 dark:bg-slate-900/10">
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                      <HardDrive className="h-3 w-3" /> Size
                    </span>
                    <p className="text-xs font-bold text-foreground">{activeVideo.size}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                      <Calendar className="h-3 w-3" /> Uploaded
                    </span>
                    <p className="text-xs font-bold text-foreground">{activeVideo.date}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                      <Cpu className="h-3 w-3" /> Pipeline Version
                    </span>
                    <p className="text-xs font-mono font-bold text-foreground">{activeVideo.pipelineVersion}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                      <FileText className="h-3 w-3" /> Last Question
                    </span>
                    <p className="text-xs font-bold text-foreground">{activeVideo.lastQuestionDate}</p>
                  </div>
                </div>

                {/* Pipeline Artifacts checklist */}
                <div className="space-y-2.5">
                  <h5 className="text-xs font-bold text-foreground flex items-center gap-1.5 uppercase tracking-wide">
                    <Cpu className="h-3.5 w-3.5 text-primary" /> Extraction Artifacts
                  </h5>
                  <div className="border rounded-lg divide-y bg-card overflow-hidden">
                    <ArtifactRow label="Transcript Timeline Spans" active={activeVideo.artifacts.transcript} />
                    <ArtifactRow label="OCR Frame Text Extraction" active={activeVideo.artifacts.ocr} />
                    <ArtifactRow label="Speaker Diarization Turn Markers" active={activeVideo.artifacts.speakers} />
                    <ArtifactRow label="Audio Event Classifications" active={activeVideo.artifacts.audio} />
                    <ArtifactRow label="Hierarchical ChromaDB Retrieval Vectors" active={activeVideo.artifacts.chromadb} />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 border-t pt-4 mt-2">
            <Button variant="ghost" size="sm" onClick={() => setDialogType(null)}>
              Close
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link to={`/videos/${activeVideo?.id}`} onClick={() => setDialogType(null)}>
                <Play className="mr-1 h-3.5 w-3.5 fill-current" /> Open Workspace
              </Link>
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Inline component for Artifact items inside the Details modal
function ArtifactRow({ label, active }: { label: string; active: boolean }) {
  return (
    <div className="flex items-center justify-between px-3 py-2 text-xs">
      <span className="text-foreground font-medium">{label}</span>
      {active ? (
        <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900/50 gap-1 font-semibold text-[10px]">
          <Check className="h-3 w-3" /> Ready
        </Badge>
      ) : (
        <Badge variant="outline" className="bg-slate-100 text-slate-400 border-slate-200 dark:bg-slate-900 dark:text-slate-600 dark:border-slate-800 gap-1 font-medium text-[10px]">
          <AlertCircle className="h-3 w-3" /> Pending
        </Badge>
      )}
    </div>
  );
}

// Elegant Empty State display component
function LibraryEmptyState() {
  return (
    <Card className="flex flex-col items-center justify-center p-8 py-16 text-center border-2 border-dashed border-border/80 shadow-soft rounded-2xl bg-card">
      {/* Dynamic graphic illustration */}
      <div className="relative mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-slate-50 dark:bg-slate-950/40 border">
        {/* Core background shapes */}
        <div className="absolute inset-2 rounded-full bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 animate-pulse duration-slow" />
        <Video className="relative h-10 w-10 text-primary" />
        <div className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-slate-950 border border-slate-800 text-white grid place-items-center text-[10px] font-bold">
          0
        </div>
      </div>

      <div className="max-w-md space-y-2">
        <h3 className="text-lg font-bold tracking-tight text-foreground">Your video library is empty</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Upload your video clips to start creating a searchable temporal memory index. Once ingested, you can query transcripts, locate key visual frames, and extract citations.
        </p>
      </div>

      <div className="mt-8 flex flex-col sm:flex-row items-center gap-3">
        <Button asChild variant="primary" className="shadow-sm h-10 px-5">
          <Link to="/videos/new">
            <UploadCloud className="h-4 w-4" />
            Upload Your First Video
          </Link>
        </Button>
      </div>

      {/* Helpful list guide */}
      <div className="mt-10 max-w-sm rounded-xl border border-border/60 bg-slate-50/50 p-4 text-left text-xs text-muted-foreground dark:bg-slate-950/20">
        <p className="font-semibold text-foreground mb-2">Supported Formats & Pipelines:</p>
        <ul className="list-disc pl-4 space-y-1">
          <li>MP4, MOV, and AVI containers up to 5GB.</li>
          <li>Balanced profiles include OCR, audio, and speakers.</li>
          <li>Hierarchical indexes are synchronized with ChromaDB.</li>
        </ul>
      </div>
    </Card>
  );
}



