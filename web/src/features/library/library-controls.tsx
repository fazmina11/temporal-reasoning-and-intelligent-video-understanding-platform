import { useState, useEffect } from "react";
import { Search, SlidersHorizontal, X, Sliders, Calendar, Clock, Tag, FolderOpen } from "lucide-react";
import type { ComponentType } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

interface SearchBarProps {
  value: string;
  onChange: (val: string) => void;
}

export function SearchBar({ value, onChange }: SearchBarProps) {
  const [focused, setFocused] = useState(false);

  // Focus with "/" key shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        const searchInput = document.getElementById("library-search") as HTMLInputElement;
        searchInput?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div
      className={`relative w-full transition-all duration-normal ease-emphasized ${
        focused ? "max-w-md scale-[1.01]" : "max-w-xs"
      }`}
    >
      <Search
        className={`absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 transition-colors duration-fast ${
          focused ? "text-primary" : "text-muted-foreground"
        }`}
      />
      <Input
        id="library-search"
        type="text"
        aria-label="Search videos"
        placeholder="Search videos... (Press '/' to focus)"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="pl-10 pr-10 h-10 w-full rounded-lg border border-border/80 bg-background/50 focus-visible:bg-background/90 shadow-sm transition-all focus:border-primary/80 focus:ring-2 focus:ring-primary/20"
      />
      
      {value ? (
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-1.5 top-1/2 h-7 w-7 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          onClick={() => onChange("")}
          aria-label="Clear search query"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      ) : (
        <kbd className="pointer-events-none absolute right-3.5 top-1/2 hidden -translate-y-1/2 rounded border border-border/70 bg-muted/60 px-2 py-0.5 font-mono text-[9px] font-bold text-muted-foreground shadow-xs sm:block">
          /
        </kbd>
      )}
    </div>
  );
}

interface FilterButtonProps {
  onClick: () => void;
  active?: boolean;
  activeFiltersCount: number;
}

export function FilterButton({ onClick, active, activeFiltersCount }: FilterButtonProps) {
  return (
    <Button
      variant={active ? "secondary" : "outline"}
      onClick={onClick}
      className={`h-10 gap-2 border bg-card relative ${
        active ? "border-primary/30 shadow-sm" : "hover:border-border"
      }`}
    >
      <SlidersHorizontal className={`h-4 w-4 ${active ? "text-primary" : "text-muted-foreground"}`} />
      <span>Filters</span>
      {activeFiltersCount > 0 && (
        <motion.span
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-primary px-1.5 font-mono text-[10px] font-bold text-primary-foreground shadow-sm animate-fade-in"
        >
          {activeFiltersCount}
        </motion.span>
      )}
    </Button>
  );
}

export interface FilterState {
  status: string;
  dateRange: string;
  duration: string;
  tag: string;
  collection: string;
}

const defaultFilters: FilterState = {
  status: "All statuses",
  dateRange: "Any time",
  duration: "Any duration",
  tag: "All tags",
  collection: "All collections"
};

interface FilterDrawerProps {
  open: boolean;
  onClose: () => void;
  filters: FilterState;
  onApplyFilters: (filters: FilterState) => void;
}

export function FilterDrawer({ open, onClose, filters, onApplyFilters }: FilterDrawerProps) {
  const [localFilters, setLocalFilters] = useState<FilterState>({ ...filters });

  // Sync with prop when drawer opens
  useEffect(() => {
    if (open) {
      setLocalFilters({ ...filters });
    }
  }, [open, filters]);

  const handleChange = (key: keyof FilterState, val: string) => {
    setLocalFilters((prev) => ({
      ...prev,
      [key]: val
    }));
  };

  const handleReset = () => {
    setLocalFilters({ ...defaultFilters });
  };

  const handleApply = () => {
    onApplyFilters(localFilters);
    onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop Blur Overlay */}
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-xs"
            aria-label="Close filter panel"
          />

          {/* Sliding Aside Drawer */}
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label="Video filters"
            initial={{ opacity: 0, x: "100%" }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: "100%" }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 z-50 flex h-full w-[min(26rem,90vw)] flex-col border-l border-border bg-card shadow-elevated"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b px-6 py-5">
              <div>
                <p className="text-sm font-semibold tracking-tight text-foreground">Filter library</p>
                <p className="mt-1 text-xs text-muted-foreground">Refine and organize your video collection view</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                aria-label="Close filters"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Scrollable Form Fields */}
            <div className="flex-1 space-y-6 overflow-y-auto p-6">
              <FilterSelect
                label="Processing status"
                icon={Sliders}
                value={localFilters.status}
                onChange={(val) => handleChange("status", val)}
                options={["All statuses", "Uploaded", "Processing", "Completed", "Failed", "Indexed"]}
              />
              <FilterSelect
                label="Upload date"
                icon={Calendar}
                value={localFilters.dateRange}
                onChange={(val) => handleChange("dateRange", val)}
                options={["Any time", "Today", "This week", "This month"]}
              />
              <FilterSelect
                label="Duration"
                icon={Clock}
                value={localFilters.duration}
                onChange={(val) => handleChange("duration", val)}
                options={["Any duration", "Under 10 minutes", "10â€“60 minutes", "Over 1 hour"]}
              />
              <FilterSelect
                label="Tags"
                icon={Tag}
                value={localFilters.tag}
                onChange={(val) => handleChange("tag", val)}
                options={["All tags", "research", "technical", "planning", "product", "design", "workshop", "customer", "interview", "event", "keynote", "archive"]}
              />
              <FilterSelect
                label="Collections"
                icon={FolderOpen}
                value={localFilters.collection}
                onChange={(val) => handleChange("collection", val)}
                options={["All collections", "My videos", "Shared with me", "Archive"]}
              />
            </div>

            {/* Action buttons */}
            <div className="flex gap-3 border-t border-border px-6 py-5 bg-slate-50/50 dark:bg-slate-950/20">
              <Button variant="outline" className="flex-1 h-10 text-xs font-semibold" onClick={handleReset}>
                Reset
              </Button>
              <Button className="flex-1 h-10 text-xs font-semibold" onClick={handleApply}>
                Apply filters
              </Button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

interface FilterSelectProps {
  label: string;
  icon: ComponentType<any>;
  value: string;
  onChange: (val: string) => void;
  options: string[];
}

function FilterSelect({ label, icon: Icon, value, onChange, options }: FilterSelectProps) {
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-1.5 text-xs font-semibold tracking-tight text-foreground/80">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="focus-ring h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground hover:bg-background/80 transition-colors"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

