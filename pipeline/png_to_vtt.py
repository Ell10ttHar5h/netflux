#!/usr/bin/env python3
"""
png_to_vtt.py - OCR timestamped subtitle PNGs (from pgs_to_png.py) into WebVTT.

Pipeline:
    PGS -> pgs_to_png.py -> sub_*.png + manifest.json -> this script -> .vtt

Why this exists:
  PGS subtitles are bitmap images. pgs_to_png.py decodes each subtitle pack
  into a crisp white-on-black PNG with exact start/end timestamps. This script
  closes the loop: it OCRs each PNG with Tesseract and assembles a WebVTT file
  using the manifest timestamps, giving you soft subs a browser can display.

OCR quality notes (tuned for clean English bitmap subs on black):
  1. Grayscale + content bounding-box crop (removes the black frame padding).
  2. Invert to black-on-white (Tesseract prefers dark text on light).
  3. Upscale small crops up to 3x (Lanczos) so glyph height is OCR-friendly.
  4. Tesseract 5 LSTM, lang=eng, --psm 6 (uniform block of text).

Caching:
  OCR results are stored in <png_dir>/ocr_cache.json keyed by PNG filename.
  Re-runs (e.g. tweaking --psm) skip already-OCRed frames. Delete the cache
  file (or use --no-cache) to force a full re-OCR.

Requirements:
  - Tesseract on PATH, next to this script, or in C:\\Program Files\\Tesseract-OCR
    (winget install --id tesseract-ocr.tesseract)
  - Pillow (pip install pillow)

Usage:
  python png_to_vtt.py test\\httyd_pgs1
  python png_to_vtt.py test\\httyd_pgs1 --limit 20        # smoke test
  python png_to_vtt.py test\\httyd_pgs1 --out C:\\subs\\httyd_en.vtt --force
"""

import sys
import json
import time
import shutil
import argparse
import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def find_tesseract(explicit: str = None) -> str:
    """Resolve the tesseract binary: explicit flag, next to script, PATH, common dirs."""
    if explicit:
        if Path(explicit).exists():
            return explicit
        sys.exit(f"[ERROR] --tesseract path not found: {explicit}")
    p = _HERE / "tesseract.exe"
    if p.exists():
        return str(p)
    w = shutil.which("tesseract")
    if w:
        return w
    for cand in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if Path(cand).exists():
            return cand
    sys.exit("[ERROR] tesseract not found. Install with "
             "'winget install --id tesseract-ocr.tesseract' or pass --tesseract.")


try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("[ERROR] Pillow is required: pip install pillow")


def preprocess(src: Path, dst: Path) -> bool:
    """Crop to text bbox, invert, upscale. Returns False if nothing visible."""
    im = Image.open(src).convert("L")
    # Find extent of bright pixels (text is light on a black base).
    bbox = im.point(lambda p: 255 if p >= 24 else 0).getbbox()
    if bbox is None:
        return False
    x0, y0, x1, y1 = bbox
    pad = max(16, int(0.05 * max(x1 - x0, y1 - y0)))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(im.width, x1 + pad)
    y1 = min(im.height, y1 + pad)
    crop = im.crop((x0, y0, x1, y1))
    if crop.height < 200:
        scale = min(3, max(2, 200 // max(crop.height, 1)))
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)),
                           Image.LANCZOS)
    ImageOps.invert(crop).save(dst)
    return True


def ocr_image(tess: str, img: Path, lang: str, psm: int) -> str:
    r = subprocess.run([tess, str(img), "stdout", "-l", lang, "--psm", str(psm)],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"tesseract failed (code {r.returncode}): {r.stderr.strip()}")
    return r.stdout


def clean_text(raw: str) -> str:
    """Normalize: collapse whitespace, drop blank lines, keep line structure."""
    import re
    lines = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def to_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR subtitle PNGs (from pgs_to_png.py) into a WebVTT file.")
    parser.add_argument("png_dir",
                        help="Directory containing sub_*.png and manifest.json")
    parser.add_argument("--out", default=None,
                        help="Output .vtt path (default: <png_dir>/<dir_name>.vtt)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing output VTT")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N events (smoke test)")
    parser.add_argument("--lang", default="eng",
                        help="Tesseract language (default: eng)")
    parser.add_argument("--psm", type=int, default=6,
                        help="Tesseract page segmentation mode (default: 6)")
    parser.add_argument("--tesseract", default=None,
                        help="Path to tesseract binary (default: auto-detect)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore and do not update ocr_cache.json")
    args = parser.parse_args()

    png_dir = Path(args.png_dir)
    if not (png_dir / "manifest.json").exists():
        sys.exit(f"[ERROR] No manifest.json in {png_dir} (run pgs_to_png.py first).")
    manifest = json.loads((png_dir / "manifest.json").read_text(encoding="utf-8"))
    events = manifest["events"]
    if args.limit is not None:
        events = events[:args.limit]
    if not events:
        sys.exit("[ERROR] No events in manifest.")

    tess = find_tesseract(args.tesseract)
    print(f"[INFO] Tesseract: {tess}")
    print(f"[INFO] {len(events)} events, lang={args.lang} psm={args.psm}")

    out_path = (Path(args.out) if args.out
                else png_dir.with_name(png_dir.name + ".vtt"))
    if out_path.exists() and not args.force:
        sys.exit(f"[ERROR] {out_path} already exists. Use --force to overwrite.")

    cache_path = png_dir / "ocr_cache.json"
    cache = {}
    if not args.no_cache and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            print(f"[INFO] Loaded OCR cache: {len(cache)} entries")
        except (json.JSONDecodeError, OSError):
            cache = {}

    tmp_img = png_dir / "_ocr_tmp.png"
    cues = []          # (start, end, text)
    empty = 0
    missing = 0
    cached_hits = 0
    last_dur = None
    t0 = time.time()

    for i, e in enumerate(events, 1):
        fname = e["file"]
        if fname in cache:
            text = clean_text(cache[fname])
            cached_hits += 1
        else:
            src = png_dir / fname
            if not src.exists():
                print(f"[WARN] {i}/{len(events)}: missing {fname}, skipping")
                missing += 1
                continue
            try:
                if not preprocess(src, tmp_img):
                    text = ""
                    print(f"[WARN] {i}/{len(events)}: no visible text in {fname}")
                else:
                    text = clean_text(ocr_image(tess, tmp_img, args.lang, args.psm))
            except RuntimeError as ex:
                sys.exit(f"[ERROR] {ex}")
            cache[fname] = text
            if i % 100 == 0:
                elapsed = time.time() - t0
                print(f"[INFO] {i}/{len(events)} OCR'd "
                      f"({(i - cached_hits) / max(elapsed, 0.001):.1f} img/s)")

        if not text:
            empty += 1
            continue

        start = e["start"]
        end = e["end"]
        if end is None:
            # Last pack: manifest has no end. Use last known duration, else 2s.
            end = start + (last_dur if last_dur else 2.0)
        else:
            last_dur = end - start
        cues.append((start, end, text))

    tmp_img.unlink(missing_ok=True)

    # --- Write cache -----------------------------------------------------------
    if not args.no_cache:
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    # --- Write VTT ---------------------------------------------------------------
    lines = ["WEBVTT", "Language: en", ""]
    for n, (s, e, text) in enumerate(cues, 1):
        lines += [str(n), f"{to_ts(s)} --> {to_ts(e)}", text, ""]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    # --- Summary ------------------------------------------------------------------
    elapsed = time.time() - t0
    ocrd = len(events) - cached_hits - missing
    print("=" * 62)
    print(f"[SUCCESS] {len(cues)} cues from {len(events)} events "
          f"({empty} empty, {missing} missing, {cached_hits} cached)")
    print(f"  output:  {out_path}")
    print(f"  cache:   {cache_path if not args.no_cache else '(disabled)'}")
    print(f"  timing:  {ocrd} OCR'd in {elapsed:.1f}s"
          + (f" ({ocrd / max(elapsed, 0.001):.1f} img/s)" if ocrd else ""))
    if cues:
        first, last = cues[0], cues[-1]
        print(f"  first: {to_ts(first[0])}  {first[2].splitlines()[0][:50]!r}")
        print(f"  last:  {to_ts(last[0])}   {last[2].splitlines()[0][:50]!r}")


if __name__ == "__main__":
    main()
