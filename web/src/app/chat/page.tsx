"use client";

import { useState, useRef, useEffect } from "react";
import { 
  Send, Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX, 
  MessageSquare, Loader2, Maximize2 
} from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
  timestamps?: Array<{
    timestamp: number;
    formatted: string;
    context: string;
  }>;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoName, setVideoName] = useState<string | null>(null);
  const [videoExt, setVideoExt] = useState<string>("mp4");
  
  // Video Player States
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [showControls, setShowControls] = useState(true);
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const controlsTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const storedVideoId = localStorage.getItem("current_video_id");
    const storedVideoName = localStorage.getItem("current_video_name");
    const storedVideoExt = localStorage.getItem("current_video_ext");
    
    if (storedVideoId) setVideoId(storedVideoId);
    if (storedVideoName) setVideoName(storedVideoName);
    if (storedVideoExt) setVideoExt(storedVideoExt);
    else if (storedVideoName) {
      const ext = storedVideoName.split(".").pop() || "mp4";
      setVideoExt(ext);
    }
    
    setMessages([
      {
        id: "1",
        role: "assistant",
        content: `I've analyzed your video. You can ask me to find specific scenes or explain concepts from the video. I'll jump directly to the right time for you!`,
      },
    ]);
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Video Control Handlers
  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) videoRef.current.pause();
      else videoRef.current.play();
      setIsPlaying(!isPlaying);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const skip = (amount: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime += amount;
    }
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value);
    setVolume(value);
    if (videoRef.current) {
      videoRef.current.volume = value;
      setIsMuted(value === 0);
    }
  };

  const toggleMute = () => {
    if (videoRef.current) {
      const newMute = !isMuted;
      setIsMuted(newMute);
      videoRef.current.muted = newMute;
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    setCurrentTime(time);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
    }
  };

  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return [h, m, s]
      .map(v => v < 10 ? "0" + v : v)
      .filter((v, i) => v !== "00" || i > 0)
      .join(":");
  };

  const handleMouseMove = () => {
    setShowControls(true);
    if (controlsTimeoutRef.current) clearTimeout(controlsTimeoutRef.current);
    controlsTimeoutRef.current = setTimeout(() => setShowControls(false), 3000);
  };

  const handleSend = async () => {
    if (!input.trim() || !videoId) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: videoId, query: input }),
      });

      if (!response.ok) throw new Error("Failed to get answer");

      const data = await response.json();
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.answer,
        timestamp: data.timestamp,
        timestamps: data.citations?.map((cit: { timestamp?: string; visual_summary?: string }) => ({
          timestamp: cit.timestamp || 0,
          formatted: cit.timestamp || "00:00",
          context: cit.visual_summary?.substring(0, 100) + "..." || ""
        })) || []
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (data.timestamp !== undefined && videoRef.current) {
        videoRef.current.currentTime = data.timestamp;
        videoRef.current.play();
        setIsPlaying(true);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "Sorry, I encountered an error while processing your request.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-screen bg-slate-950 flex flex-col overflow-hidden text-slate-100">
      {/* Top Navigation / Header */}
      <header className="h-16 border-b border-white/10 flex items-center justify-between px-6 bg-slate-900/50 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center font-bold text-white shadow-lg shadow-primary/20">
            V
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-tight truncate max-w-[200px] md:max-w-md">
              {videoName || "Processing Video..."}
            </h1>
            <p className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold">AI Video Insight</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-full border border-white/10">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-xs font-medium text-slate-300">Analysis Engine Online</span>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top: Video Player Section */}
        <div className="h-[60%] flex flex-col bg-black relative group" onMouseMove={handleMouseMove}>
          <div className="flex-1 flex items-center justify-center p-4 bg-gradient-to-b from-slate-900 to-black">
            <video
              ref={videoRef}
              src={`${API_BASE}/data/uploads/${videoId}.${videoExt}`}
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={handleLoadedMetadata}
              onClick={togglePlay}
              className="max-w-full max-h-full rounded-lg shadow-2xl transition-transform duration-500"
            />
          </div>

          {/* Custom Video Controls */}
          <div className={cn(
            "absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black via-black/80 to-transparent transition-opacity duration-300",
            showControls ? "opacity-100" : "opacity-0 pointer-events-none"
          )}>
            {/* Progress Bar */}
            <div className="group/progress relative h-1.5 mb-6 cursor-pointer">
              <input
                type="range"
                min="0"
                max={duration || 0}
                value={currentTime}
                onChange={handleSeek}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
              />
              <div className="absolute inset-0 bg-white/20 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-primary relative"
                  style={{ width: `${(currentTime / (duration || 1)) * 100}%` }}
                >
                  <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-lg scale-0 group-hover/progress:scale-100 transition-transform"></div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <button onClick={togglePlay} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                  {isPlaying ? <Pause className="w-6 h-6 fill-white" /> : <Play className="w-6 h-6 fill-white" />}
                </button>
                <button onClick={() => skip(-10)} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                  <RotateCcw className="w-5 h-5" />
                </button>
                <button onClick={() => skip(10)} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                  <RotateCw className="w-5 h-5" />
                </button>
                <div className="flex items-center gap-3 ml-2 group/volume">
                  <button onClick={toggleMute} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                    {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
                  </button>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={volume}
                    onChange={handleVolumeChange}
                    className="w-0 group-hover/volume:w-20 transition-all duration-300 h-1 bg-white/20 rounded-full appearance-none cursor-pointer overflow-hidden [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:rounded-full"
                  />
                </div>
                <div className="text-xs font-mono text-slate-300 ml-4">
                  <span>{formatTime(currentTime)}</span>
                  <span className="mx-1 text-slate-500">/</span>
                  <span className="text-slate-500">{formatTime(duration)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="p-2 hover:bg-white/10 rounded-full transition-colors">
                  <Maximize2 className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom: Chat Sidebar (Now as a section below video) */}
        <div className="flex-1 bg-slate-900 border-t border-white/5 flex flex-col shadow-2xl relative z-20">
          {/* Chat Header */}
          <div className="p-4 border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-primary/20 rounded-xl flex items-center justify-center border border-primary/20">
                <MessageSquare className="w-4 h-4 text-primary" />
              </div>
              <div>
                <h2 className="font-bold text-xs">AI Scene Assistant</h2>
                <p className="text-[9px] text-slate-500 uppercase tracking-tighter">Semantic Search Enabled</p>
              </div>
            </div>
          </div>

          {/* Messages */}
          <div 
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth bg-slate-900/50"
          >
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex flex-col max-w-[80%]",
                  msg.role === "user" ? "ml-auto items-end" : "mr-auto items-start"
                )}
              >
                <div
                  className={cn(
                    "p-3 rounded-2xl text-xs leading-relaxed shadow-sm transition-all",
                    msg.role === "user"
                      ? "bg-primary text-white rounded-tr-none"
                      : "bg-white/5 text-slate-200 border border-white/5 rounded-tl-none"
                  )}
                >
                  {msg.content}
                  {(msg.timestamp !== undefined || msg.timestamps) && (
                    <div className="mt-3 space-y-2">
                      {/* Primary timestamp jump */}
                      {msg.timestamp !== undefined && (
                        <button
                          onClick={() => {
                            if (videoRef.current) {
                              videoRef.current.currentTime = msg.timestamp!;
                              videoRef.current.play();
                              setIsPlaying(true);
                            }
                          }}
                          className="flex items-center gap-2 text-[10px] font-bold text-primary-foreground bg-primary/20 hover:bg-primary/30 transition-all px-3 py-1.5 rounded-xl border border-primary/20 w-full justify-center"
                        >
                          <Play className="w-3 h-3 fill-current" />
                          JUMP TO {formatTime(msg.timestamp)}
                        </button>
                      )}
                      
                      {/* All timestamp references */}
                      {msg.timestamps && msg.timestamps.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-[9px] text-slate-400 font-semibold mb-2">📍 ALL REFERENCES IN VIDEO:</p>
                          {msg.timestamps.map((ts, idx) => (
                            <button
                              key={idx}
                              onClick={() => {
                                if (videoRef.current) {
                                  videoRef.current.currentTime = ts.timestamp;
                                  videoRef.current.play();
                                  setIsPlaying(true);
                                }
                              }}
                              className="flex items-start gap-2 text-[9px] bg-white/5 hover:bg-white/10 transition-all px-2 py-1.5 rounded-lg border border-white/10 w-full text-left"
                            >
                              <Play className="w-3 h-3 fill-primary mt-0.5 flex-shrink-0" />
                              <div className="flex-1 min-w-0">
                                <div className="font-bold text-primary">{ts.formatted}</div>
                                {ts.context && (
                                  <div className="text-slate-400 truncate mt-0.5">{ts.context}</div>
                                )}
                              </div>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-slate-500 text-[10px] font-medium animate-pulse">
                <Loader2 className="w-3 h-3 animate-spin text-primary" />
                Analyzing video segments...
              </div>
            )}
          </div>

          {/* Input area */}
          <div className="p-4 bg-slate-950/50 border-t border-white/5">
            <div className="relative group max-w-4xl mx-auto">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Find a scene, summarize, or ask..."
                className="w-full bg-white/5 border border-white/10 rounded-2xl py-3 pl-5 pr-12 text-xs focus:ring-2 focus:ring-primary/20 focus:border-primary/30 transition-all placeholder:text-slate-600 text-slate-100"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 w-8 h-8 bg-primary text-white rounded-xl flex items-center justify-center hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-primary/20"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
