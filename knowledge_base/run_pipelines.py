#!/usr/bin/env python3
"""
knowledge_base 文件变更 → 全量流水线编排
==========================================
当 file_watcher 检测到 knowledge_base 有新文件时，调用本脚本依次执行：

  Pipeline 1: PPTX → JSON 索引   (PPT_Recall/indexer.py)
  Pipeline 2: 文档图片提取        (image_extract/indexer.py)
  Pipeline 3: 向量库创建          (LLM_Search/indexer.py)

使用方式：
  python run_pipelines.py                  # 默认: knowledge_base 目录
  python run_pipelines.py --kb-root <dir>  # 指定 KB 根目录
  python run_pipelines.py --skip-ppt       # 跳过 Pipeline 1
  python run_pipelines.py --skip-img       # 跳过 Pipeline 2
  python run_pipelines.py --skip-vec       # 跳过 Pipeline 3
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# ── 确保 scripts 目录在 sys.path 中 ─────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # deepppt-main/
_SCRIPTS_DIR = _PROJECT_ROOT / "skills" / "deepppt" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ── 配置 logging ───────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent / "pipeline.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("pipeline")


# ══════════════════════════════════════════════════════════
# Pipeline 1: PPTX → JSON 索引
# ══════════════════════════════════════════════════════════

def run_pptx_to_json(kb_root: Path) -> Dict[str, Any]:
    """扫描 knowledge_base 下所有 PPTX，生成 kb_index.json"""
    try:
        from PPT_Recall.indexer import scan_and_index

        logger.info("=" * 60)
        logger.info("Pipeline 1: PPTX → JSON (PPT_Recall)")
        logger.info("=" * 60)

        output_path = _PROJECT_ROOT / "kb_index.json"
        start = time.time()

        result = scan_and_index(str(kb_root), str(output_path), verbose=True)

        elapsed = time.time() - start
        logger.info(
            f"✓ Pipeline 1 完成 ({elapsed:.1f}s): "
            f"{result['total_pptx']} 个 PPTX, {result['total_slides']} 页"
        )
        return {"status": "ok", "output": str(output_path), "result": result}

    except Exception as e:
        logger.error(f"✗ Pipeline 1 失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ══════════════════════════════════════════════════════════
# Pipeline 2: 文档图片提取
# ══════════════════════════════════════════════════════════

def run_image_extract(kb_root: Path) -> Dict[str, Any]:
    """扫描 knowledge_base 下所有 PPTX，提取图片并建立索引"""
    try:
        from image_extract.indexer import scan_and_index as img_scan

        logger.info("=" * 60)
        logger.info("Pipeline 2: 图片提取 (image_extract)")
        logger.info("=" * 60)

        output_path = _PROJECT_ROOT / "images" / "image_extract_index.json"
        start = time.time()

        result = img_scan(str(kb_root), str(output_path), verbose=True)

        elapsed = time.time() - start
        logger.info(
            f"✓ Pipeline 2 完成 ({elapsed:.1f}s): "
            f"{result['total_images']} 张图片"
        )
        return {"status": "ok", "output": str(output_path), "result": result}

    except Exception as e:
        logger.error(f"✗ Pipeline 2 失败: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ══════════════════════════════════════════════════════════
# Pipeline 3: 向量库创建
# ══════════════════════════════════════════════════════════

def run_vector_build(kb_root: Path) -> Dict[str, Any]:
    """通过 LLM_Search 自带环境构建 FAISS 向量库。

    LLM_Search 模块自带完整依赖（Python 3.10 + numpy/onnx/faiss），
    通过其 CLI 入口直接调用，无需额外安装依赖。"""
    import subprocess

    logger.info("=" * 60)
    logger.info("Pipeline 3: 向量库创建 (LLM_Search)")
    logger.info("=" * 60)

    # LLM_Search 固定使用 Python 3.10 环境（run.bat 中指定）
    PYTHON_310 = "C:/Python310/python.exe"
    LLM_SEARCH_DIR = _SCRIPTS_DIR / "LLM_Search"
    LLM_SEARCH_CLI = LLM_SEARCH_DIR / "cli.py"

    if not Path(PYTHON_310).exists():
        logger.error(f"LLM_Search 依赖的 Python 3.10 不存在: {PYTHON_310}")
        return {"status": "error", "error": f"Python 3.10 not found: {PYTHON_310}"}

    if not LLM_SEARCH_CLI.exists():
        logger.error(f"LLM_Search CLI 不存在: {LLM_SEARCH_CLI}")
        return {"status": "error", "error": f"CLI not found: {LLM_SEARCH_CLI}"}

    # 调用 LLM_Search 自带 CLI 构建全部向量索引
    # --from-pptx: 直接从 knowledge_base 下的 PPTX 读取（零依赖自举）
    # --force: 强制重建，确保数据最新
    cmd = [
        PYTHON_310,
        str(LLM_SEARCH_CLI),
        "build",
        "--from-pptx",
        "--force",
    ]

    logger.info(f"  命令: {' '.join(cmd)}")
    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(LLM_SEARCH_DIR),
            capture_output=True,
            text=True,
            timeout=1800,  # 30分钟超时（模型加载+向量生成）
        )

        # 输出 LLM_Search 的日志
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                logger.info(f"  [LLM_Search] {line}")

        elapsed = time.time() - start

        if result.returncode == 0:
            logger.info(f"✓ Pipeline 3 完成 ({elapsed:.1f}s)")
            return {"status": "ok", "summary": "vector index built"}
        else:
            err_msg = result.stderr.strip() if result.stderr else f"exit code {result.returncode}"
            logger.error(f"✗ Pipeline 3 失败 ({elapsed:.1f}s): {err_msg}")
            return {"status": "error", "error": err_msg}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        logger.error(f"✗ Pipeline 3 超时 ({elapsed:.1f}s)")
        return {"status": "error", "error": "timeout (30min)"}
    except Exception as e:
        logger.error(f"✗ Pipeline 3 异常: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ══════════════════════════════════════════════════════════
# Pipeline 4: 向量库去重
# ══════════════════════════════════════════════════════════

def run_dedup() -> Dict[str, Any]:
    """对向量库执行去重（余弦相似度 + 文件哈希）。"""
    import subprocess

    PYTHON_310 = "C:/Python310/python.exe"
    DEDUP_SCRIPT = _SCRIPTS_DIR / "LLM_Search" / "vector_store" / "dedup.py"

    if not Path(PYTHON_310).exists():
        logger.error(f"Python 3.10 不存在: {PYTHON_310}")
        return {"status": "error", "error": "Python 3.10 not found"}
    if not DEDUP_SCRIPT.exists():
        logger.error(f"去重脚本不存在: {DEDUP_SCRIPT}")
        return {"status": "error", "error": f"dedup.py not found: {DEDUP_SCRIPT}"}

    logger.info("=" * 60)
    logger.info("Pipeline 4: 向量去重 (dedup)")
    logger.info("=" * 60)

    cmd = [PYTHON_310, str(DEDUP_SCRIPT), "all"]
    logger.info(f"  命令: {' '.join(cmd)}")
    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(DEDUP_SCRIPT.parent),
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
        )

        # 输出去重日志
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    logger.info(f"  [dedup] {line}")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    logger.info(f"  [dedup] {line}")

        elapsed = time.time() - start

        if result.returncode == 0:
            logger.info(f"✓ Pipeline 4 完成 ({elapsed:.1f}s)")
            return {"status": "ok", "summary": "dedup completed"}
        else:
            logger.warning(f"△ Pipeline 4 非零退出 ({elapsed:.1f}s), 不影响主流程")
            return {"status": "warning", "error": f"exit code {result.returncode}"}

    except subprocess.TimeoutExpired:
        logger.warning("△ Pipeline 4 超时, 不影响主流程")
        return {"status": "warning", "error": "timeout"}
    except Exception as e:
        logger.warning(f"△ Pipeline 4 异常: {e}")
        return {"status": "warning", "error": str(e)}


# ══════════════════════════════════════════════════════════
# 统一编排入口
# ══════════════════════════════════════════════════════════

def run_all(kb_root: Path = None, skip_ppt=False, skip_img=False,
            skip_vec=False, skip_dedup=False):
    """依次执行四条流水线"""
    if kb_root is None:
        kb_root = Path(__file__).resolve().parent

    logger.info(f"🚀 流水线启动 — KB根目录: {kb_root}")
    logger.info(f"   时间: {datetime.now().isoformat()}")
    logger.info(f"   跳过: PPT={'是' if skip_ppt else '否'} "
                f"图片={'是' if skip_img else '否'} "
                f"向量={'是' if skip_vec else '否'} "
                f"去重={'是' if skip_dedup else '否'}")

    total_start = time.time()
    results = {}

    if not skip_ppt:
        results["pptx_to_json"] = run_pptx_to_json(kb_root)
    else:
        logger.info("⊙ Pipeline 1 (PPTX→JSON) 已跳过")

    if not skip_img:
        results["image_extract"] = run_image_extract(kb_root)
    else:
        logger.info("⊙ Pipeline 2 (图片提取) 已跳过")

    if not skip_vec:
        results["vector_build"] = run_vector_build(kb_root)
    else:
        logger.info("⊙ Pipeline 3 (向量库) 已跳过")

    # Pipeline 4: 去重 — 在向量库构建完成后自动触发
    if not skip_dedup:
        results["dedup"] = run_dedup()
    else:
        logger.info("⊙ Pipeline 4 (向量去重) 已跳过")

    total_elapsed = time.time() - total_start

    # ── 汇总 ────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("📊 流水线执行汇总")
    logger.info("=" * 60)
    all_ok = True
    for name, r in results.items():
        status = r.get("status", "unknown")
        if status == "ok":
            icon = "✓"
        elif status == "warning":
            icon = "△"
        else:
            icon = "✗"
            all_ok = False
        logger.info(f"  {icon} {name}: {status}")
    logger.info(f"  总耗时: {total_elapsed:.1f}s")
    logger.info(f"  结果: {'全部成功' if all_ok else '存在失败'}")
    logger.info("=" * 60)

    return results, all_ok


# ── CLI ───────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="knowledge_base 全量流水线编排",
    )
    parser.add_argument(
        "--kb-root",
        default=None,
        help="knowledge_base 目录路径 (默认: 脚本所在目录)",
    )
    parser.add_argument(
        "--skip-ppt", action="store_true",
        help="跳过 Pipeline 1: PPTX → JSON",
    )
    parser.add_argument(
        "--skip-img", action="store_true",
        help="跳过 Pipeline 2: 图片提取",
    )
    parser.add_argument(
        "--skip-vec", action="store_true",
        help="跳过 Pipeline 3: 向量库创建",
    )
    parser.add_argument(
        "--skip-dedup", action="store_true",
        help="跳过 Pipeline 4: 向量去重",
    )

    args = parser.parse_args()

    kb_root = Path(args.kb_root) if args.kb_root else None
    results, all_ok = run_all(
        kb_root=kb_root,
        skip_ppt=args.skip_ppt,
        skip_img=args.skip_img,
        skip_vec=args.skip_vec,
        skip_dedup=args.skip_dedup,
    )

    sys.exit(0 if all_ok else 1)
