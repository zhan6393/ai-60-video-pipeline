#!/usr/bin/env python3
"""AI 60-Second — offline demo of an automated short-video pipeline.

Stages: brief -> script -> voiceover -> visuals -> assemble.

This is a *demo replica* of a real production pipeline (topic briefing,
script writing, TTS voiceover, AI image generation, ffmpeg assembly into a
45-60s vertical 9:16 video). The demo runs fully offline using only the
Python standard library, with graceful degradation:

  - voiceover : stdlib `wave` placeholder tone in demo mode; real speech via
                optional `edge-tts` when `--tts edge` is passed and installed.
  - visuals   : placeholder vertical cards via optional Pillow; skipped with
                a warning when Pillow is missing.
  - assemble  : `output/demo.mp4` via optional ffmpeg; otherwise only
                `output/manifest.json` is produced.

CLI:
    python pipeline.py --list-topics
    python pipeline.py --topic topics/open-weights-model.json --demo
    python pipeline.py --topic topics/ai-chip.json --tts edge   # needs edge-tts
"""

import argparse
import json
import math
import shutil
import struct
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOPICS_DIR = ROOT / "topics"
SCRIPTS_DIR = ROOT / "scripts"
OUT_DIR = ROOT / "output"

TARGET_SECONDS = 60.0   # keep the video in the 45-60s band
MIN_SECONDS = 45.0


# ---------------------------------------------------------------- brief ----
def load_topic(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        topic = json.load(f)
    for field in ("title", "hook", "key_points", "cta"):
        if field not in topic:
            raise ValueError(f"topic file {path} is missing field: {field}")
    return topic


def list_topics() -> None:
    files = sorted(TOPICS_DIR.glob("*.json"))
    if not files:
        print(f"No topic files found in {TOPICS_DIR}")
        return
    print(f"Available topics in {TOPICS_DIR}/:")
    for p in files:
        try:
            title = load_topic(p).get("title", "?")
        except Exception as exc:  # keep listing even if one file is broken
            title = f"<unreadable: {exc}>"
        print(f"  {p.name:32s} {title}")


# --------------------------------------------------------------- script ----
def build_script(topic: dict) -> tuple[str, list[str]]:
    """Assemble narration text plus a storyboard (one visual per beat)."""
    narration = [topic["hook"], ""]
    storyboard = [f"Title card — {topic['title']}"]
    for i, point in enumerate(topic["key_points"], 1):
        narration.append(point)
        keyword = point.split(",")[0][:48]
        storyboard.append(f"Beat {i}: keyword card — \"{keyword}\"")
    narration += ["", topic["cta"]]
    return "\n".join(narration), storyboard


def estimate_duration(narration: str) -> float:
    """~150 wpm spoken English; clamp into the 45-60s band."""
    words = len(narration.split())
    seconds = words / 2.5
    return max(MIN_SECONDS, min(TARGET_SECONDS, seconds))


# ------------------------------------------------------------ voiceover ----
def synth_placeholder_wav(path: Path, duration: float, sr: int = 22050) -> None:
    """Stdlib-only placeholder 'voiceover': soft alternating tones.

    It marks the timing of the narration track without claiming to be
    speech. Real speech comes from `--tts edge` (optional edge-tts).
    """
    n = int(duration * sr)
    freqs = (220.0, 261.63, 293.66, 329.63)  # A3 C4 D4 E4, 5s per segment
    seg = 5.0
    frames = bytearray()
    for i in range(n):
        t = i / sr
        f = freqs[int(t / seg) % len(freqs)]
        env = min(1.0, t / 0.3, (duration - t) / 0.3)  # fade in/out
        v = int(9000 * env * math.sin(2 * math.pi * f * t))
        frames += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def voiceover_edge_tts(narration: str, path: Path) -> bool:
    """Try real TTS via edge-tts; return True on success."""
    try:
        import edge_tts  # noqa: F401  (only checking availability)
    except ImportError:
        return False
    cmd = [
        sys.executable, "-m", "edge_tts",
        "--voice", "en-US-AriaNeural",
        "--text", narration,
        "--write-media", str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# -------------------------------------------------------------- visuals ----
def render_cards(storyboard: list[str], out_dir: Path) -> list[Path]:
    """Render 1080x1920 placeholder cards with Pillow. Returns image paths."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[visuals] Pillow not installed — skipping visuals "
              "(pip install Pillow to enable).")
        return []

    W, H = 1080, 1920
    BG, ACCENT, TEXT = (11, 16, 32), (0, 229, 255), (240, 245, 255)
    font_big = ImageFont.load_default(size=64)
    font_small = ImageFont.load_default(size=40)

    def wrap(draw, text, font, max_w):
        words, lines, cur = text.split(), [], ""
        for wd in words:
            trial = f"{cur} {wd}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
        return lines

    paths = []
    for idx, beat in enumerate(storyboard):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 14], fill=ACCENT)
        d.rectangle([0, H - 14, W, H], fill=ACCENT)
        lines = wrap(d, beat, font_big, W - 160)
        y = H // 2 - len(lines) * 40
        for line in lines:
            d.text((80, y), line, font=font_big, fill=TEXT)
            y += 84
        d.text((80, 120), f"AI 60s · {idx + 1}/{len(storyboard)}",
               font=font_small, fill=ACCENT)
        p = out_dir / f"card_{idx:02d}.png"
        img.save(p)
        paths.append(p)
    print(f"[visuals] rendered {len(paths)} placeholder cards (1080x1920).")
    return paths


# ------------------------------------------------------------- assemble ----
def assemble_video(images: list[Path], audio: Path, out_dir: Path,
                   duration: float) -> Path | None:
    """Assemble output/demo.mp4 with ffmpeg; None when ffmpeg is missing."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("[assemble] ffmpeg not found — skipping mp4, "
              "manifest.json is the final artifact.")
        return None
    if not images:
        print("[assemble] no visuals — skipping mp4, "
              "manifest.json is the final artifact.")
        return None

    per = duration / len(images)
    lst = out_dir / "concat.txt"
    with open(lst, "w", encoding="utf-8") as f:
        for img in images:
            f.write(f"file '{img.name}'\n duration {per:.2f}\n")
        f.write(f"file '{images[-1].name}'\n")  # concat demuxer tail rule
    mp4 = out_dir / "demo.mp4"
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-i", str(audio), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-r", "30", "-c:a", "aac", "-shortest", str(mp4)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        print(f"[assemble] ffmpeg failed: {exc.stderr[-500:]}")
        return None
    print(f"[assemble] wrote {mp4} ({mp4.stat().st_size / 1024:.0f} KB).")
    return mp4


# ------------------------------------------------------------------ main ----
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list-topics", action="store_true",
                    help="list available topic files and exit")
    ap.add_argument("--topic", type=Path,
                    help="topic JSON file, e.g. topics/open-weights-model.json")
    ap.add_argument("--demo", action="store_true",
                    help="offline demo mode: placeholder audio (default)")
    ap.add_argument("--tts", choices=["demo", "edge"], default="demo",
                    help="voiceover engine: demo placeholder (default) or edge-tts")
    args = ap.parse_args()

    if args.list_topics:
        list_topics()
        return 0
    if not args.topic:
        ap.error("--topic is required (or use --list-topics)")

    topic_path = args.topic if args.topic.is_absolute() else ROOT / args.topic
    try:
        topic = load_topic(topic_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error loading topic: {exc}", file=sys.stderr)
        return 1

    SCRIPTS_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)

    # 1. brief
    slug = topic_path.stem
    print(f"[brief] {topic['title']}")
    print(f"        hook: {topic['hook'][:72]}...")

    # 2. script
    narration, storyboard = build_script(topic)
    duration = estimate_duration(narration)
    script_file = SCRIPTS_DIR / f"{slug}_script.txt"
    script_file.write_text(
        f"# {topic['title']}\n# ~{duration:.0f}s narration\n\n{narration}\n",
        encoding="utf-8")
    print(f"[script] wrote {script_file.relative_to(ROOT)} "
          f"({len(narration.split())} words, ~{duration:.0f}s)")

    # 3. voiceover
    audio_file = OUT_DIR / "voiceover.wav"
    tts_used = "demo-placeholder"
    if args.tts == "edge" and not args.demo:
        if voiceover_edge_tts(narration, audio_file):
            tts_used = "edge-tts"
            print(f"[voiceover] edge-tts wrote {audio_file.name}")
        else:
            print("[voiceover] edge-tts unavailable — falling back to "
                  "demo placeholder audio.")
    if tts_used == "demo-placeholder":
        synth_placeholder_wav(audio_file, duration)
        print(f"[voiceover] demo placeholder tone -> {audio_file.name} "
              f"({duration:.0f}s, stdlib wave only)")

    # 4. visuals
    images = render_cards(storyboard, OUT_DIR)

    # 5. assemble
    mp4 = assemble_video(images, audio_file, OUT_DIR, duration)

    # manifest — always produced; it is the contract of this demo
    manifest = {
        "project": "ai-60-video-pipeline (offline demo replica)",
        "topic": topic["title"],
        "mode": "demo" if args.demo or args.tts == "demo" else args.tts,
        "stages": {
            "brief": {"topic_file": str(topic_path.relative_to(ROOT))},
            "script": {"file": str(script_file.relative_to(ROOT)),
                       "words": len(narration.split()),
                       "estimated_seconds": round(duration, 1),
                       "storyboard_beats": len(storyboard)},
            "voiceover": {"file": str(audio_file.relative_to(ROOT)),
                          "engine": tts_used},
            "visuals": {"cards": [str(p.relative_to(ROOT)) for p in images],
                        "resolution": "1080x1920" if images else None},
            "assemble": {"mp4": str(mp4.relative_to(ROOT)) if mp4 else None,
                         "ffmpeg_available": shutil.which("ffmpeg") is not None},
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": ("Demo replica: placeholder tone audio and keyword cards stand "
                 "in for real TTS and AI-generated visuals. See README "
                 "\"Honest caveats\"."),
    }
    manifest_file = OUT_DIR / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[done] manifest -> {manifest_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
