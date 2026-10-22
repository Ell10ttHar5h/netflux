#!/usr/bin/env python3
"""
pgs_to_png.py - Decode PGS (Blu-ray bitmap) subtitle frames from an MKV into
individual PNG images, each paired with its display timestamp.

Why this exists:
  PGS subtitles are bitmap images, not text. Browsers cannot display them and
  they cannot be converted to WebVTT directly. The route to soft subs is:

      PGS -> PNG + timestamps (this script) -> OCR -> assemble WebVTT

How it works:
  1. ffprobe -show_frames enumerates every subtitle "pack" (event) with its
     exact PTS. num_rects == 0 marks the empty "clear" packs.
  2. One ffmpeg pass renders the whole subtitle stream onto a black
     full-frame base (lavfi color source + overlay filter, the same filter
     used for PGS burn-in). Note: the `subtitles`/`ass` filters refuse
     bitmap subs ("Only text based subtitles are currently supported"),
     which is why overlay is used.
  3. For each visible event, the rendered frame closest to the event's
     midpoint is copied out. Each PNG therefore shows exactly that subtitle,
     crisp on a black background (ideal for OCR).
  4. A manifest (JSON + TSV) maps each PNG to its start/end timestamps.

Frame-index math (verified empirically):
  rendered frame N (1-based) is at t = (N-1)/fps, so the frame for time t is
  1-based index round(t*fps)+1  (0-based: round(t*fps)).

Usage:
  python pgs_to_png.py input.mkv
  python pgs_to_png.py input.mkv --list
  python pgs_to_png.py input.mkv --si 1 --out C:\\subs_pngs --force
"""

import sys
import json
import math
import shutil
import argparse
import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def find_binary(stem: str) -> str:
    """Prefer ffmpeg/ffprobe shipped next to this script, else PATH."""
    for name in (f"{stem}.exe", stem):
        p = _HERE / name
        if p.exists():
            return str(p)
    return stem


FFMPEG = find_binary("ffmpeg")
FFPROBE = find_binary("ffprobe")


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def probe_streams(input_path: str) -> list:
    r = run([FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_streams", input_path])
    if r.returncode != 0:
        sys.exit(f"[ERROR] ffprobe failed:\n{r.stderr.strip()}")
    return json.loads(r.stdout).get("streams", [])


def probe_events(input_path: str, si: int) -> list:
    r = run([FFPROBE, "-v", "quiet", "-select_streams", f"s:{si}",
             "-show_frames", "-of", "json", input_path])
    if r.returncode != 0:
        sys.exit(f"[ERROR] ffprobe -show_frames failed:\n{r.stderr.strip()}")
    return json.loads(r.stdout).get("frames", [])


def to_timecode(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode PGS subtitle frames from an MKV into timestamped PNGs.")
    parser.add_argument("input", help="Input file (MKV or any ffmpeg-readable container)")
    parser.add_argument("--si", type=int, default=None,
                        help="Subtitle stream index, 0-based among subtitle streams "
                             "(default: first English, else first)")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: <input_stem>_pgs_pngs next to input)")
    parser.add_argument("--fps", type=float, default=None,
                        help="Render frame rate (default: auto >= 2, safe for the shortest subtitle)")
    parser.add_argument("--list", action="store_true", help="List subtitle streams and exit")
    parser.add_argument("--keep-clears", action="store_true",
                        help="Also emit PNGs for empty 'clear' packs (default: visible subs only)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing output directory")
    args = parser.parse_args()

    input_path = args.input
    if not Path(input_path).exists():
        sys.exit(f"[ERROR] Input file not found: {input_path}")

    streams = probe_streams(input_path)
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]

    if args.list:
        if not subs:
            print("No subtitle streams.")
            return
        print(f"Subtitle streams in {input_path}:")
        for i, s in enumerate(subs):
            tags = s.get("tags", {})
            print(f"  si={i}  global #{s['index']:<3} codec={s.get('codec_name','?'):<20} "
                  f"lang={tags.get('language','?'):<5} title={tags.get('title','')}")
        return

    if not subs:
        sys.exit("[ERROR] No subtitle streams in input.")

    # --- Pick the subtitle stream --------------------------------------------
    if args.si is not None:
        if not 0 <= args.si < len(subs):
            sys.exit(f"[ERROR] --si {args.si} out of range (0..{len(subs)-1}).")
        si = args.si
    else:
        si = 0
        for i, s in enumerate(subs):
            tags = s.get("tags", {})
            lang = (tags.get("language") or "").lower()
            title = (tags.get("title") or "").lower()
            if lang in ("eng", "en") or "english" in title:
                si = i
                break
    chosen = subs[si]
    codec = chosen.get("codec_name", "")
    tags = chosen.get("tags", {})
    print(f"[INFO] Subtitle stream si={si} (global #{chosen['index']}): "
          f"codec={codec} lang={tags.get('language','?')} title={tags.get('title') or ''}")
    if codec in ("subrip", "ass", "ssa", "webvtt", "mov_text"):
        print("[WARN] This stream is TEXT-based. Extracting to SRT/VTT directly is simpler "
              "than PNG+OCR; this script is intended for bitmap (PGS/DVB) subs.")

    # --- Enumerate events -----------------------------------------------------
    print("[INFO] Enumerating subtitle events (ffprobe -show_frames)...")
    frames = probe_events(input_path, si)
    events = []
    for i, f in enumerate(frames):
        pt = f.get("pts_time")
        if pt in (None, "", "N/A"):
            continue
        start = float(pt)
        nxt = frames[i + 1].get("pts_time") if i + 1 < len(frames) else None
        end = float(nxt) if nxt not in (None, "", "N/A") else None
        events.append({"start": start, "end": end, "num_rects": f.get("num_rects", 0)})
    if not events:
        sys.exit("[ERROR] No subtitle events found in stream.")
    print(f"[INFO] {len(events)} subtitle packs: "
          f"{sum(1 for e in events if e['num_rects'] > 0)} visible, "
          f"{sum(1 for e in events if e['num_rects'] == 0)} clear")

    emit = [e for e in events if e["num_rects"] > 0] if not args.keep_clears else events
    if not emit:
        sys.exit("[ERROR] Nothing to emit (all packs are empty clears).")

    # --- Pick a safe render frame rate ----------------------------------------
    # The frame closest to an event's midpoint is guaranteed to fall inside the
    # event's window as long as frame spacing (1/fps) < window length.
    windows = [e["end"] - e["start"] for e in emit if e["end"] is not None]
    min_win = min(windows) if windows else 1.0
    fps = args.fps if args.fps is not None else max(2.0, math.ceil(1.0 / min_win))
    if 1.0 / fps >= min_win:
        sys.exit(f"[ERROR] fps={fps} too low: shortest emitted window is {min_win:.3f}s "
                 f"(need fps > {1.0 / min_win:.2f}). Raise --fps.")
    print(f"[INFO] Shortest window {min_win:.3f}s -> rendering at {fps:g} fps")

    # Cap the render at the last event so the infinite color source doesn't
    # keep emitting color-only frames after the subtitle stream ends.
    ends = [e["end"] for e in events if e["end"] is not None]
    render_end = max(max(ends) if ends else 0.0, events[-1]["start"] + 5.0)

    # --- Prepare output --------------------------------------------------------
    out_dir = (Path(args.out) if args.out
               else Path(input_path).with_name(Path(input_path).stem + "_pgs_pngs"))
    if out_dir.exists():
        existing = list(out_dir.glob("sub_*.png"))
        if existing and not args.force:
            sys.exit(f"[ERROR] {out_dir} already contains {len(existing)} PNGs. "
                     f"Use --force to overwrite.")
        for f in existing:
            f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Video size for the black base (PGS is full-frame; match the movie).
    w, h = 1920, 1080
    for s in streams:
        if s.get("codec_type") == "video" and s.get("width") and s.get("height"):
            w, h = s["width"], s["height"]
            break

    tmp_dir = out_dir / "_render_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()
    pattern = str(tmp_dir / "out_%06d.png")

    # --- Render pass -----------------------------------------------------------
    cmd = [
        FFMPEG, "-hide_banner",
        "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps:g}",
        "-i", input_path,
        "-filter_complex", f"[0:v][1:s:{si}]overlay=format=auto[v]",
        "-map", "[v]",
        "-t", f"{render_end:.3f}",
        "-c:v", "png",
        "-y", pattern,
    ]
    print(f"[INFO] Rendering subtitle stream onto black {w}x{h} base "
          f"({render_end:.0f}s @ {fps:g} fps, ~{render_end * fps:.0f} frames) ...")
    print("       " + " ".join(cmd))
    r = run(cmd)
    if r.returncode != 0:
        print(r.stderr[-3000:], file=sys.stderr)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(f"[ERROR] ffmpeg render failed (code {r.returncode}).")

    rendered = sorted(tmp_dir.glob("out_*.png"))
    if not rendered:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit("[ERROR] Render produced no frames.")
    expected = render_end * fps
    if len(rendered) > expected * 3 + 100:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(f"[ERROR] Render produced {len(rendered)} frames, expected ~{expected:.0f}. "
                 f"Frame-rate runaway — aborting to avoid garbage output.")
    print(f"[INFO] Render produced {len(rendered)} frames (expected ~{expected:.0f})")

    # --- Sample one frame per event -------------------------------------------
    manifest_events = []
    for n, e in enumerate(emit, start=1):
        if e["end"] is not None:
            mid = (e["start"] + e["end"]) / 2.0
        else:
            mid = e["start"] + 0.3  # last pack: unknown end, sample shortly after start
        idx = max(0, min(int(round(mid * fps)), len(rendered) - 1))
        dst = out_dir / f"sub_{n:05d}.png"
        shutil.copy2(rendered[idx], dst)
        manifest_events.append({
            "index": n,
            "file": dst.name,
            "start": e["start"],
            "end": e["end"],
            "start_tc": to_timecode(e["start"]),
            "end_tc": to_timecode(e["end"]) if e["end"] is not None else None,
            "num_rects": e["num_rects"],
        })

    # --- Manifest ---------------------------------------------------------------
    manifest = {
        "source": str(Path(input_path).resolve()),
        "subtitle_stream": {
            "si": si,
            "global_index": chosen["index"],
            "codec": codec,
            "language": tags.get("language"),
            "title": tags.get("title"),
        },
        "render_fps": fps,
        "frame_count": len(manifest_events),
        "events": manifest_events,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with open(out_dir / "manifest.tsv", "w", encoding="utf-8", newline="") as fh:
        fh.write("index\tfile\tstart\tend\tstart_tc\tend_tc\n")
        for e in manifest_events:
            fh.write(f"{e['index']}\t{e['file']}\t{e['start']:.3f}\t"
                     f"{e['end'] if e['end'] is not None else ''}\t"
                     f"{e['start_tc']}\t{e['end_tc'] or ''}\n")

    shutil.rmtree(tmp_dir, ignore_errors=True)

    # --- Summary -----------------------------------------------------------------
    total = sum(f.stat().st_size for f in out_dir.glob("sub_*.png"))
    first, last = manifest_events[0], manifest_events[-1]
    print("=" * 62)
    print(f"[SUCCESS] {len(manifest_events)} subtitle PNGs in: {out_dir}")
    print(f"  first: {first['file']}  {first['start_tc']}  ({first['start']:.3f}s)")
    print(f"  last:  {last['file']}   {last['start_tc']}  ({last['start']:.3f}s)")
    print(f"  total PNG size: {total / 1_048_576:.1f} MB")
    print("  manifest: manifest.json / manifest.tsv")
    print("  next step: OCR each PNG and pair with start/end to build WebVTT")


if __name__ == "__main__":
    main()
