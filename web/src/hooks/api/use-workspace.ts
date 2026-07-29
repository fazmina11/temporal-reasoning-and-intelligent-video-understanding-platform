import { useQuery } from "@tanstack/react-query";
import {
  getAudioEvents,
  getBoundaries,
  getChunkValidation,
  getFrames,
  getOCR,
  getScenes,
  getSpeakers,
  getTimeline,
  getTranscript,
  getVisualArtifacts,
  getWorkspace
} from "@/api/workspace";

async function optionalArtifact<T>(request: () => Promise<T>): Promise<T | null> {
  try {
    return await request();
  } catch {
    return null;
  }
}

export function useWorkspace(videoId?: string) {
  return useQuery({
    queryKey: ["workspace", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      const manifest = await getWorkspace(videoId);
      const [transcript, timeline, ocr, scenes, boundaries, frames, chunkValidation, visualArtifacts, speakers, audioEvents] = await Promise.all([
        optionalArtifact(() => getTranscript(videoId)),
        optionalArtifact(() => getTimeline(videoId)),
        optionalArtifact(() => getOCR(videoId)),
        optionalArtifact(() => getScenes(videoId)),
        optionalArtifact(() => getBoundaries(videoId)),
        optionalArtifact(() => getFrames(videoId)),
        optionalArtifact(() => getChunkValidation(videoId)),
        optionalArtifact(() => getVisualArtifacts(videoId)),
        optionalArtifact(() => getSpeakers(videoId)),
        optionalArtifact(() => getAudioEvents(videoId))
      ]);

      return {
        manifest,
        transcript,
        timeline,
        ocr,
        scenes,
        boundaries,
        frames,
        chunkValidation,
        visualArtifacts,
        speakers,
        audioEvents
      };
    },
    staleTime: 30_000
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
