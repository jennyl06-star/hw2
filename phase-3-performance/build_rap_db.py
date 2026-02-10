#!/usr/bin/env python3
"""
build_rap_db.py — Smart Rap Clip Database Builder (v3)

Pipeline:
  1. Downloads rap songs from YouTube (yt-dlp)
  2. Fetches real lyrics from lyrics-api (Musixmatch / YouTube Music)
  3. Uses Grok text API to pick the best, punchiest lines for mosaic clips
  4. Aligns lyrics to audio using Grok Voice API transcription + fuzzy matching
     (falls back to librosa onset heuristic when Grok is unavailable)
  5. Chops audio at phrase-aligned boundaries
  6. Each clip has REAL, accurate lyrics that match the audio

Usage:
  uv run python build_rap_db.py                        # full pipeline
  uv run python build_rap_db.py --skip-download        # lyrics + chop only
  uv run python build_rap_db.py --artists "kendrick"   # subset
  uv run python build_rap_db.py --max-songs 3          # limit
  uv run python build_rap_db.py --skip-download --force-realign  # re-align

Requires:
  - XAI_API_KEY in .env (for Grok phrase selection + voice alignment)
  - ffmpeg on PATH
  - yt-dlp (installed via uv)
"""

import os
import sys
import json
import subprocess
import argparse
import random
import time
import re
import asyncio
import base64
import urllib.parse
from pathlib import Path
from difflib import SequenceMatcher
from dotenv import load_dotenv

import numpy as np
import requests
import soundfile as sf
import librosa

# Load .env
load_dotenv(Path(__file__).parent.parent / ".env")

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
FULL_SONGS_DIR = BASE_DIR / "rap_full_songs"
RAP_CLIPS_DIR = BASE_DIR / "rap_clips"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
METADATA_FILE = BASE_DIR / "clip_metadata.json"
CLIPS_LIST_FILE = BASE_DIR / "rap-clips.txt"
LYRICS_FILE = BASE_DIR / "clip_lyrics.txt"

SAMPLE_RATE = 44100
XAI_API_KEY = os.getenv("XAI_API_KEY", "")

# Clip constraints
MIN_PHRASE_DURATION = 0.6   # seconds — minimum clip length
MAX_PHRASE_DURATION = 4.0   # seconds — maximum clip length
MAX_CLIPS_PER_SONG = 50    # limit per song


# ──────────────────────────────────────────────────────────────────────────────
# RAP SONG DATABASE
# ──────────────────────────────────────────────────────────────────────────────

RAP_SONGS = [
    # ── Kendrick Lamar ──
    ("Kendrick Lamar", "HUMBLE.", "https://www.youtube.com/watch?v=tvTRZJ-4EyI"),
    ("Kendrick Lamar", "DNA.", "https://www.youtube.com/watch?v=NLZRYQMLDW4"),
    ("Kendrick Lamar", "m.A.A.d city", "https://www.youtube.com/watch?v=10yrPDf92hY"),
    ("Kendrick Lamar", "Not Like Us", "https://www.youtube.com/watch?v=T6eK-2OQtew"),
    # ── Drake ──
    ("Drake", "God's Plan", "https://www.youtube.com/watch?v=xpVfcZ0ZcFM"),
    ("Drake", "Started From The Bottom", "https://www.youtube.com/watch?v=RubBzkZzpUA"),
    ("Drake", "Hotline Bling", "https://www.youtube.com/watch?v=uxpDa-c-4Mc"),
    # ── J. Cole ──
    ("J. Cole", "No Role Modelz", "https://www.youtube.com/watch?v=imgYGEn0sWs"),
    ("J. Cole", "Middle Child", "https://www.youtube.com/watch?v=WILNIXZr2oc"),
    ("J. Cole", "LOVE YOURZ", "https://www.youtube.com/watch?v=Ka4BxFED_PU"),
    # ── Travis Scott ──
    ("Travis Scott", "SICKO MODE", "https://www.youtube.com/watch?v=6ONRf7h3Mdk"),
    ("Travis Scott", "goosebumps", "https://www.youtube.com/watch?v=Dst9gZkq1a8"),
    ("Travis Scott", "HIGHEST IN THE ROOM", "https://www.youtube.com/watch?v=tfSS1e3kYeo"),
    # ── Tupac ──
    ("Tupac", "California Love", "https://www.youtube.com/watch?v=5wBTdfAkqGU"),
    ("Tupac", "Hit Em Up", "https://www.youtube.com/watch?v=41qC3w3UUkU"),
    ("Tupac", "Changes", "https://www.youtube.com/watch?v=eXvBjCO19QY"),
    # ── Biggie ──
    ("Biggie", "Juicy", "https://www.youtube.com/watch?v=_JZom_gVfuw"),
    ("Biggie", "Hypnotize", "https://www.youtube.com/watch?v=glEiPXAYE-U"),
    ("Biggie", "Big Poppa", "https://www.youtube.com/watch?v=phaJXp_zMpY"),
    # ── A$AP Rocky ──
    ("ASAP Rocky", "Praise The Lord", "https://www.youtube.com/watch?v=Kbj2Zss-5GY"),
    ("ASAP Rocky", "L$D", "https://www.youtube.com/watch?v=yEG2VTHS9og"),
    # ── Eminem ──
    ("Eminem", "Lose Yourself", "https://www.youtube.com/watch?v=_Yhyp-_hX2s"),
    ("Eminem", "Rap God", "https://www.youtube.com/watch?v=XbGs_qK2PQA"),
    ("Eminem", "Without Me", "https://www.youtube.com/watch?v=YVkUvmDQ3HY"),
    # ── Kanye West ──
    ("Kanye West", "Stronger", "https://www.youtube.com/watch?v=PsO6ZnUZI0g"),
    ("Kanye West", "Gold Digger", "https://www.youtube.com/watch?v=6vwNcNOTVzY"),
    ("Kanye West", "POWER", "https://www.youtube.com/watch?v=L53gjP-TtGE"),
    # ── Nas ──
    ("Nas", "N.Y. State of Mind", "https://www.youtube.com/watch?v=hI8A14Qcv68"),
    ("Nas", "The World Is Yours", "https://www.youtube.com/watch?v=_srvHOu75vM"),
    # ── Jay-Z ──
    ("Jay-Z", "Empire State of Mind", "https://www.youtube.com/watch?v=0UjsXo9l6I8"),
    ("Jay-Z", "99 Problems", "https://www.youtube.com/watch?v=WwoM5fLITfk"),
    # ── Lil Wayne ──
    ("Lil Wayne", "A Milli", "https://www.youtube.com/watch?v=P19dow9ALYM"),
    ("Lil Wayne", "Lollipop", "https://www.youtube.com/watch?v=2IH8tNQAzSs"),
    # ── Others ──
    ("21 Savage", "a lot", "https://www.youtube.com/watch?v=DmWWqogr_r8"),
    ("Future", "Mask Off", "https://www.youtube.com/watch?v=xvZqHgFz51I"),
    ("Megan Thee Stallion", "Savage Remix", "https://www.youtube.com/watch?v=mRgI9aiCMSY"),
    ("Cardi B", "Bodak Yellow", "https://www.youtube.com/watch?v=PEGccV-NOm8"),
    ("Pop Smoke", "Dior", "https://www.youtube.com/watch?v=jnuKA5VFtRk"),
    ("Playboi Carti", "Magnolia", "https://www.youtube.com/watch?v=oCveByMXd_0"),
    ("Metro Boomin", "Creepin", "https://www.youtube.com/watch?v=6WB6gOBlJBs"),
]


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: Download (reuse from crawl_rap.py)
# ──────────────────────────────────────────────────────────────────────────────

def safe_name(index: int, artist: str, title: str) -> str:
    s = f"{index:03d}_{artist.replace(' ', '_')}_{title.replace(' ', '_')}"
    return "".join(c for c in s if c.isalnum() or c in "_-")


def download_song(artist: str, title: str, url: str, index: int) -> Path | None:
    name = safe_name(index, artist, title)
    output_path = FULL_SONGS_DIR / f"{name}.wav"
    if output_path.exists():
        print(f"  [skip] {output_path.name}")
        return output_path

    outtmpl = str(FULL_SONGS_DIR / f"{name}.%(ext)s")
    cmd = [
        "yt-dlp", "--js-runtimes", "node", "--remote-components", "ejs:github",
        "-f", "bestaudio/best", "-x", "--audio-format", "wav",
        "--audio-quality", "0",
        "--postprocessor-args", f"ffmpeg:-ar {SAMPLE_RATE} -ac 1",
        "-o", outtmpl, "--no-playlist",
        "--socket-timeout", "30", "--retries", "3", url,
    ]
    print(f"  [{index:03d}] Downloading: {artist} — {title}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            errs = [l for l in result.stderr.split('\n') if 'ERROR' in l]
            print(f"  [ERROR] {' '.join(errs)[:200]}")
            return None
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  [ERROR] {e}")
        return None

    if output_path.exists():
        return output_path
    for f in FULL_SONGS_DIR.glob(f"{name}.*"):
        if f.suffix == ".wav":
            return f
    return None


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: Fetch real lyrics from lyrics-api (Musixmatch / YouTube Music)
# ──────────────────────────────────────────────────────────────────────────────

LYRICS_API_BASE = "https://lyrics.lewdhutao.my.eu.org"


def fetch_lyrics(artist: str, title: str, song_name: str) -> dict | None:
    """
    Fetch lyrics from the public lyrics-api (LewdHuTao/lyrics-api).
    Tries Musixmatch first, falls back to YouTube Music.
    Caches results in transcripts/ directory.
    Returns: {"text": str, "lines": [str, ...], "source": str}
    """
    cache_path = TRANSCRIPTS_DIR / f"{song_name}.json"
    if cache_path.exists():
        print(f"  [cache] {cache_path.name}")
        with open(cache_path) as f:
            return json.load(f)

    # Clean title for search (remove special chars that confuse the API)
    clean_title = re.sub(r'[.\-\'\"!?]', '', title).strip()
    clean_artist = re.sub(r'[$]', 'S', artist)  # A$AP → ASAP

    lyrics_text = None
    source = None

    # Try Musixmatch first
    for endpoint, src_name in [
        (f"/v2/musixmatch/lyrics", "Musixmatch"),
        (f"/v2/youtube/lyrics", "YouTube Music"),
    ]:
        try:
            params = {"title": clean_title, "artist": clean_artist}
            url = f"{LYRICS_API_BASE}{endpoint}?{urllib.parse.urlencode(params)}"
            print(f"    Trying {src_name}: {clean_artist} — {clean_title}")
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("data", {}).get("lyrics", "")
                if text and len(text) > 50:  # sanity check
                    lyrics_text = text
                    source = src_name
                    break
            elif resp.status_code == 429:
                print(f"    [RATE LIMITED] Waiting 5s...")
                time.sleep(5)
                continue
        except Exception as e:
            print(f"    [{src_name} error] {e}")
            continue

    if not lyrics_text:
        print(f"  [WARN] No lyrics found for {artist} — {title}")
        return None

    # Split into lines, filter empty
    lines = [l.strip() for l in lyrics_text.split("\n") if l.strip()]

    result = {
        "text": lyrics_text,
        "lines": lines,
        "num_lines": len(lines),
        "source": source,
        "artist": artist,
        "title": title,
    }

    # Cache
    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"  → {len(lines)} lines from {source}")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: Grok Voice API alignment + Grok text API phrase selection
# ──────────────────────────────────────────────────────────────────────────────

# ── Grok Voice API: segment transcription for forced alignment ──

GROK_WS_URL = "wss://api.x.ai/v1/realtime"
GROK_SR = 24000  # Grok Realtime expects 24 kHz PCM16
SEG_DURATION = 10.0  # seconds per transcription window
SEG_STEP = 5.0       # step between windows


async def _grok_transcribe_segment(audio_24k, seg_id: str) -> str:
    """Send an audio segment to Grok Realtime Voice API, return transcript.

    Uses the input_audio_transcription event (not the response) to get the
    transcription of what was actually spoken/rapped in the audio.
    """
    import websockets

    pcm_int16 = (np.clip(audio_24k, -1.0, 1.0) * 32767).astype(np.int16)
    pcm_bytes = pcm_int16.tobytes()
    headers = {"Authorization": f"Bearer {XAI_API_KEY}"}
    transcript = ""

    try:
        async with websockets.connect(
            GROK_WS_URL, additional_headers=headers, close_timeout=10,
        ) as ws:
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "instructions": (
                        "You are a precise audio transcriber for rap music. "
                        "Transcribe EXACTLY what is rapped or spoken. "
                        "Output ONLY the raw transcription. "
                        "If purely instrumental, output: [INSTRUMENTAL]"
                    ),
                    "turn_detection": None,
                    "input_audio_transcription": {"model": "grok-2-latest"},
                    "audio": {
                        "input": {"format": {"type": "audio/pcm", "rate": GROK_SR}},
                    },
                }
            }))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                if msg.get("type") == "session.updated":
                    break

            CHUNK = 48000
            for i in range(0, len(pcm_bytes), CHUNK):
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm_bytes[i:i + CHUNK]).decode(),
                }))

            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await ws.send(json.dumps({
                "type": "response.create",
                "response": {"modalities": ["text"]},
            }))

            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    mtype = msg.get("type", "")
                    if mtype == "conversation.item.input_audio_transcription.completed":
                        transcript = msg.get("transcript", "")
                    elif mtype == "response.text.delta":
                        if not transcript:
                            transcript += msg.get("delta", "")
                    elif mtype == "response.done":
                        break
                    elif mtype == "error":
                        print(f"    [API ERR] {seg_id}: {msg.get('error', msg)}")
                        return ""
                except asyncio.TimeoutError:
                    break
    except Exception as e:
        print(f"    [CONN ERR] {seg_id}: {e}")
        return ""

    return transcript.strip()


def grok_transcribe_song(wav_path: Path, song_name: str) -> list[dict]:
    """
    Transcribe a full song in overlapping segments using Grok Voice API.
    Returns: [{"start": float, "end": float, "text": str}, ...]
    Cached in transcripts/{song_name}_grok_align.json.
    """
    cache = TRANSCRIPTS_DIR / f"{song_name}_grok_align.json"
    if cache.exists():
        print(f"  [align cache] {cache.name}")
        with open(cache) as f:
            return json.load(f)

    y, sr = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True)
    dur = len(y) / sr
    segments = []
    t = 0.0
    seg_num = 0

    while t < dur:
        e = min(t + SEG_DURATION, dur)
        seg_audio = y[int(t * sr):int(e * sr)]
        audio_24k = librosa.resample(seg_audio, orig_sr=SAMPLE_RATE, target_sr=GROK_SR)
        seg_id = f"{song_name}_s{seg_num:03d}"
        seg_num += 1

        text = ""
        for attempt in range(3):
            try:
                text = asyncio.run(
                    asyncio.wait_for(_grok_transcribe_segment(audio_24k, seg_id), timeout=45)
                ) or ""
                break
            except (asyncio.TimeoutError, Exception) as exc:
                if attempt < 2:
                    time.sleep(1)
                else:
                    print(f"    [WARN] Segment {seg_id} failed after 3 attempts: {exc}")

        segments.append({"start": round(t, 3), "end": round(e, 3), "text": text})

        if text and "[INSTRUMENTAL]" not in text.upper():
            print(f"    [{t:.0f}–{e:.0f}s] {text[:60]}...")
        t += SEG_STEP
        time.sleep(0.2)

    with open(cache, "w") as f:
        json.dump(segments, f, indent=2)
    return segments


def _clean_text(s: str) -> str:
    return re.sub(r"[^a-z0-9\s']", "", s.lower()).strip()


def _words(s: str) -> list[str]:
    return _clean_text(s).split()


def grok_align_line(lyric: str, segments: list[dict], duration: float) -> tuple[float, float, float]:
    """
    Given a lyric line and Grok-transcribed segments, find the best-matching
    segment and estimate the timestamp. Returns (start, end, confidence).
    """
    lw = _words(lyric)
    if not lw:
        return 0.0, MIN_PHRASE_DURATION, 0.0

    best_seg = None
    best_score = 0.0

    for seg in segments:
        text = seg.get("text", "")
        if not text or "[INSTRUMENTAL]" in text.upper():
            continue
        tw = _words(text)
        if not tw:
            continue

        # Strategy 1: word-set overlap
        lset, tset = set(lw), set(tw)
        overlap = len(lset & tset) / len(lset) if lset else 0

        # Strategy 2: consecutive-word sliding window
        consec = 0.0
        if len(lw) >= 2:
            for i in range(max(1, len(tw) - len(lw) + 1)):
                window = tw[i:i + len(lw)]
                m = sum(1 for a, b in zip(lw, window)
                        if a == b or SequenceMatcher(None, a, b).ratio() > 0.75)
                consec = max(consec, m / len(lw))

        # Strategy 3: SequenceMatcher on full strings
        seq = SequenceMatcher(None, _clean_text(lyric), _clean_text(text)).ratio()

        score = max(overlap * 0.85, consec * 0.95, seq)
        if score > best_score:
            best_score = score
            best_seg = seg

    if not best_seg or best_score < 0.15:
        return 0.0, MIN_PHRASE_DURATION, 0.0

    # Refine: estimate position within the matched segment
    text = best_seg["text"]
    tw = _words(text)
    seg_start = best_seg["start"]
    seg_dur = best_seg["end"] - seg_start

    best_pos = 0
    best_r = 0.0
    for i in range(max(1, len(tw) - len(lw) + 1)):
        window = tw[i:i + len(lw)]
        m = sum(1 for a, b in zip(lw, window)
                if a == b or SequenceMatcher(None, a, b).ratio() > 0.7)
        r = m / len(lw)
        if r > best_r:
            best_r = r
            best_pos = i

    wps = len(tw) / seg_dur if seg_dur > 0 else 5.0
    est_start = seg_start + best_pos / wps
    est_dur = max(MIN_PHRASE_DURATION, min(len(lw) / wps, MAX_PHRASE_DURATION))
    est_end = est_start + est_dur

    est_start = max(0.0, min(est_start, duration - MIN_PHRASE_DURATION))
    est_end = min(duration, max(est_end, est_start + MIN_PHRASE_DURATION))

    return round(est_start, 3), round(est_end, 3), round(best_score, 3)


def estimate_line_timestamps(wav_path: Path, num_lines: int) -> list[tuple[float, float]]:
    """
    FALLBACK (used when Grok Voice API is unavailable / --no-grok).
    Uses librosa onset detection to estimate where each lyric line falls.
    NOTE: This is inaccurate — onset detection captures drums/bass, not just
    vocals, and the linear mapping breaks on intros/bridges/choruses.
    Prefer grok_align_line() for accurate alignment.
    """
    y, sr = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True)
    duration = len(y) / sr

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=512,
        backtrack=True, units="frames"
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)

    if len(onset_times) < 2:
        line_dur = duration / num_lines
        return [(i * line_dur, (i + 1) * line_dur) for i in range(num_lines)]

    segments = []
    seg_start = onset_times[0]
    seg_end = onset_times[0]
    for t in onset_times[1:]:
        if t - seg_end < 0.3:
            seg_end = t
        else:
            segments.append((seg_start, seg_end))
            seg_start = t
            seg_end = t
    segments.append((seg_start, seg_end))

    while len(segments) < num_lines:
        longest_idx = max(range(len(segments)),
                         key=lambda i: segments[i][1] - segments[i][0])
        s, e = segments[longest_idx]
        mid = (s + e) / 2
        segments[longest_idx:longest_idx+1] = [(s, mid), (mid, e)]

    while len(segments) > num_lines and len(segments) > 1:
        min_gap_idx = min(range(len(segments) - 1),
                         key=lambda i: segments[i+1][0] - segments[i][1])
        merged = (segments[min_gap_idx][0], segments[min_gap_idx + 1][1])
        segments[min_gap_idx:min_gap_idx+2] = [merged]

    timestamps = []
    for i, (s, e) in enumerate(segments[:num_lines]):
        if i + 1 < len(segments):
            end = min(segments[i + 1][0], s + MAX_PHRASE_DURATION + 1.0)
        else:
            end = min(duration, s + MAX_PHRASE_DURATION + 1.0)
        end = max(end, s + MIN_PHRASE_DURATION)
        timestamps.append((round(s, 3), round(end, 3)))

    return timestamps


def grok_select_phrases(lyrics: dict, wav_path: Path, artist: str, title: str) -> list[dict]:
    """
    Use Grok text API to select the best lines, then Grok Voice API to
    align them to the audio with accurate timestamps.

    Pipeline:
      1. Grok text API → select punchiest lines
      2. Grok Voice API → transcribe song segments (cached)
      3. Fuzzy-match selected lines against transcriptions → timestamps
      4. Fallback to onset heuristic for lines that don't match
    """
    lines = lyrics["lines"]
    if not lines:
        return []

    if not XAI_API_KEY:
        print("  [WARN] No XAI_API_KEY — using onset fallback for all lines")
        timestamps = estimate_line_timestamps(wav_path, len(lines))
        return _lines_to_phrases(lines, timestamps)

    # ── Step 1: Grok text API — select best lines ──
    lines_str = "\n".join(f"{i}: {line}" for i, line in enumerate(lines))

    prompt = f"""You are selecting the BEST rap lines from "{title}" by {artist} for a sound mosaic art project.

Here are all the lyrics lines (numbered):

{lines_str}

Select the {min(MAX_CLIPS_PER_SONG, len(lines))} BEST lines that are:
- Punchy, iconic, quotable, or have strong energy
- Complete thoughts (not fragments like "yeah" or "uh")
- Suitable as standalone audio clips (1-4 seconds when spoken/rapped)

Skip: ad-libs only, pure repetition of the same line, section headers like "[Chorus]", 
very short filler lines ("yeah", "uh-huh", "what").

Return ONLY a JSON array of line numbers (integers). Example: [0, 3, 5, 8, 12]
Return ONLY the JSON array, no markdown, no explanation."""

    selected_indices = list(range(len(lines)))  # fallback: all lines
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "grok-3-mini-fast",
                "messages": [
                    {"role": "system", "content": "You are a precise JSON-only API. Return only valid JSON arrays of integers."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        if content.startswith("json"):
            content = content[4:].strip()

        selected_indices = json.loads(content)
        selected_indices = [i for i in selected_indices if isinstance(i, int) and 0 <= i < len(lines)]
        print(f"    → Grok selected {len(selected_indices)} / {len(lines)} lines")

    except Exception as e:
        print(f"  [ERROR] Grok text API failed: {e}")
        print("  Using all lines...")

    # ── Step 2: Grok Voice API — transcribe song for alignment ──
    song_name = wav_path.stem
    try:
        grok_segments = grok_transcribe_song(wav_path, song_name)
    except Exception as e:
        print(f"  [ERROR] Grok Voice transcription failed: {e}")
        print("  Falling back to onset heuristic...")
        grok_segments = None

    # Get song duration
    info = sf.info(str(wav_path))
    duration = info.duration

    # ── Step 3: Align selected lines ──
    phrases = []
    onset_fallback_count = 0
    onset_timestamps = None  # lazy-computed fallback

    if grok_segments:
        for idx in selected_indices:
            lyric = lines[idx]
            start, end, confidence = grok_align_line(lyric, grok_segments, duration)

            if confidence >= 0.25:
                phrases.append({
                    "lyric": lyric,
                    "start": start,
                    "end": end,
                    "line_index": idx,
                    "confidence": confidence,
                })
            else:
                # Fall back to onset heuristic for this line
                onset_fallback_count += 1
                if onset_timestamps is None:
                    onset_timestamps = estimate_line_timestamps(wav_path, len(lines))
                if idx < len(onset_timestamps):
                    s, e = onset_timestamps[idx]
                    phrases.append({
                        "lyric": lyric,
                        "start": s,
                        "end": e,
                        "line_index": idx,
                        "confidence": 0.0,
                    })

        if onset_fallback_count:
            print(f"    → {onset_fallback_count} lines fell back to onset heuristic")
    else:
        # Full onset fallback
        timestamps = estimate_line_timestamps(wav_path, len(lines))
        for idx in selected_indices:
            if idx < len(timestamps):
                start, end = timestamps[idx]
                phrases.append({
                    "lyric": lines[idx],
                    "start": start,
                    "end": end,
                    "line_index": idx,
                })

    return phrases


def _lines_to_phrases(lines: list[str], timestamps: list[tuple[float, float]]) -> list[dict]:
    """Convert all lyric lines to phrases (fallback when Grok unavailable)."""
    phrases = []
    for i, line in enumerate(lines):
        # Skip very short/filler lines
        if len(line.split()) < 3:
            continue
        if i < len(timestamps):
            start, end = timestamps[i]
            phrases.append({
                "lyric": line,
                "start": start,
                "end": end,
                "line_index": i,
            })
    return phrases[:MAX_CLIPS_PER_SONG]


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4: Chop audio at phrase-aligned boundaries
# ──────────────────────────────────────────────────────────────────────────────

def chop_song_by_phrases(
    wav_path: Path, phrases: list[dict],
    artist: str, title: str, song_idx: int,
    clip_dir: Path
) -> list[dict]:
    """
    Chop audio at estimated phrase boundaries from lyrics + onset alignment.
    Each clip = one complete rap phrase with accurate lyrics.
    """
    print(f"  Chopping: {artist} — {title} ({len(phrases)} phrases)")

    try:
        y, sr = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True)
    except Exception as e:
        print(f"  [ERROR] load failed: {e}")
        return []

    duration = len(y) / sr
    clips_meta = []
    safe_artist = "".join(c for c in artist if c.isalnum() or c in "_-")
    safe_title = "".join(c for c in title.replace(" ", "_") if c.isalnum() or c in "_-")

    for ci, phrase in enumerate(phrases[:MAX_CLIPS_PER_SONG]):
        start = phrase["start"]
        end = phrase["end"]

        # Add small padding (50ms) for natural sound
        start_padded = max(0, start - 0.05)
        end_padded = min(duration, end + 0.05)

        phrase_dur = end_padded - start_padded
        if phrase_dur < MIN_PHRASE_DURATION or phrase_dur > MAX_PHRASE_DURATION + 0.5:
            continue

        start_sample = int(start_padded * sr)
        end_sample = int(end_padded * sr)
        clip_audio = y[start_sample:end_sample]

        # Skip near-silent clips
        rms_val = float(np.sqrt(np.mean(clip_audio ** 2)))
        if rms_val < 0.005:
            continue

        clip_name = f"{song_idx:03d}_{safe_artist}_{safe_title}_p{ci:03d}.wav"
        clip_path = clip_dir / clip_name
        sf.write(str(clip_path), clip_audio, sr)

        clips_meta.append({
            "clip_file": clip_name,
            "artist": artist,
            "title": title,
            "lyric": phrase["lyric"],
            "start_time": round(start, 3),
            "end_time": round(end, 3),
            "duration": round(phrase_dur, 3),
            "rms": round(rms_val, 4),
            "song_index": song_idx,
            "clip_index": ci,
        })

    print(f"    → {len(clips_meta)} clips saved")
    return clips_meta


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5: Generate output files (with explicit/clean filtering)
# ──────────────────────────────────────────────────────────────────────────────

# Words/patterns that make a clip "explicit"
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
    "hoe", "hoes", "ho",
    "whore", "whores",
    # Drug references
    "cocaine", "crack", "molly", "ecstasy", "heroin",
    # Violent
    "kill", "murder", "murdered", "shooting", "shoot",
}


def is_explicit(lyric: str) -> bool:
    """Check if a lyric line contains explicit content."""
    words = set(re.sub(r'[^a-zA-Z\s\']', '', lyric.lower()).split())
    return bool(words & EXPLICIT_WORDS)


def generate_outputs(all_clips: list[dict]):
    # Tag each clip as explicit or clean
    for clip in all_clips:
        clip["explicit"] = is_explicit(clip.get("lyric", ""))

    clean_clips = [c for c in all_clips if not c["explicit"]]
    explicit_clips = [c for c in all_clips if c["explicit"]]

    print(f"  Content filter: {len(clean_clips)} clean, {len(explicit_clips)} explicit")

    # ── ALL clips (explicit) ──
    with open(CLIPS_LIST_FILE, "w") as f:
        for clip in all_clips:
            f.write(f"rap_clips/{clip['clip_file']}\n")
    print(f"  → {CLIPS_LIST_FILE.name}: {len(all_clips)} clips (all)")

    # ── CLEAN clips only ──
    clean_list_file = BASE_DIR / "rap-clips-clean.txt"
    with open(clean_list_file, "w") as f:
        for clip in clean_clips:
            f.write(f"rap_clips/{clip['clip_file']}\n")
    print(f"  → {clean_list_file.name}: {len(clean_clips)} clips (clean)")

    # ── CLEAN lyrics (for ChucK display) ──
    clean_lyrics_file = BASE_DIR / "clip_lyrics_clean.txt"
    with open(clean_lyrics_file, "w") as f:
        for clip in clean_clips:
            f.write(f"{clip['artist']}: {clip['lyric']}\n")
    print(f"  → {clean_lyrics_file.name}")

    # clip_metadata.json (all clips, with explicit flag)
    with open(METADATA_FILE, "w") as f:
        json.dump(all_clips, f, indent=2)
    print(f"  → {METADATA_FILE.name}")

    # clip_lyrics.txt (for ChucK — all)
    with open(LYRICS_FILE, "w") as f:
        for clip in all_clips:
            lyric = clip.get("lyric", "")
            artist = clip.get("artist", "")
            f.write(f"{artist}: {lyric}\n")
    print(f"  → {LYRICS_FILE.name}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN (parallelized)
# ──────────────────────────────────────────────────────────────────────────────

from concurrent.futures import ThreadPoolExecutor, as_completed

# Max parallel workers for I/O-bound tasks (lyrics API, Grok API)
MAX_WORKERS_IO = 8
# Max parallel workers for CPU-bound tasks (librosa onset analysis, audio chop)
MAX_WORKERS_CPU = 4


def _fetch_lyrics_task(args_tuple):
    """Worker for parallel lyrics fetching."""
    wav_path, artist, title, idx = args_tuple
    name = safe_name(idx, artist, title)
    lyrics = fetch_lyrics(artist, title, name)
    return idx, lyrics


def _process_song_task(args_tuple):
    """
    Worker for parallel Step 3+4: phrase selection + audio alignment + chopping.
    Each song is independent so this parallelizes well.
    """
    wav_path, artist, title, idx, lyrics, use_grok, clip_dir = args_tuple

    # Check phrase cache first
    phrase_cache = TRANSCRIPTS_DIR / f"{safe_name(idx, artist, title)}_phrases.json"
    if phrase_cache.exists():
        print(f"  [cache] {phrase_cache.name}")
        with open(phrase_cache) as f:
            phrases = json.load(f)
    else:
        print(f"  Processing: {artist} — {title} ({lyrics['num_lines']} lines)...")
        if use_grok and XAI_API_KEY:
            phrases = grok_select_phrases(lyrics, wav_path, artist, title)
        else:
            timestamps = estimate_line_timestamps(wav_path, len(lyrics["lines"]))
            phrases = _lines_to_phrases(lyrics["lines"], timestamps)

        # Cache
        with open(phrase_cache, "w") as f:
            json.dump(phrases, f, indent=2)

    # Chop immediately (no need to wait for other songs)
    clips = chop_song_by_phrases(wav_path, phrases, artist, title, idx, clip_dir)
    return idx, phrases, clips


def main():
    parser = argparse.ArgumentParser(description="Build lyric-aligned rap clip database (v3)")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--artists", type=str, default=None)
    parser.add_argument("--max-songs", type=int, default=None)
    parser.add_argument("--no-grok", action="store_true",
                        help="Skip Grok API, use heuristic phrase segmentation only")
    parser.add_argument("--force-realign", action="store_true",
                        help="Delete phrase caches to force re-alignment with Grok Voice API")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS_IO,
                        help=f"Number of parallel workers (default {MAX_WORKERS_IO})")
    args = parser.parse_args()

    for d in [FULL_SONGS_DIR, RAP_CLIPS_DIR, TRANSCRIPTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Clear phrase caches if --force-realign
    if args.force_realign:
        print("\n[force-realign] Deleting phrase caches and Grok alignment caches...")
        for f in TRANSCRIPTS_DIR.glob("*_phrases.json"):
            f.unlink()
            print(f"  deleted {f.name}")
        for f in TRANSCRIPTS_DIR.glob("*_grok_align.json"):
            f.unlink()
            print(f"  deleted {f.name}")

    # Clear old clips
    for f in RAP_CLIPS_DIR.glob("*.wav"):
        f.unlink()

    artists_filter = None
    if args.artists:
        artists_filter = [a.strip().lower() for a in args.artists.split(",")]

    # ── STEP 1: Download (sequential — yt-dlp handles its own concurrency) ──
    songs = []
    if not args.skip_download:
        print("\n" + "=" * 60)
        print("STEP 1: Downloading rap songs from YouTube")
        print("=" * 60)
        for i, (artist, title, url) in enumerate(RAP_SONGS):
            if artists_filter and not any(a in artist.lower() for a in artists_filter):
                continue
            path = download_song(artist, title, url, i)
            if path and path.exists():
                songs.append((path, artist, title, i))
    else:
        print("\n[skip-download] Using existing files")
        for i, (artist, title, url) in enumerate(RAP_SONGS):
            if artists_filter and not any(a in artist.lower() for a in artists_filter):
                continue
            name = safe_name(i, artist, title)
            p = FULL_SONGS_DIR / f"{name}.wav"
            if p.exists():
                songs.append((p, artist, title, i))

    if args.max_songs:
        songs = songs[:args.max_songs]

    print(f"\n{len(songs)} songs ready for processing")

    # ── STEP 2: Fetch lyrics (PARALLEL — all HTTP requests at once) ──
    print("\n" + "=" * 60)
    print(f"STEP 2: Fetching lyrics from lyrics-api ({args.workers} workers)")
    print("=" * 60)
    all_lyrics = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_fetch_lyrics_task, s): s for s in songs}
        for future in as_completed(futures):
            idx, lyrics = future.result()
            if lyrics and lyrics.get("lines"):
                all_lyrics[idx] = lyrics
            else:
                s = futures[future]
                print(f"  [SKIP] No lyrics for {s[1]} — {s[2]}")

    print(f"\n{len(all_lyrics)} songs with lyrics")

    # ── STEP 3+4: Phrase selection + alignment + chopping (PARALLEL) ──
    print("\n" + "=" * 60)
    print(f"STEP 3+4: Phrase selection + chopping ({args.workers} workers)")
    use_grok = not args.no_grok
    if use_grok:
        print(f"  (using Grok API: {'YES' if XAI_API_KEY else 'NO — using all lines'})")
    print("=" * 60)

    all_phrases = {}
    all_clips = []
    task_args = [
        (wav_path, artist, title, idx, all_lyrics[idx], use_grok, RAP_CLIPS_DIR)
        for wav_path, artist, title, idx in songs
        if idx in all_lyrics
    ]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_process_song_task, ta): ta for ta in task_args}
        for future in as_completed(futures):
            try:
                idx, phrases, clips = future.result()
                all_phrases[idx] = phrases
                all_clips.extend(clips)
            except Exception as e:
                ta = futures[future]
                print(f"  [ERROR] {ta[1]} — {ta[2]}: {e}")

    total_phrases = sum(len(p) for p in all_phrases.values())
    print(f"\n{total_phrases} total phrases across {len(all_phrases)} songs")

    # Shuffle for KNN variety
    random.seed(42)
    random.shuffle(all_clips)

    print(f"Total clips: {len(all_clips)}")

    # ── STEP 5: Output ──
    print("\n" + "=" * 60)
    print("STEP 5: Generating output files")
    print("=" * 60)
    generate_outputs(all_clips)

    # Summary
    artists_in_db = set(c["artist"] for c in all_clips)
    avg_dur = sum(c["duration"] for c in all_clips) / max(len(all_clips), 1)
    print("\n" + "=" * 60)
    print("DONE! Lyric-aligned database ready.")
    print("=" * 60)
    print(f"  Artists:    {len(artists_in_db)}")
    print(f"  Songs:      {len(songs)}")
    print(f"  Clips:      {len(all_clips)}")
    print(f"  Avg length: {avg_dur:.2f}s")
    print(f"\nSample clips:")
    for c in all_clips[:5]:
        print(f'  [{c["clip_file"]}] "{c["lyric"]}" ({c["duration"]}s)')
    print(f"\nNext: chuck --silent extract-rap-db.ck")


if __name__ == "__main__":
    main()
