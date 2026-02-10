#!/usr/bin/env python3
"""
crawl_podcasts.py — Download deepfake-themed podcasts/talks for Phase 3.

Downloads audio from YouTube, converts to 44.1 kHz mono WAV, and names
them podcast_<key>.wav so deepfake-diss.ck can pick them up automatically.

Usage:
  uv run python crawl_podcasts.py              # download all
  uv run python crawl_podcasts.py --list       # show what's available
  uv run python crawl_podcasts.py --only bbc   # download one by key
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
SAMPLE_RATE = 44100

# ──────────────────────────────────────────────────────────────────────────────
# PODCAST / TALK DATABASE
# Format: (key, title, subtitle, host_label, youtube_url, trim_seconds)
#   key        → output file: podcast_<key>.wav
#   trim_seconds → optional (start, end) to grab just a segment; None = full
# ──────────────────────────────────────────────────────────────────────────────

PODCASTS = [
    # ── Already have these; script will skip if file exists ──
    ("wsj",
     "The Journal",
     "Her Client Was Deepfaked. She Says xAI Is to Blame.",
     "WSJ",
     "https://www.youtube.com/watch?v=jKBi1wMJl1Y",
     None),

    ("ted",
     "TED Talks",
     "Fake videos of real people — and how to spot them",
     "TED",
     "https://www.youtube.com/watch?v=o2DDU4g0PRo",
     None),

    ("cnbc",
     "CNBC",
     "The Rise of AI Deepfakes",
     "CNBC",
     "https://www.youtube.com/watch?v=pkF2-R_yjDI",
     None),

    # ── New downloads ──
    ("60min",
     "60 Minutes",
     "Dark Sides of Artificial Intelligence — Deepfakes",
     "CBS",
     "https://www.youtube.com/watch?v=Yb1GCjmw8_8",
     None),

    ("bbc",
     "BBC News",
     "Deepfake scams — How AI became the con artist's best tool",
     "BBC",
     "https://www.youtube.com/watch?v=ohmajJTcpNk",
     None),

    ("vice",
     "VICE",
     "Deepfakes: The Danger of Artificial Intelligence",
     "VICE",
     "https://www.youtube.com/watch?v=gLoI9hAX9dw",
     None),

    ("vox",
     "Vox",
     "The most urgent threat of deepfakes isn't politics",
     "Vox",
     "https://www.youtube.com/watch?v=hHHCrf2-x6w",
     None),

    ("nbc",
     "NBC News",
     "Experts warn deepfakes and AI could threaten elections",
     "NBC",
     "https://www.youtube.com/watch?v=xe0ZfDXma9Y",
     None),
]


def download_podcast(key, title, subtitle, host, url, trim, force=False):
    """Download a single podcast from YouTube as 44.1 kHz mono WAV."""
    out_path = BASE_DIR / f"podcast_{key}.wav"

    if out_path.exists() and not force:
        size_mb = out_path.stat().st_size / 1e6
        print(f"  [skip] podcast_{key}.wav already exists ({size_mb:.1f} MB)")
        return True

    print(f"  [{key}] Downloading: {title} — {subtitle}")
    print(f"         {url}")

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--postprocessor-args", f"ffmpeg:-ar {SAMPLE_RATE} -ac 1",
        "-o", str(out_path.with_suffix(".%(ext)s")),
        "--no-playlist",
        "--socket-timeout", "30",
        "--retries", "3",
    ]

    # Optional time trimming
    if trim:
        start, end = trim
        cmd.extend(["--download-sections", f"*{start}-{end}"])

    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            err = [l for l in result.stderr.split("\n") if "ERROR" in l]
            print(f"  [ERROR] yt-dlp failed: {' '.join(err)[:300]}")
            # Print full stderr for debugging
            if not err:
                print(f"  [STDERR] {result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] Download timed out")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

    if out_path.exists():
        size_mb = out_path.stat().st_size / 1e6
        print(f"  [OK] podcast_{key}.wav ({size_mb:.1f} MB)")
        return True
    else:
        # yt-dlp might have saved with a slightly different name
        for f in BASE_DIR.glob(f"podcast_{key}.*"):
            if f.suffix == ".wav":
                print(f"  [OK] {f.name}")
                return True
        print(f"  [WARN] File not found after download")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download deepfake-themed podcasts")
    parser.add_argument("--list", action="store_true", help="List available podcasts")
    parser.add_argument("--only", type=str, default=None,
                        help="Download only this key (e.g. 'bbc')")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if file exists")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable podcasts:\n")
        for key, title, subtitle, host, url, trim in PODCASTS:
            out = BASE_DIR / f"podcast_{key}.wav"
            status = "✓" if out.exists() else "✗"
            size = f" ({out.stat().st_size / 1e6:.1f} MB)" if out.exists() else ""
            print(f"  [{status}] {key:8s}  {title} — {subtitle}{size}")
        print()
        return

    targets = PODCASTS
    if args.only:
        targets = [(k, t, s, h, u, tr) for k, t, s, h, u, tr in PODCASTS
                    if k == args.only]
        if not targets:
            print(f"Unknown key: {args.only}")
            print(f"Available: {', '.join(k for k, *_ in PODCASTS)}")
            return

    print(f"\n{'=' * 60}")
    print(f"Downloading {len(targets)} podcast(s)")
    print(f"{'=' * 60}\n")

    ok = 0
    for key, title, subtitle, host, url, trim in targets:
        if download_podcast(key, title, subtitle, host, url, trim, args.force):
            ok += 1
        print()

    print(f"\n{'=' * 60}")
    print(f"Done: {ok}/{len(targets)} podcasts ready")
    print(f"{'=' * 60}")

    # Show what's on disk
    existing = sorted(BASE_DIR.glob("podcast_*.wav"))
    print(f"\nPodcast files on disk:")
    for f in existing:
        print(f"  {f.name}  ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
