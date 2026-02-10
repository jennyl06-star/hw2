# Install:
#   uv add yt-dlp
# Requirements:
#   ffmpeg must be installed and on PATH:
#     macOS: brew install ffmpeg
#
# This script downloads audio from each YouTube URL and converts it to .wav
# using yt-dlp + ffmpeg (no pytube, no pydub).

import os
import subprocess

urls = [
    "https://www.youtube.com/watch?v=d3Ia0giTLhk",       # 1. Vine Boom
    "https://www.youtube.com/watch?v=D2_r4q2imnQ",       # 2. Bruh
    "https://www.youtube.com/watch?v=-hc3nTS7Poo",       # 3. He He He Ha
    "https://www.youtube.com/watch?v=YN1SGS7N02U",       # 4. Fart
    "https://www.youtube.com/watch?v=2D-ZO2rGcSA",       # 5. John Cena
    "https://www.youtube.com/watch?v=VXwBY_dv2Qo",       # 6. Rizz
    "https://www.youtube.com/watch?v=FgxoZ1qi4JM",       # 7. Man Screaming
    "https://www.youtube.com/watch?v=A8wK-vhuWog",       # 8. Windows XP Shutdown
    "https://www.youtube.com/watch?v=QQR7t712Mhg",       # 9. FBI Open Up
    "https://www.youtube.com/watch?v=K0f7mz3UxBw",       # 10. Hawk Tuah
    "https://www.youtube.com/watch?v=OFr74zI1LBM",       # 11. Airhorn
    "https://www.youtube.com/watch?v=CQeezCdF4mk",       # 13. Sad Trombone
    "https://www.youtube.com/watch?v=r6JK-gRELI0",       # 14. Wilhelm Scream
    "https://www.youtube.com/watch?v=kNAQ9THQm5g",       # 15. Sin City
    "https://www.youtube.com/watch?v=ahAIvjWs0Gs",       # 16. Bababooey
    "https://www.youtube.com/watch?v=CpGtBnVZLSk",       # 17. Awkward Crickets
    "https://www.youtube.com/watch?v=ZKFDK-Z1QUE",       # 18. Pew
    "https://www.youtube.com/watch?v=FRpq7o1mKXY",       # 19. Wrong Buzzer
    "https://www.youtube.com/watch?v=gQk8SrLjqvg"        # 20. English or Spanish
]

output_dir = "meme_sounds_wav"
os.makedirs(output_dir, exist_ok=True)


def require_on_path(cmd: str) -> None:
    """Exit early with a helpful message if a required binary isn't available."""
    try:
        subprocess.run([cmd, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        raise SystemExit(
            f"'{cmd}' not found on PATH. Install it first.\n"
            f"macOS: brew install {cmd}\n"
        )


def safe_outtmpl(i: int) -> str:
    """
    yt-dlp output template.
    - %(title).100s truncates title to 100 chars
    - {i:02d} keeps ordering stable
    """
    return os.path.join(output_dir, f"{i:02d}_%(title).100s.%(ext)s")


def download_wav(url: str, i: int) -> None:
    """
    Uses yt-dlp to:
      - download best audio
      - extract audio (-x)
      - convert to wav via ffmpeg
    """
    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "-o", safe_outtmpl(i),
        "--no-playlist",
        url,
    ]

    print(f"[{i:02d}] Downloading + converting: {url}")
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed with exit code {result.returncode}")


def main():
    require_on_path("ffmpeg")
    require_on_path("yt-dlp")

    errors = []
    for i, url in enumerate(urls, 1):
        try:
            download_wav(url, i)
            print(f"[{i:02d}] Saved to: {output_dir}")
        except Exception as e:
            print(f"Error with {url}: {e}")
            errors.append((i, url, str(e)))

    print("\nAll downloads and conversions complete!")
    if errors:
        print("\nSome items failed:")
        for i, url, msg in errors:
            print(f"  - [{i:02d}] {url} -> {msg}")


if __name__ == "__main__":
    main()
