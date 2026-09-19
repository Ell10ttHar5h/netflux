# Video Player Component — Build Specification

| | |
|---|---|
| **Component** | `VideoPlayer` (`netflux/app/components/video-player.tsx`) |
| **Status** | Implemented (this document specifies the current build in detail) |
| **Framework** | Next.js 16.2.6 (App Router, Turbopack), React 19, TypeScript, Tailwind CSS v4 |
| **Component type** | Client component (`"use client"` — uses hooks, DOM events, Fullscreen API) |
| **Consumed by** | `netflux/app/page.tsx` (home page, rendered inside `<main class="max-w-4xl">`) |

---

## 1. Purpose & Scope

The Video Player is a self-contained HTML5 video player for the netflux home page. It plays a
server-hosted MP4 by default, degrades gracefully when that source fails, and lets the user load an
arbitrary local video file. All playback state lives inside the component; it takes **no props**.

**In scope:** source selection & fallback, transport controls (play/pause/seek/volume/speed/loop),
local file loading, cross-platform fullscreen, keyboard shortcuts, time display, error surfacing.

**Out of scope:** multi-track audio/subtitle selection, picture-in-picture, HLS/DASH streaming,
playlist management, persistence of playback position.

---

## 2. Functional Requirements

### 2.1 Source handling & fallback

| ID | Requirement |
|----|-------------|
| FR-01 | The component SHALL define two module-level constants: `PRIMARY_SOURCE = "/familyontheedge.mp4"` and `FALLBACK_SOURCE = "/sample.mp4"`. |
| FR-02 | On mount, the `<video>` element SHALL use `src={PRIMARY_SOURCE}`. |
| FR-03 | If a `error` event fires **and** the active source is `PRIMARY_SOURCE`, the component SHALL switch `src` to `FALLBACK_SOURCE`, set the displayed file name to `"Local sample — primary source unavailable"`, flag `usingFallback = true`, and reset `currentTime`/`duration` to 0. |
| FR-04 | If an error fires while already on the fallback (or a user-loaded) source, the component SHALL NOT attempt further fallbacks; it SHALL leave the current state as-is. |
| FR-05 | While `usingFallback` is true, the component SHALL render an amber warning line: *"Primary source failed to load — showing local sample. Fix the PRIMARY_SOURCE url in video-player.tsx, or pick a file manually."* |
| FR-06 | The `<video>` element SHALL contain fallback text for browsers without HTML5 video support: *"Your browser does not support the video tag."* |

### 2.2 Transport controls

| ID | Requirement |
|----|-------------|
| FR-10 | **Play/Pause.** A button SHALL toggle playback based on `video.paused` (call `play()` when paused, else `pause()`). The button label SHALL read `Pause` while playing and `Play` otherwise. Clicking the video surface itself SHALL also toggle play/pause. |
| FR-11 | **Seek bar.** A range input (`min=0`, `max=duration || 0`, `step=0.1`) bound to `currentTime`. Changing it SHALL set `video.currentTime` and update state immediately (no debounce). The filled portion of the track SHALL be rendered white up to `progress = currentTime/duration*100%` via an inline `linear-gradient(to right, #fff {p}%, #3f3f46 {p}%)`; the unfilled remainder is zinc (`#3f3f46`). |
| FR-12 | **Time display.** A text node SHALL show `{formatTime(currentTime)} / {formatTime(duration)}` using tabular numerals. `formatTime` SHALL render `m:ss` with zero-padded seconds, and return `"0:00"` for non-finite input (e.g., before metadata loads). |
| FR-13 | **Mute.** A button SHALL toggle `video.muted`. Its icon is an inline SVG speaker; when muted **or** volume is 0 it SHALL show a crossed-out variant, otherwise sound-wave arcs. |
| FR-14 | **Volume slider.** Range input (`min=0`, `max=1`, `step=0.05`). Setting a value SHALL assign `video.volume` and force `muted = true` when the value is 0 (unmuting requires moving above 0). The displayed value SHALL be `0` while muted, otherwise the current volume. |
| FR-15 | **Playback speed.** A `<select>` labeled "Speed" with options `0.5x, 1x, 1.5x, 2x`. Changing it SHALL set both component state and `video.playbackRate` directly. Default is `1x`. |
| FR-16 | **Loop.** A checkbox labeled "Loop" SHALL bind to the `<video loop>` attribute. Default off. |

### 2.3 Local file loading

| ID | Requirement |
|----|-------------|
| FR-20 | An **"Open file…"** button SHALL open a hidden `<input type="file" accept="video/*">`. |
| FR-21 | Selecting a file SHALL create an object URL (`URL.createObjectURL`) and set it as the active `src`, display the file's name, and clear the fallback flag. |

### 2.4 Fullscreen (cross-platform)

The component MUST work on desktop browsers **and** mobile Safari, which do not implement the
standard element Fullscreen API.

| ID | Requirement |
|----|-------------|
| FR-30 | A button SHALL toggle fullscreen; its label reads `Exit FS` while in any fullscreen mode, else `Fullscreen`. The target of standard fullscreen is the **player container** (video + controls), not just the video element. |
| FR-31 | **Exit precedence.** On toggle, exit whichever mode is active, checked in this order: ① `document.fullscreenElement` → `document.exitFullscreen()`; ② `document.webkitFullscreenElement` → `webkitExitFullscreen()`; ③ iOS inline fullscreen (tracked via ref) → `video.webkitExitFullscreen()`. |
| FR-32 | **Enter precedence.** When not in any fullscreen mode: ① if `video.webkitEnterFullscreen` exists as a function (iOS Safari), use the video's native **inline** fullscreen; ② else call `container.requestFullscreen()`; ③ else fall back to `container.webkitRequestFullscreen()`. |
| FR-33 | All Fullscreen API calls SHALL be wrapped in `try/catch`; rejections/throws (e.g., interrupted user gestures, unsupported environments) are silently ignored. |
| FR-34 | **State sync.** `isFullscreen` SHALL be derived from: `document.fullscreenElement` or `document.webkitFullscreenElement` via a `fullscreenchange` listener; plus the iOS-only pair of events on the video element — `webkitbeginfullscreen` / `webkitendfullscreen` — which also maintain an `iosInlineFsRef` boolean (iOS inline fullscreen never sets `document.fullscreenElement`). |
| FR-35 | Event listeners added in the mount effect SHALL be removed on unmount. |

### 2.5 Keyboard shortcuts

A single `window` `keydown` listener SHALL implement:

| Key | Action | Notes |
|-----|--------|-------|
| `Space` or `K` / `k` | Toggle play/pause | `preventDefault()` to stop page scroll |
| `→` (ArrowRight) | Seek **+5 s** from current time | |
| `←` (ArrowLeft) | Seek **−5 s**, clamped at 0 | `Math.max(0, t − 5)` |
| `M` / `m` | Toggle mute | |
| `F` / `f` | Toggle fullscreen | |

| ID | Requirement |
|----|-------------|
| FR-40 | Shortcuts SHALL be **suppressed** when the event target is an `<input>` or `<select>` (so typing in form fields doesn't trigger playback). Key matching is case-insensitive via `e.key.toLowerCase()`. |

### 2.6 Status line

| ID | Requirement |
|----|-------------|
| FR-50 | Below the controls, a truncated single-line label SHALL always show the active file name (default `"familyontheedge.mp4"`). |

---

## 3. Component Architecture

### 3.1 State model

| State | Type / Default | Driven by |
|-------|----------------|-----------|
| `src` | `string`, `PRIMARY_SOURCE` | mount, error fallback, file load |
| `fileName` | `string`, `"familyontheedge.mp4"` | fallback switch, file load |
| `usingFallback` | `boolean`, `false` | error handler |
| `isPlaying` | `boolean`, `false` | video `play` / `pause` events |
| `currentTime` | `number`, `0` | `timeupdate` events, seek actions |
| `duration` | `number`, `0` | `loadedmetadata` event |
| `volume` | `number`, `1` | volume slider |
| `muted` | `boolean`, `false` | mute button / volume=0 |
| `loop` | `boolean`, `false` | loop checkbox |
| `playbackRate` | `number`, `1` | speed select |
| `isFullscreen` | `boolean`, `false` | fullscreenchange + iOS webkit events |

### 3.2 Refs

| Ref | Target | Purpose |
|-----|--------|---------|
| `videoRef` | `<video>` | imperative playback API (`play/pause/currentTime/volume/muted/playbackRate`) |
| `containerRef` | outer wrapper `<div>` | standard-fullscreen target (includes controls) |
| `fileInputRef` | hidden file input | programmatic `.click()` from "Open file…" button |
| `iosInlineFsRef` | — (boolean flag) | tracks iOS inline fullscreen, which is invisible to the document-level Fullscreen API |

### 3.3 Effects & lifecycle

1. **Mount effect (`[]`)** — registers `fullscreenchange` on `document` and `webkitbeginfullscreen` /
   `webkitendfullscreen` on the video element; cleans all three up on unmount.
2. **Keyboard effect (`[togglePlay]`)** — attaches/detaches the window `keydown` handler.

### 3.4 Data flow principle

The `<video>` DOM node is the source of truth for playback; React state mirrors it for rendering.
Control handlers mutate the element first, then sync state (e.g., `changeVolume` sets
`video.volume`, *then* `setVolume`). Media events (`play`, `pause`, `timeupdate`,
`loadedmetadata`, `error`) push DOM → state.

### 3.5 Render tree

```
div.containerRef            group w-full overflow-hidden rounded-md bg-black shadow-lg
├── video.videoRef          aspect-video w-full cursor-pointer bg-black
│                           (src, loop, playsInline, preload="metadata", onClick=togglePlay)
└── div.controls            flex flex-col gap-2 bg-zinc-900 px-4 py-3 text-zinc-100
    ├── input[range]        seek bar (gradient-filled track, h-1.5, aria-label "Seek")
    └── div.row             flex flex-wrap items-center gap-x-4 gap-y-2 text-sm
        ├── button          Play / Pause  (bg-white text-black hover:bg-zinc-200)
        ├── span            time display  (tabular-nums text-zinc-300)
        ├── div             mute button (SVG icon) + volume slider (w-24, accent-white)
        ├── label+select    Speed: 0.5x / 1x / 1.5x / 2x
        ├── label+checkbox  Loop (accent-white)
        └── div.ml-auto     "Open file…" button + hidden file input + Fullscreen/Exit FS button
    [conditional] p         amber-400 fallback warning (only when usingFallback)
    p                       truncated file name (text-xs text-zinc-400)
```

---

## 4. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | **Styling.** Tailwind v4 utility classes only; no CSS modules or inline styles except the seek-bar gradient fill and (none other). Corner radius is `rounded-md` (6 px) on the container and all buttons — deliberately tighter than the original 12 px (`rounded-xl`). Palette: black video area, `zinc-900` control bar, white accents. |
| NFR-02 | **Performance.** `<video preload="metadata">` so only headers + metadata are fetched before first play; no full-file download on mount (the primary asset is ~200 MB). |
| NFR-03 | **Streaming compatibility.** The served MP4 MUST be browser-streamable: H.264/AVC video, AAC audio, `moov` atom at front (`faststart`). The server MUST support HTTP byte-range requests (`Accept-Ranges: bytes`, `206 Partial Content`) for seeking — Next.js static file serving satisfies this; verified against `/familyontheedge.mp4`. |
| NFR-04 | **Accessibility.** Every icon-only control carries an `aria-label` (Play/Pause, Mute/Unmute, Seek, Volume, Toggle fullscreen). Controls are real `<button>`/`<input>` elements (keyboard-focusable), not divs. |
| NFR-05 | **Cross-platform.** Must work on desktop Chrome/Firefox/Safari and mobile Safari (iOS) including inline fullscreen; Android uses the standard Fullscreen API path. `playsInline` is set so iOS does not force native takeover on tap-to-play. |
| NFR-06 | **Robustness.** All imperative DOM access is null-guarded (`videoRef.current?.…`). Fullscreen calls are exception-safe (FR-33). Non-finite durations render as `0:00` rather than `NaN`. |
| NFR-07 | **Type safety.** Must pass `npx tsc --noEmit` and the project ESLint config. WebKit-prefixed APIs are typed via local intersection types (`WebkitVideo`, `WebkitDoc`) — no `any`. |

---

## 5. Platform / Fullscreen Behavior Matrix

| Environment | Enter path (FR-32) | Exit path (FR-31) | State source (FR-34) |
|-------------|--------------------|-------------------|----------------------|
| Desktop Chrome/Firefox/Safari, Android | `container.requestFullscreen()` | `document.exitFullscreen()` | `fullscreenchange` → `document.fullscreenElement` |
| Legacy WebKit | `container.webkitRequestFullscreen()` | `doc.webkitExitFullscreen()` | `webkitFullscreenElement` |
| iOS Safari (iPhone/iPad) | `video.webkitEnterFullscreen()` — native inline fullscreen, video only | `video.webkitExitFullscreen()` | `webkitbeginfullscreen` / `webkitendfullscreen` + `iosInlineFsRef` |

---

## 6. Acceptance Criteria

1. **Load:** opening the home page shows a black 16:9 area; metadata loads without downloading the full file (Network tab: no full-range GET before interaction).
2. **Play/pause:** button, video click, and `Space`/`K` all toggle playback; label and icon state stay in sync.
3. **Seek:** dragging the bar jumps instantly; filled gradient tracks position; `←`/`→` move ±5 s (never below 0); time readout updates live.
4. **Volume/mute:** slider changes volume; setting it to 0 mutes and shows the crossed speaker icon; `M` toggles mute.
5. **Speed & loop:** 2× plays at double speed; with Loop on, playback restarts at end of file.
6. **Fallback:** with `/familyontheedge.mp4` unavailable (e.g., renamed in `public/`), the player switches to `/sample.mp4`, shows the amber warning and the "Local sample…" name — no blank screen, no console crash loop.
7. **File open:** selecting a local `.mp4` plays it and displays its file name; fallback flag clears.
8. **Fullscreen desktop:** `F` or button enters fullscreen covering video + controls; label flips to `Exit FS`; Esc or toggle exits; state stays consistent through OS-level exit (Esc).
9. **Fullscreen iOS Safari:** tapping Fullscreen on an iPhone enters native inline fullscreen and the button reads `Exit FS`; exiting (swipe down / tap) restores the normal layout with correct button state.
10. **Keyboard hygiene:** shortcuts do not fire while focus is in a form control; Space does not scroll the page.
11. **Build gates:** `npx tsc --noEmit` clean, `npm run build` succeeds, ESLint passes.

---

## 7. Known Limitations & Open Issues (for future iterations)

| # | Item | Detail |
|---|------|--------|
| L-1 | Object URLs are never revoked | Repeated "Open file…" loads accumulate `URL.createObjectURL` blobs; should call `revokeObjectURL` on the previous URL when replacing it. |
| L-2 | Keyboard guard is incomplete | Only `INPUT`/`SELECT` targets are ignored — `TEXTAREA` and `contenteditable` elements would still trigger shortcuts. |
| L-3 | Seek bar inert before metadata | Until `loadedmetadata`, `max=0`; the slider renders but can't be used (acceptable, but a disabled state would be clearer). |
| L-4 | No buffering indicator | Network stalls show no visual feedback; consider a spinner on `waiting`/`stalled` events. |
| L-5 | Playback rate not re-applied after source change | Browsers reset `playbackRate` to 1 when `src` changes, but the select keeps showing the old value until the user interacts. |
| L-6 | Controls always visible | No auto-hide/hover behavior; controls occupy permanent vertical space below the video (by design for now). |

---

## 8. Integration Notes

- **Page:** `app/page.tsx` renders `<VideoPlayer />` inside a centered `max-w-4xl` column and prints
  the shortcut legend beneath it: *"Shortcuts: Space/K play-pause, ←/→ seek 5s, M mute, F fullscreen."*
- **Assets:** `public/familyontheedge.mp4` (primary, ~200 MB, faststart H.264/AAC) and
  `public/sample.mp4` (fallback). Both are served by Next.js static file handling with range support.
- **Hosting:** for LAN access the app is run as a production build (`npm run build && npm start`);
  dev-mode cross-origin HMR is separately configured via `allowedDevOrigins` in `next.config.ts`.
