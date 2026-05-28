---
name: gemini-dictat-generator
description: Generate leveled dictation audio packages in any requested language with Google Gemini TTS. Use when users want classroom dictations, adapted or exact source-text dictations, TTS-ready transcripts with pauses and repetitions, clean proofreading transcripts, speed variants, WAV/MP3 exports, chunked Gemini requests, or controlled TTS concurrency.
---

# Gemini Dictation Generator

## Overview

Create reusable classroom dictation packages with Google Gemini TTS. The bundled script can:

- Generate a new leveled dictation from a topic.
- Adapt ordinary prose into a dictation script.
- Synthesize an existing TTS transcript.
- Export a clean continuous transcript for correction.
- Create WAV and MP3 outputs, including speed variants.

Prefer `scripts/generate_dictat.py` for repeatable runs. Read `references/levels.md` when choosing level, sentence length, punctuation, repetitions, or pause policy.

## Workflow

1. Clarify or infer the working directory, output directory, dictation language, and target level: `initial`, `basic`, `intermediate`, or `advanced`.
2. Confirm that a Google Gemini API key is available via `GEMINI_API_KEY`, `--api-key`, or `--env-file`. Never print API keys and never inspect `.env` files with commands such as `cat`, `sed`, or `grep` that can expose secret values in logs. If a path is known, pass it with `--env-file`.
3. Confirm Python can import `google.genai`. If not, create an environment and install `google-genai` from `requirements.txt`.
4. Choose the input mode:
   - Topic: use `--topic`.
   - Existing TTS script: use `--transcript-file`.
   - Prose to adapt: use `--source-text-file --source-mode adapt`.
   - Prose to preserve exactly: use `--source-text-file --source-mode exact`.
5. Use `--repeat-policy twice` for normal classroom dictation unless the user asks for a different pattern. The TTS transcript must not include spoken/meta labels such as `Repeat:`, `Again:`, `First reading:`, `Second reading:`, or `Title:`. Repetitions must be written as complete repeated dictation units, not as partial endings.
6. Use sequential TTS by default. If the user wants faster generation and quota allows it, use modest concurrency such as `--tts-concurrency 2` or `3`. If chunks stall or time out, lower `--max-chunk-chars`. The script prints total/cached/missing TTS chunk counts before synthesis; treat the missing count as the Gemini TTS request cost.
7. Leave the default TTS chunk cache enabled so quota failures can resume later without repeating completed chunks. Use `--no-tts-cache` only when the user explicitly wants a fresh synthesis.
8. Generate MP3 deliverables at `1.0x` and `1.25x` by default. Treat WAV files as intermediates and remove them after MP3 export unless the user asks for `--keep-base-wav`, `--keep-speed-wavs`, `--speeds`, or `--no-mp3`.
9. Verify generated files with `file`, `ffprobe`, and `ls -lh`.

## Quick Start

Run from the user's project directory so outputs land where expected:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --env-file .env \
  --topic "a school trip to a natural park" \
  --level basic \
  --repeat-policy twice \
  --out-dir dictation_output \
  --basename natural_park \
  --tts-concurrency 1 \
  --tts-retries 2 \
  --max-chunk-chars 700 \
  --mp3-speeds 1.0 1.25
```

Generate MP3 deliverables while preserving WAV intermediates:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --source-text-file source.txt \
  --level basic \
  --repeat-policy twice \
  --out-dir dictation_output \
  --basename source_dictation \
  --mp3-speeds 1.0 1.25 \
  --keep-base-wav \
  --keep-speed-wavs
```

## Inputs

- `--topic`: generate a new dictation script from a topic.
- `--source-text-file --source-mode adapt`: adapt ordinary prose into a leveled dictation script before synthesis.
- `--source-text-file --source-mode exact`: keep the final text unchanged while adding dictation pauses, repetitions, and spoken punctuation.
- `--transcript-file`: synthesize an already prepared TTS transcript.

Always set `--language` so transcript generation and TTS instructions match the intended language.

For repeated dictation units, write the full unit twice. Good:

```text
The results surprised us. [short pause]
The results surprised us. Period. [long pause]
```

Bad:

```text
Repeat: The results surprised us.
The results surprised us. [short pause]
surprised us. Period.
```

## Output Files

Default outputs:

- `<basename>_transcript.txt`: Gemini TTS script with repetitions, pauses, and spoken punctuation.
- `<basename>_continuous.txt`: ordinary prose for proofreading and correction.
- `<basename>.mp3`: mobile-friendly 1.0x MP3, unless `--no-mp3` is used.
- `<basename>_1_25x.mp3`: mobile-friendly 1.25x MP3 by default, unless `--no-mp3` is used.

WAV files are temporary by default. Use `--keep-base-wav` for `<basename>.wav`, `--keep-speed-wavs` for all speed-variant WAV intermediates, or `--speeds 1.0 1.25` to keep specific WAV deliverables. `--mp3-speed` still works as a deprecated single-speed alias, but prefer `--mp3-speeds`.

## Preflight

- Install dependencies: `python -m pip install -r requirements.txt`.
- Set `GEMINI_API_KEY` or pass `--api-key`.
- Prefer `--env-file <path>` when the API key lives in a dotenv file. Do not print dotenv files in terminal output.
- Install `ffmpeg` if exporting MP3 or speed variants.
- Check input files exist before running.

## Common Failures

- `No API key provided`: set `GEMINI_API_KEY` or pass `--api-key`.
- `Env file not found`: check the `--env-file` path.
- `ffmpeg is required`: install ffmpeg or rerun with `--no-mp3`.
- `429`: reduce `--tts-concurrency` to `1` or `2`.
- `504 DEADLINE_EXCEEDED`: transient TTS timeout; the script retries chunks with `--tts-retries 2` by default.
- Long TTS stalls: split long transcripts into shorter paragraphs or reduce `--max-chunk-chars`.
- Spoken/meta labels such as `Repeat:` or `Title:` cause the script to stop before TTS. Remove the label and write the complete dictation unit twice instead.

## Quota and Resume Notes

Each TTS chunk is one Gemini TTS request. A dictation with 18 chunks can consume 18 daily requests even though it is only one dictation. The script prints a line like:

```text
TTS chunks: 18 total; 13 cached; 5 Gemini TTS requests needed.
```

Completed chunks are cached in `<basename>_chunks/` inside the output directory and reused on later runs when the text, language, model, and voice match. If a daily quota failure stops a run, rerun the same command after reset; only missing chunks should call Gemini again.

## Gemini TTS Notes

The default TTS model is `gemini-3.1-flash-tts-preview` and the default text model is `gemini-2.5-flash`. The script concatenates returned `audio/L16` PCM by chunk index before writing a WAV header, so parallel chunk completion order does not affect the final audio order.
