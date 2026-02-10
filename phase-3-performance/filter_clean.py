#!/usr/bin/env python3
"""
filter_clean.py — Generate clean (non-explicit) clip lists from existing metadata.

Reads clip_metadata.json and deepfake_metadata.json, filters out explicit lyrics,
and generates *-clean.txt file lists + updated metadata for ChucK.

Run this after build_rap_db.py and generate_deepfakes.py.

Usage:
  uv run python filter_clean.py
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── Explicit word list ──
EXPLICIT_WORDS = {
    # Slurs & variants
    "nigga", "niggas", "nigger", "niggers", "niggaz",
    # Hard profanity
    "fuck", "fuckin", "fuckin'", "fucking", "fucked", "fucker", "motherfucker",
    "motherfuckin", "motherfuckin'", "motherfucking", "muthafucka",
    "shit", "shitty", "bullshit",
    "bitch", "bitches", "bitchin",
    "ass", "asses", "asshole",
    "dick", "dicks",
    "pussy", "pussies",
    "hoe", "hoes",
    "whore", "whores",
    # Drug references
    "cocaine", "crack", "molly", "ecstasy", "heroin",
    # Violent
    "kill", "murder", "murdered", "shooting", "shoot",
}


def is_explicit(lyric: str) -> bool:
    words = set(re.sub(r"[^a-zA-Z\s']", "", lyric.lower()).split())
    return bool(words & EXPLICIT_WORDS)


def filter_clips(meta_file: str, list_file: str, clean_list_file: str,
                 lyrics_file: str, clean_lyrics_file: str, prefix: str):
    """Filter a clip metadata file into clean/explicit lists."""
    meta_path = BASE_DIR / meta_file
    if not meta_path.exists():
        print(f"  [SKIP] {meta_file} not found")
        return

    with open(meta_path) as f:
        clips = json.load(f)

    # Tag each clip
    for clip in clips:
        clip["explicit"] = is_explicit(clip.get("lyric", ""))

    clean = [c for c in clips if not c["explicit"]]
    explicit = [c for c in clips if c["explicit"]]

    print(f"\n{meta_file}: {len(clips)} total → {len(clean)} clean, {len(explicit)} explicit")

    # Show some examples of what got filtered
    if explicit:
        print(f"  Filtered examples:")
        for c in explicit[:5]:
            print(f"    ✗ \"{c['lyric'][:70]}\"")
    if clean:
        print(f"  Clean examples:")
        for c in clean[:5]:
            print(f"    ✓ \"{c['lyric'][:70]}\"")

    # Determine clip path prefix from first clip
    file_key = "clip_file" if "clip_file" in clips[0] else "deepfake_file"
    dir_prefix = prefix

    # Write ALL list
    with open(BASE_DIR / list_file, "w") as f:
        for c in clips:
            f.write(f"{dir_prefix}/{c[file_key]}\n")
    print(f"  → {list_file}: {len(clips)} clips")

    # Write CLEAN list
    with open(BASE_DIR / clean_list_file, "w") as f:
        for c in clean:
            f.write(f"{dir_prefix}/{c[file_key]}\n")
    print(f"  → {clean_list_file}: {len(clean)} clips")

    # Write lyrics files
    with open(BASE_DIR / lyrics_file, "w") as f:
        for c in clips:
            f.write(f"{c.get('artist', '')}: {c.get('lyric', '')}\n")

    with open(BASE_DIR / clean_lyrics_file, "w") as f:
        for c in clean:
            f.write(f"{c.get('artist', '')}: {c.get('lyric', '')}\n")
    print(f"  → {clean_lyrics_file}: {len(clean)} lyrics")

    # Update metadata with explicit flag
    with open(meta_path, "w") as f:
        json.dump(clips, f, indent=2)
    print(f"  → {meta_file} updated (explicit flag added)")

    return len(clean), len(explicit)


def main():
    print("=" * 60)
    print("Filtering explicit content from clip databases")
    print("=" * 60)

    # Real rap clips
    r = filter_clips(
        meta_file="clip_metadata.json",
        list_file="rap-clips.txt",
        clean_list_file="rap-clips-clean.txt",
        lyrics_file="clip_lyrics.txt",
        clean_lyrics_file="clip_lyrics_clean.txt",
        prefix="rap_clips",
    )

    # Deepfake clips
    d = filter_clips(
        meta_file="deepfake_metadata.json",
        list_file="deepfake-clips.txt",
        clean_list_file="deepfake-clips-clean.txt",
        lyrics_file="deepfake_lyrics.txt",
        clean_lyrics_file="deepfake_lyrics_clean.txt",
        prefix="deepfake_clips",
    )

    print(f"\n{'=' * 60}")
    print("Done! ChucK can now toggle between:")
    print("  EXPLICIT: rap-clips.txt / deepfake-clips.txt")
    print("  CLEAN:    rap-clips-clean.txt / deepfake-clips-clean.txt")
    print("=" * 60)


if __name__ == "__main__":
    main()
