#!/usr/bin/env python3
"""
Local TTS Test Environment — Phase 1 Setup

This module tests and validates the local voice cloning pipeline.
Supports multiple backends with graceful fallback.

Backends (priority order):
  1. Coqui XTTS v2 — local voice cloning (GPU recommended, CPU slow)
  2. Piper TTS — lightweight local synthesis (no cloning, CPU friendly)
  3. edge-tts — cloud fallback (always available)

Usage:
    # Test the environment
    python local_tts/phase1_test.py

    # Generate a test voice sample
    python local_tts/phase1_test.py --text "你好，这是测试语音" --output test.mp3
"""

import argparse
import os
import sys
import time
from pathlib import Path

LOCAL_TTS_DIR = Path(__file__).resolve().parent
MODELS_DIR = LOCAL_TTS_DIR / "models"
REF_AUDIO_DIR = LOCAL_TTS_DIR / "reference_audio"
TEST_OUTPUT_DIR = LOCAL_TTS_DIR / "test_output"


def check_environment():
    """Check hardware and software environment."""
    results = {}

    # Python version
    results["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # OS
    import platform
    results["os"] = f"{platform.system()} {platform.release()}"

    # CPU
    results["cpu_cores"] = os.cpu_count()

    # RAM
    try:
        import ctypes
        k = ctypes.windll.kernel32
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        k.GlobalMemoryStatusEx(ctypes.byref(m))
        results["ram_total_gb"] = f"{m.ullTotalPhys/1e9:.1f}"
        results["ram_free_gb"] = f"{m.ullAvailPhys/1e9:.1f}"
    except Exception:
        results["ram_total_gb"] = "unknown"
        results["ram_free_gb"] = "unknown"

    # GPU (NVIDIA)
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip():
            results["gpu"] = r.stdout.strip()
        else:
            results["gpu"] = "none"
    except Exception:
        results["gpu"] = "none"

    # PyTorch
    try:
        import torch
        results["torch"] = torch.__version__
        results["cuda_available"] = torch.cuda.is_available()
    except ImportError:
        results["torch"] = "not installed"
        results["cuda_available"] = False

    # edge-tts (baseline)
    try:
        import edge_tts
        results["edge_tts"] = "available"
    except ImportError:
        results["edge_tts"] = "not installed"

    return results


def check_backend_availability():
    """Check which TTS backends are available."""
    backends = {}

    # Coqui TTS / XTTS
    try:
        import TTS
        backends["coqui_tts"] = {"status": "available", "version": TTS.__version__}
    except ImportError:
        backends["coqui_tts"] = {"status": "not installed", "install": "pip install TTS"}

    # Piper TTS
    try:
        import piper  # noqa: F401
        backends["piper"] = {"status": "available"}
    except ImportError:
        backends["piper"] = {"status": "not installed", "install": "pip install piper-tts"}

    # F5-TTS
    try:
        import f5_tts  # noqa: F401
        backends["f5_tts"] = {"status": "available"}
    except ImportError:
        backends["f5_tts"] = {"status": "not installed", "install": "pip install f5-tts"}

    return backends


def generate_edge_tts(text: str, output_path: str, voice: str = "zh-CN-YunjianNeural") -> bool:
    """Fallback: generate audio using edge-tts (always available)."""
    try:
        import asyncio
        import edge_tts

        async def _gen():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

        asyncio.run(_gen())
        return True
    except Exception as e:
        print(f"[ERROR] edge-tts generation failed: {e}")
        return False


def generate_piper_tts(text: str, output_path: str, voice: str = "zh_CN-huayan-medium") -> bool:
    """Generate audio using Piper TTS (lightweight, CPU)."""
    try:
        import subprocess
        # Piper provides a CLI; model must be downloaded first
        # echo 'text' | piper --model <model.onnx> --output_file output.wav
        model_path = MODELS_DIR / f"{voice}.onnx"
        if not model_path.exists():
            print(f"[WARN] Piper model not found: {model_path}")
            print(f"  Download: curl -L <url> -o {model_path}")
            return False

        result = subprocess.run(
            ["piper", "--model", str(model_path), "--output_file", output_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] Piper generation failed: {e}")
        return False


def main():
    # Fix Windows GBK console encoding
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Local TTS Phase 1 Test Environment")
    parser.add_argument("--text", type=str, default="你好，这是本地语音合成测试。",
                       help="Text to synthesize")
    parser.add_argument("--output", type=str, default=None,
                       help="Output file path (default: test_output/test_<ts>.mp3)")
    parser.add_argument("--env-only", action="store_true",
                       help="Only check environment, don't generate audio")
    args = parser.parse_args()

    print("=" * 60)
    print("  Local TTS — Phase 1 Environment Check")
    print("=" * 60)

    # 1. Environment
    print("\n[HARDWARE]")
    env = check_environment()
    for k, v in env.items():
        print(f"  {k}: {v}")

    # 2. Backend availability
    print("\n[BACKENDS]")
    backends = check_backend_availability()
    for name, info in backends.items():
        status = info["status"]
        marker = "✅" if status == "available" else "❌"
        print(f"  {marker} {name}: {status}")
        if "install" in info:
            print(f"       Install: {info['install']}")

    # 3. Recommended backend
    print("\n[RECOMMENDATION]")
    has_gpu = env.get("cuda_available", False)
    ram_free = float(env.get("ram_free_gb", "0").replace("unknown", "0"))

    if backends.get("coqui_tts", {}).get("status") == "available":
        print("  ✅ Coqui TTS available — use for voice cloning (GPU recommended)")
    elif backends.get("f5_tts", {}).get("status") == "available":
        print("  ✅ F5-TTS available — use for zero-shot voice cloning")
    elif backends.get("piper", {}).get("status") == "available":
        print("  ⚠️  Piper available — lightweight synthesis, no cloning")
    else:
        print("  ⚠️  No local backend available. Falling back to edge-tts (cloud).")
        if not has_gpu:
            print("  💡 To enable local TTS: install a GPU or use Piper TTS (CPU-friendly)")

    # 4. Generate test audio (if not env-only)
    if not args.env_only:
        output = args.output or str(TEST_OUTPUT_DIR / f"test_{int(time.time())}.mp3")

        print(f"\n[GENERATE] Text: \"{args.text[:50]}...\"")
        print(f"  Output: {output}")

        success = generate_edge_tts(args.text, output)
        if success:
            size = os.path.getsize(output)
            print(f"  ✅ Generated: {size/1024:.1f}KB")
            print(f"  📁 {output}")
        else:
            print(f"  ❌ Generation failed")
            return 1

    print(f"\n{'='*60}")
    print(f"  Phase 1 check complete!")
    print(f"  Next: review backend availability above to decide local setup approach.")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
