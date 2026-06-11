#!/usr/bin/env python3
"""
FakeYou TTS Backend — Free Community-Powered Voice Library

FakeYou (https://fakeyou.com) hosts 3,500+ community-contributed voices,
including Donald Trump, Obama, celebrities, cartoon characters, etc.

This backend provides:
  - Free TTS generation (rate-limited by IP)
  - Voice listing/search
  - Integration with notes_to_audio.py pipeline

Setup:
    No API key required for basic usage.
    Optional: FakeYou login cookie for higher rate limits.

Usage:
    # List Trump-related voices
    python backend_fakeyou.py --search trump

    # Generate a test clip
    python backend_fakeyou.py --text "We're going to make AI great again!" \
        --voice "TM:weight_7p2j8f3k" --output trump_test.wav

    # In the PPT pipeline
    python scripts/notes_to_audio.py <project> \
        --provider fakeyou \
        --voice-id "TM:weight_7p2j8f3k"
"""

import argparse
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = "https://api.fakeyou.com"

# Well-known voice tokens (verified working as of 2025-2026)
KNOWN_VOICES = {
    "trump": {
        "token": "TM:2cnbwzd9fqw8",
        "name": "Donald Trump",
        "language": "en",
        "note": "Standard Trump voice",
    },
    "trump_angry": {
        "token": "TM:9m0k5zh7gq3r",
        "name": "Donald Trump (Angry)",
        "language": "en",
        "note": "Angry/aggressive Trump tone",
    },
    "obama": {
        "token": "TM:nf8pj2mq4v7k",
        "name": "Barack Obama",
        "language": "en",
        "note": "Standard Obama voice",
    },
    "biden": {
        "token": "TM:7x9vw3sk1p2m",
        "name": "Joe Biden",
        "language": "en",
        "note": "Standard Biden voice",
    },
}

# Cahe for voice list (avoids re-fetching)
_voice_cache: dict | None = None
_cache_time: float = 0
CACHE_TTL = 3600  # 1 hour


def _api_get(path: str) -> dict:
    """GET request to FakeYou API (uses curl_cffi for Cloudflare bypass)."""
    url = f"{API_BASE}{path}"
    try:
        from curl_cffi import requests as cf_req
        resp = cf_req.get(url, headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }, impersonate="chrome120", timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"FakeYou API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()
    except ImportError:
        # Fallback to urllib with browser headers
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"FakeYou API error {e.code}: {body[:200]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"FakeYou API unreachable: {e.reason}") from e


def _api_post(path: str, payload: dict) -> dict:
    """POST request to FakeYou API (uses curl_cffi for Cloudflare bypass)."""
    url = f"{API_BASE}{path}"
    try:
        from curl_cffi import requests as cf_req
        resp = cf_req.post(url, json=payload, headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }, impersonate="chrome120", timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"FakeYou API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()
    except ImportError:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"FakeYou API error {e.code}: {body[:200]}") from e


def list_voices(search: str | None = None) -> list[dict]:
    """List FakeYou voices, optionally filtered by search term."""
    global _voice_cache, _cache_time

    # Use cache if fresh
    now = time.time()
    if _voice_cache is not None and (now - _cache_time) < CACHE_TTL:
        voices = _voice_cache
    else:
        result = _api_get("/tts/list")
        voices = result.get("models", [])
        _voice_cache = voices
        _cache_time = now

    if search:
        search_lower = search.lower()
        voices = [
            v for v in voices
            if search_lower in v.get("title", "").lower()
            or search_lower in v.get("model_token", "").lower()
            or search_lower in " ".join(v.get("tags", [])).lower()
        ]

    return voices


def generate_tts(text: str, voice_token: str, output_path: str,
                 timeout: int = 120) -> bool:
    """Generate TTS audio using FakeYou API.

    Args:
        text: Text to synthesize (max ~600 chars per request)
        voice_token: FakeYou model token (e.g., "TM:2cnbwzd9fqw8")
        output_path: Path to save the WAV/audio file
        timeout: Max wait time in seconds

    Returns:
        True if successful
    """
    # Step 1: Submit inference job
    job_id = str(uuid.uuid4())
    payload = {
        "uuid_idempotency_token": job_id,
        "tts_model_token": voice_token,
        "inference_text": text,
    }

    result = _api_post("/tts/inference", payload)
    if not result.get("success"):
        error_reason = result.get("error_reason", "unknown")
        raise RuntimeError(f"FakeYou inference rejected: {error_reason}")

    job_token = result.get("inference_job_token")
    if not job_token:
        raise RuntimeError("FakeYou: no inference_job_token in response")

    # Step 2: Poll for completion
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(2)  # Rate-limit friendly polling
        status = _api_get(f"/tts/job/{job_token}")
        state = status.get("state", {})

        if state.get("status") == "complete_success":
            audio_url = state.get("maybe_public_bucket_wav_audio_path")
            if audio_url:
                # Step 3: Download audio
                _download_audio(audio_url, output_path)
                return True
            raise RuntimeError("FakeYou: completed but no audio URL")

        if state.get("status") in ("complete_failure", "dead"):
            raise RuntimeError(f"FakeYou: job failed ({state.get('status')})")

        # Still pending — continue polling

    raise RuntimeError(f"FakeYou: timeout after {timeout}s (job may still be queued)")


def _download_audio(url: str, output_path: str):
    """Download generated audio from FakeYou CDN."""
    # FakeYou URLs may need http → https
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)

    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(data)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Failed to download audio: HTTP {e.code}") from e


def search_voices(keyword: str, limit: int = 20):
    """Search and display FakeYou voices matching a keyword."""
    voices = list_voices(keyword)
    if not voices:
        print(f"No voices found for '{keyword}'")
        return

    print(f"\nFound {len(voices)} voice(s) matching '{keyword}':\n")
    print(f"{'Token':<25} {'Title':<45} {'Lang':<8} {'Tags'}")
    print("-" * 110)

    for v in voices[:limit]:
        token = v.get("model_token", "?")[:24]
        title = v.get("title", "?")[:44]
        lang = v.get("ietf_primary_language_subtag", "?")[:7]
        tags = ", ".join(v.get("tags", [])[:4])[:35]
        print(f"{token:<25} {title:<45} {lang:<8} {tags}")

    if len(voices) > limit:
        print(f"\n  ... and {len(voices) - limit} more. Narrow your search.")


def main():
    parser = argparse.ArgumentParser(
        description="FakeYou TTS Backend — Free Community Voice Library",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for Trump voices
  python backend_fakeyou.py --search trump

  # Generate a test clip with Trump voice
  python backend_fakeyou.py --text "Make AI great again!" --voice trump --output test.wav

  # List known celebrity voices
  python backend_fakeyou.py --known
        """,
    )
    parser.add_argument("--search", type=str, help="Search FakeYou voice library")
    parser.add_argument("--known", action="store_true", help="Show known celebrity voices")
    parser.add_argument("--text", type=str, help="Text to synthesize")
    parser.add_argument("--voice", type=str, help="Voice token or known voice name (e.g., 'trump')")
    parser.add_argument("--output", type=str, default="fakeyou_output.wav", help="Output file path")
    args = parser.parse_args()

    if args.known:
        print("\nKnown Celebrity Voices:\n")
        for key, info in KNOWN_VOICES.items():
            print(f"  {key:<15} → {info['token']}")
            print(f"              {info['name']} ({info['language']}) — {info['note']}")
            print()

    if args.search:
        search_voices(args.search)

    if args.text and args.voice:
        # Resolve voice
        voice_token = KNOWN_VOICES.get(args.voice, {}).get("token", args.voice)
        print(f"\nGenerating TTS...")
        print(f"  Voice: {args.voice} ({voice_token})")
        print(f"  Text:  \"{args.text[:80]}...\"")
        print(f"  Output: {args.output}")

        try:
            start = time.time()
            generate_tts(args.text, voice_token, args.output)
            elapsed = time.time() - start
            size = os.path.getsize(args.output)
            print(f"\n  Done! {size/1024:.1f}KB in {elapsed:.1f}s")
            print(f"  Saved: {args.output}")
        except Exception as e:
            print(f"\n  Error: {e}")
            return 1

    if not (args.known or args.search or (args.text and args.voice)):
        parser.print_help()
        print("\nQuick start:")
        print("  python backend_fakeyou.py --known          # Show celebrity voices")
        print("  python backend_fakeyou.py --search trump   # Search online")
        print("  python backend_fakeyou.py --text \"Hello\" --voice trump --output test.wav")

    return 0


if __name__ == "__main__":
    sys.exit(main())
