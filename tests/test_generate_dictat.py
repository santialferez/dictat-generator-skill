from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "gemini-dictat-generator"
    / "scripts"
    / "generate_dictat.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("generate_dictat", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_speed_label_formats_decimal_speeds():
    module = load_module()

    assert module.speed_label(1.25) == "1_25"
    assert module.speed_label(1.0) == "1"
    assert module.speed_label(0.75) == "0_75"


def test_unique_speeds_preserves_order_and_deduplicates_close_values():
    module = load_module()

    assert module.unique_speeds([1.0, 1.25, 1.0, 1.2504, 0.9]) == [1.0, 1.25, 0.9]


def test_parse_audio_mime_type_handles_case_and_spacing():
    module = load_module()

    assert module.parse_audio_mime_type("audio/L16;rate=24000") == {
        "bits_per_sample": 16,
        "rate": 24000,
        "channels": 1,
    }
    assert module.parse_audio_mime_type("audio/l16; rate=16000; channels=2") == {
        "bits_per_sample": 16,
        "rate": 16000,
        "channels": 2,
    }


def test_chunk_transcript_respects_blank_line_blocks_and_max_chars():
    module = load_module()
    transcript = "First short block.\n\n" + "Sentence one is long enough. Sentence two is also long enough."

    chunks = module.chunk_transcript(transcript, max_chars=35)

    assert chunks == [
        "First short block.",
        "Sentence one is long enough.",
        "Sentence two is also long enough.",
    ]


def test_convert_to_wav_writes_valid_pcm_header():
    module = load_module()
    audio = b"\x01\x00\x02\x00"

    wav = module.convert_to_wav(audio, "audio/L16;rate=24000")

    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    channels, sample_rate, bits_per_sample = struct.unpack("<H I 6x H", wav[22:36])
    assert channels == 1
    assert sample_rate == 24000
    assert bits_per_sample == 16
    assert wav[-4:] == audio


def test_main_keeps_base_and_speed_wav_when_mp3_is_disabled(tmp_path, monkeypatch):
    module = load_module()
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("One sentence.", encoding="utf-8")
    out_dir = tmp_path / "out"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(sys, "argv", [
        "generate_dictat.py",
        "--language",
        "English",
        "--transcript-file",
        str(transcript),
        "--out-dir",
        str(out_dir),
        "--basename",
        "sample",
        "--speeds",
        "1.0",
        "1.25",
        "--no-mp3",
        "--no-continuous-transcript",
    ])
    monkeypatch.setattr(module.genai, "Client", lambda *args, **kwargs: object())
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(module, "synthesize_wav", lambda *args, **kwargs: (out_dir / "sample.wav").write_bytes(b"wav"))

    def fake_ffmpeg(command):
        Path(command[-1]).write_bytes(b"speed")

    monkeypatch.setattr(module, "run_ffmpeg", fake_ffmpeg)

    module.main()

    assert (out_dir / "sample.wav").exists()
    assert (out_dir / "sample_1_25x.wav").exists()
    assert not (out_dir / "sample_1_25x.mp3").exists()


def test_main_exports_default_mp3_speeds_and_removes_wavs_by_default(tmp_path, monkeypatch):
    module = load_module()
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("One sentence.", encoding="utf-8")
    out_dir = tmp_path / "out"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(sys, "argv", [
        "generate_dictat.py",
        "--language",
        "English",
        "--transcript-file",
        str(transcript),
        "--out-dir",
        str(out_dir),
        "--basename",
        "sample",
        "--no-continuous-transcript",
    ])
    monkeypatch.setattr(module.genai, "Client", lambda *args, **kwargs: object())
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(module, "synthesize_wav", lambda *args, **kwargs: (out_dir / "sample.wav").write_bytes(b"wav"))

    def fake_ffmpeg(command):
        Path(command[-1]).write_bytes(b"audio")

    monkeypatch.setattr(module, "run_ffmpeg", fake_ffmpeg)

    module.main()

    assert not (out_dir / "sample.wav").exists()
    assert not (out_dir / "sample_1_25x.wav").exists()
    assert (out_dir / "sample.mp3").exists()
    assert (out_dir / "sample_1_25x.mp3").exists()


def test_main_can_keep_base_wav_with_mp3_exports(tmp_path, monkeypatch):
    module = load_module()
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("One sentence.", encoding="utf-8")
    out_dir = tmp_path / "out"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(sys, "argv", [
        "generate_dictat.py",
        "--language",
        "English",
        "--transcript-file",
        str(transcript),
        "--out-dir",
        str(out_dir),
        "--basename",
        "sample",
        "--mp3-speeds",
        "1.0",
        "1.25",
        "--keep-base-wav",
        "--no-continuous-transcript",
    ])
    monkeypatch.setattr(module.genai, "Client", lambda *args, **kwargs: object())
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(module, "synthesize_wav", lambda *args, **kwargs: (out_dir / "sample.wav").write_bytes(b"wav"))

    def fake_ffmpeg(command):
        Path(command[-1]).write_bytes(b"audio")

    monkeypatch.setattr(module, "run_ffmpeg", fake_ffmpeg)

    module.main()

    assert (out_dir / "sample.wav").exists()
    assert not (out_dir / "sample_1_25x.wav").exists()
    assert (out_dir / "sample.mp3").exists()
    assert (out_dir / "sample_1_25x.mp3").exists()


def test_main_supports_deprecated_single_mp3_speed(tmp_path, monkeypatch):
    module = load_module()
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("One sentence.", encoding="utf-8")
    out_dir = tmp_path / "out"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(sys, "argv", [
        "generate_dictat.py",
        "--language",
        "English",
        "--transcript-file",
        str(transcript),
        "--out-dir",
        str(out_dir),
        "--basename",
        "sample",
        "--mp3-speed",
        "1.25",
        "--no-continuous-transcript",
    ])
    monkeypatch.setattr(module.genai, "Client", lambda *args, **kwargs: object())
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(module, "synthesize_wav", lambda *args, **kwargs: (out_dir / "sample.wav").write_bytes(b"wav"))

    def fake_ffmpeg(command):
        Path(command[-1]).write_bytes(b"audio")

    monkeypatch.setattr(module, "run_ffmpeg", fake_ffmpeg)

    module.main()

    assert not (out_dir / "sample.wav").exists()
    assert not (out_dir / "sample.mp3").exists()
    assert (out_dir / "sample_1_25x.mp3").exists()
