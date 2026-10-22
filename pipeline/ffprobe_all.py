#!/usr/bin/env python3
"""
Pull all available metadata from a media file using ffprobe.
Outputs a single JSON object to stdout.
Requires ffprobe (part of FFmpeg) to be installed and on PATH.
"""

import json
import subprocess
import sys
from pathlib import Path


def run_ffprobe(args: list) -> dict:
    """Run ffprobe with the given extra args and return parsed JSON."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")

    return json.loads(result.stdout) if result.stdout else {}


def get_full_metadata(filepath: str, include_frames: bool, include_packets: bool) -> dict:
    if not Path(filepath).exists():
        raise FileNotFoundError(f"No such file: {filepath}")

    metadata = run_ffprobe([
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-show_programs",
        "-show_error",
        "-show_data_hash", "sha256",
        filepath,
    ])

    if include_frames:
        frame_data = run_ffprobe(["-show_frames", filepath])
        metadata["frames"] = frame_data.get("frames", [])

    if include_packets:
        packet_data = run_ffprobe(["-show_packets", filepath])
        metadata["packets"] = packet_data.get("packets", [])

    return metadata


def main():
    if len(sys.argv) < 2:
        print("Usage: python probe_all.py <file> [--frames] [--packets]", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    include_frames = "--frames" in sys.argv
    include_packets = "--packets" in sys.argv

    try:
        metadata = get_full_metadata(filepath, include_frames, include_packets)
    except (FileNotFoundError, RuntimeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()