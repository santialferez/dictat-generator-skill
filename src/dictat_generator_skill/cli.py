from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "gemini-dictat-generator"
        / "scripts"
        / "generate_dictat.py"
    )
    if not script.is_file():
        raise SystemExit(f"Bundled script not found: {script}")
    runpy.run_path(str(script), run_name="__main__")

