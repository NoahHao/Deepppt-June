#!/usr/bin/env python3
"""
使用本地 vLLM 模型 (qwen3.6-35b) 生成 SVG 图。
通过 chat completions API，让 LLM 输出纯 SVG 代码，然后保存为 .svg 文件。

用法:
    python svg_gen.py "一张现代数据中心架构图"
    python svg_gen.py "画一个微服务架构图" -o microservice.svg
    python svg_gen.py "复杂图表" --max-tokens 16384
"""
import argparse
import os
import re
import sys

import requests


def find_project_root() -> str:
    """从脚本所在目录向上搜索，找到 .env 所在的项目根目录。"""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.exists(os.path.join(current, ".env")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    raise FileNotFoundError("Could not find project root (no .env found in parent directories)")


def load_env(env_path: str):
    """从 .env 文件加载环境变量（不覆盖已存在的）。"""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def extract_svg(text: str) -> str | None:
    """从响应文本中提取 <svg ...> ... </svg> 块。"""
    m = re.search(r"```(?:svg|xml|html)\s*\n(.*?)\n\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(<svg[\s\S]*?</svg>)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def build_prompt(user_request: str) -> str:
    """根据用户输入构建 SVG 生成 prompt。"""
    return (
        f"用 SVG 画出以下内容：{user_request}\n\n"
        "要求：\n"
        "- 使用现代、干净的设计风格\n"
        "- 合适的颜色搭配和圆角\n"
        "- 添加标注文字\n"
        "- 只输出纯 SVG 代码，不要任何解释，不要 markdown 代码块标记"
    )


def main():
    parser = argparse.ArgumentParser(description="用本地 vLLM 模型生成 SVG 图")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="图片描述（例如: 一张现代数据中心架构图）")
    parser.add_argument("-o", "--output", default=None,
                        help="输出文件名（默认: 自动生成）")
    parser.add_argument("--max-tokens", type=int, default=8192,
                        help="最大生成 token 数（默认: 8192）")
    args = parser.parse_args()

    # ── 加载配置 ──
    project_root = find_project_root()
    env_file = os.path.join(project_root, ".env")
    load_env(env_file)

    # skill 根目录（skills/deepppt/）
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    API_KEY = os.environ.get("QWEN_API_KEY", "")
    raw_base = os.environ.get("QWEN_BASE_URL", "http://10.226.72.52:8000/v1").rstrip("/")
    API_BASE = raw_base.replace("https://", "http://")
    MODEL = os.environ.get("QWEN_MODEL", "qwen3.6-35b")

    if not API_KEY:
        print("ERROR: QWEN_API_KEY not found in .env")
        print(f"       Looked in: {env_file}")
        sys.exit(1)

    print(f"Project:  {project_root}")
    print(f"Endpoint: {API_BASE}/chat/completions")
    print(f"Model:    {MODEL}")
    print()

    # ── 确定 prompt ──
    if args.prompt:
        prompt = build_prompt(args.prompt)
    else:
        prompt = """用 SVG 画一个简单的架构图：
- 左侧一个用户图标（用 circle + path 画小人），背景色 #f0f4ff
- 箭头指向中间的"API Gateway"方框（蓝色圆角矩形）
- 再箭头指向右侧的"Qwen3.6"椭圆（绿色渐变）
- 底部加一行小字标注"本地 vLLM 部署"
- 只输出纯 SVG 代码，不要解释，不要 markdown 代码块标记"""

    # ── 调用 API ──
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个 SVG 绘图专家。只输出纯 SVG 代码，不要任何解释或 markdown 标记。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": args.max_tokens,
        "stream": False,
    }

    print(f"Prompt: {args.prompt or prompt[:80]}...")
    print("Calling vLLM...")

    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"\n[OK] Response received ({len(content)} chars)")
        print(f"Usage: {data.get('usage', {})}")

    except requests.exceptions.SSLError as e:
        print(f"\n[SSL ERROR] {e}")
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"\n[CONNECTION ERROR] {e}")
        print("Cannot reach the vLLM server. Is it running?")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)

    # ── 提取并保存 SVG ──
    svg_code = extract_svg(content)

    if not svg_code:
        if "<svg" in content.lower() and "</svg>" not in content.lower():
            print("\n[WARN] SVG output was truncated (hit max_tokens limit). Try --max-tokens 16384.")
        else:
            print("\n[WARN] No <svg> tag found in response. Raw output:")
        print("-" * 60)
        print(content[:2000])
        print("-" * 60)
        sys.exit(1)

    # 输出到 skills/deepppt/projects/image_output/
    output_dir = os.path.join(skill_root, "projects", "image_output")
    os.makedirs(output_dir, exist_ok=True)

    if args.output:
        output_path = os.path.join(output_dir, args.output)
    else:
        safe_name = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", (args.prompt or "architecture")[:40])
        output_path = os.path.join(output_dir, f"{safe_name}.svg")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_code)

    print(f"\n[SAVED] {output_path}")
    print(f"[SIZE]  {len(svg_code)} chars")


if __name__ == "__main__":
    main()
