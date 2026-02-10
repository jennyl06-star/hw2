#!/usr/bin/env python3
"""
generate_deepfakes.py — Generate AI deepfake rap clips using Grok Voice API TTS

Takes the real rap clips (with lyrics from clip_metadata.json) and generates
AI voice deepfake versions using xAI's Grok Voice Agent API.

Each clip gets deepfaked in one of 5 Grok voice personas:
  Ara  — warm female        Rex — confident male
  Sal  — neutral            Eve — energetic female
  Leo  — authoritative male

The deepfake clips are used in the performance to gradually replace
the real clips as the "AI takeover" escalates.

Usage:
  uv run python generate_deepfakes.py                   # all clips, 8 workers
  uv run python generate_deepfakes.py --max-clips 10    # test with 10
  uv run python generate_deepfakes.py --workers 4       # fewer workers
  uv run python generate_deepfakes.py --voices rex,ara  # specific voices only

Requires:
  - XAI_API_KEY in .env
  - clip_metadata.json (from build_rap_db.py)
"""

import os
import sys
import json
import asyncio
import base64
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

import numpy as np
import soundfile as sf

# Load .env
load_dotenv(Path(__file__).parent.parent / ".env")

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
METADATA_FILE = BASE_DIR / "clip_metadata.json"
DEEPFAKE_DIR = BASE_DIR / "deepfake_clips"
DEEPFAKE_LIST_FILE = BASE_DIR / "deepfake-clips.txt"
DEEPFAKE_METADATA_FILE = BASE_DIR / "deepfake_metadata.json"

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
GROK_VOICE_WS_URL = "wss://api.x.ai/v1/realtime"

# Output sample rate (match our audio pipeline)
OUTPUT_SR = 44100
# Grok Voice API sample rate
GROK_SR = 24000

# Available Grok voice personas
VOICES = {
    "Ara": "warm female voice, smooth and confident",
    "Rex": "confident male voice, deep and powerful",
    "Sal": "neutral voice, clean and precise",
    "Eve": "energetic female voice, dynamic and bold",
    "Leo": "authoritative male voice, commanding and clear",
}

MAX_WORKERS = 8


# ──────────────────────────────────────────────────────────────────────────────
# GROK VOICE TTS
# ──────────────────────────────────────────────────────────────────────────────

async def _tts_one_clip(lyric: str, voice: str, clip_name: str) -> bytes | None:
    """
    Generate TTS audio for a single lyric using Grok Voice API.

    Protocol:
      1. Connect WebSocket to wss://api.x.ai/v1/realtime
      2. session.update: set voice, output audio format (PCM 24kHz)
      3. conversation.item.create: add text message with the lyric
      4. response.create: request audio modality
      5. Collect response.output_audio.delta chunks → PCM bytes
    """
    import websockets

    headers = {"Authorization": f"Bearer {XAI_API_KEY}"}
    audio_chunks = []

    try:
        async with websockets.connect(
            GROK_VOICE_WS_URL,
            additional_headers=headers,
            close_timeout=10,
        ) as ws:
            # 1. Configure session
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "voice": voice,
                    "instructions": (
                        "You are a rapper performing a verse. "
                        "Rap the given text with energy and flow. "
                        "Do NOT add any words, commentary, or explanation. "
                        "Just perform the exact lyrics given, nothing more."
                    ),
                    "turn_detection": None,  # manual mode
                    "audio": {
                        "output": {
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

            # 2. Send the lyric as a user message
            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": f"Rap this line: {lyric}",
                    }],
                }
            }))

            # 3. Request audio response
            await ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["audio"],
                }
            }))

            # 4. Collect audio delta chunks
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    msg_type = msg.get("type", "")

                    if msg_type == "response.output_audio.delta":
                        chunk_b64 = msg.get("delta", "")
                        if chunk_b64:
                            audio_chunks.append(base64.b64decode(chunk_b64))

                    elif msg_type == "response.done":
                        break

                    elif msg_type == "error":
                        print(f"    [ERROR] {clip_name}: {msg.get('error', msg)}")
                        return None

                except asyncio.TimeoutError:
                    print(f"    [TIMEOUT] {clip_name}")
                    break

    except Exception as e:
        print(f"    [CONN ERROR] {clip_name}: {e}")
        return None

    if not audio_chunks:
        return None

    return b"".join(audio_chunks)


def generate_deepfake_clip(clip: dict, voice: str) -> dict | None:
    """
    Generate a single deepfake clip. Returns metadata dict or None on failure.
    """
    lyric = clip["lyric"]
    orig_name = clip["clip_file"]
    # Name: deepfake_{voice}_{original_name}
    df_name = f"df_{voice.lower()}_{orig_name}"
    df_path = DEEPFAKE_DIR / df_name

    # Skip if already generated
    if df_path.exists():
        return {
            "deepfake_file": df_name,
            "original_file": orig_name,
            "voice": voice,
            "lyric": lyric,
            "artist": clip["artist"],
            "title": clip["title"],
        }

    # Run async TTS
    pcm_bytes = asyncio.run(_tts_one_clip(lyric, voice, df_name))
    if not pcm_bytes:
        return None

    # Convert PCM16 24kHz → float → resample to 44100 → save WAV
    pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
    audio_24k = pcm_int16.astype(np.float32) / 32768.0

    # Resample 24kHz → 44100Hz
    import librosa
    audio_44k = librosa.resample(audio_24k, orig_sr=GROK_SR, target_sr=OUTPUT_SR)

    # Save
    sf.write(str(df_path), audio_44k, OUTPUT_SR)

    return {
        "deepfake_file": df_name,
        "original_file": orig_name,
        "voice": voice,
        "lyric": lyric,
        "artist": clip["artist"],
        "title": clip["title"],
        "duration": round(len(audio_44k) / OUTPUT_SR, 3),
    }


def _worker(args_tuple):
    """Thread worker for parallel deepfake generation."""
    clip, voice = args_tuple
    try:
        result = generate_deepfake_clip(clip, voice)
        if result:
            print(f"  ✓ [{voice:3s}] {result['deepfake_file']}")
        return result
    except Exception as e:
        print(f"  ✗ [{voice:3s}] {clip['clip_file']}: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate AI deepfake rap clips via Grok Voice TTS")
    parser.add_argument("--max-clips", type=int, default=None,
                        help="Limit number of clips to process")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS,
                        help=f"Parallel workers (default {MAX_WORKERS})")
    parser.add_argument("--voices", type=str, default=None,
                        help="Comma-separated voices to use (default: all 5)")
    parser.add_argument("--voice-per-clip", action="store_true",
                        help="Generate ALL voices for each clip (5x output)")
    args = parser.parse_args()

    if not XAI_API_KEY:
        print("ERROR: XAI_API_KEY not set in .env")
        sys.exit(1)

    # Load clip metadata
    if not METADATA_FILE.exists():
        print(f"ERROR: {METADATA_FILE} not found. Run build_rap_db.py first.")
        sys.exit(1)

    with open(METADATA_FILE) as f:
        clips = json.load(f)

    print(f"Loaded {len(clips)} clips from {METADATA_FILE.name}")

    # Parse voice selection
    if args.voices:
        selected_voices = [v.strip().capitalize() for v in args.voices.split(",")]
        for v in selected_voices:
            if v not in VOICES:
                print(f"ERROR: Unknown voice '{v}'. Available: {list(VOICES.keys())}")
                sys.exit(1)
    else:
        selected_voices = list(VOICES.keys())

    print(f"Voices: {', '.join(selected_voices)}")

    # Create output directory
    DEEPFAKE_DIR.mkdir(parents=True, exist_ok=True)

    # Limit clips if requested
    if args.max_clips:
        clips = clips[:args.max_clips]

    # Build task list: assign each clip a voice (round-robin) or all voices
    tasks = []
    if args.voice_per_clip:
        # Every clip × every voice = 5x clips
        for clip in clips:
            for voice in selected_voices:
                tasks.append((clip, voice))
        print(f"Generating {len(tasks)} deepfake clips ({len(clips)} × {len(selected_voices)} voices)")
    else:
        # Each clip gets ONE voice (round-robin for variety)
        for i, clip in enumerate(clips):
            voice = selected_voices[i % len(selected_voices)]
            tasks.append((clip, voice))
        print(f"Generating {len(tasks)} deepfake clips (1 voice each, round-robin)")

    # ── PARALLEL GENERATION ──
    print(f"\n{'=' * 60}")
    print(f"Generating deepfakes ({args.workers} parallel workers)")
    print(f"{'=' * 60}")

    all_results = []
    succeeded = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_worker, t): t for t in tasks}
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_results.append(result)
                succeeded += 1
            else:
                failed += 1

    # ── OUTPUT FILES ──
    print(f"\n{'=' * 60}")
    print(f"Results: {succeeded} succeeded, {failed} failed")
    print(f"{'=' * 60}")

    # deepfake-clips.txt (for ChucK)
    with open(DEEPFAKE_LIST_FILE, "w") as f:
        for r in all_results:
            f.write(f"deepfake_clips/{r['deepfake_file']}\n")
    print(f"  → {DEEPFAKE_LIST_FILE.name}: {len(all_results)} clips")

    # deepfake_metadata.json
    with open(DEEPFAKE_METADATA_FILE, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"  → {DEEPFAKE_METADATA_FILE.name}")

    # Voice distribution
    voice_counts = {}
    for r in all_results:
        v = r["voice"]
        voice_counts[v] = voice_counts.get(v, 0) + 1
    print(f"\nVoice distribution:")
    for v, c in sorted(voice_counts.items()):
        print(f"  {v}: {c} clips")

    print(f"\nSample deepfakes:")
    for r in all_results[:5]:
        print(f'  [{r["voice"]:3s}] "{r["lyric"][:60]}" → {r["deepfake_file"]}')

    print(f"\nDone! Deepfake clips saved to {DEEPFAKE_DIR}/")


if __name__ == "__main__":
    main()
