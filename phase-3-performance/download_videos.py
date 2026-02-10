#!/usr/bin/env python3
"""
download_videos.py — Download podcast + rap music videos for ChuGL playback.

ChuGL's Video class requires MPEG1 video / MP2 audio (.mpg).
This script:
  1. Downloads YouTube videos via yt-dlp
  2. Converts to MPEG1 via ffmpeg
  3. Trims to relevant segments (saves disk space)

Usage:
  uv run python download_videos.py              # download all
  uv run python download_videos.py --podcasts   # podcasts only
  uv run python download_videos.py --rap        # rap only
"""

import subprocess
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
PODCAST_VIDEO_DIR = BASE_DIR / "podcast_videos"
RAP_VIDEO_DIR = BASE_DIR / "rap_videos"

# ── Resolution: 480p is enough (we're showing inside a ChuGL window) ──
VIDEO_RES = "480"

# ── PODCAST VIDEOS (deepfake-related YouTube videos) ──
# Each maps to a podcast_*.wav already in our library
PODCAST_VIDEOS = [
    {
        "id": "podcast_ted",
        "url": "https://www.youtube.com/watch?v=o2DDU4g0PRo",  # Supasorn Suwajanakorn: Fake videos of real people
        "title": "TED Talks",
        "trim_start": "00:00:10",
        "trim_duration": "00:10:00",
    },
    {
        "id": "podcast_wsj",
        "url": "https://www.youtube.com/watch?v=FPwQEw-Bxoc",  # WSJ: Deepfakes are getting real
        "title": "WSJ - The Journal",
        "trim_start": "00:00:00",
        "trim_duration": "00:10:00",
    },
    {
        "id": "podcast_bbc",
        "url": "https://www.youtube.com/watch?v=T6mNpmjMZBk",  # BBC: AI deepfake scams
        "title": "BBC News",
        "trim_start": "00:00:00",
        "trim_duration": "00:10:00",
    },
    {
        "id": "podcast_cnbc",
        "url": "https://www.youtube.com/watch?v=lI4OOVQbbFs",  # CNBC: The Rise of AI Deepfakes
        "title": "CNBC",
        "trim_start": "00:00:00",
        "trim_duration": "00:12:00",
    },
    {
        "id": "podcast_vice",
        "url": "https://www.youtube.com/watch?v=OathO-Hz8Mc",  # VICE: Deepfakes
        "title": "VICE",
        "trim_start": "00:00:00",
        "trim_duration": "00:10:00",
    },
    {
        "id": "podcast_vox",
        "url": "https://www.youtube.com/watch?v=gLoI9hAX9dw",  # Vox: Deepfakes explained
        "title": "Vox",
        "trim_start": "00:00:00",
        "trim_duration": "00:08:00",
    },
    {
        "id": "podcast_nbc",
        "url": "https://www.youtube.com/watch?v=1OqFY_2JE1c",  # NBC: AI deepfake threats
        "title": "NBC News",
        "trim_start": "00:00:00",
        "trim_duration": "00:08:00",
    },
    {
        "id": "podcast_60min",
        "url": "https://www.youtube.com/watch?v=FkGTsJTfJSU",  # 60 Minutes: Deepfakes
        "title": "60 Minutes",
        "trim_start": "00:00:00",
        "trim_duration": "00:14:00",
    },
]

# ── RAP MUSIC VIDEOS (official YouTube music videos) ──
RAP_VIDEOS = [
    {"id": "000_Kendrick_Lamar_HUMBLE",       "url": "https://www.youtube.com/watch?v=tvTRZJ-4EyI"},
    {"id": "001_Kendrick_Lamar_DNA",           "url": "https://www.youtube.com/watch?v=NLZRYQMLDW4"},
    {"id": "003_Kendrick_Lamar_Not_Like_Us",   "url": "https://www.youtube.com/watch?v=T6eK-2OQtew"},
    {"id": "004_Drake_Gods_Plan",              "url": "https://www.youtube.com/watch?v=xpVfcZ0ZcFM"},
    {"id": "005_Drake_Started_From_The_Bottom", "url": "https://www.youtube.com/watch?v=RubBzkZzpUA"},
    {"id": "008_J_Cole_Middle_Child",          "url": "https://www.youtube.com/watch?v=WILNIXZr2oc"},
    {"id": "010_Travis_Scott_SICKO_MODE",      "url": "https://www.youtube.com/watch?v=6ONRf7h3Mdk"},
    {"id": "011_Travis_Scott_goosebumps",      "url": "https://www.youtube.com/watch?v=Dst9gZkq1a8"},
    {"id": "012_Travis_Scott_HIGHEST_IN_THE_ROOM", "url": "https://www.youtube.com/watch?v=tfSS1e3kYeo"},
    {"id": "014_Tupac_Hit_Em_Up",              "url": "https://www.youtube.com/watch?v=41qC3w3UUkU"},
    {"id": "015_Tupac_Changes",                "url": "https://www.youtube.com/watch?v=eXvBjCO19QY"},
    {"id": "016_Biggie_Juicy",                 "url": "https://www.youtube.com/watch?v=_JZom_gVfuw"},
    {"id": "019_ASAP_Rocky_Praise_The_Lord",   "url": "https://www.youtube.com/watch?v=Kbj2Zss-5GY"},
    {"id": "022_Eminem_Rap_God",               "url": "https://www.youtube.com/watch?v=XbGs_qK2PQA"},
    {"id": "024_Kanye_West_Stronger",          "url": "https://www.youtube.com/watch?v=PsO6ZnUZI0g"},
    {"id": "025_Kanye_West_Gold_Digger",       "url": "https://www.youtube.com/watch?v=6vwNcNOTVzY"},
    {"id": "026_Kanye_West_POWER",             "url": "https://www.youtube.com/watch?v=L53gjP-TtGE"},
    {"id": "032_Lil_Wayne_Lollipop",           "url": "https://www.youtube.com/watch?v=2IH8tNQAzSs"},
    {"id": "034_Future_Mask_Off",              "url": "https://www.youtube.com/watch?v=xvZqHgFz51I"},
    {"id": "036_Cardi_B_Bodak_Yellow",         "url": "https://www.youtube.com/watch?v=PEGccV-NOoU"},
    {"id": "038_Playboi_Carti_Magnolia",       "url": "https://www.youtube.com/watch?v=oCveByMXd_0"},
]


def download_and_convert(url: str, output_mpg: Path, trim_start: str = "00:00:00",
                          trim_duration: str = "00:05:00", label: str = ""):
    """Download a YouTube video via yt-dlp and convert to ChuGL-compatible MPEG1."""
    if output_mpg.exists():
        print(f"  [skip] {output_mpg.name} already exists")
        return True

    tmp_mp4 = output_mpg.with_suffix(".tmp.mp4")

    # Step 1: Download via yt-dlp
    print(f"  ⬇ Downloading: {label or url}")
    dl_cmd = [
        "yt-dlp",
        "-f", f"bestvideo[height<={VIDEO_RES}]+bestaudio/best[height<={VIDEO_RES}]",
        "--merge-output-format", "mp4",
        "-o", str(tmp_mp4),
        "--no-playlist",
        "--quiet", "--progress",
        url,
    ]
    r = subprocess.run(dl_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [ERROR] yt-dlp failed: {r.stderr[:200]}")
        return False

    # Step 2: Convert to MPEG1 + MP2 via ffmpeg (ChuGL requirement)
    print(f"  🔄 Converting to MPEG1: {output_mpg.name}")
    ff_cmd = [
        "ffmpeg", "-y",
        "-ss", trim_start,
        "-i", str(tmp_mp4),
        "-t", trim_duration,
        "-c:v", "mpeg1video",
        "-q:v", "4",            # quality (lower = better, 2-6 good range)
        "-vf", f"scale={VIDEO_RES}:-2",  # maintain aspect ratio
        "-c:a", "mp2",
        "-b:a", "192k",
        "-f", "mpeg",
        str(output_mpg),
    ]
    r = subprocess.run(ff_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [ERROR] ffmpeg failed: {r.stderr[:200]}")
        return False

    # Clean up temp file
    tmp_mp4.unlink(missing_ok=True)
    # Also check for .tmp.mp4.part files
    for leftover in tmp_mp4.parent.glob(f"{tmp_mp4.stem}*"):
        leftover.unlink(missing_ok=True)

    size_mb = output_mpg.stat().st_size / (1024 * 1024)
    print(f"  ✅ {output_mpg.name} ({size_mb:.1f} MB)")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--podcasts", action="store_true", help="Download podcasts only")
    parser.add_argument("--rap", action="store_true", help="Download rap videos only")
    args = parser.parse_args()

    do_all = not args.podcasts and not args.rap

    PODCAST_VIDEO_DIR.mkdir(exist_ok=True)
    RAP_VIDEO_DIR.mkdir(exist_ok=True)

    if do_all or args.podcasts:
        print("=" * 60)
        print("PODCAST VIDEOS")
        print("=" * 60)
        for p in PODCAST_VIDEOS:
            out = PODCAST_VIDEO_DIR / f"{p['id']}.mpg"
            download_and_convert(
                p["url"], out,
                trim_start=p.get("trim_start", "00:00:00"),
                trim_duration=p.get("trim_duration", "00:10:00"),
                label=f"{p['title']}",
            )
            print()

    if do_all or args.rap:
        print("=" * 60)
        print("RAP MUSIC VIDEOS")
        print("=" * 60)
        for r in RAP_VIDEOS:
            out = RAP_VIDEO_DIR / f"{r['id']}.mpg"
            download_and_convert(
                r["url"], out,
                trim_start="00:00:00",
                trim_duration="00:05:00",  # first 5 min of each music video
                label=r["id"].replace("_", " "),
            )
            print()

    print("=" * 60)
    print("DONE!")
    podcast_count = len(list(PODCAST_VIDEO_DIR.glob("*.mpg")))
    rap_count = len(list(RAP_VIDEO_DIR.glob("*.mpg")))
    print(f"  Podcast videos: {podcast_count}")
    print(f"  Rap videos: {rap_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
