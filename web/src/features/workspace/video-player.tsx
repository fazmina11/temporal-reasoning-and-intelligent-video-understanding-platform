import { useEffect, useRef, useState } from "react";
import { Film, Loader2 } from "lucide-react";
import { getVideoMediaUrl } from "@/api/workspace";
import { formatTimestamp } from "@/api/artifact-adapters";

interface VideoPlayerProps {
  videoId: string;
  title: string;
  seekRequestSec: number | null;
  onTimeUpdate: (seconds: number) => void;
}

export function VideoPlayer({
  videoId,
  title,
  seekRequestSec,
  onTimeUpdate
}: VideoPlayerProps) {
  const ref = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const player = ref.current;
    if (!player || seekRequestSec === null || !Number.isFinite(seekRequestSec)) return;
    const applySeek = () => {
      const bounded = Math.max(0, Math.min(seekRequestSec, player.duration || seekRequestSec));
      player.currentTime = bounded;
      setCurrentTime(bounded);
      onTimeUpdate(bounded);
      void player.play().catch(() => undefined);
    };
    if (player.readyState >= HTMLMediaElement.HAVE_METADATA) applySeek();
    else player.addEventListener("loadedmetadata", applySeek, { once: true });
    return () => player.removeEventListener("loadedmetadata", applySeek);
  }, [seekRequestSec, onTimeUpdate]);

  return (
    <div className="relative h-full min-h-64 overflow-hidden bg-black">
      {!ready && !failed && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-slate-950 text-slate-300">
          <div className="flex items-center gap-2 text-xs">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading source video
          </div>
        </div>
      )}
      {failed && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-slate-950 p-6 text-center">
          <div>
            <Film className="mx-auto h-7 w-7 text-slate-500" />
            <p className="mt-3 text-sm font-semibold text-slate-200">Source video unavailable</p>
            <p className="mt-1 text-xs text-slate-500">
              The manifest exists, but its managed media file could not be streamed.
            </p>
          </div>
        </div>
      )}
      <video
        ref={ref}
        key={videoId}
        src={getVideoMediaUrl(videoId)}
        controls
        preload="metadata"
        playsInline
        aria-label={`Video player for ${title}`}
        className="h-full w-full object-contain"
        onLoadedMetadata={(event) => {
          setReady(true);
          setFailed(false);
          setDuration(event.currentTarget.duration || 0);
        }}
        onTimeUpdate={(event) => {
          const next = event.currentTarget.currentTime;
          setCurrentTime(next);
          onTimeUpdate(next);
        }}
        onError={() => {
          setReady(false);
          setFailed(true);
        }}
      />
      {ready && (
        <div className="pointer-events-none absolute right-3 top-3 rounded bg-black/70 px-2 py-1 font-mono text-[10px] text-white">
          {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
        </div>
      )}
    </div>
  );
}
