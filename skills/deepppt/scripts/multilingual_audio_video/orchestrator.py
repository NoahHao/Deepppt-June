#!/usr/bin/env python3
"""
Multilingual Audio-Video Generation Orchestrator
================================================

One-command pipeline: speaker-notes splitting → TTS audio generation → PPTX export
with embedded narration and slide timings. Guarantees audio finishes before slide advance.

Usage:
    # Full pipeline (split + audio + export)
    python3 scripts/multilingual_audio_video/orchestrator.py <project_path> \\
        --voice zh-CN-YunjianNeural --rate +0%

    # Split only
    python3 scripts/multilingual_audio_video/orchestrator.py <project_path> --split-only

    # Audio only (after split)
    python3 scripts/multilingual_audio_video/orchestrator.py <project_path> \\
        --voice ja-JP-NanamiNeural --audio-only

    # Export only (after audio generated)
    python3 scripts/multilingual_audio_video/orchestrator.py <project_path> --export-only

Pipeline stages:
    Stage 1: total_md_split.py  → notes/total.md → notes/slide_*.md
    Stage 2: notes_to_audio.py  → notes/slide_*.md → audio/slide_*.mp3
    Stage 3: svg_to_pptx.py     → SVG + audio → PPTX with embedded narration
              --recorded-narration audio
              --animation-trigger after-previous
              (CRITICAL: audio duration from mutagen ensures slide advance ≥ audio length)

Dependencies:
    edge-tts, mutagen — auto-installed if missing
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Find the scripts/ parent directory
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
MODULE_DIR = Path(__file__).resolve().parent

# Paths to pipeline scripts (relative to scripts/)
TOTAL_MD_SPLIT = SCRIPTS_DIR / "total_md_split.py"
NOTES_TO_AUDIO = SCRIPTS_DIR / "notes_to_audio.py"
SVG_TO_PPTX = SCRIPTS_DIR / "svg_to_pptx.py"

# Config file (same directory as this script)
CONFIG_FILE = MODULE_DIR / "tts_config.json"


def load_tts_config() -> dict:
    """Load TTS configuration from tts_config.json.
    Returns defaults if file doesn't exist or is invalid.
    """
    defaults = {
        "default_provider": "edge",
        "providers": {
            "edge": {
                "voice_defaults": {"zh-CN": "zh-CN-YunjianNeural"},
                "rate": "+0%",
            }
        },
    }
    if not CONFIG_FILE.exists():
        return defaults
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        # Merge with defaults to fill missing fields
        merged = {**defaults, **cfg}
        if "providers" in cfg:
            for p in defaults.get("providers", {}):
                if p in cfg.get("providers", {}):
                    merged["providers"][p] = {**defaults["providers"].get(p, {}), **cfg["providers"][p]}
        return merged
    except (json.JSONDecodeError, IOError):
        return defaults


def get_voice_for_language(config: dict, provider: str, language: str) -> str:
    """Get the recommended voice for a given language and provider."""
    provider_cfg = config.get("providers", {}).get(provider, {})
    voice_defaults = provider_cfg.get("voice_defaults", {})
    # Exact match first
    if language in voice_defaults:
        return voice_defaults[language]
    # Prefix match (e.g., 'zh' matches 'zh-CN')
    for key in voice_defaults:
        if key.startswith(language):
            return voice_defaults[key]
    # Fallback
    return "zh-CN-YunjianNeural"


def get_rate_for_provider(config: dict, provider: str) -> str:
    """Get the default rate for a given provider."""
    provider_cfg = config.get("providers", {}).get(provider, {})
    return provider_cfg.get("rate", "+0%")


def ensure_deps():
    """Check and install required Python packages."""
    deps = {"edge_tts": "edge-tts", "mutagen": "mutagen"}
    missing = []
    for module, package in deps.items():
        try:
            __import__(module.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        print(f"[DEPS] Installing: {' '.join(missing)}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
            check=True,
        )
        print("[DEPS] Done")


def run_stage(name: str, cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a pipeline stage, print status, return success."""
    print(f"\n{'='*60}")
    print(f"  Stage: {name}")
    print(f"{'='*60}")

    result = subprocess.run(
        cmd,
        cwd=str(cwd or SCRIPTS_DIR),
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"\n[ERROR] {name} failed (exit code {result.returncode})")
        return False
    print(f"[OK] {name} completed")
    return True


def stage_split(project_path: str) -> bool:
    """Stage 1: Split speaker notes into per-slide files."""
    return run_stage(
        "1/3 Notes Split",
        [sys.executable, str(TOTAL_MD_SPLIT), str(project_path)],
    )


def stage_audio(
    project_path: str,
    voice: str,
    rate: str = "+0%",
    provider: str | None = None,
    voice_id: str | None = None,
    provider_model: str | None = None,
) -> bool:
    """Stage 2: Generate per-slide audio narration."""
    cmd = [
        sys.executable,
        str(NOTES_TO_AUDIO),
        str(project_path),
        "--voice", voice,
        "--rate", rate,
    ]
    if provider:
        cmd.extend(["--provider", provider])
    if voice_id:
        cmd.extend(["--voice-id", voice_id])
    if provider_model and provider == "elevenlabs":
        cmd.extend(["--elevenlabs-model", provider_model])
    elif provider_model and provider == "minimax":
        cmd.extend(["--minimax-model", provider_model])
    elif provider_model and provider == "qwen":
        cmd.extend(["--qwen-model", provider_model])
    elif provider_model and provider == "cosyvoice":
        cmd.extend(["--cosyvoice-model", provider_model])

    return run_stage("2/3 Audio Generation", cmd)


def stage_export(project_path: str) -> bool:
    """Stage 3: Export PPTX with embedded narration + slide timings.

    CRITICAL: Uses mutagen for accurate audio duration measurement.
    This ensures slide advance timing ≥ audio length — no cut-off narration.
    """
    return run_stage(
        "3/3 PPTX Export (with narration)",
        [
            sys.executable,
            str(SVG_TO_PPTX),
            str(project_path),
            "--recorded-narration", "audio",
            "--animation-trigger", "after-previous",
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Multilingual Audio-Video PPTX Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with config auto-detection (Japanese female voice from config)
  %(prog)s projects/my_project --language ja-JP

  # Full pipeline, explicit voice override
  %(prog)s projects/my_project --voice en-US-JennyNeural --rate -5%%

  # Full pipeline with cloud provider
  %(prog)s projects/my_project --provider elevenlabs --voice-id <id>

  # Audio generation only
  %(prog)s projects/my_project --voice zh-CN-XiaoxiaoNeural --audio-only
        """,
    )

    parser.add_argument("project", help="Path to the project directory")
    parser.add_argument(
        "--language", type=str, default=None,
        help="Target language (e.g. zh-CN, en-US, ja-JP). Auto-selects voice from tts_config.json.",
    )
    parser.add_argument(
        "--voice", type=str, default=None,
        help="TTS voice ShortName. If omitted, auto-selected from config by --language.",
    )
    parser.add_argument(
        "--rate", type=str, default=None,
        help="Speech rate adjustment. If omitted, uses config default.",
    )
    parser.add_argument(
        "--provider", type=str, default=None,
        help="TTS provider. If omitted, uses config default (edge).",
    )
    parser.add_argument(
        "--voice-id", type=str, default=None,
        help="Cloud provider voice ID (required for non-edge providers)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Provider model override (e.g. eleven_multilingual_v2, speech-2.8-hd)",
    )

    # Stage selection
    parser.add_argument("--split-only", action="store_true", help="Run only notes split")
    parser.add_argument("--audio-only", action="store_true", help="Run only audio generation")
    parser.add_argument("--export-only", action="store_true", help="Run only PPTX export")

    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.exists():
        print(f"[ERROR] Project not found: {project_path}")
        return 1

    ensure_deps()

    # Load TTS config
    config = load_tts_config()
    provider = args.provider or config.get("default_provider", "edge")
    provider_cfg = config.get("providers", {}).get(provider, {})

    # Resolve voice
    voice = args.voice
    if not voice and args.language:
        voice = get_voice_for_language(config, provider, args.language)
    if not voice:
        voice = get_voice_for_language(config, provider, "zh-CN")

    # Resolve rate
    rate = args.rate or get_rate_for_provider(config, provider)

    # Resolve model
    model = args.model or provider_cfg.get("model")

    # Determine which stages to run
    if args.split_only:
        ok = stage_split(str(project_path))
        return 0 if ok else 1

    if args.audio_only:
        ok = stage_audio(
            str(project_path), voice, rate,
            provider, args.voice_id, model,
        )
        return 0 if ok else 1

    if args.export_only:
        ok = stage_export(str(project_path))
        return 0 if ok else 1

    # Full pipeline
    print(f"\n{'='*60}")
    print(f"  Multilingual Audio-Video Pipeline")
    print(f"{'='*60}")
    print(f"  Project:  {project_path.name}")
    print(f"  Language: {args.language or 'auto'}")
    print(f"  Provider: {provider}")
    print(f"  Voice:    {voice}")
    print(f"  Rate:     {rate}")
    if model:
        print(f"  Model:    {model}")

    # Stage 1
    if not stage_split(str(project_path)):
        return 1

    # Stage 2
    if not stage_audio(
        str(project_path), voice, rate,
        provider, args.voice_id, model,
    ):
        return 1

    # Stage 3
    if not stage_export(str(project_path)):
        return 1

    print(f"\n{'='*60}")
    print(f"  Pipeline Complete!")
    print(f"{'='*60}")
    print(f"\n  Output: {project_path}/exports/<name>_<timestamp>.pptx")
    print(f"  Open in PowerPoint → Slide Show → Use Recorded Timings\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
