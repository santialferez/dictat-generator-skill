#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google import genai
from google.genai import types


LEVEL_PROFILES = {
    "initial": {
        "words": "50-120",
        "style": "extremely slow, very short phrases, concrete vocabulary, every fragment repeated twice, punctuation spoken aloud in the target language",
    },
    "basic": {
        "words": "100-180",
        "style": "slow and clear, simple sentences, familiar vocabulary, every fragment repeated once, punctuation spoken aloud in the target language",
    },
    "intermediate": {
        "words": "160-260",
        "style": "clear classroom dictation pace, richer sentences, some connectors and subordinate clauses, selective repetition",
    },
    "advanced": {
        "words": "220-400",
        "style": "near-natural but well-articulated pace, varied syntax, precise vocabulary, minimal repetition",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate leveled dictation audio in a selected language with Gemini TTS.")
    parser.add_argument("--language", required=True, help="Dictation language, for example Catalan, Spanish, English, or French.")
    parser.add_argument("--topic", help="Topic to use when generating a transcript.")
    parser.add_argument("--transcript-file", type=Path, help="Existing transcript to synthesize.")
    parser.add_argument("--source-text-file", type=Path, help="Ordinary prose text to adapt into a dictation script before synthesis.")
    parser.add_argument(
        "--source-mode",
        choices=["adapt", "exact"],
        default="adapt",
        help="How to handle --source-text-file. Use 'adapt' to simplify/level the text, or 'exact' to preserve its wording.",
    )
    parser.add_argument("--level", choices=LEVEL_PROFILES, default="basic")
    parser.add_argument(
        "--repeat-policy",
        choices=["twice", "once", "selective", "none", "level"],
        default="twice",
        help="How phrases should be repeated in the generated dictation script.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    parser.add_argument("--basename", default="dictation_gemini")
    parser.add_argument("--voice", default="Zephyr")
    parser.add_argument("--model", default="gemini-3.1-flash-tts-preview")
    parser.add_argument("--text-model", default="gemini-2.5-flash")
    parser.add_argument("--api-key", help="Gemini API key. If omitted, GEMINI_API_KEY is used.")
    parser.add_argument("--env-file", type=Path, help="Optional dotenv-style file to read GEMINI_API_KEY from without printing it.")
    parser.add_argument(
        "--tts-concurrency",
        type=int,
        default=1,
        help="Number of Gemini TTS chunks to generate in parallel. Defaults to 1 for sequential generation.",
    )
    parser.add_argument(
        "--tts-retries",
        type=int,
        default=2,
        help="Number of retry attempts per TTS chunk after transient API failures. Defaults to 2.",
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=700,
        help="Maximum characters per Gemini TTS chunk. Lower this if long chunks stall or time out.",
    )
    parser.add_argument(
        "--speeds",
        nargs="*",
        type=float,
        default=[],
        help="Audio speed factors to keep as WAV files. Defaults to no final WAV outputs unless --no-mp3 is used.",
    )
    parser.add_argument(
        "--mp3-speeds",
        nargs="*",
        type=float,
        default=[1.0, 1.25],
        help="Audio speed factors to export as MP3. Defaults to 1.0 and 1.25.",
    )
    parser.add_argument(
        "--mp3-speed",
        type=float,
        help="Deprecated alias for exporting a single MP3 speed. Overrides --mp3-speeds when set.",
    )
    parser.add_argument("--no-mp3", action="store_true", help="Skip mobile MP3 export.")
    parser.add_argument(
        "--keep-base-wav",
        action="store_true",
        help="Keep the original-speed WAV master. By default it is removed after MP3 export.",
    )
    parser.add_argument(
        "--keep-speed-wavs",
        action="store_true",
        help="Keep temporary WAV speed variants after MP3 export.",
    )
    parser.add_argument(
        "--no-continuous-transcript",
        action="store_true",
        help="Skip writing the clean continuous transcript used for proofreading.",
    )
    parser.add_argument(
        "--no-tts-cache",
        action="store_true",
        help="Do not reuse or write cached TTS chunk audio. By default, chunks are cached for resumable runs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY") or read_api_key_from_env_file(args.env_file)
    if not api_key:
        raise SystemExit("No API key provided. Pass --api-key, --env-file, or set GEMINI_API_KEY.")
    if not args.transcript_file and not args.source_text_file and not args.topic:
        raise SystemExit("Provide --topic, --transcript-file, or --source-text-file.")
    if args.transcript_file and not args.transcript_file.is_file():
        raise SystemExit(f"Transcript file not found: {args.transcript_file}")
    if args.source_text_file and not args.source_text_file.is_file():
        raise SystemExit(f"Source text file not found: {args.source_text_file}")
    if args.tts_concurrency < 1:
        raise SystemExit("--tts-concurrency must be 1 or greater.")
    if args.tts_retries < 0:
        raise SystemExit("--tts-retries must be 0 or greater.")
    if args.max_chunk_chars < 100:
        raise SystemExit("--max-chunk-chars must be at least 100.")
    wav_speeds = unique_speeds(args.speeds)
    mp3_speeds = [] if args.no_mp3 else unique_speeds([args.mp3_speed] if args.mp3_speed is not None else args.mp3_speeds)
    for speed in wav_speeds + mp3_speeds:
        if speed <= 0:
            raise SystemExit("Audio speed factors must be greater than 0.")
    if (any(abs(speed - 1.0) >= 0.001 for speed in wav_speeds + mp3_speeds) or mp3_speeds) and not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required for speed variants or MP3 export.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120000))

    if args.transcript_file:
        transcript = args.transcript_file.read_text(encoding="utf-8")
    elif args.source_text_file:
        source_text = args.source_text_file.read_text(encoding="utf-8")
        if args.source_mode == "exact":
            transcript = script_exact_source_text(client, args.text_model, source_text, args.level, args.language, args.repeat_policy)
        else:
            transcript = adapt_source_text(client, args.text_model, source_text, args.level, args.language, args.repeat_policy)
    else:
        transcript = generate_transcript(client, args.text_model, args.topic, args.level, args.language, args.repeat_policy)

    transcript_path = args.out_dir / f"{args.basename}_transcript.txt"
    validate_transcript(transcript)
    transcript_path.write_text(transcript, encoding="utf-8")
    print(f"Transcript saved to: {transcript_path.resolve()}", flush=True)

    if not args.no_continuous_transcript:
        continuous_transcript = make_continuous_transcript(client, args.text_model, transcript, args.language)
        continuous_path = args.out_dir / f"{args.basename}_continuous.txt"
        continuous_path.write_text(continuous_transcript, encoding="utf-8")
        print(f"Continuous transcript saved to: {continuous_path.resolve()}", flush=True)

    base_wav = args.out_dir / f"{args.basename}.wav"
    synthesize_wav(
        client,
        args.model,
        args.voice,
        transcript,
        base_wav,
        args.language,
        args.tts_concurrency,
        args.tts_retries,
        args.max_chunk_chars,
        None if args.no_tts_cache else args.out_dir / f"{args.basename}_chunks",
    )

    needed_speed_wavs = unique_speeds([
        speed
        for speed in wav_speeds + mp3_speeds
        if abs(speed - 1.0) >= 0.001
    ])
    speed_wavs: dict[float, Path] = {}
    for speed in needed_speed_wavs:
        if abs(speed - 1.0) < 0.001:
            continue
        speed_wav = args.out_dir / f"{args.basename}_{speed_label(speed)}x.wav"
        run_ffmpeg(["ffmpeg", "-y", "-i", str(base_wav), "-filter:a", f"atempo={speed}", str(speed_wav)])
        speed_wavs[speed] = speed_wav
        print(f"Speed WAV created: {speed_wav}", flush=True)

    for mp3_speed in mp3_speeds:
        if abs(mp3_speed - 1.0) < 0.001:
            mp3_source = base_wav
        else:
            mp3_source = speed_wavs[mp3_speed]
        mp3_path = args.out_dir / f"{mp3_source.stem}.mp3"
        run_ffmpeg(["ffmpeg", "-y", "-i", str(mp3_source), "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3_path)])
        print(f"Mobile MP3 saved to: {mp3_path.resolve()}", flush=True)

    for speed, speed_wav in speed_wavs.items():
        should_keep = args.no_mp3 or args.keep_speed_wavs or speed in wav_speeds
        if not should_keep and speed_wav.exists():
            speed_wav.unlink()
            print(f"Removed intermediate speed WAV: {speed_wav}", flush=True)

    keep_base_wav = args.no_mp3 or args.keep_base_wav or any(abs(speed - 1.0) < 0.001 for speed in wav_speeds)
    if not keep_base_wav and base_wav.exists():
        base_wav.unlink()
        print(f"Removed intermediate base WAV: {base_wav}", flush=True)


def generate_transcript(client: genai.Client, model: str, topic: str, level: str, language: str, repeat_policy: str) -> str:
    profile = LEVEL_PROFILES[level]
    prompt = f"""Write a school dictation script in {language}.

Level: {level}
Approximate length: {profile["words"]} content words.
Topic: {topic}
Style: {profile["style"]}.
Repetition: {repetition_instruction(repeat_policy, level)}.
Dictation script rules:
{dictation_script_rules(language)}

Return only the script to be read aloud. The script itself must be in {language}. Include cues such as [slow], [short pause], and [long pause] when useful. Include punctuation words in {language} that the learner must write, such as the local equivalents of comma, full stop/period, new paragraph, and final stop."""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def adapt_source_text(client: genai.Client, model: str, source_text: str, level: str, language: str, repeat_policy: str) -> str:
    profile = LEVEL_PROFILES[level]
    prompt = f"""Adapt the following source text into a school dictation script in {language}.

Level: {level}
Approximate length: {profile["words"]} content words unless the source is shorter.
Style: {profile["style"]}.
Repetition: {repetition_instruction(repeat_policy, level)}.
Dictation script rules:
{dictation_script_rules(language)}

Keep the main content and facts from the source, but adjust vocabulary, sentence length, repetitions, pauses, and punctuation words for the target level. Return only the script to be read aloud. The script itself must be in {language}. Include cues such as [slow], [short pause], and [long pause] when useful. Include punctuation words in {language} that the learner must write.

Source text:
{source_text}"""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def script_exact_source_text(client: genai.Client, model: str, source_text: str, level: str, language: str, repeat_policy: str) -> str:
    profile = LEVEL_PROFILES[level]
    prompt = f"""Convert the following source text into a school dictation script in {language}.

Level: {level}
Style: {profile["style"]}.
Repetition: {repetition_instruction(repeat_policy, level)}.
Dictation script rules:
{dictation_script_rules(language)}

Preserve the exact final text the learner is expected to write: do not simplify, summarize, reorder, add facts, remove facts, or change wording, spelling, accents, capitalization, quotes, or punctuation. You may split the text into short dictation units, repeat units according to the repetition policy, add bracketed delivery cues such as [slow], [short pause], and [long pause], and say punctuation words in {language}.

Return only the TTS script to be read aloud.

Source text:
{source_text}"""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def make_continuous_transcript(client: genai.Client, model: str, transcript: str, language: str) -> str:
    prompt = f"""Convert this school dictation script into clean continuous prose in {language}.

The input is a TTS script, so it may contain repeated phrases, bracketed delivery cues such as [slow], [short pause], or [long pause], and spoken punctuation words. Produce the text that the learner is expected to write.

Rules:
- Return only the continuous text, with normal punctuation and paragraph breaks.
- Remove delivery cues.
- Remove duplicated dictation units caused by repetition.
- Convert spoken punctuation words in {language} to punctuation marks and paragraph breaks.
- Preserve the wording, spelling, accents, capitalization, quotes, and meaning of the intended final dictation text.

Dictation script:
{transcript}"""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def repetition_instruction(repeat_policy: str, level: str) -> str:
    if repeat_policy == "twice":
        return "read each complete dictation unit twice before moving to the next unit"
    if repeat_policy == "once":
        return "read each complete dictation unit once"
    if repeat_policy == "selective":
        return "repeat only complete longer or difficult dictation units, not fragments"
    if repeat_policy == "none":
        return "do not repeat dictation units unless needed for punctuation clarity"
    return LEVEL_PROFILES[level]["style"]


def dictation_script_rules(language: str) -> str:
    return f"""- Do not write or speak labels such as "Repeat", "Again", "First reading", "Second reading", or "Title" unless those exact words are part of the dictation text.
- To repeat a unit, write the complete unit twice on consecutive lines. Never repeat only the ending or a trailing fragment.
- For intermediate and advanced levels, a dictation unit should normally be a complete sentence. For initial and basic levels, a unit may be a complete short sentence or a meaningful complete clause.
- The first and second reading of a repeated unit must contain the same words. The second reading may add the punctuation word in {language} at the end, such as comma, full stop/period, new paragraph, or final stop.
- Bracketed cues such as [slow], [short pause], and [long pause] are delivery cues, not words to dictate."""


def validate_transcript(transcript: str) -> None:
    forbidden_label = re.compile(
        r'^\s*(?:\[[^\]]+\]\s*)?(?:repeat|repeated|again|first reading|second reading|title)\s*[:：-]',
        re.IGNORECASE,
    )
    for line_number, line in enumerate(transcript.splitlines(), start=1):
        if forbidden_label.search(line):
            raise SystemExit(
                f"Transcript contains a spoken/meta label on line {line_number}: {line.strip()!r}. "
                "Remove labels such as Repeat/Again/Title before synthesizing audio."
            )


def read_api_key_from_env_file(env_file: Path | None) -> str | None:
    if env_file is None:
        return None
    if not env_file.is_file():
        raise SystemExit(f"Env file not found: {env_file}")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "GEMINI_API_KEY":
            return value.strip().strip('"').strip("'") or None
    return None


def synthesize_wav(
    client: genai.Client,
    model: str,
    voice: str,
    transcript: str,
    output: Path,
    language: str,
    concurrency: int,
    retries: int,
    max_chunk_chars: int,
    cache_dir: Path | None,
) -> None:
    chunks = chunk_transcript(transcript, max_chars=max_chunk_chars)
    chunk_inputs = [
        TTSChunkInput(index=index, total=len(chunks), text=chunk_text, language=language, model=model, voice=voice)
        for index, chunk_text in enumerate(chunks, start=1)
    ]
    cached_results = load_cached_chunks(chunk_inputs, cache_dir)
    missing_inputs = [chunk_input for chunk_input in chunk_inputs if chunk_input.index not in cached_results]
    print(f"TTS chunks: {len(chunks)} total; {len(cached_results)} cached; {len(missing_inputs)} Gemini TTS requests needed.", flush=True)

    if not missing_inputs:
        generated_results = []
    elif concurrency == 1 or len(chunks) <= 1:
        generated_results = [
            synthesize_chunk_with_retries(client, chunk_input, retries, cache_dir)
            for chunk_input in missing_inputs
        ]
    else:
        workers = min(concurrency, len(missing_inputs))
        print(f"Generating {len(missing_inputs)} missing audio chunks with concurrency {workers}", flush=True)
        generated_results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    synthesize_chunk_with_retries,
                    client,
                    chunk_input,
                    retries,
                    cache_dir,
                ): chunk_input.index
                for chunk_input in missing_inputs
            }
            for future in as_completed(futures):
                index = futures[future]
                generated_results.append(future.result())
                print(f"Finished audio chunk {index}/{len(chunks)}", flush=True)

    chunk_result_by_index = cached_results | {result.index: result for result in generated_results}
    chunk_results = [chunk_result_by_index[index] for index in range(1, len(chunks) + 1)]
    mime_type = chunk_results[0].mime_type if chunk_results else "audio/L16;rate=24000"
    audio_parameters = parse_audio_mime_type(mime_type)
    raw_audio = bytearray()
    for chunk_result in chunk_results:
        if parse_audio_mime_type(chunk_result.mime_type) != audio_parameters:
            raise RuntimeError(f"Mixed TTS audio formats are not supported: {mime_type} and {chunk_result.mime_type}")
        raw_audio.extend(chunk_result.audio_data)
    output.write_bytes(convert_to_wav(bytes(raw_audio), mime_type))
    print(f"WAV saved to: {output.resolve()}", flush=True)


class TTSChunkInput:
    def __init__(self, index: int, total: int, text: str, language: str, model: str, voice: str) -> None:
        self.index = index
        self.total = total
        self.text = text
        self.language = language
        self.model = model
        self.voice = voice
        self.cache_key = chunk_cache_key(self)


class TTSChunkResult:
    def __init__(self, index: int, audio_data: bytes, mime_type: str) -> None:
        self.index = index
        self.audio_data = audio_data
        self.mime_type = mime_type

    def __iter__(self):
        yield self.audio_data
        yield self.mime_type


def synthesize_chunk_with_retries(
    client: genai.Client,
    chunk_input: TTSChunkInput,
    retries: int,
    cache_dir: Path | None,
) -> TTSChunkResult:
    for attempt in range(retries + 1):
        try:
            result = synthesize_chunk(client, chunk_input)
            write_cached_chunk(result, chunk_input, cache_dir)
            return result
        except Exception as error:
            if attempt >= retries:
                raise
            delay = min(2 ** attempt, 10)
            print(
                f"Audio chunk {chunk_input.index}/{chunk_input.total} failed ({type(error).__name__}); retrying in {delay}s "
                f"({attempt + 1}/{retries})",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable retry state")


def synthesize_chunk(
    client: genai.Client,
    chunk_input: TTSChunkInput,
) -> TTSChunkResult:
    config = types.GenerateContentConfig(
        temperature=1,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=chunk_input.voice)
            )
        ),
    )
    raw_audio = bytearray()
    mime_type = "audio/L16;rate=24000"
    print(f"Generating audio chunk {chunk_input.index}/{chunk_input.total}", flush=True)
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=tts_prompt(chunk_input.text, chunk_input.language))],
        )
    ]
    for chunk in client.models.generate_content_stream(model=chunk_input.model, contents=contents, config=config):
        if chunk.parts is None:
            continue
        inline_data = chunk.parts[0].inline_data
        if inline_data and inline_data.data:
            mime_type = inline_data.mime_type
            raw_audio.extend(inline_data.data)
        elif chunk.text:
            print(chunk.text, flush=True)
    return TTSChunkResult(chunk_input.index, bytes(raw_audio), mime_type)


def chunk_cache_key(chunk_input: TTSChunkInput) -> str:
    payload = {
        "text": chunk_input.text,
        "language": chunk_input.language,
        "model": chunk_input.model,
        "voice": chunk_input.voice,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def chunk_cache_paths(cache_dir: Path, index: int) -> tuple[Path, Path]:
    stem = f"chunk_{index:03d}"
    return cache_dir / f"{stem}.bin", cache_dir / f"{stem}.json"


def load_cached_chunks(chunk_inputs: list[TTSChunkInput], cache_dir: Path | None) -> dict[int, TTSChunkResult]:
    if cache_dir is None:
        return {}
    cached: dict[int, TTSChunkResult] = {}
    for chunk_input in chunk_inputs:
        audio_path, manifest_path = chunk_cache_paths(cache_dir, chunk_input.index)
        if not audio_path.is_file() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if manifest.get("cache_key") != chunk_input.cache_key:
            continue
        mime_type = manifest.get("mime_type")
        if not isinstance(mime_type, str):
            continue
        cached[chunk_input.index] = TTSChunkResult(chunk_input.index, audio_path.read_bytes(), mime_type)
    return cached


def write_cached_chunk(result: TTSChunkResult, chunk_input: TTSChunkInput, cache_dir: Path | None) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_path, manifest_path = chunk_cache_paths(cache_dir, chunk_input.index)
    audio_path.write_bytes(result.audio_data)
    manifest = {
        "index": chunk_input.index,
        "total": chunk_input.total,
        "cache_key": chunk_input.cache_key,
        "mime_type": result.mime_type,
        "model": chunk_input.model,
        "voice": chunk_input.voice,
        "language": chunk_input.language,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def tts_prompt(chunk_text: str, language: str) -> str:
    return f"""## Scene:
A school teacher gives a dictation in {language} with a clear, well-articulated voice. Respect the script's pauses, repetitions, and punctuation words.

## Transcript:
{chunk_text}"""


def chunk_transcript(transcript: str, max_chars: int = 700) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", transcript) if block.strip()]
    chunks: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            chunks.append(block)
            continue
        pieces = re.split(r"(?<=[.!?])\s+", block)
        current = ""
        for piece in pieces:
            if len(current) + len(piece) > max_chars and current:
                chunks.append(current.strip())
                current = piece
            else:
                current = f"{current} {piece}".strip()
        if current:
            chunks.append(current.strip())
    return chunks


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = parameters["channels"]
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict[str, int]:
    bits_per_sample = 16
    rate = 24000
    channels = 1
    for param in mime_type.split(";"):
        param = param.strip()
        if param.lower().startswith("rate="):
            rate = int(param.split("=", 1)[1])
        elif param.lower().startswith("channels="):
            channels = int(param.split("=", 1)[1])
        elif param.lower().startswith("audio/l"):
            bits_per_sample = int(param.lower().split("l", 1)[1])
    return {"bits_per_sample": bits_per_sample, "rate": rate, "channels": channels}


def speed_label(speed: float) -> str:
    return str(speed).replace(".", "_").rstrip("0").rstrip("_")


def unique_speeds(speeds: list[float]) -> list[float]:
    unique: list[float] = []
    for speed in speeds:
        if not any(abs(speed - existing) < 0.001 for existing in unique):
            unique.append(speed)
    return unique


def run_ffmpeg(command: list[str]) -> None:
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
