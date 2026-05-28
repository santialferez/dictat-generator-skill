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

This layout is compatible with tools that install skills from a `skills/<skill-name>/SKILL.md` repository layout, including Codex-style skills directories and the multi-agent `skills` CLI used by skills.sh.

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

## Using uv

`uv` is recommended for local use because it keeps dependencies isolated from your system Python.

For repeated use, create a project virtual environment:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
source .venv/bin/activate
export GEMINI_API_KEY="your-key-here"
```

Then run the script with the active environment:

```bash
python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --topic "a school trip to a natural park" \
  --level basic \
  --out-dir outputs/test \
  --basename test_dictation
```

For one-off runs without creating a persistent `.venv`:

```bash
GEMINI_API_KEY="your-key-here" uv run --with google-genai \
  python skills/gemini-dictat-generator/scripts/generate_dictat.py \
  --language "Catalan" \
  --topic "a school trip to a natural park" \
  --level basic \
  --out-dir outputs/test \
  --basename test_dictation
```

## Install the Skill

### Multi-Agent Install

For Claude Code, Codex, Cursor, and other agents supported by the `skills` CLI, use:

```bash
npx skills add santialferez/dictat-generator-skill \
  --skill gemini-dictat-generator \
  -a claude-code \
  -a codex
```

Install globally with:

```bash
npx skills add santialferez/dictat-generator-skill \
  --skill gemini-dictat-generator \
  -a claude-code \
  -a codex \
  -g
```

Add more `-a` flags for other supported agents when needed.

### Pi Install

For Pi Coding Agent, use Pi's package installer:

```bash
pi install git:github.com/santialferez/dictat-generator-skill
```

For a project-local Pi install:

```bash
pi install -l git:github.com/santialferez/dictat-generator-skill
```

The repository includes a `package.json` with a `pi.skills` manifest entry so Pi can load the bundled skill from `./skills`.

### Local Codex-Style Install

This repository also includes a small local installer for Codex-style skill directories. From a local checkout:

```bash
./skills.sh
```

By default this installs to `~/.codex/skills`, or `$CODEX_HOME/skills` when `CODEX_HOME` is set. This script is intentionally simple and does not manage Claude Code, Cursor, or other agent-specific locations. Use `npx skills add ... -a <agent>` for multi-agent installs. You can override the local destination:

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
