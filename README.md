# AI 60-Second — Automated Short-Video Pipeline (Offline Demo)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/deps-stdlib%20only-brightgreen)](requirements.txt)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

An end-to-end pipeline that turns a news topic into a 45–60 second vertical (9:16) short video:
**topic brief → narration script → voiceover → visuals → ffmpeg assembly**.

> **Demo replica.** This repo is an *offline, dependency-free re-implementation* of a real
> production pipeline I built and operate daily ("AI 60秒"). It demonstrates the **orchestration
> logic** — stage contracts, timing math, and graceful degradation — using placeholder audio
> and images instead of paid LLM / TTS / image-generation APIs. See [Honest caveats](#honest-caveats).

## Pipeline

```
┌─────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐   ┌───────────┐
│  brief  │──▶│  script  │──▶│ voiceover  │──▶│ visuals  │──▶│ assemble  │
│topic    │   │hook + key│   │demo: wave  │   │demo: PIL  │   │demo:      │
│JSON     │   │points →  │   │placeholder │   │1080x1920  │   │ffmpeg →   │
│         │   │narration │   │tone (or    │   │keyword    │   │demo.mp4   │
│         │   │+storyboard│  │edge-tts)   │   │cards      │   │           │
└─────────┘   └──────────┘   └────────────┘   └──────────┘   └───────────┘
                                                              │ no ffmpeg?
                                                              ▼
                                                     output/manifest.json
                                                     (always produced)
```

Each stage prints a one-line status; `output/manifest.json` records every stage's inputs,
outputs, and timings — it is the pipeline's contract and always produced, even when
optional dependencies are missing.

## Quickstart

Zero required dependencies (Python 3.10+ stdlib only):

```bash
# see the example topics
python pipeline.py --list-topics

# run the full pipeline in offline demo mode
python pipeline.py --topic topics/open-weights-model.json --demo

# real TTS voiceover (optional: pip install edge-tts)
python pipeline.py --topic topics/ai-chip.json --tts edge
```

Optional extras:

```bash
pip install -r requirements.txt   # edge-tts (real voice) + Pillow (visual cards)
```

Behavior without them: voiceover still works (stdlib `wave` placeholder tone), visuals are
skipped with a warning, and the mp4 step is skipped — `output/manifest.json` is still written.

## Example output

`output/manifest.json` (from `--topic topics/open-weights-model.json --demo`):

```json
{
  "project": "ai-60-video-pipeline (offline demo replica)",
  "topic": "Astra-2B: A New Open-Weights Model (Example Topic)",
  "mode": "demo",
  "stages": {
    "brief": { "topic_file": "topics/open-weights-model.json" },
    "script": {
      "file": "scripts/open-weights-model_script.txt",
      "words": 108,
      "estimated_seconds": 45.0,
      "storyboard_beats": 5
    },
    "voiceover": { "file": "output/voiceover.wav", "engine": "demo-placeholder" },
    "visuals": { "cards": ["output/card_00.png", "..."], "resolution": "1080x1920" },
    "assemble": { "mp4": "output/demo.mp4", "ffmpeg_available": true }
  },
  "generated_at": "2026-10-10T...",
  "note": "Demo replica: placeholder tone audio and keyword cards stand in for real TTS and AI-generated visuals."
}
```

With ffmpeg installed you also get `output/demo.mp4` — a 1080×1920 video with the
placeholder voiceover track; without it, the manifest is the final artifact.

## Project structure

```
ai-60-video-pipeline/
├── pipeline.py            # the whole pipeline: brief → script → voiceover → visuals → assemble
├── topics/                # example topic briefs (title, hook, key_points, cta)
│   ├── open-weights-model.json
│   ├── ai-chip.json
│   └── robotics-fleet.json
├── scripts/               # generated narration scripts (gitignored)
├── output/                # generated audio / cards / demo.mp4 / manifest.json (gitignored)
├── requirements.txt       # optional deps only (edge-tts, Pillow)
├── LICENSE                # MIT
└── .gitignore
```

## Honest caveats

- **This is a demo replica, not the production system.** The real pipeline uses an LLM for
  topic research and scriptwriting, a neural TTS service for voiceover, and an image-generation
  API for visuals. This repo replaces those with a JSON topic file, a template script builder,
  a stdlib-synthesized placeholder tone, and Pillow keyword cards — so it runs offline, for free.
- **Example topics are fictional.** Names like "Astra-2B" and "Helios-A1" are invented for the
  demo; any resemblance to real products is coincidental.
- **The demo voiceover is a tone, not speech.** It exists only to carry correct timing into the
  assembled mp4. Pass `--tts edge` (with `edge-tts` installed) for real speech.
- **No credentials, no network calls, no personal data** anywhere in this repo.

## Why this exists

The production version of this pipeline runs on a daily schedule and produces a finished
short video every day — briefing, production, and publish reminders all automated. This repo
exists to show *how the orchestration works*: deterministic stage contracts, duration math
that keeps every video in the 45–60s band, and degradation paths that never leave the
pipeline in a broken half-state.
