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
2. Confirm that a Google Gemini API key is available via `GEMINI_API_KEY` or `--api-key`. Never print API keys.
3. Confirm Python can import `google.genai`. If not, create an environment and install `google-genai` from `requirements.txt`.
4. Choose the input mode:
   - Topic: use `--topic`.
   - Existing TTS script: use `--transcript-file`.
   - Prose to adapt: use `--source-text-file --source-mode adapt`.
   - Prose to preserve exactly: use `--source-text-file --source-mode exact`.
5. Use `--repeat-policy twice` for normal classroom dictation unless the user asks for a different pattern.
6. Use sequential TTS by default. If the user wants faster generation and quota allows it, use modest concurrency such as `--tts-concurrency 2` or `3`. If chunks stall or time out, lower `--max-chunk-chars`.
7. Keep only the base WAV master by default. Speed-variant WAVs are treated as intermediates and removed after MP3 export unless `--keep-speed-wavs` is set.
8. Verify generated files with `file`, `ffprobe`, and `ls -lh`.

## Quick Start

Run from the user's project directory so outputs land where expected:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --topic "a school trip to a natural park" \
  --level basic \
  --repeat-policy twice \
  --out-dir dictation_output \
  --basename natural_park \
  --tts-concurrency 1 \
  --tts-retries 2 \
  --max-chunk-chars 700 \
  --speeds 1.0 \
  --mp3-speed 1.0
```

Generate a 1.25x WAV variant and mobile MP3 from it:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --source-text-file source.txt \
  --level basic \
  --repeat-policy twice \
  --out-dir dictation_output \
  --basename source_dictation \
  --speeds 1.0 1.25 \
  --mp3-speed 1.25
```

## Inputs

- `--topic`: generate a new dictation script from a topic.
- `--source-text-file --source-mode adapt`: adapt ordinary prose into a leveled dictation script before synthesis.
- `--source-text-file --source-mode exact`: keep the final text unchanged while adding dictation pauses, repetitions, and spoken punctuation.
- `--transcript-file`: synthesize an already prepared TTS transcript.

Always set `--language` so transcript generation and TTS instructions match the intended language.

## Output Files

Default outputs:

- `<basename>_transcript.txt`: Gemini TTS script with repetitions, pauses, and spoken punctuation.
- `<basename>_continuous.txt`: ordinary prose for proofreading and correction.
- `<basename>.wav`: original-speed PCM WAV.
- `<basename>.mp3`: mobile-friendly MP3, unless `--no-mp3` is used.

Speed variants use `<basename>_<speed>x.wav`, for example `<basename>_1_25x.wav`. If `--mp3-speed 1.25` is set, the MP3 is exported from the 1.25x WAV. Speed-variant WAVs are removed by default after MP3 export to avoid leaving large intermediate files; use `--keep-speed-wavs` to retain them.

## Preflight

- Install dependencies: `python -m pip install -r requirements.txt`.
- Set `GEMINI_API_KEY` or pass `--api-key`.
- Install `ffmpeg` if exporting MP3 or speed variants.
- Check input files exist before running.

## Common Failures

- `No API key provided`: set `GEMINI_API_KEY` or pass `--api-key`.
- `ffmpeg is required`: install ffmpeg or rerun with `--no-mp3`.
- `429`: reduce `--tts-concurrency` to `1` or `2`.
- `504 DEADLINE_EXCEEDED`: transient TTS timeout; the script retries chunks with `--tts-retries 2` by default.
- Long TTS stalls: split long transcripts into shorter paragraphs or reduce `--max-chunk-chars`.

## Gemini TTS Notes

The default TTS model is `gemini-3.1-flash-tts-preview` and the default text model is `gemini-2.5-flash`. The script concatenates returned `audio/L16` PCM by chunk index before writing a WAV header, so parallel chunk completion order does not affect the final audio order.
