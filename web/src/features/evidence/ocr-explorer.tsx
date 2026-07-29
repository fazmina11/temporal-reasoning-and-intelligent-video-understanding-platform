import { useMemo, useState } from "react";
import { Eye, Image, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { OcrEvidenceView } from "@/types/api";

interface OcrExplorerProps {
  records: OcrEvidenceView[];
  onSeekToTimestamp?: (seconds: number) => void;
}

export function OcrExplorer({ records, onSeekToTimestamp }: OcrExplorerProps) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return records;
    return records.filter((record) => record.text.toLowerCase().includes(normalized));
  }, [query, records]);

  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      <div className="flex items-center gap-3 border-b border-slate-800 p-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search visible text"
            className="h-9 border-slate-800 bg-slate-900 pl-9 text-xs"
          />
        </div>
        <Badge variant="outline" className="border-cyan-500/30 text-cyan-300">
          {filtered.length} readable spans
        </Badge>
      </div>

      <div className="grid flex-1 gap-3 overflow-y-auto p-3 sm:grid-cols-2 xl:grid-cols-3">
        {filtered.map((record) => (
          <button
            key={record.id}
            type="button"
            onClick={() => onSeekToTimestamp?.(record.startSec)}
            className="focus-ring overflow-hidden rounded-md border border-slate-800 bg-slate-900/70 text-left transition hover:border-cyan-500/50"
          >
            <div className="aspect-video bg-slate-900">
              {record.frameUri ? (
                <img
                  src={record.frameUri}
                  alt={`Frame ${record.frameId || ""} containing ${record.text}`}
                  loading="lazy"
                  className="h-full w-full object-contain"
                />
              ) : (
                <div className="grid h-full place-items-center text-slate-600">
                  <Image className="h-7 w-7" />
                </div>
              )}
            </div>
            <div className="space-y-2 p-3">
              <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
                <span className="font-mono">{record.timestamp}</span>
                <span>{Math.round(record.qualityScore * 100)}% quality</span>
              </div>
              <p className="line-clamp-3 text-xs font-semibold text-slate-100">{record.text}</p>
              <p className="flex items-center gap-1 text-[10px] text-cyan-300">
                <Eye className="h-3 w-3" />
                {record.frameId || "Representative frame"}
              </p>
            </div>
          </button>
        ))}

        {filtered.length === 0 && (
          <div className="col-span-full grid min-h-48 place-items-center text-sm text-slate-400">
            No readable OCR evidence matches this search.
          </div>
        )}
      </div>
    </div>
  );
}
