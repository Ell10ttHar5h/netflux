#!/usr/bin/env python3
"""
media_to_streaming_mp4.py - Convert MKV / MP4 / AVI / MOV to an MP4 optimized for browser streaming.

Why this differs from a generic container conversion — every setting targets
progressive HTTP playback in web browsers (Safari, Chrome, Firefox, Edge, iOS, Android):

  * H.264 High profile + yuv420p (8-bit)
        The only video combination guaranteed to play everywhere. 10-bit or
        4:4:4 sources are automatically down-converted.
  * AAC-LC stereo @ 48 kHz
        The most universally supported web audio codec/profile.
  * Forced keyframe every 2 seconds
        Seeking/scrubbing lands within ~2 s of the target without downloading
        a huge GOP — the same cadence HLS uses.
  * -movflags +faststart
        Moves the moov index atom to the front of the file so the browser can
        start playback almost immediately instead of waiting for the full
        download (this is what makes progressive streaming work).
  * CRF quality target capped by a max bitrate
        Consistent web-friendly file sizes instead of unbounded local-quality output.

Accepted input containers: .mkv, .mp4, .avi, .mov (anything ffmpeg can read,
but these four are the expected ones). Output is always a streaming-optimized
MP4, regardless of the input container.

Subtitles (--subs):
   vtt    (default) Extract text-based English subs to a .vtt sidecar next to the MP4 so
          browsers can offer them as toggleable soft subtitles (<track> tag).
          Image-based subs are dropped (pass --subs burn to burn them in).
  burn   Burn the first English subtitle track into the video pixels.
         Works for text and image-based subs; visible to every viewer.
         Pass --subs burn explicitly to enable.
  none   Drop all subtitle tracks.

Usage:
    python media_to_streaming_mp4.py input.mkv [output.mp4]
    python media_to_streaming_mp4.py input.avi --subs vtt --crf 23 --maxrate 4M
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

_HERE   = Path(__file__).parent
FFMPEG  = str(_HERE / "ffmpeg.exe")
FFPROBE = str(_HERE / "ffprobe.exe")

# --- Accepted input containers ------------------------------------------------
ACCEPTED_INPUT_EXTS = {".mkv", ".mp4", ".avi", ".mov"}

# --- Web streaming defaults ---------------------------------------------------
DEFAULT_CRF      = 21    # near-transparent quality, far smaller than CRF 18
DEFAULT_MAXRATE  = "5M"  # keeps HD in a sane web bandwidth range
DEFAULT_BUFSIZE  = "10M" # ~2x maxrate (standard VBV sizing)
DEFAULT_PRESET   = "medium"
DEFAULT_AUDIO_BR = "160k"
KEYFRAME_SECONDS = 2     # forced keyframe cadence -> fast seeking


def get_streams(input_path: str) -> list:
    """Use ffprobe to extract all streams from the input file."""
    cmd = [
        FFPROBE,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] ffprobe failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout).get("streams", [])


def get_duration(path: str):
    """Return media duration in seconds, or None if unknown."""
    cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError):
        return None


def find_english_subtitle_index(streams: list) -> tuple[int, bool]:
    """
    Find the subtitle-track index (si=) for the first English subtitle stream.
    'si' is the index among subtitle streams only, not the global stream index.
    Returns (subtitle_stream_index, is_text_based), or (-1, False) if none found.
    """
    subtitle_si = 0
    best_si = -1
    best_is_text = False

    for stream in streams:
        if stream.get("codec_type") != "subtitle":
            continue

        tags = stream.get("tags", {})
        lang = (tags.get("language") or tags.get("LANGUAGE") or "").lower()
        title = (tags.get("title") or tags.get("TITLE") or "").lower()

        is_english = lang in ("eng", "en") or "english" in title

        if is_english:
            codec = stream.get("codec_name", "")
            is_text = codec in ("subrip", "ass", "ssa", "webvtt", "mov_text")
            print(
                f"[INFO] Found English subtitle stream — "
                f"global index #{stream['index']}, subtitle index si={subtitle_si}, "
                f"codec={codec}, lang='{lang}', title='{title}'"
            )
            if best_si == -1:
                best_si = subtitle_si
                best_is_text = is_text
            elif is_text and not best_is_text:
                # Upgrade: prefer text-based over image-based
                best_si = subtitle_si
                best_is_text = True

        subtitle_si += 1

    return best_si, best_is_text


def get_global_subtitle_index(streams: list, subtitle_si: int) -> int:
    """Convert a subtitle-only stream index (si=) to a global stream index."""
    si_count = 0
    for stream in streams:
        if stream.get("codec_type") == "subtitle":
            if si_count == subtitle_si:
                return stream["index"]
            si_count += 1
    return -1


def find_audio_stream_index(streams: list) -> int:
    """
    Pick ONE audio track for web output (smaller file, no ambiguity in the
    browser): prefer an English-language track, otherwise the first one.
    Returns the global stream index, or -1 if there is no audio.
    """
    fallback = -1
    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue

        tags = stream.get("tags", {})
        lang = (tags.get("language") or tags.get("LANGUAGE") or "").lower()
        title = (tags.get("title") or tags.get("TITLE") or "").lower()

        if fallback == -1:
            fallback = stream["index"]
        if lang in ("eng", "en") or "english" in title:
            return stream["index"]
    return fallback


def is_interlaced(streams: list) -> bool:
    """Check if any video stream has interlaced field order."""
    for stream in streams:
        if stream.get("codec_type") != "video":
            continue
        field_order = (stream.get("field_order") or "").lower()
        # Interlaced values: tt, tb, pp, bd, db, bff, tff
        if field_order and field_order not in ("progressive", "progressive_open", ""):
            print(f"[INFO] Video stream is interlaced (field_order={field_order})")
            return True
    return False


def convert(
    input_path: str,
    output_path: str,
    subs: str = "vtt",
    crf: int = DEFAULT_CRF,
    maxrate: str = DEFAULT_MAXRATE,
    bufsize: str = DEFAULT_BUFSIZE,
    preset: str = DEFAULT_PRESET,
    audio_bitrate: str = DEFAULT_AUDIO_BR,
    force_deinterlace: bool = False,
) -> None:
    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Create the output directory structure if it doesn't exist (e.g. out/season01/ep01.mp4)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if not Path(FFMPEG).exists() or not Path(FFPROBE).exists():
        print(
            f"[ERROR] ffmpeg.exe / ffprobe.exe not found next to this script ({_HERE}).",
            file=sys.stderr,
        )
        sys.exit(1)

    if input_file.suffix.lower() not in ACCEPTED_INPUT_EXTS:
        print(
            f"[WARN] Input extension not in {sorted(ACCEPTED_INPUT_EXTS)}: {input_path}"
        )

    if output_file.suffix.lower() != ".mp4":
        print(f"[WARN] Output does not have a .mp4 extension: {output_path}")

    print(f"[INFO] Inspecting streams in: {input_path}")
    streams = get_streams(input_path)

    video_count = sum(1 for s in streams if s.get("codec_type") == "video")
    if video_count == 0:
        print("[ERROR] No video stream found in input.", file=sys.stderr)
        sys.exit(1)

    audio_idx = find_audio_stream_index(streams)
    subtitle_si, is_text = find_english_subtitle_index(streams)

    # --- Decide what to do with subtitles ------------------------------------
    vtt_path = None  # set when we extract a WebVTT sidecar instead of burning

    if subs == "vtt":
        if subtitle_si == -1:
            print("[WARN] No English subtitle track found; nothing to extract.")
            subs = "none"
        elif not is_text:
            print(
                "[WARN] Best English subtitle is image-based (cannot convert to WebVTT); "
                "dropping it. Pass --subs burn to burn image-based subtitles."
            )
            subs = "none"
        else:
            vtt_path = output_file.with_suffix(".vtt")
            print(f"[INFO] Will extract English subtitles to: {vtt_path}")

    # --- Build video filter chain --------------------------------------------
    needs_deinterlace = force_deinterlace or is_interlaced(streams)
    yadif_filter = "yadif=mode=1"  # mode=1 processes only interlaced frames

    vf_filter = None
    filter_complex = None

    if subs == "burn":
        if subtitle_si == -1:
            print(
                "[WARN] No English subtitle track found. "
                "Converting without subtitles."
            )
            vf_filter = yadif_filter if needs_deinterlace else None
        elif is_text:
            escaped = input_path.replace("\\", "/").replace(":", "\\:")
            sub_filter = f"subtitles='{escaped}':si={subtitle_si}"
            vf_filter = f"{yadif_filter},{sub_filter}" if needs_deinterlace else sub_filter
        else:
            global_idx = get_global_subtitle_index(streams, subtitle_si)
            print(
                f"[INFO] Image-based subtitle (global stream #{global_idx}) — "
                "using overlay filter."
            )
            # For image subtitles with deinterlacing, use filter_complex
            if needs_deinterlace:
                filter_complex = f"[0:v]{yadif_filter}[vtmp];[vtmp][0:{global_idx}]overlay[v]"
            else:
                filter_complex = f"[0:v][0:{global_idx}]overlay[v]"
    else:  # "none" (or vtt extraction handled separately)
        vf_filter = yadif_filter if needs_deinterlace else None

    # Log deinterlacing status
    if needs_deinterlace and not force_deinterlace:
        print("[INFO] Deinterlacing enabled (auto-detected interlaced footage)")
    elif force_deinterlace:
        print("[INFO] Deinterlacing enabled (forced via --deinterlace flag)")

    # --- Assemble the ffmpeg command ------------------------------------------
    cmd = [FFMPEG, "-i", input_path]

    if filter_complex:
        cmd += ["-filter_complex", filter_complex]
    elif vf_filter:
        cmd += ["-vf", vf_filter]

    # Explicit stream mapping (once -map is used, ffmpeg's auto-selection is off).
    # NOTE: a bare number in -map means "input file index", so the audio must be
    # referenced as file:stream -> "0:<global_index>".
    for spec in ([ "[v]" ] if filter_complex else [ "0:v:0" ]) + (
        [f"0:{audio_idx}"] if audio_idx != -1 else []
    ):
        cmd += ["-map", spec]

    # Video: universal browser compatibility + fast seeking
    cmd += [
        "-c:v", "libx264",
        "-profile:v", "high",          # H.264 High — plays in every modern browser
        "-pix_fmt", "yuv420p",         # 8-bit 4:2:0 — required for browser playback
        "-crf", str(crf),              # quality target (lower = bigger)
        "-preset", preset,             # encode speed vs. efficiency tradeoff
        "-maxrate", maxrate,           # bitrate cap -> predictable web file sizes
        "-bufsize", bufsize,
        "-force_key_frames", f"expr:gte(t,n_forced*{KEYFRAME_SECONDS})",  # keyframe every N s
    ]

    # Audio: AAC-LC stereo — the most universally supported web audio
    if audio_idx != -1:
        cmd += [
            "-c:a", "aac",
            "-profile:a", "aac_low",   # plain AAC-LC (no HE-AAC quirks)
            "-b:a", audio_bitrate,
            "-ar", "48000",
            "-ac", "2",                # stereo
        ]
    else:
        print("[WARN] No audio stream found; output will be silent.")
        cmd += ["-an"]

    cmd += [
        "-sn",                        # drop remaining subtitle tracks (burned in or extracted)
        "-movflags", "+faststart",    # moov atom up front -> instant start for progressive streaming
        "-y",
        str(output_file),
    ]

    print(f"[INFO] Running ffmpeg:\n  {' '.join(cmd)}\n")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("[ERROR] ffmpeg conversion failed.", file=sys.stderr)
        sys.exit(result.returncode)

    # --- Optional WebVTT sidecar (soft subtitles for the browser) --------------
    if vtt_path is not None:
        print(f"[INFO] Extracting WebVTT subtitles to: {vtt_path}")
        vtt_cmd = [
            FFMPEG, "-i", input_path,
            "-map", f"0:s:{subtitle_si}",
            "-c:s", "webvtt",
            "-y", str(vtt_path),
        ]
        result2 = subprocess.run(vtt_cmd)
        if result2.returncode != 0:
            print(
                "[WARN] WebVTT extraction failed; MP4 was still written without soft subs.",
                file=sys.stderr,
            )

    print_summary(output_file, vtt_path)


def print_summary(output_file: Path, vtt_path) -> None:
    """Report final size / duration / average bitrate so you can gauge bandwidth fit."""
    size_bytes = output_file.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    duration = get_duration(str(output_file))

    print("\n" + "=" * 60)
    print(f"[SUCCESS] Output written to: {output_file}")
    if vtt_path is not None and Path(vtt_path).exists():
        print(
            f"[SUCCESS] Soft subtitles:      {vtt_path}\n"
            "          (serve it alongside the MP4 and add a <track> tag in your HTML)"
        )
    print(f"  Size:     {size_mb:.1f} MB")
    if duration:
        h, rem = divmod(int(duration), 3600)
        m, s = divmod(rem, 60)
        avg_kbps = size_bytes * 8 / duration / 1000
        print(f"  Duration: {h:d}:{m:02d}:{s:02d}")
        print(f"  Avg rate: {avg_kbps:.0f} kbps (video+audio)")


def main():
    parser = argparse.ArgumentParser(
        description="Convert MKV/MP4/AVI/MOV to an MP4 optimized for progressive streaming in web browsers."
    )
    parser.add_argument("input", help="Input file path (MKV, MP4, AVI, MOV or any ffmpeg-readable container)")
    parser.add_argument(
        "output", nargs="?", default=None,
        help="Output MP4 path (default: <input>_web.mp4 next to the input)",
    )
    parser.add_argument(
        "--subs", choices=["burn", "vtt", "none"], default="vtt",
        help="English subtitle handling: extract WebVTT sidecar (default), burn into video, or drop",
    )
    parser.add_argument("--crf", type=int, default=DEFAULT_CRF,
                        help=f"x264 quality target, lower = bigger/better (default {DEFAULT_CRF})")
    parser.add_argument("--maxrate", default=DEFAULT_MAXRATE,
                        help=f"video bitrate cap for web-friendly sizes (default {DEFAULT_MAXRATE})")
    parser.add_argument("--bufsize", default=DEFAULT_BUFSIZE,
                        help=f"VBV buffer size, ~2x maxrate (default {DEFAULT_BUFSIZE})")
    parser.add_argument("--preset", default=DEFAULT_PRESET,
                        help=f"x264 speed/efficiency preset (default {DEFAULT_PRESET})")
    parser.add_argument("--audio-bitrate", default=DEFAULT_AUDIO_BR,
                        help=f"AAC stereo bitrate (default {DEFAULT_AUDIO_BR})")
    parser.add_argument("--deinterlace", action="store_true",
                        help="Force deinterlacing (useful for SD footage)")

    args = parser.parse_args()

    output_path = args.output or str(
        Path(args.input).with_name(Path(args.input).stem + "_web.mp4")
    )

    convert(
        input_path=args.input,
        output_path=output_path,
        subs=args.subs,
        crf=args.crf,
        maxrate=args.maxrate,
        bufsize=args.bufsize,
        preset=args.preset,
        audio_bitrate=args.audio_bitrate,
        force_deinterlace=args.deinterlace,
    )


if __name__ == "__main__":
    main()
