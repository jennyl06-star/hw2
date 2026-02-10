#!/usr/bin/env python3
"""
crawl_rap.py — Rap Song Database Builder for Phase 3: Deepfake Diss Track

Pipeline:
  1. Download rap songs from YouTube (yt-dlp)
  2. Chop them into short clips (1-3s) using onset/beat detection (librosa)
  3. Normalize audio to 44.1 kHz mono WAV (ChucK compatible)
  4. Generate rap-clips.txt for mosaic-extract.ck
  5. Store metadata (artist, song, lyric snippet) as JSON for ChuGL display

Usage:
  uv run python crawl_rap.py                 # download + chop all
  uv run python crawl_rap.py --skip-download # chop only (if already downloaded)
  uv run python crawl_rap.py --artists "kendrick,drake"  # subset of artists
"""

import os
import sys
import json
import subprocess
import argparse
import random
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf


# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
FULL_SONGS_DIR = BASE_DIR / "rap_full_songs"
RAP_CLIPS_DIR = BASE_DIR / "rap_clips"
METADATA_FILE = BASE_DIR / "clip_metadata.json"
CLIPS_LIST_FILE = BASE_DIR / "rap-clips.txt"

# Target audio format for ChucK
SAMPLE_RATE = 44100
CHANNELS = 1  # mono

# Clip parameters
MIN_CLIP_DURATION = 0.8   # seconds
MAX_CLIP_DURATION = 3.0   # seconds
DEFAULT_CLIP_DURATION = 1.5  # seconds (fallback when onsets are too far apart)
MAX_CLIPS_PER_SONG = 40   # limit per song to keep DB manageable
ONSET_STRENGTH_THRESHOLD = 0.5  # only keep loud enough onsets


# ──────────────────────────────────────────────────────────────────────────────
# RAP SONG DATABASE — iconic tracks across many artists
# Format: (artist, song_title, youtube_url, [optional lyric snippets])
# ──────────────────────────────────────────────────────────────────────────────

RAP_SONGS = [
    # ── Kendrick Lamar ──
    ("Kendrick Lamar", "HUMBLE.",
     "https://www.youtube.com/watch?v=tvTRZJ-4EyI",
     ["Sit down", "Be humble", "Hold up lil bitch", "My left stroke just went viral"]),
    ("Kendrick Lamar", "DNA.",
     "https://www.youtube.com/watch?v=NLZRYQMLDW4",
     ["I got loyalty got royalty inside my DNA", "This is my DNA"]),
    ("Kendrick Lamar", "m.A.A.d city",
     "https://www.youtube.com/watch?v=10yrPDf92hY",
     ["If Pirus and Crips all got along", "Man down, where you from"]),
    ("Kendrick Lamar", "Not Like Us",
     "https://www.youtube.com/watch?v=T6eK-2OQtew",
     ["They not like us", "Certified lover boy", "How many opps you got"]),

    # ── Drake ──
    ("Drake", "God's Plan",
     "https://www.youtube.com/watch?v=xpVfcZ0ZcFM",
     ["God's plan", "She said do you love me", "I only love my bed and my mama"]),
    ("Drake", "Started From The Bottom",
     "https://www.youtube.com/watch?v=RubBzkZzpUA",
     ["Started from the bottom now we here", "Started from the bottom"]),
    ("Drake", "Hotline Bling",
     "https://www.youtube.com/watch?v=uxpDa-c-4Mc",
     ["You used to call me on my cell phone", "Hotline bling"]),

    # ── J. Cole ──
    ("J. Cole", "No Role Modelz",
     "https://www.youtube.com/watch?v=imgYGEn0sWs",
     ["Don't save her", "She don't wanna be saved", "First things first rest in peace Uncle Phil"]),
    ("J. Cole", "Middle Child",
     "https://www.youtube.com/watch?v=WILNIXZr2oc",
     ["I'm dead in the middle of two generations", "Middle child"]),
    ("J. Cole", "LOVE YOURZ",
     "https://www.youtube.com/watch?v=Ka4BxFED_PU",
     ["No such thing as a life that's better than yours", "Love yourz"]),

    # ── Travis Scott ──
    ("Travis Scott", "SICKO MODE",
     "https://www.youtube.com/watch?v=6ONRf7h3Mdk",
     ["Sun is down", "Astroworld", "She's in love with who I am"]),
    ("Travis Scott", "goosebumps",
     "https://www.youtube.com/watch?v=Dst9gZkq1a8",
     ["I get those goosebumps every time", "You come around"]),
    ("Travis Scott", "HIGHEST IN THE ROOM",
     "https://www.youtube.com/watch?v=tfSS1e3kYeo",
     ["Highest in the room", "She fill my mind up with ideas"]),

    # ── Tupac ──
    ("Tupac", "California Love",
     "https://www.youtube.com/watch?v=5wBTdfAkqGU",
     ["California love", "California knows how to party", "Shake it"]),
    ("Tupac", "Hit Em Up",
     "https://www.youtube.com/watch?v=41qC3w3UUkU",
     ["That's why I", "First off", "Grab your glocks"]),
    ("Tupac", "Changes",
     "https://www.youtube.com/watch?v=eXvBjCO19QY",
     ["I see no changes", "That's just the way it is", "Things will never be the same"]),

    # ── The Notorious B.I.G. ──
    ("Biggie", "Juicy",
     "https://www.youtube.com/watch?v=_JZom_gVfuw",
     ["It was all a dream", "Juicy", "Birthdays was the worst days"]),
    ("Biggie", "Hypnotize",
     "https://www.youtube.com/watch?v=glEiPXAYE-U",
     ["Biggie Biggie Biggie", "Can't you see", "Hypnotize"]),
    ("Biggie", "Big Poppa",
     "https://www.youtube.com/watch?v=phaJXp_zMpY",
     ["I love it when you call me Big Poppa", "Throw your hands in the air"]),

    # ── A$AP Rocky ──
    ("ASAP Rocky", "Praise The Lord",
     "https://www.youtube.com/watch?v=Kbj2Zss-5GY",
     ["Praise the Lord", "I might take your girl", "Hallelujah"]),
    ("ASAP Rocky", "L$D",
     "https://www.youtube.com/watch?v=yEG2VTHS9og",
     ["I love long", "She love long", "LSD"]),

    # ── Eminem ──
    ("Eminem", "Lose Yourself",
     "https://www.youtube.com/watch?v=_Yhyp-_hX2s",
     ["Lose yourself", "Mom's spaghetti", "You only get one shot"]),
    ("Eminem", "Rap God",
     "https://www.youtube.com/watch?v=XbGs_qK2PQA",
     ["I'm beginning to feel like a Rap God", "Rap God"]),
    ("Eminem", "Without Me",
     "https://www.youtube.com/watch?v=YVkUvmDQ3HY",
     ["Guess who's back", "Back again", "Shady's back"]),

    # ── Kanye West ──
    ("Kanye West", "Stronger",
     "https://www.youtube.com/watch?v=PsO6ZnUZI0g",
     ["That that don't kill me", "Can only make me stronger", "Work it harder"]),
    ("Kanye West", "Gold Digger",
     "https://www.youtube.com/watch?v=6vwNcNOTVzY",
     ["She take my money", "Gold digger", "I ain't saying she a gold digger"]),
    ("Kanye West", "POWER",
     "https://www.youtube.com/watch?v=L53gjP-TtGE",
     ["No one man should have all that power", "Power", "The clocks ticking"]),

    # ── Nas ──
    ("Nas", "N.Y. State of Mind",
     "https://www.youtube.com/watch?v=hI8A14Qcv68",
     ["I don't know how to start this", "Rappers I monkey flip em", "New York state of mind"]),
    ("Nas", "The World Is Yours",
     "https://www.youtube.com/watch?v=_srvHOu75vM",
     ["Whose world is this", "The world is yours", "It's mine"]),

    # ── Jay-Z ──
    ("Jay-Z", "Empire State of Mind",
     "https://www.youtube.com/watch?v=0UjsXo9l6I8",
     ["In New York", "Concrete jungle where dreams are made of", "New York"]),
    ("Jay-Z", "99 Problems",
     "https://www.youtube.com/watch?v=WwoM5fLITfk",
     ["I got 99 problems", "But a b ain't one", "Hit me"]),

    # ── Lil Wayne ──
    ("Lil Wayne", "A Milli",
     "https://www.youtube.com/watch?v=P19dow9ALYM",
     ["A milli a milli", "A million", "Young Money"]),
    ("Lil Wayne", "Lollipop",
     "https://www.youtube.com/watch?v=2IH8tNQAzSs",
     ["Lollipop", "She lick me like a lollipop", "Shawty want a"]),

    # ── 21 Savage ──
    ("21 Savage", "a]lot",
     "https://www.youtube.com/watch?v=DmWWqogr_r8",
     ["A lot", "How much money you got", "A lot of"]),

    # ── Future ──
    ("Future", "Mask Off",
     "https://www.youtube.com/watch?v=xvZqHgFz51I",
     ["Mask off", "Percocet", "Molly Percocet"]),

    # ── Megan Thee Stallion ──
    ("Megan Thee Stallion", "Savage Remix",
     "https://www.youtube.com/watch?v=mRgI9aiCMSY",
     ["Savage", "Classy bougie ratchet", "I'm a savage"]),

    # ── Cardi B ──
    ("Cardi B", "Bodak Yellow",
     "https://www.youtube.com/watch?v=PEGccV-NOm8",
     ["Bodak yellow", "I don't dance now I make money moves", "Said lil bitch"]),

    # ── Pop Smoke ──
    ("Pop Smoke", "Dior",
     "https://www.youtube.com/watch?v=jnuKA5VFtRk",
     ["Christian Dior Dior", "I'm a star", "Pop Smoke"]),

    # ── Playboi Carti ──
    ("Playboi Carti", "Magnolia",
     "https://www.youtube.com/watch?v=oCveByMXd_0",
     ["In New York I milly rock", "Magnolia", "Carti"]),

    # ── Metro Boomin ──
    ("Metro Boomin", "Creepin",
     "https://www.youtube.com/watch?v=6WB6gOBlJBs",
     ["Creepin", "I don't wanna", "Somebody's watching me"]),
]


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: Download songs from YouTube
# ──────────────────────────────────────────────────────────────────────────────

def download_song(artist: str, title: str, url: str, index: int) -> Path | None:
    """Download a song from YouTube as WAV using yt-dlp + ffmpeg."""
    safe_name = f"{index:03d}_{artist.replace(' ', '_')}_{title.replace(' ', '_')}"
    # Remove any problematic characters
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
    output_path = FULL_SONGS_DIR / f"{safe_name}.wav"

    if output_path.exists():
        print(f"  [skip] Already downloaded: {output_path.name}")
        return output_path

    outtmpl = str(FULL_SONGS_DIR / f"{safe_name}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--postprocessor-args", f"ffmpeg:-ar {SAMPLE_RATE} -ac {CHANNELS}",
        "-o", outtmpl,
        "--no-playlist",
        "--socket-timeout", "30",
        "--retries", "3",
        url,
    ]

    print(f"  [{index:03d}] Downloading: {artist} — {title}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            # Show just the ERROR lines, not warnings
            error_lines = [l for l in result.stderr.split('\n') if 'ERROR' in l]
            print(f"  [ERROR] yt-dlp failed (exit={result.returncode}): {' '.join(error_lines)[:300]}")
            return None
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] Download timed out")
        return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    if output_path.exists():
        print(f"  [OK] Saved: {output_path.name}")
        return output_path
    else:
        # yt-dlp may have saved with different extension then converted
        # look for any file matching the prefix
        for f in FULL_SONGS_DIR.glob(f"{safe_name}.*"):
            if f.suffix == ".wav":
                return f
        print(f"  [WARN] File not found after download: {output_path}")
        return None


def download_all_songs(artists_filter: list[str] | None = None) -> list[tuple[Path, dict]]:
    """Download all songs, return list of (path, metadata) tuples."""
    results = []
    for i, (artist, title, url, lyrics) in enumerate(RAP_SONGS):
        if artists_filter and not any(a.lower() in artist.lower() for a in artists_filter):
            continue
        path = download_song(artist, title, url, i)
        if path and path.exists():
            results.append((path, {
                "artist": artist,
                "title": title,
                "url": url,
                "lyrics": lyrics,
                "index": i,
            }))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: Chop songs into short clips using onset/beat detection
# ──────────────────────────────────────────────────────────────────────────────

def chop_song(wav_path: Path, metadata: dict, clip_dir: Path) -> list[dict]:
    """
    Use librosa onset detection to find natural breakpoints,
    then slice into short clips (MIN_CLIP_DURATION to MAX_CLIP_DURATION seconds).
    Returns list of clip metadata dicts.
    """
    artist = metadata["artist"]
    title = metadata["title"]
    lyrics = metadata.get("lyrics", [])
    song_idx = metadata["index"]

    print(f"  Chopping: {artist} — {title} ({wav_path.name})")

    try:
        y, sr = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True)
    except Exception as e:
        print(f"  [ERROR] Failed to load {wav_path}: {e}")
        return []

    duration = len(y) / sr
    if duration < 5.0:
        print(f"  [SKIP] Too short ({duration:.1f}s)")
        return []

    # Get onset times using onset detection
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr, onset_envelope=onset_env,
        backtrack=True, units='frames'
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    # Also get beat times as backup boundaries
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Merge onsets and beats, sort, deduplicate
    all_boundaries = sorted(set(
        [0.0] +
        list(onset_times) +
        list(beat_times) +
        [duration]
    ))

    # Build clips from consecutive boundary pairs
    clips_meta = []
    clip_count = 0

    i = 0
    while i < len(all_boundaries) - 1 and clip_count < MAX_CLIPS_PER_SONG:
        start = all_boundaries[i]

        # Find the end boundary that gives us a clip in the right duration range
        end = start + DEFAULT_CLIP_DURATION
        for j in range(i + 1, len(all_boundaries)):
            candidate_end = all_boundaries[j]
            candidate_dur = candidate_end - start
            if candidate_dur >= MIN_CLIP_DURATION:
                end = candidate_end
                if candidate_dur >= DEFAULT_CLIP_DURATION:
                    break

        clip_duration = end - start
        if clip_duration < MIN_CLIP_DURATION:
            i += 1
            continue
        if clip_duration > MAX_CLIP_DURATION:
            end = start + MAX_CLIP_DURATION
            clip_duration = MAX_CLIP_DURATION

        # Extract clip samples
        start_sample = int(start * sr)
        end_sample = int(end * sr)
        clip_audio = y[start_sample:end_sample]

        # Check if clip has enough energy (skip silent parts)
        rms = np.sqrt(np.mean(clip_audio ** 2))
        if rms < 0.01:
            # Skip near-silent clips
            i += 1
            continue

        # Save clip
        safe_artist = "".join(c for c in artist if c.isalnum() or c in "_-")
        safe_title = "".join(c for c in title.replace(" ", "_") if c.isalnum() or c in "_-")
        clip_name = f"{song_idx:03d}_{safe_artist}_{safe_title}_clip{clip_count:03d}.wav"
        clip_path = clip_dir / clip_name

        sf.write(str(clip_path), clip_audio, sr)

        # Pick a lyric snippet for display (cycle through available lyrics)
        lyric = ""
        if lyrics:
            lyric = lyrics[clip_count % len(lyrics)]

        clips_meta.append({
            "clip_file": clip_name,
            "artist": artist,
            "title": title,
            "start_time": round(start, 3),
            "end_time": round(end, 3),
            "duration": round(clip_duration, 3),
            "rms": round(float(rms), 4),
            "lyric": lyric,
            "song_index": song_idx,
            "clip_index": clip_count,
        })

        clip_count += 1

        # Advance to next non-overlapping boundary
        next_i = i + 1
        while next_i < len(all_boundaries) and all_boundaries[next_i] < end:
            next_i += 1
        i = next_i

    print(f"    → {clip_count} clips extracted")
    return clips_meta


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: Generate output files for ChucK
# ──────────────────────────────────────────────────────────────────────────────

def generate_clips_list(all_clips_meta: list[dict], clips_dir: Path, list_file: Path):
    """Generate rap-clips.txt listing all clip files for mosaic-extract.ck."""
    with open(list_file, "w") as f:
        for clip in all_clips_meta:
            # Use relative path from phase-3-performance directory
            f.write(f"rap_clips/{clip['clip_file']}\n")
    print(f"\n[OK] Wrote {len(all_clips_meta)} clip paths to {list_file.name}")


def generate_metadata_json(all_clips_meta: list[dict], meta_file: Path):
    """Save full metadata as JSON for ChuGL lyric display + deepfake pipeline."""
    with open(meta_file, "w") as f:
        json.dump(all_clips_meta, f, indent=2)
    print(f"[OK] Wrote metadata to {meta_file.name}")


def generate_lyrics_file(all_clips_meta: list[dict], base_dir: Path):
    """
    Generate a simple text file mapping clip index → lyric line
    (for easy reading in ChucK).
    Format: one lyric per line, indexed by clip order.
    """
    lyrics_file = base_dir / "clip_lyrics.txt"
    with open(lyrics_file, "w") as f:
        for clip in all_clips_meta:
            lyric = clip.get("lyric", "")
            artist = clip.get("artist", "")
            # Format: "ARTIST: lyric" or just artist name if no lyric
            if lyric:
                f.write(f"{artist}: {lyric}\n")
            else:
                f.write(f"{artist}\n")
    print(f"[OK] Wrote {len(all_clips_meta)} lyrics to {lyrics_file.name}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build rap clip database for Phase 3")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading, only chop existing files")
    parser.add_argument("--artists", type=str, default=None,
                        help="Comma-separated artist filter (e.g., 'kendrick,drake')")
    parser.add_argument("--max-songs", type=int, default=None,
                        help="Maximum number of songs to process")
    args = parser.parse_args()

    # Ensure directories exist
    FULL_SONGS_DIR.mkdir(parents=True, exist_ok=True)
    RAP_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    artists_filter = None
    if args.artists:
        artists_filter = [a.strip() for a in args.artists.split(",")]
        print(f"Filtering to artists: {artists_filter}")

    # Step 1: Download
    if not args.skip_download:
        print("\n" + "=" * 60)
        print("STEP 1: Downloading rap songs from YouTube")
        print("=" * 60)
        songs = download_all_songs(artists_filter)
        print(f"\nDownloaded {len(songs)} songs successfully")
    else:
        print("\n[skip-download] Using existing files in rap_full_songs/")
        songs = []
        for i, (artist, title, url, lyrics) in enumerate(RAP_SONGS):
            if artists_filter and not any(a.lower() in artist.lower() for a in artists_filter):
                continue
            safe_name = f"{i:03d}_{artist.replace(' ', '_')}_{title.replace(' ', '_')}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
            wav_path = FULL_SONGS_DIR / f"{safe_name}.wav"
            if wav_path.exists():
                songs.append((wav_path, {
                    "artist": artist, "title": title, "url": url,
                    "lyrics": lyrics, "index": i,
                }))
        print(f"Found {len(songs)} existing song files")

    if args.max_songs:
        songs = songs[:args.max_songs]

    # Step 2: Chop into clips
    print("\n" + "=" * 60)
    print("STEP 2: Chopping songs into short clips")
    print("=" * 60)
    all_clips_meta = []
    for wav_path, meta in songs:
        clips = chop_song(wav_path, meta, RAP_CLIPS_DIR)
        all_clips_meta.extend(clips)

    print(f"\nTotal clips: {len(all_clips_meta)}")

    # Shuffle clips so KNN gets variety across artists
    random.seed(42)
    random.shuffle(all_clips_meta)

    # Step 3: Generate output files
    print("\n" + "=" * 60)
    print("STEP 3: Generating output files")
    print("=" * 60)
    generate_clips_list(all_clips_meta, RAP_CLIPS_DIR, CLIPS_LIST_FILE)
    generate_metadata_json(all_clips_meta, METADATA_FILE)
    generate_lyrics_file(all_clips_meta, BASE_DIR)

    # Summary
    print("\n" + "=" * 60)
    print("DONE! Database ready.")
    print("=" * 60)
    artists_in_db = set(c["artist"] for c in all_clips_meta)
    print(f"  Artists: {len(artists_in_db)}")
    print(f"  Songs: {len(songs)}")
    print(f"  Clips: {len(all_clips_meta)}")
    print(f"  Files:")
    print(f"    {CLIPS_LIST_FILE}  (for mosaic-extract.ck)")
    print(f"    {METADATA_FILE}    (full metadata)")
    print(f"    {BASE_DIR / 'clip_lyrics.txt'}  (for ChuGL)")
    print(f"\nNext step:")
    print(f"  cd phase-3-performance")
    print(f"  chuck --silent ../phase-2-mosaic/mosaic-extract.ck:rap-clips.txt:rap_db.txt")


if __name__ == "__main__":
    main()
