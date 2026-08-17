import VideoPlayer from "./components/video-player";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <header className="w-full border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
        <h1 className="text-lg font-semibold tracking-tight text-black dark:text-zinc-50">
          netflux
        </h1>
      </header>

      <main className="flex w-full max-w-4xl flex-col gap-6 px-6 py-12">
        <VideoPlayer />
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Shortcuts: Space/K play-pause, ←/→ seek 5s, M mute, F fullscreen.
        </p>
      </main>
    </div>
  );
}
