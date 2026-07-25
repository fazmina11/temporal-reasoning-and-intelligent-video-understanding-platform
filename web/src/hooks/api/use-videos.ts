import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAnalytics } from "@/api/analytics";
import { getProcessingStatus } from "@/api/processing";
import { cancelVideo, deleteVideo, getVideoManifest, getVideoQuestions, getVideos, retryVideo } from "@/api/videos";
import { mapManifestToLibraryVideo, mapVideoSummaryToLibraryVideo } from "@/api/adapters";

export function useVideos() {
  return useQuery({
    queryKey: ["videos"],
    queryFn: async () => {
      const response = await getVideos();
      const videos = await Promise.all(
        response.videos.map(async (video, index) => {
          try {
            const manifest = await getVideoManifest(video.video_id);
            return mapManifestToLibraryVideo(manifest, index);
          } catch {
            return mapVideoSummaryToLibraryVideo(video, index);
          }
        })
      );

      return { videos };
    }
  });
}

export function useVideo(videoId?: string) {
  return useQuery({
    queryKey: ["video", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      const manifest = await getVideoManifest(videoId);
      return mapManifestToLibraryVideo(manifest);
    }
  });
}

export function useVideoQuestions(videoId?: string) {
  return useQuery({
    queryKey: ["video", videoId, "questions"],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return { questions: [] };
      return getVideoQuestions(videoId);
    }
  });
}

export function useProcessing(videoId?: string) {
  return useQuery({
    queryKey: ["processing", videoId],
    enabled: Boolean(videoId),
    queryFn: async () => {
      if (!videoId) return null;
      return getProcessingStatus(videoId);
    },
    refetchInterval: 3000
  });
}

export function useDeleteVideo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteVideo,
    onSuccess: async (_response, videoId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["videos"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics"] }),
        queryClient.invalidateQueries({ queryKey: ["video", videoId] })
      ]);
    }
  });
}

export function useRetryVideo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: retryVideo,
    onSuccess: async (_response, videoId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["videos"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics"] }),
        queryClient.invalidateQueries({ queryKey: ["video", videoId] }),
        queryClient.invalidateQueries({ queryKey: ["processing", videoId] })
      ]);
    }
  });
}

export function useCancelVideo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: cancelVideo,
    onSuccess: async (_response, videoId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["videos"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics"] }),
        queryClient.invalidateQueries({ queryKey: ["video", videoId] }),
        queryClient.invalidateQueries({ queryKey: ["processing", videoId] })
      ]);
    }
  });
}

export function useAnalytics() {
  return useQuery({
    queryKey: ["analytics"],
    queryFn: getAnalytics
  });
}
