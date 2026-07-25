import { useMutation } from "@tanstack/react-query";
import { askQuestion, askQuestionDebug } from "@/api/ask";

export function useAsk() {
  return useMutation({
    mutationFn: askQuestion
  });
}

export function useAskDebug() {
  return useMutation({
    mutationFn: askQuestionDebug
  });
}
