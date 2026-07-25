import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadVideo } from "@/api/upload";

export function useUpload() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: uploadVideo,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["videos"] });
      await queryClient.invalidateQueries({ queryKey: ["analytics"] });
    }
  });
}
