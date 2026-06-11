#!/usr/bin/env python3
"""
Local TTS Backend — Integration Template

This is the backend that will be registered in `scripts/tts_backends/`
once a local model (Coqui XTTS / F5-TTS) is installed with GPU support.

For Phase 1 (current environment: CPU-only, low RAM):
  - edge-tts is the default fallback
  - This backend is ready but disabled until GPU is available

Usage (when GPU available):
    pip install TTS torch torchaudio
    python scripts/notes_to_audio.py <project> --provider local

Architecture:
    notes_to_audio.py
      └── tts_backends/backend_local.py  ← this file
            ├── local_tts/models/         ← model checkpoint
            └── local_tts/reference_audio/ ← voice samples
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional

# Locate the local_tts directory
# When this file is at: <skill_root>/local_tts/backend_local.py
# After integration, it will be at: <skill_root>/skills/deepppt/scripts/tts_backends/backend_local.py
_LOCAL_TTS_CANDIDATES = [
    Path(__file__).resolve().parent,                                                    # local_tts/
    Path(__file__).resolve().parent.parent.parent / "local_tts",                       # from tts_backends/
    Path(__file__).resolve().parent.parent.parent.parent.parent / "local_tts",         # from scripts/tts_backends/
]

LOCAL_TTS_DIR = None
for candidate in _LOCAL_TTS_CANDIDATES:
    if (candidate / "voice_config.json").exists():
        LOCAL_TTS_DIR = candidate
        break

if LOCAL_TTS_DIR is None:
    LOCAL_TTS_DIR = Path(__file__).resolve().parent  # fallback
MODELS_DIR = LOCAL_TTS_DIR / "models"
REF_AUDIO_DIR = LOCAL_TTS_DIR / "reference_audio"
VOICE_CONFIG_FILE = LOCAL_TTS_DIR / "voice_config.json"

# Default config
DEFAULT_CONFIG = {
    "backend": "coqui_xtts",  # coqui_xtts | f5_tts | piper
    "device": "cpu",          # cpu | cuda
    "default_voice": "default",
    "voices": {
        "default": {
            "model": "tts_models/multilingual/multi-dataset/xtts_v2",
            "reference_audio": "reference_audio/default.wav",
        }
    },
}


def load_voice_config() -> dict:
    """Load local voice configuration."""
    if not VOICE_CONFIG_FILE.exists():
        return DEFAULT_CONFIG
    try:
        with open(VOICE_CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return {**DEFAULT_CONFIG, **cfg}
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG


def save_voice_config(config: dict):
    """Save local voice configuration."""
    VOICE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VOICE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def is_available() -> bool:
    """Check if local TTS backend is usable."""
    try:
        import torch
        config = load_voice_config()
        device = config.get("device", "cpu")

        if device == "cuda" and not torch.cuda.is_available():
            return False

        # Check backend-specific imports
        backend = config.get("backend", "coqui_xtts")
        if backend == "coqui_xtts":
            import TTS  # noqa: F401
        elif backend == "f5_tts":
            import f5_tts  # noqa: F401

        return True
    except ImportError:
        return False


def generate(
    text: str,
    output_path: Path,
    voice_id: str = "default",
    device: Optional[str] = None,
) -> bool:
    """Generate audio using the configured local TTS backend.

    Args:
        text: Text to synthesize
        output_path: Where to save the audio file
        voice_id: Voice preset ID (must exist in voice_config.json)
        device: Override device (cpu/cuda)
    """
    config = load_voice_config()
    backend = config.get("backend", "coqui_xtts")
    device = device or config.get("device", "cpu")

    voice_cfg = config.get("voices", {}).get(voice_id)
    if not voice_cfg:
        print(f"[ERROR] Voice '{voice_id}' not found in voice_config.json")
        return False

    ref_audio = LOCAL_TTS_DIR / voice_cfg.get("reference_audio", "")
    if not ref_audio.exists():
        print(f"[ERROR] Reference audio not found: {ref_audio}")
        return False

    try:
        if backend == "coqui_xtts":
            return _generate_coqui(text, output_path, voice_cfg, ref_audio, device)
        elif backend == "f5_tts":
            return _generate_f5tts(text, output_path, voice_cfg, ref_audio, device)
        else:
            print(f"[ERROR] Unknown backend: {backend}")
            return False
    except Exception as e:
        print(f"[ERROR] Local TTS generation failed: {e}")
        return False


def _generate_coqui(text: str, output_path: Path, voice_cfg: dict,
                    ref_audio: Path, device: str) -> bool:
    """Generate using Coqui XTTS v2."""
    import torch
    from TTS.api import TTS

    model_name = voice_cfg.get("model", "tts_models/multilingual/multi-dataset/xtts_v2")

    tts = TTS(model_name=model_name).to(device)

    tts.tts_to_file(
        text=text,
        speaker_wav=str(ref_audio),
        file_path=str(output_path),
        language=voice_cfg.get("language", "zh"),
    )
    return True


def _generate_f5tts(text: str, output_path: Path, voice_cfg: dict,
                    ref_audio: Path, device: str) -> bool:
    """Generate using F5-TTS."""
    # Placeholder — requires f5-tts package
    import torch
    import torchaudio

    # F5-TTS integration would go here
    # from f5_tts.model import F5TTS
    # model = F5TTS(model_dir=str(MODELS_DIR))
    # audio = model.synthesize(text, ref_audio=str(ref_audio))
    # torchaudio.save(str(output_path), audio, 24000)

    print("[WARN] F5-TTS backend not yet implemented.")
    return False


def print_voices():
    """List available local voices."""
    config = load_voice_config()
    voices = config.get("voices", {})
    if not voices:
        print("No local voices configured.")
        print(f"\nAdd voices to: {VOICE_CONFIG_FILE}")
        return

    print(f"{'Voice ID':<20} {'Model':<50} {'Reference':<30}")
    print("-" * 100)
    for vid, cfg in voices.items():
        model = cfg.get("model", "?")[:48]
        ref = cfg.get("reference_audio", "?")[:28]
        print(f"{vid:<20} {model:<50} {ref:<30}")


if __name__ == "__main__":
    print("Local TTS Backend — Status Check")
    print(f"  Config:  {VOICE_CONFIG_FILE}")
    print(f"  Models:  {MODELS_DIR}")
    print(f"  Ref Audio: {REF_AUDIO_DIR}")
    print(f"  Available: {is_available()}")
    print()
    print_voices()
    print()
    print("To add a voice:")
    print(f"  1. Place reference audio in: {REF_AUDIO_DIR}/")
    print(f"  2. Edit config: {VOICE_CONFIG_FILE}")
    print()
    print("To use in PPT pipeline:")
    print(f"  python scripts/notes_to_audio.py <project> --provider local --voice-id <voice_id>")
