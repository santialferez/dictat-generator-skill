# Gemini Dictation Generator Skill

Reusable Agent Skill and CLI for generating **classroom dictation audio packages** in any language with Google Gemini TTS.

From a topic, a piece of prose, or a ready-made transcript, the tool produces a complete dictation package: a TTS-ready script with repetitions, pauses and spoken punctuation; a clean transcript for proofreading; and `WAV`/`MP3` audio, including optional speed variants.

It works both as a standalone command-line script and as an installable [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) (`SKILL.md`) for Claude Code, Codex, Cursor, Pi, and other agents.

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Input Modes](#input-modes)
- [Dictation Levels](#dictation-levels)
- [CLI Reference](#cli-reference)
- [Output Files](#output-files)
- [Install the Skill](#install-the-skill)
- [Troubleshooting](#troubleshooting)
- [Repository Layout](#repository-layout)
- [License](#license)

## Features

- **Language-neutral.** Pass any `--language` (Catalan, Spanish, English, French, …); script generation and TTS instructions adapt to it, including spoken punctuation words.
- **Four input modes.** Generate from a topic, adapt existing prose, preserve a text exactly, or synthesize a prepared transcript.
- **Four difficulty levels.** `initial`, `basic`, `intermediate`, `advanced`, each with its own length, vocabulary, grammar, and repetition policy (see [`references/levels.md`](skills/gemini-dictat-generator/references/levels.md)).
- **Classroom-ready audio.** Controlled repetition, `[slow]` / `[short pause]` / `[long pause]` cues, and punctuation spoken aloud so learners know what to write.
- **No spoken meta labels.** The generator rejects labels such as `Repeat:` or `Title:` before TTS so they do not leak into the audio.
- **Clean proofreading transcript.** A continuous-prose version of the dictation for correcting students' work.
- **MP3-first output.** Export classroom-ready MP3s at `1.0x` and `1.25x` by default, while treating WAV files as intermediates unless explicitly kept.
- **Quota-aware TTS.** Print the number of Gemini TTS requests before synthesis and cache each completed chunk so interrupted runs can resume without repeating successful requests.
- **Robust generation.** Long scripts are chunked, with automatic retries on transient API errors and optional concurrency.

## How It Works

```text
input (topic | prose | transcript)
        │
        ▼
  [gemini text model]  ──►  <basename>_transcript.txt   (TTS script: repeats, pauses, spoken punctuation)
        │                   <basename>_continuous.txt   (clean prose for proofreading)
        ▼
  [gemini TTS model]   ──►  <basename>.wav              (original-speed PCM audio)
        │
        ▼
      [ffmpeg]         ──►  <basename>.mp3               (1.0x MP3)
                            <basename>_1_25x.mp3         (default faster MP3)
```

The text model writes/adapts the dictation script; the TTS model synthesizes it chunk by chunk and the chunks are concatenated in order before the WAV header is written, so parallel completion order never reorders the audio. `ffmpeg` then produces speed variants and the MP3.

## Requirements

- **Python 3.10+**
- **`ffmpeg`** — required for MP3 export and speed variants (skip with `--no-mp3`).
- **A Google Gemini API key.**

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

For the `dictat-gen` console command, install the project in editable mode:

```bash
python -m pip install -e .
```

Install `ffmpeg`:

```bash
# Debian / Ubuntu
sudo apt install ffmpeg
# macOS (Homebrew)
brew install ffmpeg
# Arch Linux
sudo pacman -S ffmpeg
```

Set your API key (never commit it):

```bash
export GEMINI_API_KEY="your-key-here"
```

Or keep it in a dotenv-style file and pass it without printing the file contents:

```bash
dictat-gen --env-file .env --language "Catalan" --topic "a school trip" --out-dir outputs/test
```

Do not inspect secrets with commands such as `cat .env` or `sed -n ... .env` in shared logs.

### Using uv (recommended)

[`uv`](https://docs.astral.sh/uv/) keeps dependencies isolated from your system Python.

Persistent project environment:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e .
source .venv/bin/activate
export GEMINI_API_KEY="your-key-here"
```

One-off run without a persistent `.venv`:

```bash
GEMINI_API_KEY="your-key-here" uv run --with google-genai \
  python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --env-file .env \
  --topic "a school trip to a natural park" \
  --level basic \
  --out-dir outputs/test \
  --basename test_dictation
```

## Quick Start

Generate a basic Catalan dictation from a topic, with each phrase read twice:

```bash
dictat-gen \
  --language "Catalan" \
  --topic "a school trip to a natural park" \
  --level basic \
  --repeat-policy twice \
  --out-dir outputs/natural_park \
  --basename natural_park
```

This writes the transcript, the clean proofreading text, and two MP3 files: `natural_park.mp3` at `1.0x` and `natural_park_1_25x.mp3` at `1.25x`. Intermediate WAV files are removed by default; add `--keep-base-wav` or `--keep-speed-wavs` if you want to keep them.

## Input Modes

Choose exactly one input. Always set `--language`.

| Mode | Flags | What it does |
| --- | --- | --- |
| **Topic** | `--topic "..."` | Generates a brand-new leveled dictation about the topic. |
| **Adapt prose** | `--source-text-file f.txt --source-mode adapt` | Rewrites existing prose to match the target level (vocabulary, sentence length, repetitions). |
| **Exact prose** | `--source-text-file f.txt --source-mode exact` | Keeps the wording/spelling/punctuation **unchanged**, only adding pauses, repetitions, and spoken punctuation. |
| **Transcript** | `--transcript-file t.txt` | Synthesizes an already-prepared TTS script as-is (no text model call). |

Examples:

```bash
# Adapt Spanish prose to intermediate level
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Spanish" --source-text-file source.txt --source-mode adapt \
  --level intermediate --out-dir outputs/source_dictation --basename source_dictation

# Preserve a Catalan text exactly, basic pacing
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" --source-text-file source.txt --source-mode exact \
  --level basic --out-dir outputs/exact --basename exact_dictation \
  --mp3-speeds 1.0 1.25

# Synthesize a prepared transcript
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "English" --transcript-file transcript.txt \
  --out-dir outputs/from_transcript --basename from_transcript
```

## Dictation Levels

`--level` controls length, vocabulary, grammar, and repetition. Full rubric in [`references/levels.md`](skills/gemini-dictat-generator/references/levels.md).

| Level | Audience | Words | Sentence length | Repetition |
| --- | --- | --- | --- | --- |
| `initial` | First exposure, young children, very early learners | 50–120 | 4–8 words | Every phrase twice |
| `basic` | Primary school, A1–A2 | 100–180 | 8–14 words | Every phrase twice |
| `intermediate` | Upper primary, secondary, B1 | 160–260 | 12–22 words | Twice (classroom) / selective |
| `advanced` | Confident learners, C1, exam practice | 220–400 | Natural, longer clauses | Phrase or minimal |

`--repeat-policy` overrides repetition independently of level: `twice` (default), `once`, `selective`, `none`, or `level` (use the level's default).

## CLI Reference

| Flag | Default | Description |
| --- | --- | --- |
| `--language` | *(required)* | Dictation language, e.g. `Catalan`, `Spanish`, `English`, `French`. |
| `--topic` | — | Topic to generate a dictation from. |
| `--source-text-file` | — | Prose file to adapt or preserve. |
| `--source-mode` | `adapt` | `adapt` (re-level the text) or `exact` (preserve wording). |
| `--transcript-file` | — | Existing TTS transcript to synthesize directly. |
| `--level` | `basic` | `initial`, `basic`, `intermediate`, `advanced`. |
| `--repeat-policy` | `twice` | `twice`, `once`, `selective`, `none`, `level`. |
| `--out-dir` | `.` | Output directory (created if missing). |
| `--basename` | `dictation_gemini` | Prefix for all output files. |
| `--voice` | `Zephyr` | Gemini prebuilt voice name. |
| `--model` | `gemini-3.1-flash-tts-preview` | TTS model. |
| `--text-model` | `gemini-2.5-flash` | Text model for script generation/adaptation. |
| `--api-key` | `$GEMINI_API_KEY` | Gemini API key (env var used if omitted). |
| `--env-file` | — | Dotenv-style file to read `GEMINI_API_KEY` from without printing it. |
| `--tts-concurrency` | `1` | Parallel TTS chunks. Raise to `2`/`3` only when quota allows. |
| `--tts-retries` | `2` | Retry attempts per chunk after transient failures. |
| `--max-chunk-chars` | `700` | Maximum characters per Gemini TTS chunk. Lower it if chunks stall or time out. |
| `--speeds` | *(none)* | Space-separated WAV tempos to keep, e.g. `1.0 1.25`. By default, WAVs are temporary. |
| `--mp3-speeds` | `1.0 1.25` | Space-separated MP3 tempos to export. |
| `--mp3-speed` | — | Deprecated single-speed alias. Overrides `--mp3-speeds` when set. |
| `--no-mp3` | off | Skip MP3 export. |
| `--keep-base-wav` | off | Keep the original-speed WAV master. By default, it is removed after MP3 export. |
| `--keep-speed-wavs` | off | Keep temporary speed-variant WAV files after MP3 export. |
| `--no-continuous-transcript` | off | Skip the clean proofreading transcript. |
| `--no-tts-cache` | off | Disable resumable TTS chunk cache. |

## Output Files

Written to `--out-dir` with the chosen `--basename`:

| File | Purpose |
| --- | --- |
| `<basename>_transcript.txt` | TTS script: repetitions, `[…]` pause cues, spoken punctuation. |
| `<basename>_continuous.txt` | Clean continuous prose for proofreading (skip with `--no-continuous-transcript`). |
| `<basename>.mp3` | Mobile-friendly MP3 at `1.0x` by default. |
| `<basename>_1_25x.mp3` | Mobile-friendly MP3 at `1.25x` by default. |
| `<basename>.wav` | Original-speed PCM WAV, only kept with `--keep-base-wav`, `--no-mp3`, or `--speeds 1.0`. |
| `<basename>_1_25x.wav` | Speed-variant WAV, only kept with `--keep-speed-wavs`, `--no-mp3`, or `--speeds 1.25`. |

When `--mp3-speeds` contains non-`1.0` speeds, temporary WAV variants are created for conversion and removed unless explicitly kept.

TTS chunks are cached in `<basename>_chunks/` inside the output directory. On rerun, matching cached chunks are reused and only missing chunks call Gemini TTS. The script prints a request estimate before synthesis, for example:

```text
TTS chunks: 18 total; 13 cached; 5 Gemini TTS requests needed.
```

Repeated units should be written as complete repeated units, not as spoken labels or fragments:

```text
The results surprised us. [short pause]
The results surprised us. Period. [long pause]
```

Avoid:

```text
Repeat: The results surprised us.
The results surprised us. [short pause]
surprised us. Period.
```

A `_transcript.txt` looks like this (Catalan, `basic`):

```text
[slow]
La classe va fer una excursió.
La classe va fer una excursió. [punt]
[short pause]
Van anar a un parc natural.
Van anar a un parc natural. [punt]
[long pause]
```

…and the matching `_continuous.txt` is the clean version students should produce:

```text
La classe va fer una excursió. Van anar a un parc natural.
```

## Install the Skill

The repository follows the `skills/<skill-name>/SKILL.md` layout, so it can be installed by the multi-agent `skills` CLI, by Pi, or copied manually.

### Multi-agent install (`skills` CLI)

For Claude Code, Codex, Cursor, and others:

```bash
npx skills add santialferez/dictat-generator-skill \
  --skill gemini-dictat-generator \
  -a claude-code \
  -a codex
```

Add `-g` to install globally, and more `-a <agent>` flags for other agents.

### Pi install

```bash
pi install git:github.com/santialferez/dictat-generator-skill
# project-local:
pi install -l git:github.com/santialferez/dictat-generator-skill
```

`package.json` includes a `pi.skills` manifest pointing at `./skills`.

### Local Codex-style install

A small bundled installer copies the skill into a Codex-style directory (`~/.codex/skills`, or `$CODEX_HOME/skills`):

```bash
./skills.sh            # install
./skills.sh --list     # list available skills
./skills.sh --dry-run  # show actions without copying
./skills.sh --dest ~/.codex/skills
```

Or copy it manually:

```bash
mkdir -p ~/.codex/skills
cp -R skills/gemini-dictat-generator ~/.codex/skills/
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No API key provided` | Set `GEMINI_API_KEY` or pass `--api-key`. |
| `Env file not found` | Check the `--env-file` path. |
| `ffmpeg is required …` | Install `ffmpeg`, or run with `--no-mp3`. |
| HTTP `429` (rate limit) | Lower `--tts-concurrency` to `1`; retry later. |
| `504 DEADLINE_EXCEEDED` | Transient TTS timeout; retried automatically (`--tts-retries`). |
| Long stalls on big scripts | Split the source into shorter paragraphs, or lower `--max-chunk-chars`. |
| `Transcript contains a spoken/meta label …` | Remove labels such as `Repeat:`, `Again:`, or `Title:`. Repeat the full dictation unit as text instead. |

Never print or commit API keys. `.env`, audio files, chunk caches, and `outputs/` are git-ignored by default.

## Repository Layout

```text
skills/gemini-dictat-generator/
  SKILL.md                    # Skill definition and agent workflow
  agents/openai.yaml          # Agent interface metadata
  references/levels.md        # Level rubric (length, grammar, pacing, punctuation)
  scripts/generate_dictat.py  # The CLI
requirements.txt              # Python dependency (google-genai)
pyproject.toml                # Editable install and dictat-gen console entrypoint
package.json                  # Pi skills manifest
skills.sh                     # Local Codex-style installer
```

## License

MIT — see [`LICENSE`](LICENSE).
