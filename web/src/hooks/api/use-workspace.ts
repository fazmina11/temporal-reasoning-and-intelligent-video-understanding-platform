import { useQuery } from "@tanstack/react-query";
import { getBoundaries, getChunkValidation, getFrames, getOCR, getScenes, getTimeline, getTranscript, getWorkspace } from "@/api/workspace";

export function useWorkspace(videoId?: string) {
  return useQuery({
    queryKey: ["workspace", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      const [manifest, transcript, timeline, ocr, scenes, boundaries, frames, chunkValidation] = await Promise.all([
        getWorkspace(videoId),
        getTranscript(videoId),
        getTimeline(videoId),
        getOCR(videoId),
        getScenes(videoId),
        getBoundaries(videoId),
        getFrames(videoId),
        getChunkValidation(videoId)
      ]);

      return {
        manifest,
        transcript,
        timeline,
        ocr,
        scenes,
        boundaries,
        frames,
        chunkValidation
      };
    },
    refetchInterval: 5000
  });
}

export function useTranscript(videoId?: string) {
  return useQuery({
    queryKey: ["transcript", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      return getTranscript(videoId);
    }
  });
}

export function useTimeline(videoId?: string) {
  return useQuery({
    queryKey: ["timeline", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      return getTimeline(videoId);
    }
  });
}

export function useOCR(videoId?: string) {
  return useQuery({
    queryKey: ["ocr", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      return getOCR(videoId);
    }
  });
}

export function useScenes(videoId?: string) {
  return useQuery({
    queryKey: ["scenes", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      return getScenes(videoId);
    }
  });
}
