#!/usr/bin/env python3
import argparse
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
    parser.add_argument("--speeds", nargs="*", type=float, default=[1.0], help="Audio speed factors to export as WAV. Defaults to only the original speed.")
    parser.add_argument("--mp3-speed", type=float, default=1.0, help="Speed factor to use for MP3 export. Defaults to original speed.")
    parser.add_argument("--no-mp3", action="store_true", help="Skip mobile MP3 export.")
    parser.add_argument(
        "--keep-speed-wavs",
        action="store_true",
        help="Keep WAV speed variants after MP3 export. By default, only the base WAV master is kept.",
    )
    parser.add_argument(
        "--no-continuous-transcript",
        action="store_true",
        help="Skip writing the clean continuous transcript used for proofreading.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("No API key provided. Pass --api-key or set GEMINI_API_KEY.")
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
    if (any(abs(speed - 1.0) >= 0.001 for speed in args.speeds) or not args.no_mp3) and not shutil.which("ffmpeg"):
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
    )

    speed_wavs: dict[float, Path] = {}
    for speed in args.speeds:
        if abs(speed - 1.0) < 0.001:
            continue
        speed_wav = args.out_dir / f"{args.basename}_{speed_label(speed)}x.wav"
        run_ffmpeg(["ffmpeg", "-y", "-i", str(base_wav), "-filter:a", f"atempo={speed}", str(speed_wav)])
        speed_wavs[speed] = speed_wav
        print(f"Speed variant saved to: {speed_wav}", flush=True)

    mp3_source = base_wav
    if not args.no_mp3:
        if args.mp3_speed and abs(args.mp3_speed - 1.0) >= 0.001:
            mp3_source = speed_wavs.get(args.mp3_speed) or args.out_dir / f"{args.basename}_{speed_label(args.mp3_speed)}x.wav"
            if args.mp3_speed not in speed_wavs:
                run_ffmpeg(["ffmpeg", "-y", "-i", str(base_wav), "-filter:a", f"atempo={args.mp3_speed}", str(mp3_source)])
                speed_wavs[args.mp3_speed] = mp3_source
        mp3_path = args.out_dir / f"{mp3_source.stem}.mp3"
        run_ffmpeg(["ffmpeg", "-y", "-i", str(mp3_source), "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3_path)])
        print(f"Mobile MP3 saved to: {mp3_path.resolve()}", flush=True)

        if not args.keep_speed_wavs:
            for speed_wav in speed_wavs.values():
                if speed_wav != base_wav and speed_wav.exists():
                    speed_wav.unlink()
                    print(f"Removed intermediate speed WAV: {speed_wav}", flush=True)


def generate_transcript(client: genai.Client, model: str, topic: str, level: str, language: str, repeat_policy: str) -> str:
    profile = LEVEL_PROFILES[level]
    prompt = f"""Write a school dictation script in {language}.

Level: {level}
Approximate length: {profile["words"]} content words.
Topic: {topic}
Style: {profile["style"]}.
Repetition: {repetition_instruction(repeat_policy, level)}.

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
        return "repeat every phrase or short dictation unit two times before moving to the next unit"
    if repeat_policy == "once":
        return "repeat every phrase or short dictation unit one time"
    if repeat_policy == "selective":
        return "repeat only longer or difficult clauses, not every phrase"
    if repeat_policy == "none":
        return "do not repeat phrases unless needed for punctuation clarity"
    return LEVEL_PROFILES[level]["style"]


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
) -> None:
    chunks = chunk_transcript(transcript, max_chars=max_chunk_chars)
    if concurrency == 1 or len(chunks) <= 1:
        chunk_results = [
            synthesize_chunk_with_retries(client, model, voice, chunk_text, language, index, len(chunks), retries)
            for index, chunk_text in enumerate(chunks, start=1)
        ]
    else:
        workers = min(concurrency, len(chunks))
        print(f"Generating {len(chunks)} audio chunks with concurrency {workers}", flush=True)
        chunk_results = [None] * len(chunks)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    synthesize_chunk_with_retries,
                    client,
                    model,
                    voice,
                    chunk_text,
                    language,
                    index,
                    len(chunks),
                    retries,
                ): index
                for index, chunk_text in enumerate(chunks, start=1)
            }
            for future in as_completed(futures):
                index = futures[future]
                chunk_results[index - 1] = future.result()
                print(f"Finished audio chunk {index}/{len(chunks)}", flush=True)

    mime_type = chunk_results[0][1] if chunk_results else "audio/L16;rate=24000"
    audio_parameters = parse_audio_mime_type(mime_type)
    raw_audio = bytearray()
    for audio_data, result_mime_type in chunk_results:
        if parse_audio_mime_type(result_mime_type) != audio_parameters:
            raise RuntimeError(f"Mixed TTS audio formats are not supported: {mime_type} and {result_mime_type}")
        raw_audio.extend(audio_data)
    output.write_bytes(convert_to_wav(bytes(raw_audio), mime_type))
    print(f"WAV saved to: {output.resolve()}", flush=True)


def synthesize_chunk_with_retries(
    client: genai.Client,
    model: str,
    voice: str,
    chunk_text: str,
    language: str,
    index: int,
    total: int,
    retries: int,
) -> tuple[bytes, str]:
    for attempt in range(retries + 1):
        try:
            return synthesize_chunk(client, model, voice, chunk_text, language, index, total)
        except Exception as error:
            if attempt >= retries:
                raise
            delay = min(2 ** attempt, 10)
            print(
                f"Audio chunk {index}/{total} failed ({type(error).__name__}); retrying in {delay}s "
                f"({attempt + 1}/{retries})",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable retry state")


def synthesize_chunk(
    client: genai.Client,
    model: str,
    voice: str,
    chunk_text: str,
    language: str,
    index: int,
    total: int,
) -> tuple[bytes, str]:
    config = types.GenerateContentConfig(
        temperature=1,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )
    raw_audio = bytearray()
    mime_type = "audio/L16;rate=24000"
    print(f"Generating audio chunk {index}/{total}", flush=True)
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=tts_prompt(chunk_text, language))],
        )
    ]
    for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
        if chunk.parts is None:
            continue
        inline_data = chunk.parts[0].inline_data
        if inline_data and inline_data.data:
            mime_type = inline_data.mime_type
            raw_audio.extend(inline_data.data)
        elif chunk.text:
            print(chunk.text, flush=True)
    return bytes(raw_audio), mime_type


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


def run_ffmpeg(command: list[str]) -> None:
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
