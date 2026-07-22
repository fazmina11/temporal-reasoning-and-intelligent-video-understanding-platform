"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileVideo, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const handleFile = (f: File) => {
    setFile(f);
    setError(null);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setStatus("Uploading video...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Upload failed");
      const { video_id, extension } = await response.json();
      localStorage.setItem("current_video_id", video_id);
      localStorage.setItem("current_video_name", file.name);
      localStorage.setItem("current_video_ext", extension);
      pollStatus(video_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "An error occurred");
      setUploading(false);
    }
  };

  const pollStatus = (videoId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/status/${videoId}`);
        if (!response.ok) throw new Error("Failed to fetch status");
        const data = await response.json();
        setStatus(data.status);
        setProgress(data.progress);
        if (data.status === "completed") {
          clearInterval(interval);
          router.push("/chat");
        } else if (data.status === "failed") {
          clearInterval(interval);
          setError(data.error || "Processing failed");
          setUploading(false);
        }
      } catch {
        clearInterval(interval);
        setError("Error polling status");
        setUploading(false);
      }
    }, 2000);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-xl w-full bg-white rounded-3xl shadow-xl p-8 md:p-12">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Upload Video</h1>
          <p className="text-slate-500">Upload your video to start the AI scene analysis</p>
        </div>

        {!uploading ? (
          <>
            <label
              onDragOver={(e) => { e.preventDefault(); setIsDragActive(true); }}
              onDragLeave={() => setIsDragActive(false)}
              onDrop={onDrop}
              className={cn(
                "border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all flex flex-col items-center",
                isDragActive ? "border-primary bg-primary/5" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50",
                file && "border-green-200 bg-green-50"
              )}
            >
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
              {file ? (
                <>
                  <FileVideo className="w-16 h-16 text-green-500 mb-4" />
                  <p className="text-slate-900 font-medium">{file.name}</p>
                  <p className="text-slate-500 text-sm">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
                    <Upload className="w-8 h-8 text-slate-400" />
                  </div>
                  <p className="text-slate-900 font-medium">
                    {isDragActive ? "Drop the video here" : "Drag & drop your video"}
                  </p>
                  <p className="text-slate-500 text-sm">or click to browse files</p>
                </>
              )}
            </label>

            {error && (
              <div className="mt-6 p-4 bg-red-50 border border-red-100 rounded-xl flex items-center gap-3 text-red-600">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <p className="text-sm">{error}</p>
              </div>
            )}

            <button
              onClick={handleUpload}
              disabled={!file}
              className="w-full mt-8 bg-slate-900 text-white font-semibold py-4 rounded-xl shadow-lg hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              Process Video
            </button>
          </>
        ) : (
          <div className="text-center py-12">
            <div className="relative w-32 h-32 mx-auto mb-8">
              <div className="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xl font-bold text-slate-900">{progress}%</span>
              </div>
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">Processing...</h2>
            <div className="flex items-center justify-center gap-2 text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{status}</span>
            </div>
            <p className="mt-8 text-sm text-slate-400 max-w-xs mx-auto">
              This might take a few minutes depending on the video length and complexity.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
