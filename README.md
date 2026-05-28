# Gemini Dictation Generator Skill

Reusable Agent Skill and CLI script for generating classroom dictation audio packages with Google Gemini TTS.

The repository is structured for SKILL.md-compatible agents and installers:

```text
skills/gemini-dictat-generator/
  SKILL.md
  agents/openai.yaml
  references/levels.md
  scripts/generate_dictat.py
```

This layout is compatible with tools that install skills from a `skills/<skill-name>/SKILL.md` repository layout, including Codex-style skills directories and `skills.sh`-style installers.

## Requirements

- Python 3.10+
- `ffmpeg` for MP3 exports and speed variants
- A Google Gemini API key

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Set your API key:

```bash
export GEMINI_API_KEY="your-key-here"
```

Do not commit `.env` files or API keys.

## Install the Skill

From a local checkout:

```bash
./skills.sh
```

By default this installs to `~/.codex/skills`, or `$CODEX_HOME/skills` when `CODEX_HOME` is set. You can override the destination:

```bash
./skills.sh --dest ~/.codex/skills
./skills.sh --list
./skills.sh --dry-run
```

You can also manually copy the skill directory:

```bash
mkdir -p ~/.codex/skills
cp -R skills/gemini-dictat-generator ~/.codex/skills/
```

## Use the CLI Directly

Generate a dictation from a topic:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --topic "a school trip to a natural park" \
  --level basic \
  --repeat-policy twice \
  --out-dir outputs/natural_park \
  --basename natural_park \
  --speeds 1.0 1.25 \
  --mp3-speed 1.25
```

Generate from an existing source text:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Spanish" \
  --source-text-file source.txt \
  --source-mode adapt \
  --level intermediate \
  --repeat-policy twice \
  --out-dir outputs/source_dictation \
  --basename source_dictation
```

Preserve an existing text exactly while turning it into dictation audio:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --source-text-file source.txt \
  --source-mode exact \
  --level basic \
  --repeat-policy twice \
  --out-dir outputs/exact_dictation \
  --basename exact_dictation \
  --speeds 1.0 1.25 \
  --mp3-speed 1.25
```

Synthesize a prepared TTS transcript:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "English" \
  --transcript-file transcript.txt \
  --out-dir outputs/from_transcript \
  --basename from_transcript
```

## Outputs

The script writes:

- `<basename>_transcript.txt`: TTS prompt transcript with repetitions, pauses, and spoken punctuation.
- `<basename>_continuous.txt`: clean text for proofreading.
- `<basename>.wav`: original speed audio.
- `<basename>.mp3`: mobile-friendly MP3.
- `<basename>_1_25x.wav`: speed variants when requested.

## Notes

- Default text model: `gemini-2.5-flash`.
- Default TTS model: `gemini-3.1-flash-tts-preview`.
- Default voice: `Zephyr`.
- TTS chunk generation is sequential by default. Use `--tts-concurrency 2` or `3` when quota allows it.
- Use `--tts-retries` for transient TTS failures.
