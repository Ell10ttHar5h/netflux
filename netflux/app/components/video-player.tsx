"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const PRIMARY_SOURCE =
  "/familyontheedge.mp4";
const FALLBACK_SOURCE = "/sample.mp4";

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function VideoPlayer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [src, setSrc] = useState(PRIMARY_SOURCE);
  const [fileName, setFileName] = useState("familyontheedge.mp4");
  const [usingFallback, setUsingFallback] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [loop, setLoop] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const onFsChange = () =>
      setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }, []);

  const seekTo = (time: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = time;
    setCurrentTime(time);
  };

  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  };

  const changeVolume = (value: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = value;
    video.muted = value === 0;
    setVolume(value);
    setMuted(video.muted);
  };

  const toggleFullscreen = () => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen();
  };

  const loadFile = (file: File | undefined) => {
    if (!file) return;
    setSrc(URL.createObjectURL(file));
    setFileName(file.name);
    setUsingFallback(false);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "SELECT") return;
      switch (e.key.toLowerCase()) {
        case " ":
        case "k":
          e.preventDefault();
          togglePlay();
          break;
        case "arrowright":
          seekTo((videoRef.current?.currentTime ?? 0) + 5);
          break;
        case "arrowleft":
          seekTo(Math.max(0, (videoRef.current?.currentTime ?? 0) - 5));
          break;
        case "m":
          toggleMute();
          break;
        case "f":
          toggleFullscreen();
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay]);

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div
      ref={containerRef}
      className="group w-full overflow-hidden rounded-xl bg-black shadow-lg"
    >
      <video
        ref={videoRef}
        src={src}
        loop={loop}
        playsInline
        preload="metadata"
        onClick={togglePlay}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onError={() => {
          if (src === PRIMARY_SOURCE) {
            setSrc(FALLBACK_SOURCE);
            setFileName("Local sample — primary source unavailable");
            setUsingFallback(true);
            setCurrentTime(0);
            setDuration(0);
          }
        }}
        className="aspect-video w-full cursor-pointer bg-black"
      >
        Your browser does not support the video tag.
      </video>

      <div className="flex flex-col gap-2 bg-zinc-900 px-4 py-3 text-zinc-100">
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={currentTime}
          onChange={(e) => seekTo(Number(e.target.value))}
          aria-label="Seek"
          className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-zinc-700 accent-white"
          style={{
            background: `linear-gradient(to right, #fff ${progress}%, #3f3f46 ${progress}%)`,
          }}
        />

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <button
            onClick={togglePlay}
            aria-label={isPlaying ? "Pause" : "Play"}
            className="rounded-md bg-white px-3 py-1.5 font-medium text-black transition-colors hover:bg-zinc-200"
          >
            {isPlaying ? "Pause" : "Play"}
          </button>

          <span className="tabular-nums text-zinc-300">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleMute}
              aria-label={muted ? "Unmute" : "Mute"}
              className="rounded-md px-2 py-1 transition-colors hover:bg-zinc-700"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5">
                <path d="M3 9v6h4l5 5V4L7 9H3z" />
                {muted || volume === 0 ? (
                  <path d="M16.5 8.5 21 13m0-4.5L16.5 13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
                ) : (
                  <path d="M16 8a5 5 0 0 1 0 8" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
                )}
              </svg>
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={muted ? 0 : volume}
              onChange={(e) => changeVolume(Number(e.target.value))}
              aria-label="Volume"
              className="h-1 w-24 cursor-pointer accent-white"
            />
          </div>

          <label className="flex items-center gap-2">
            Speed
            <select
              value={playbackRate}
              onChange={(e) => {
                const rate = Number(e.target.value);
                setPlaybackRate(rate);
                if (videoRef.current) videoRef.current.playbackRate = rate;
              }}
              className="rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1"
            >
              {[0.5, 1, 1.5, 2].map((r) => (
                <option key={r} value={r}>
                  {r}x
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={loop}
              onChange={(e) => setLoop(e.target.checked)}
              className="accent-white"
            />
            Loop
          </label>

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="rounded-md border border-zinc-600 px-3 py-1.5 transition-colors hover:bg-zinc-700"
            >
              Open file…
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => loadFile(e.target.files?.[0])}
            />
            <button
              onClick={toggleFullscreen}
              aria-label="Toggle fullscreen"
              className="rounded-md border border-zinc-600 px-3 py-1.5 transition-colors hover:bg-zinc-700"
            >
              {isFullscreen ? "Exit FS" : "Fullscreen"}
            </button>
          </div>
        </div>

        {usingFallback && (
          <p className="text-xs font-medium text-amber-400">
            Primary source failed to load — showing local sample. Fix the
            PRIMARY_SOURCE url in video-player.tsx, or pick a file manually.
          </p>
        )}
        <p className="truncate text-xs text-zinc-400">{fileName}</p>
      </div>
    </div>
  );
}
