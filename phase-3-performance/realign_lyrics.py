#!/usr/bin/env python3
"""
realign_lyrics.py — Fix lyric→audio timestamp alignment using Grok Voice API

THE PROBLEM:
  build_rap_db.py uses librosa onset detection to GUESS where each lyric line
  falls in the audio.  This heuristic fails badly because:
    • Onset detection captures drum/bass hits, not just vocals
    • It linearly maps N lyrics → N onset segments (ignoring intros, bridges)
    • Overlapping timestamps, wildly wrong positions

THE FIX:
  1. Split each full song into overlapping 10-second segments
  2. Send each segment to Grok Realtime Voice API for transcription
  3. Fuzzy-match the known (golden) lyrics against transcriptions
  4. Refine sub-segment timing using word-position estimation
  5. Re-chop audio clips at corrected timestamps
  6. Regenerate clip_metadata.json, clip_lyrics.txt, etc.

Usage:
  uv run python realign_lyrics.py                      # all songs
  uv run python realign_lyrics.py --artists "kendrick"  # one artist
  uv run python realign_lyrics.py --max-songs 3         # test
  uv run python realign_lyrics.py --dry-run              # preview only
"""

import os
import sys
import json
import asyncio
import base64
import re
import argparse
import random
import time
from pathlib import Path
from difflib import SequenceMatcher

import numpy as np
import librosa
import soundfile as sf
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
FULL_SONGS_DIR = BASE_DIR / "rap_full_songs"
RAP_CLIPS_DIR = BASE_DIR / "rap_clips"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
METADATA_FILE = BASE_DIR / "clip_metadata.json"
CLIPS_LIST_FILE = BASE_DIR / "rap-clips.txt"
LYRICS_FILE = BASE_DIR / "clip_lyrics.txt"

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
GROK_WS_URL = "wss://api.x.ai/v1/realtime"

SAMPLE_RATE = 44100
GROK_SR = 24000  # Grok Realtime expects 24 kHz PCM16

# Segment parameters for transcription
SEG_DURATION = 10.0   # seconds per transcription window
SEG_STEP = 5.0        # step between windows (overlap = DURATION - STEP)

# Clip constraints (match build_rap_db.py)
MIN_PHRASE_DURATION = 0.6
MAX_PHRASE_DURATION = 4.0
MAX_CLIPS_PER_SONG = 50

# Minimum fuzzy-match confidence to accept an alignment
MIN_CONFIDENCE = 0.30

# Explicit word list (from build_rap_db.py / filter_clean.py)
EXPLICIT_WORDS = {
    "nigga", "niggas", "nigger", "niggers", "niggaz",
    "fuck", "fuckin", "fuckin'", "fucking", "fucked", "fucker", "motherfucker",
    "motherfuckin", "motherfuckin'", "motherfucking", "muthafucka",
    "shit", "shitty", "bullshit",
    "bitch", "bitches", "bitchin",
    "ass", "asses", "asshole",
    "dick", "dicks",
    "pussy", "pussies",
    "hoe", "hoes",
    "whore", "whores",
    "cocaine", "crack", "molly", "ecstasy", "heroin",
    "kill", "murder", "murdered", "shooting", "shoot",
}


def is_explicit(lyric: str) -> bool:
    words = set(re.sub(r"[^a-zA-Z\s']", "", lyric.lower()).split())
    return bool(words & EXPLICIT_WORDS)


# ─────────────────────────────────────────────────────────────────────────────
# GROK REALTIME VOICE API — TRANSCRIPTION
# ─────────────────────────────────────────────────────────────────────────────

async def _grok_transcribe(audio_24k: np.ndarray, seg_id: str) -> str:
    """
    Send an audio segment to Grok Realtime Voice API and get back a
    text transcription.

    Flow:
      1. WebSocket connect → session.update (enable input_audio_transcription)
      2. Stream audio via input_audio_buffer.append
      3. Commit buffer → wait for input_audio_transcription.completed event
      4. Return the transcription from the input event
    """
    import websockets

    # float32 → PCM16 bytes
    pcm_int16 = (np.clip(audio_24k, -1.0, 1.0) * 32767).astype(np.int16)
    pcm_bytes = pcm_int16.tobytes()

    headers = {"Authorization": f"Bearer {XAI_API_KEY}"}
    transcript = ""

    try:
        async with websockets.connect(
            GROK_WS_URL,
            additional_headers=headers,
            close_timeout=10,
        ) as ws:
            # ── 1. Configure session with input_audio_transcription ──
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "instructions": (
                        "You are a precise audio transcriber for rap music. "
                        "Listen to the audio and transcribe EXACTLY what is being "
                        "rapped or spoken. Output ONLY the raw transcription — "
                        "no commentary, no formatting, no timestamps. "
                        "If the segment is purely instrumental with no vocals, "
                        "output exactly: [INSTRUMENTAL]"
                    ),
                    "turn_detection": None,
                    "input_audio_transcription": {"model": "grok-2-latest"},
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": GROK_SR}
                        },
                    },
                }
            }))

            # Wait for session.updated
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                if msg.get("type") == "session.updated":
                    break

            # ── 2. Stream audio via input_audio_buffer ──
            CHUNK = 48000  # ~1 second of PCM16 at 24 kHz = 48000 bytes
            for i in range(0, len(pcm_bytes), CHUNK):
                chunk = pcm_bytes[i:i + CHUNK]
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(chunk).decode(),
                }))

            # ── 3. Commit buffer ──
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

            # ── 4. Request a response (triggers transcription pipeline) ──
            await ws.send(json.dumps({
                "type": "response.create",
                "response": {"modalities": ["text"]},
            }))

            # ── 5. Collect the input transcription event ──
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=12))
                    mtype = msg.get("type", "")

                    if mtype == "conversation.item.input_audio_transcription.completed":
                        transcript = msg.get("transcript", "")
                        # Don't break yet — wait for response.done to close cleanly
                    elif mtype == "response.text.delta":
                        # If the model responds in text mode, capture that too
                        if not transcript:
                            transcript += msg.get("delta", "")
                    elif mtype == "response.done":
                        break
                    elif mtype == "error":
                        err = msg.get("error", msg)
                        print(f"    [API ERR] {seg_id}: {err}")
                        return ""
                except asyncio.TimeoutError:
                    break

    except Exception as e:
        print(f"    [CONN ERR] {seg_id}: {e}")
        return ""

    return transcript.strip()


async def _grok_transcribe_one(audio_44k: np.ndarray, seg_id: str) -> str:
    """Async: resample 44.1 kHz → 24 kHz, then transcribe (no retries)."""
    audio_24k = librosa.resample(audio_44k, orig_sr=SAMPLE_RATE, target_sr=GROK_SR)
    try:
        result = await asyncio.wait_for(_grok_transcribe(audio_24k, seg_id), timeout=15)
        return result if result is not None else ""
    except asyncio.TimeoutError:
        return ""
    except Exception as e:
        return ""


# Concurrency for parallel transcription
PARALLEL_WORKERS = 5


# ─────────────────────────────────────────────────────────────────────────────
# TRANSCRIBE A FULL SONG IN SEGMENTS
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_song(wav_path: Path, song_name: str) -> list[dict]:
    """
    Transcribe a full song in overlapping windows using Grok Voice API.
    Sends PARALLEL_WORKERS segments concurrently for speed.
    Returns: [{"start": float, "end": float, "text": str}, ...]
    Results are cached in transcripts/{song_name}_grok_align.json.
    """
    cache = TRANSCRIPTS_DIR / f"{song_name}_grok_align.json"
    if cache.exists():
        print(f"  [cache] {cache.name}")
        with open(cache) as f:
            return json.load(f)

    y, sr = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True)
    dur = len(y) / sr

    # Build all segment windows up front
    windows = []
    t = 0.0
    seg_num = 0
    while t < dur:
        e = min(t + SEG_DURATION, dur)
        s_samp = int(t * sr)
        e_samp = int(e * sr)
        seg_audio = y[s_samp:e_samp]
        seg_id = f"{song_name}_s{seg_num:03d}"
        windows.append({"start": round(t, 3), "end": round(e, 3),
                         "audio": seg_audio, "seg_id": seg_id, "idx": seg_num})
        seg_num += 1
        t += SEG_STEP

    total = len(windows)
    print(f"  ⏳ Transcribing {total} segments ({PARALLEL_WORKERS} parallel)...", flush=True)

    segments = [None] * total

    async def _run_batch(batch):
        tasks = []
        for w in batch:
            tasks.append(_grok_transcribe_one(w["audio"], w["seg_id"]))
        return await asyncio.gather(*tasks, return_exceptions=True)

    # Process in batches of PARALLEL_WORKERS
    for batch_start in range(0, total, PARALLEL_WORKERS):
        batch = windows[batch_start : batch_start + PARALLEL_WORKERS]
        batch_end = min(batch_start + PARALLEL_WORKERS, total)
        print(f"    [{batch_start+1}–{batch_end}/{total}] ", end="", flush=True)

        results = asyncio.run(_run_batch(batch))

        for w, result in zip(batch, results):
            text = result if isinstance(result, str) else ""
            segments[w["idx"]] = {"start": w["start"], "end": w["end"], "text": text}

            if text and "[INSTRUMENTAL]" not in text.upper():
                display = text[:50].replace("\n", " ")
                print(f"✓", end="", flush=True)
            else:
                print(f"·", end="", flush=True)

        print(flush=True)

    # Cache results
    with open(cache, "w") as f:
        json.dump(segments, f, indent=2)
    print(f"  Cached → {cache.name}")

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# FUZZY MATCHING — lyrics → segments
# ─────────────────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    """Lowercase, strip punctuation, normalize whitespace."""
    return re.sub(r"[^a-z0-9\s']", "", s.lower()).strip()


def _words(s: str) -> list[str]:
    return _clean(s).split()


def match_lyric_to_segments(
    lyric: str, segments: list[dict]
) -> tuple[dict | None, float]:
    """
    Find the segment whose Grok transcription best matches `lyric`.
    Uses three strategies and takes the max score:
      1. Word set overlap
      2. Consecutive-word sliding window (tolerates transcription errors)
      3. SequenceMatcher on cleaned strings
    Returns (best_segment, confidence).
    """
    lw = _words(lyric)
    if not lw:
        return None, 0.0

    best_seg = None
    best_score = 0.0

    for seg in segments:
        text = seg.get("text", "")
        if not text or "[INSTRUMENTAL]" in text.upper():
            continue

        tw = _words(text)
        if not tw:
            continue

        # ── Strategy 1: word-set overlap ──
        lset = set(lw)
        tset = set(tw)
        overlap = len(lset & tset) / len(lset) if lset else 0

        # ── Strategy 2: consecutive-word sliding window ──
        consec = 0.0
        if len(lw) >= 2:
            for i in range(max(1, len(tw) - len(lw) + 1)):
                window = tw[i : i + len(lw)]
                matches = sum(
                    1
                    for a, b in zip(lw, window)
                    if a == b
                    or SequenceMatcher(None, a, b).ratio() > 0.75
                )
                consec = max(consec, matches / len(lw))

        # ── Strategy 3: SequenceMatcher on full cleaned strings ──
        seq = SequenceMatcher(None, _clean(lyric), _clean(text)).ratio()

        score = max(overlap * 0.85, consec * 0.95, seq)

        if score > best_score:
            best_score = score
            best_seg = seg

    return best_seg, best_score


def refine_timestamp(
    lyric: str, seg: dict, song_duration: float
) -> tuple[float, float]:
    """
    Estimate where inside a matched segment the lyric actually occurs,
    based on word position within the transcript.  Returns (start, end).
    """
    text = seg.get("text", "")
    seg_start = seg["start"]
    seg_end = seg["end"]
    seg_dur = seg_end - seg_start

    lw = _words(lyric)
    tw = _words(text)

    if not tw or not lw:
        return seg_start, min(seg_end, seg_start + MAX_PHRASE_DURATION)

    # Find best match position within transcript word list
    best_pos = 0
    best_r = 0.0
    for i in range(max(1, len(tw) - len(lw) + 1)):
        window = tw[i : i + len(lw)]
        m = sum(
            1
            for a, b in zip(lw, window)
            if a == b or SequenceMatcher(None, a, b).ratio() > 0.7
        )
        r = m / len(lw)
        if r > best_r:
            best_r = r
            best_pos = i

    # Estimate timing: proportional to word position in transcript
    words_per_sec = len(tw) / seg_dur if seg_dur > 0 else 5.0
    est_start = seg_start + best_pos / words_per_sec
    est_dur = max(MIN_PHRASE_DURATION, min(len(lw) / words_per_sec, MAX_PHRASE_DURATION))
    est_end = est_start + est_dur

    # Clamp to song bounds
    est_start = max(0.0, min(est_start, song_duration - MIN_PHRASE_DURATION))
    est_end = min(song_duration, max(est_end, est_start + MIN_PHRASE_DURATION))

    return round(est_start, 3), round(est_end, 3)


# ─────────────────────────────────────────────────────────────────────────────
# RE-CHOP AUDIO WITH CORRECTED TIMESTAMPS
# ─────────────────────────────────────────────────────────────────────────────

def rechop_song(
    wav_path: Path,
    phrases: list[dict],
    artist: str,
    title: str,
    song_idx: int,
) -> list[dict]:
    """
    Re-chop audio clips at corrected timestamps.
    Clip naming uses the same scheme as build_rap_db.py so that deepfake
    clip references remain valid.
    """
    y, sr = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True)
    dur = len(y) / sr

    safe_a = "".join(c for c in artist if c.isalnum() or c in "_-")
    safe_t = "".join(c for c in title.replace(" ", "_") if c.isalnum() or c in "_-")

    clips = []
    for ci, ph in enumerate(phrases[:MAX_CLIPS_PER_SONG]):
        s = max(0, ph["start"] - 0.05)  # 50 ms padding
        e = min(dur, ph["end"] + 0.05)

        pdur = e - s
        if pdur < MIN_PHRASE_DURATION or pdur > MAX_PHRASE_DURATION + 1.0:
            continue

        clip = y[int(s * sr) : int(e * sr)]
        rms = float(np.sqrt(np.mean(clip**2)))
        if rms < 0.005:
            continue

        name = f"{song_idx:03d}_{safe_a}_{safe_t}_p{ci:03d}.wav"
        sf.write(str(RAP_CLIPS_DIR / name), clip, sr)

        clips.append({
            "clip_file": name,
            "artist": artist,
            "title": title,
            "lyric": ph["lyric"],
            "start_time": round(ph["start"], 3),
            "end_time": round(ph["end"], 3),
            "duration": round(pdur, 3),
            "rms": round(rms, 4),
            "song_index": song_idx,
            "clip_index": ci,
            "alignment_confidence": ph.get("confidence", 0),
        })

    return clips


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT GENERATION (same format as build_rap_db.py / filter_clean.py)
# ─────────────────────────────────────────────────────────────────────────────

def generate_outputs(all_clips: list[dict]):
    """Regenerate clip_metadata.json, clip_lyrics.txt, rap-clips.txt, etc."""
    for clip in all_clips:
        clip["explicit"] = is_explicit(clip.get("lyric", ""))

    clean = [c for c in all_clips if not c["explicit"]]

    # ── clip_metadata.json ──
    with open(METADATA_FILE, "w") as f:
        json.dump(all_clips, f, indent=2)
    print(f"  → {METADATA_FILE.name}: {len(all_clips)} clips")

    # ── rap-clips.txt (all) ──
    with open(CLIPS_LIST_FILE, "w") as f:
        for c in all_clips:
            f.write(f"rap_clips/{c['clip_file']}\n")
    print(f"  → {CLIPS_LIST_FILE.name}: {len(all_clips)} clips")

    # ── rap-clips-clean.txt ──
    with open(BASE_DIR / "rap-clips-clean.txt", "w") as f:
        for c in clean:
            f.write(f"rap_clips/{c['clip_file']}\n")
    print(f"  → rap-clips-clean.txt: {len(clean)} clips")

    # ── clip_lyrics.txt (all) ──
    with open(LYRICS_FILE, "w") as f:
        for c in all_clips:
            f.write(f"{c['artist']}: {c['lyric']}\n")
    print(f"  → {LYRICS_FILE.name}")

    # ── clip_lyrics_clean.txt ──
    with open(BASE_DIR / "clip_lyrics_clean.txt", "w") as f:
        for c in clean:
            f.write(f"{c['artist']}: {c['lyric']}\n")
    print(f"  → clip_lyrics_clean.txt")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Force unbuffered output for progress visibility
    import sys
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(
        description="Fix lyric→audio alignment using Grok Voice API"
    )
    parser.add_argument("--artists", type=str, default=None,
                        help="Comma-separated artist filter")
    parser.add_argument("--max-songs", type=int, default=None,
                        help="Limit number of songs to process")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show alignment results without re-chopping")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE,
                        help=f"Min fuzzy-match confidence (default {MIN_CONFIDENCE})")
    parser.add_argument("--force", action="store_true",
                        help="Delete Grok transcription cache and re-transcribe")
    args = parser.parse_args()

    if not XAI_API_KEY:
        print("ERROR: XAI_API_KEY not set in .env")
        sys.exit(1)

    # ── Discover songs from existing phrase files ──
    phrase_files = sorted(TRANSCRIPTS_DIR.glob("*_phrases.json"))
    songs = []

    for pf in phrase_files:
        name = pf.stem.replace("_phrases", "")
        lyrics_file = TRANSCRIPTS_DIR / f"{name}.json"
        wav_file = FULL_SONGS_DIR / f"{name}.wav"

        if not lyrics_file.exists() or not wav_file.exists():
            continue

        with open(lyrics_file) as f:
            lyrics_data = json.load(f)
        with open(pf) as f:
            phrases = json.load(f)

        artist = lyrics_data.get("artist", "")
        title = lyrics_data.get("title", "")

        if args.artists:
            filt = [a.strip().lower() for a in args.artists.split(",")]
            if not any(a in artist.lower() for a in filt):
                continue

        # Song index = first 3 characters of the name
        try:
            song_idx = int(name[:3])
        except ValueError:
            continue

        songs.append({
            "name": name,
            "artist": artist,
            "title": title,
            "song_idx": song_idx,
            "wav": wav_file,
            "lyrics_data": lyrics_data,
            "phrases": phrases,
        })

    if args.max_songs:
        songs = songs[: args.max_songs]

    print(f"Found {len(songs)} songs to realign\n")

    if not songs:
        print("No songs found. Make sure transcripts/ and rap_full_songs/ exist.")
        sys.exit(1)

    # ── Delete transcription cache if --force ──
    if args.force:
        for s in songs:
            cache = TRANSCRIPTS_DIR / f"{s['name']}_grok_align.json"
            if cache.exists():
                cache.unlink()
                print(f"  [deleted cache] {cache.name}")
        print()

    # ── Process each song ──
    all_clips = []
    stats = {"matched": 0, "unmatched": 0, "kept_old": 0}

    for si, song in enumerate(songs):
        print("=" * 60)
        print(f"[{si + 1}/{len(songs)}] {song['artist']} — {song['title']}")
        print("=" * 60)
        print(f"  Phrases to align: {len(song['phrases'])}")

        # Step 1: Transcribe song segments with Grok Voice API
        segments = transcribe_song(song["wav"], song["name"])
        vocal_segs = [
            s for s in segments
            if s.get("text") and "[INSTRUMENTAL]" not in s["text"].upper()
        ]
        print(f"  Segments: {len(segments)} total, {len(vocal_segs)} with vocals\n")

        if not vocal_segs:
            print("  [WARN] No vocal segments found — keeping old timestamps")
            stats["kept_old"] += len(song["phrases"])
            if not args.dry_run:
                clips = rechop_song(
                    song["wav"], song["phrases"],
                    song["artist"], song["title"], song["song_idx"],
                )
                all_clips.extend(clips)
            continue

        # Get song duration for timestamp clamping
        info = sf.info(str(song["wav"]))
        song_dur = info.duration

        # Step 2: Match each phrase to a segment
        corrected_phrases = []
        for ph in song["phrases"]:
            best_seg, confidence = match_lyric_to_segments(ph["lyric"], segments)

            old_start = ph.get("start", 0)
            old_end = ph.get("end", 0)

            if best_seg and confidence >= args.min_confidence:
                new_start, new_end = refine_timestamp(
                    ph["lyric"], best_seg, song_dur
                )
                moved = abs(new_start - old_start)

                corrected_phrases.append({
                    "lyric": ph["lyric"],
                    "start": new_start,
                    "end": new_end,
                    "line_index": ph.get("line_index", 0),
                    "confidence": round(confidence, 3),
                })
                stats["matched"] += 1

                marker = "✓" if moved > 2.0 else "·"
                print(
                    f"  {marker} [{confidence:.2f}] "
                    f'"{ph["lyric"][:55]}"  '
                    f"{old_start:.1f}→{new_start:.1f}s"
                    + (f"  (moved {moved:.1f}s)" if moved > 2.0 else "")
                )
            else:
                # Keep old timestamp — better than nothing
                corrected_phrases.append({
                    "lyric": ph["lyric"],
                    "start": old_start,
                    "end": old_end,
                    "line_index": ph.get("line_index", 0),
                    "confidence": round(confidence, 3),
                })
                stats["unmatched"] += 1
                print(
                    f"  ✗ [{confidence:.2f}] "
                    f'"{ph["lyric"][:55]}"  (kept old: {old_start:.1f}s)'
                )

        print(f"\n  Aligned: {sum(1 for p in corrected_phrases if p['confidence'] >= args.min_confidence)}"
              f"/{len(song['phrases'])} phrases")

        if args.dry_run:
            continue

        # Step 3: Save corrected phrases
        phrases_file = TRANSCRIPTS_DIR / f"{song['name']}_phrases.json"
        with open(phrases_file, "w") as f:
            json.dump(corrected_phrases, f, indent=2)
        print(f"  → Updated {phrases_file.name}")

        # Step 4: Re-chop audio clips
        clips = rechop_song(
            song["wav"], corrected_phrases,
            song["artist"], song["title"], song["song_idx"],
        )
        all_clips.extend(clips)
        print(f"  → Re-chopped {len(clips)} clips")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print(f"ALIGNMENT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Matched:    {stats['matched']}")
    print(f"  Unmatched:  {stats['unmatched']} (kept old timestamps)")
    print(f"  Kept old:   {stats['kept_old']} (no vocal segments)")

    if args.dry_run:
        print(f"\n[DRY RUN] No files were modified.")
        return

    # ── Step 5: Regenerate metadata ──
    random.seed(42)
    random.shuffle(all_clips)

    print(f"\nRegenerating metadata for {len(all_clips)} clips...")
    generate_outputs(all_clips)

    print(f"\n{'=' * 60}")
    print(f"DONE!  {len(all_clips)} clips realigned.")
    print(f"{'=' * 60}")
    print(f"\nNext steps:")
    print(f"  1. Re-extract features:")
    print(f"       cd phase-3-performance")
    print(f"       chuck --silent extract-rap-db.ck")
    print(f"  2. Regenerate deepfake clean lists:")
    print(f"       uv run python filter_clean.py")
    print(f"  3. Test:")
    print(f"       chuck deepfake-diss.ck:rap_db.txt")


if __name__ == "__main__":
    main()
