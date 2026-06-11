#!/usr/bin/env python3
"""
Qwen3.6 SVG → PNG Image Generation Backend

Uses a local vLLM chat model (qwen3.6-35b) to generate SVG diagrams,
then converts them to PNG via svglib + renderPM for PPTX embedding.

This backend works when no real image generation model is available —
it leverages the LLM's ability to output structured SVG code.

Configuration keys (from .env):
  QWEN_API_KEY     (required)  API key for the vLLM server
  QWEN_BASE_URL    (optional)  vLLM server URL (default: http://10.226.72.52:8000/v1)
  QWEN_MODEL       (optional)  Model name (default: qwen3.6-35b)
"""

import sys

if __name__ == "__main__" and any(arg in {"-h", "--help", "help"} for arg in sys.argv[1:]):
    print(__doc__)
    print("Use via: python3 skills/deepppt/scripts/image_gen.py \"prompt\" --backend qwen36-svg")
    raise SystemExit(0)

import os
import re
import time
import io
import base64

import requests
from PIL import Image as PILImage

from image_backends.backend_common import (
    MAX_RETRIES,
    is_rate_limit_error,
    normalize_image_size,
    resolve_output_path,
    retry_delay,
    save_image_bytes,
)


DEFAULT_CHAT_URL = "http://10.226.72.52:8000/v1"
DEFAULT_MODEL = "qwen3.6-35b"

# Aspect ratio → SVG viewBox size mapping
ASPECT_RATIO_SIZE_MAP = {
    "1:1":  (800, 800),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "3:2":  (960, 640),
    "2:3":  (640, 960),
    "4:3":  (960, 720),
    "3:4":  (720, 960),
    "4:5":  (800, 1000),
    "5:4":  (1000, 800),
    "21:9": (1680, 720),
}


def _build_svg_prompt(user_prompt: str, width: int, height: int) -> str:
    """Build a prompt that instructs the LLM to output pure SVG."""
    return (
        f"用 SVG 画出以下内容：{user_prompt}\n\n"
        f"画布尺寸：{width}x{height}\n"
        "要求：\n"
        "- 使用现代、干净的设计风格，适合 PPT 演示\n"
        "- 背景使用浅色或白色\n"
        "- 合适的颜色搭配、圆角、阴影效果\n"
        "- 添加清晰的标注文字\n"
        "- 只输出纯 SVG 代码，不要任何解释，不要 markdown 代码块标记\n"
        "- 所有文字使用中文字体"
    )


def _extract_svg(text: str) -> str | None:
    """Extract <svg>...</svg> block from LLM response."""
    m = re.search(
        r"```(?:svg|xml|html)\s*\n(.*?)\n\s*```", text, re.DOTALL | re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"(<svg[\s\S]*?</svg>)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _svg_to_png_bytes(svg_code: str, width: int, height: int) -> bytes:
    """Convert SVG code to PNG bytes using svglib + reportlab."""
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM

    drawing = svg2rlg(io.BytesIO(svg_code.encode("utf-8")))
    if drawing is None:
        raise RuntimeError("svglib could not parse the SVG code")

    # Scale to fit target size
    scale_x = width / drawing.width if drawing.width else 1
    scale_y = height / drawing.height if drawing.height else 1
    scale = min(scale_x, scale_y)
    drawing.width = drawing.width * scale
    drawing.height = drawing.height * scale
    drawing.scale(scale, scale)

    png_bytes = renderPM.drawToString(drawing, fmt="PNG", dpi=96)
    if not png_bytes:
        raise RuntimeError("renderPM could not rasterize the SVG")
    return png_bytes


def _generate_image(api_key: str, prompt: str,
                    aspect_ratio: str = "1:1", image_size: str = "1K",
                    output_dir: str = None, filename: str = None,
                    model: str = DEFAULT_MODEL, chat_base_url: str = DEFAULT_CHAT_URL) -> str:
    """
    Generate an image by:
    1. Asking the vLLM chat model to produce SVG code
    2. Converting the SVG to PNG via svglib + renderPM

    Returns:
        Path of the saved PNG file
    """
    width, height = ASPECT_RATIO_SIZE_MAP.get(aspect_ratio, (800, 800))

    # Scale by image_size factor
    size_multiplier = {"512px": 0.5, "1K": 1.0, "2K": 2.0, "4K": 4.0}.get(
        normalize_image_size(image_size), 1.0
    )
    width = int(width * size_multiplier)
    height = int(height * size_multiplier)

    svg_prompt = _build_svg_prompt(prompt, width, height)
    chat_url = f"{chat_base_url.rstrip('/')}/chat/completions"

    print(f"[Qwen3.6 SVG → PNG]")
    print(f"  Prompt:       {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    print(f"  Aspect ratio: {aspect_ratio}  Size: {image_size}  Output: {width}x{height}")
    print()

    # ── Step 1: Generate SVG via chat ──
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的 SVG 绘图专家。只输出纯 SVG 代码，不要任何解释或 markdown 标记。"
            },
            {"role": "user", "content": svg_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
        "stream": False,
    }

    start_time = time.time()
    print(f"  [1/2] Generating SVG via {model}...", end="", flush=True)

    resp = requests.post(
        chat_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    svg_elapsed = time.time() - start_time
    print(f" done ({svg_elapsed:.1f}s, {len(content)} chars)")

    # ── Step 2: Extract SVG ──
    svg_code = _extract_svg(content)
    if not svg_code:
        if "<svg" in content.lower() and "</svg>" not in content.lower():
            raise RuntimeError(
                "SVG output was truncated (hit token limit). "
                "The generated image is too complex — try a simpler prompt."
            )
        raise RuntimeError(
            "No valid <svg> tag found in LLM response. "
            f"Raw response (first 500 chars): {content[:500]}"
        )

    # ── Step 3: Convert SVG → PNG ──
    print(f"  [2/2] Converting SVG → PNG ({width}x{height})...", end="", flush=True)

    try:
        png_bytes = _svg_to_png_bytes(svg_code, width, height)
    except Exception as exc:
        # If svglib fails, save the SVG as-is and warn
        svg_path = resolve_output_path(prompt, output_dir, filename, ".svg")
        os.makedirs(os.path.dirname(svg_path) or ".", exist_ok=True)
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_code)
        raise RuntimeError(
            f"SVG→PNG conversion failed ({exc}). SVG saved to: {svg_path}"
        ) from exc

    convert_elapsed = time.time() - start_time - svg_elapsed
    print(f" done ({convert_elapsed:.1f}s, {len(png_bytes)} bytes)")

    # ── Step 4: Save PNG ──
    path = resolve_output_path(prompt, output_dir, filename, ".png")
    return save_image_bytes(png_bytes, path)


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Public Entry Point  (same signature as all backends)           ║
# ╚══════════════════════════════════════════════════════════════════╝

def generate(prompt: str,
             aspect_ratio: str = "1:1", image_size: str = "1K",
             output_dir: str = None, filename: str = None,
             model: str = None, max_retries: int = MAX_RETRIES) -> str:
    """
    Generate an image via LLM → SVG → PNG pipeline with retries.

    Reads credentials from environment:
      QWEN_API_KEY
      QWEN_BASE_URL (optional)
      QWEN_MODEL    (optional)

    Args:
        prompt: Image description
        aspect_ratio: Target aspect ratio
        image_size: Output size tier (512px, 1K, 2K, 4K)
        output_dir: Output directory
        filename: Output filename (without extension)
        model: Model name override
        max_retries: Maximum number of retries

    Returns:
        Path of the saved PNG file
    """
    api_key = os.environ.get("QWEN_API_KEY", "")
    if not api_key:
        raise ValueError(
            "No API key found. Set QWEN_API_KEY in the current environment or a .env file."
        )

    chat_base_url = os.environ.get("QWEN_BASE_URL") or DEFAULT_CHAT_URL
    chat_base_url = chat_base_url.replace("https://", "http://")
    resolved_model = model or os.environ.get("QWEN_MODEL") or DEFAULT_MODEL

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return _generate_image(
                api_key=api_key,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                output_dir=output_dir,
                filename=filename,
                model=resolved_model,
                chat_base_url=chat_base_url,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            limited = is_rate_limit_error(exc)
            delay = retry_delay(attempt, rate_limited=limited)
            label = "Rate limit hit" if limited else f"Error: {exc}"
            print(f"\n  [WARN] {label}. Retrying in {delay}s...")
            time.sleep(delay)

    raise RuntimeError(f"Failed after {max_retries + 1} attempts. Last error: {last_error}")
