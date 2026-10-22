# Mediaserver Subtitle & Streaming Pipeline

Complete command-line reference for the four scripts in `E:\projects\mediaserver`,
from raw MKV to web-ready MP4 with subtitles.

## Pipeline overview

```
                        ┌─────────────────────────────────────────────────┐
                        │                TEXT-BASED SUBS                  │
 input.mkv ─────────────┤  (SRT/ASS/WebVTT in the MKV)                   │
   │                    └──────────────┬──────────────────────────────────┘
   │                                   ▼
   │                          mkv_to_streaming_mp4.py
   │                          (extract .vtt sidecar or burn)
   │                                   │
   │                                   ▼
   │                            input_web.mp4 + .vtt
   │
   │                    ┌──────────────┴──────────────────────────────────┐
   │                    │         BITMAP SUBS (PGS, Blu-ray style)        │
   │                    └──────────────┬──────────────────────────────────┘
   │                                   ▼
   │                    pgs_to_png.py  (ffmpeg: PGS packs → PNGs + manifest)
   │                                   │
   │                                   ▼
   │                    png_to_vtt.py  (Tesseract OCR → WebVTT)
   │                                   │
   │                                   ▼
   │                            input_web.mp4 + .vtt
   │                            (mkv_to_streaming_mp4.py --subs burn,
   │                             or mux the .vtt in as a soft track)
   ▼
```

**Which path do you need?**

| Subtitle type in the MKV | Path |
|---|---|
| Text-based (SRT/ASS/WebVTT) | `mkv_to_streaming_mp4.py` directly — it extracts the English track to `.vtt` automatically |
| Bitmap (PGS / DVS) | `pgs_to_png.py` → `png_to_vtt.py` → `mkv_to_streaming_mp4.py --subs burn` (or mux the VTT in) |

## Prerequisites

| Dependency | Status | Install |
|---|---|---|
| Python 3.10+ | required | `winget install --id Python.Python.3.13` |
| Pillow | required (by `png_to_vtt.py`) | `pip install pillow` |
| Tesseract OCR 5.x + `eng` | required (by `png_to_vtt.py`) | `winget install --id tesseract-ocr.tesseract` |
| ffmpeg / ffprobe | bundled in project root | already present (`ffmpeg.exe`, `ffprobe.exe`) |

Verify everything:

```bat
cd /d e:\projects\mediaserver && python --version && python -c "import PIL; print(PIL.__version__)" && "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

All scripts prefer `ffmpeg.exe`/`ffprobe.exe` sitting next to the script, and fall
back to `PATH`. Tesseract is auto-detected from the script dir, `PATH`, or
`C:\Program Files\Tesseract-OCR`.

---

## 1. `pgs_to_png.py` — decode PGS subtitle packs to timestamped PNGs

**Purpose.** PGS subtitles are bitmap images (Blu-ray style) — browsers can't
display them and they can't be turned into WebVTT directly. This script decodes
every subtitle *pack* (event) into a crisp white-on-black full-frame PNG, and
writes a `manifest.json` + `manifest.tsv` mapping each PNG to its exact
start/end timestamps.

**How it works.** `ffprobe -show_frames` enumerates every subtitle pack with its
PTS; one `ffmpeg` pass renders the whole subtitle stream onto a black base
(color source + `overlay` filter — the `subtitles`/`ass` filters refuse bitmap
subs); the rendered frame closest to each event's midpoint is copied out.

### Usage

```bat
python pgs_to_png.py input.mkv
```

### Options

| Option | Default | Description |
|---|---|---|
| `input` | (required) | Input MKV or any ffmpeg-readable container |
| `--si N` | first English, else first | Subtitle stream index, 0-based **among subtitle streams** (not the global stream index) |
| `--out DIR` | `<input_stem>_pgs_pngs` next to input | Output directory for the PNGs + manifest |
| `--fps FPS` | auto (≥ 2, safe for the shortest subtitle) | Render frame rate |
| `--list` | off | List subtitle streams and exit (dry run) |
| `--keep-clears` | off | Also emit PNGs for empty "clear" packs (default: visible subs only) |
| `--force` | off | Overwrite an existing output directory |

### Full execution examples

```bat
:: List the subtitle streams in the file first (recommended)
cd /d e:\projects\mediaserver && python pgs_to_png.py test\video_file.mkv --list

:: Decode subtitle stream #1 into test\video_file_pgs1, overwriting if present
cd /d e:\projects\mediaserver && python pgs_to_png.py test\video_file.mkv --si 1 --out test\video_file_pgs1 --force
```

**Output** (in the `--out` directory):

```
test\video_file_pgs1\
├── manifest.json      # machine-readable: events[] with file/start/end/start_tc/end_tc
├── manifest.tsv       # human-readable: id  file  start_sec  end_sec  start_tc  end_tc
├── sub_00001.png      # 1920x1080, white text on black — OCR-ready
├── sub_00002.png
└── ...
```

---

## 2. `png_to_vtt.py` — OCR the PNGs into WebVTT

**Purpose.** Closes the loop: OCRs each PNG with Tesseract and assembles a WebVTT
file using the manifest timestamps. This is the "PGS → soft subs" step.

**OCR settings (tuned for clean English bitmap subs on black).**

1. Grayscale + content bounding-box crop (removes black frame padding)
2. Invert to black-on-white (Tesseract prefers dark text on light)
3. Upscale small crops up to 3× (Lanczos) so glyph height is OCR-friendly
4. Tesseract 5 LSTM, `lang=eng`, `--psm 6` (uniform block of text)

Benchmarked against PSM 7/11, the legacy engine (`--oem 1`), Otsu binarization,
and RapidOCR — this combination won. Expect ~95%+ accuracy on clean English
bitmap subs; occasional italic-font quirks (e.g. dropped apostrophes) may need
spot-fixing in the VTT.

**Caching.** OCR results are stored in `<png_dir>\ocr_cache.json` keyed by PNG
filename. Re-runs skip already-OCRed frames, so tweaking `--psm`/`--lang` is
free. Delete the cache file (or `--no-cache`) to force a full re-OCR.

### Usage

```bat
python png_to_vtt.py test\video_file_pgs1
```

### Options

| Option | Default | Description |
|---|---|---|
| `png_dir` | (required) | Directory containing `sub_*.png` and `manifest.json` |
| `--out PATH` | `<png_dir>/<dir_name>.vtt` | Output `.vtt` path |
| `--force` | off | Overwrite an existing output VTT |
| `--limit N` | all events | Only process the first N events (smoke test) |
| `--lang CODE` | `eng` | Tesseract language |
| `--psm N` | `6` | Tesseract page segmentation mode |
| `--tesseract PATH` | auto-detect | Path to the tesseract binary |
| `--no-cache` | off | Ignore and do not update `ocr_cache.json` |

### Full execution examples

```bat
:: Smoke test - first 20 frames only (~2 seconds)
cd /d e:\projects\mediaserver && python png_to_vtt.py test\video_file_pgs1 --limit 20

:: Full run (overwrites the existing VTT)
cd /d e:\projects\mediaserver && python png_to_vtt.py test\video_file_pgs1 --force

:: Custom output location
cd /d e:\projects\mediaserver && python png_to_vtt.py test\video_file_pgs1 --out C:\subs\video_file_en.vtt --force

:: Force a full re-OCR (e.g. after changing --psm)
cd /d e:\projects\mediaserver && python png_to_vtt.py test\video_file_pgs1 --no-cache --force
```

**Output example** (`test\video_file_pgs1.vtt`):

```
WEBVTT
Language: en

1
00:00:21.021 --> 00:00:23.023
[upbeat music playing]

2
00:00:34.701 --> 00:00:36.662
[narrator] 7/his is Berk.
```

**Typical full-run summary:**

```
[SUCCESS] 1964 cues from 1964 events (0 empty, 0 missing, 20 cached)
  output:  test\video_file_pgs1.vtt
  cache:   test\video_file_pgs1\ocr_cache.json
  timing:  1944 OCR'd in 171.4s (11.3 img/s)
```

---

## 3. `mkv_to_streaming_mp4.py` — MKV → browser-optimized MP4

**Purpose.** Convert an MKV to an MP4 where *every* setting targets progressive
HTTP playback in web browsers (Safari, Chrome, Firefox, Edge, iOS, Android):

- **H.264 High + `yuv420p` (8-bit)** — the only video combo guaranteed to play
  everywhere; 10-bit / 4:4:4 sources are auto-down-converted
- **AAC-LC stereo @ 48 kHz** — the most universally supported web audio profile
- **Keyframe every 2 s** — seeking/scrubbing lands within ~2 s (same cadence as HLS)
- **`-movflags +faststart`** — `moov` atom moved to the front so playback starts
  almost immediately (this is what makes progressive streaming work)
- **CRF capped by a max bitrate** — sane web file sizes

**Subtitle handling (`--subs`).**

| Value | Behavior |
|---|---|
| `vtt` (default) | Extract the English text-based subs to a `.vtt` sidecar next to the MP4 (toggleable soft subs via `<track>`). Falls back to burn-in if only image-based subs exist. |
| `burn` | Burn the first English subtitle track into the video pixels (works for text *and* bitmap subs; visible to every viewer) |
| `none` | Drop all subtitle tracks |

### Usage

```bat
python mkv_to_streaming_mp4.py input.mkv [output.mp4]
```

### Options

| Option | Default | Description |
|---|---|---|
| `input` | (required) | Input MKV or any ffmpeg-readable container |
| `output` | `<input>_web.mp4` next to input | Output MP4 path |
| `--subs {vtt,burn,none}` | `vtt` | English subtitle handling (see table above) |
| `--crf N` | `21` | x264 quality target, lower = bigger/better |
| `--maxrate SIZE` | `5M` | Video bitrate cap for web-friendly sizes |
| `--bufsize SIZE` | `10M` | VBV buffer size, ~2× maxrate |
| `--preset NAME` | `medium` | x264 speed/efficiency preset |
| `--audio-bitrate SIZE` | `160k` | AAC stereo bitrate |
| `--deinterlace` | off | Force deinterlacing (useful for SD footage) |

### Full execution examples

```bat
:: Defaults - text subs extracted to a .vtt sidecar
cd /d e:\projects\mediaserver && python mkv_to_streaming_mp4.py test\video_file.mkv

:: Explicit output path + quality tuning
cd /d e:\projects\mediaserver && python mkv_to_streaming_mp4.py test\video_file.mkv test\video_file_web.mp4 --crf 23 --maxrate 4M

:: Burn the English subs into the picture (the right choice for PGS sources)
cd /d e:\projects\mediaserver && python mkv_to_streaming_mp4.py test\video_file.mkv --subs burn

:: No subtitles at all
cd /d e:\projects\mediaserver && python mkv_to_streaming_mp4.py test\video_file.mkv --subs none
```

---

## 4. `mkv_to_mp4.py` — simple MKV → MP4 with English burn-in

**Purpose.** Minimal converter: MKV to MP4, auto-detects the first English
subtitle stream and burns it in (text or bitmap). Use when you just need a
portable MP4 with visible subs and don't care about web-tuned settings.

### Usage

```bat
python mkv_to_mp4.py input.mkv output.mp4
```

### Options

| Option | Default | Description |
|---|---|---|
| `input` | (required) | Input MKV file path |
| `output` | (required) | Output MP4 file path |
| `--deinterlace` | off | Force deinterlacing (useful for SD footage) |

### Full execution examples

```bat
cd /d e:\projects\mediaserver && python mkv_to_mp4.py test\video_file.mkv test\video_file_burned.mp4

:: SD interlaced source
cd /d e:\projects\mediaserver && python mkv_to_mp4.py test\sd_show.mkv test\sd_show.mp4 --deinterlace
```

---

## Full end-to-end workflows

### A. PGS (bitmap) subs → web MP4 with soft WebVTT subtitles

The complete chain, start to finish. Replace `test\video_file.mkv` with your file.

```bat
:: 0) Verify prerequisites
cd /d e:\projects\mediaserver && python --version && python -c "import PIL; print(PIL.__version__)" && "C:\Program Files\Tesseract-OCR\tesseract.exe" --version

:: 1) See what subtitle streams the file has (pick the English one)
cd /d e:\projects\mediaserver && python pgs_to_png.py test\video_file.mkv --list

:: 2) Decode PGS packs to timestamped PNGs (stream #1 in this example)
cd /d e:\projects\mediaserver && python pgs_to_png.py test\video_file.mkv --si 1 --out test\video_file_pgs1 --force

:: 3) Smoke test the OCR on the first 20 frames
cd /d e:\projects\mediaserver && python png_to_vtt.py test\video_file_pgs1 --limit 20

:: 4) Full OCR run -> WebVTT
cd /d e:\projects\mediaserver && python png_to_vtt.py test\video_file_pgs1 --force

:: 5) Convert to a browser-optimized MP4.
::    The MKV's own subs are bitmap, so burn them in:
cd /d e:\projects\mediaserver && python mkv_to_streaming_mp4.py test\video_file.mkv test\video_file_web.mp4 --subs burn
```

Result: `test\video_file_web.mp4` (streaming-ready, subs burned) + `test\video_file_pgs1.vtt`
(the soft-sub sidecar you can attach to any player or `<video><track>` tag).

**Alternative for step 5 — mux the generated VTT as a soft track**
(skips burn-in; viewers can toggle subs on/off):

```bat
cd /d e:\projects\mediaserver && ffmpeg -i test\video_file.mkv -i test\video_file_pgs1.vtt -map 0 -map 1 -c copy -c:s mov_text -metadata:s:s:0 language=eng -movflags +faststart test\video_file_soft.mp4
```

### B. Text-based subs (SRT/ASS/WebVTT in the MKV) → web MP4

One command — the script extracts the English track to a `.vtt` sidecar
automatically:

```bat
cd /d e:\projects\mediaserver && python mkv_to_streaming_mp4.py test\text_subs.mkv test\text_subs_web.mp4
```

### C. Just need a portable MP4 with visible subs

```bat
cd /d e:\projects\mediaserver && python mkv_to_mp4.py test\video_file.mkv test\video_file.mp4
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `tesseract not found` from `png_to_vtt.py` | `winget install --id tesseract-ocr.tesseract`, or pass `--tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe"` |
| `No manifest.json in ...` | Run `pgs_to_png.py` on that directory first (or point `png_to_vtt.py` at the folder that contains `manifest.json`) |
| Wrong language/track being decoded | `python pgs_to_png.py input.mkv --list`, then re-run with the correct `--si N` |
| OCR text slightly off (e.g. `We re Vikings.`) | Expected italic-font OCR noise; spot-fix in the `.vtt`, or retry with `--psm 11 --no-cache --force` (results are cached, so experiments are cheap) |
| VTT won't overwrite | It exists by design — add `--force` |
| Re-OCR everything after regenerating PNGs | `python png_to_vtt.py <dir> --no-cache --force` (or delete `<dir>\ocr_cache.json`) |
| MP4 won't play in browser | Use `mkv_to_streaming_mp4.py` (H.264 High + yuv420p + AAC + faststart) rather than a generic transcode |

## File layout after a full run

```
e:\projects\mediaserver\
├── ffmpeg.exe / ffprobe.exe        # bundled binaries
├── pgs_to_png.py                   # step 1: PGS -> PNGs + manifest
├── png_to_vtt.py                   # step 2: PNGs -> WebVTT (Tesseract)
├── mkv_to_streaming_mp4.py         # step 3: MKV -> browser MP4
├── mkv_to_mp4.py                   # alternative: simple MKV -> MP4 burn-in
├── SUBTITLE_PIPELINE.md            # this file
└── test\
    ├── video_file.mkv                   # source
    ├── video_file_pgs1\                 # step 1 output
    │   ├── manifest.json
    │   ├── manifest.tsv
    │   ├── ocr_cache.json          # step 2 cache
    │   └── sub_*.png
    ├── video_file_pgs1.vtt              # step 2 output
    └── video_file_web.mp4               # step 3 output
```
