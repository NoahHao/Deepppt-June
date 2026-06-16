#!/usr/bin/env python3
"""
knowledge_base 定时文件扫描器
==============================
每1小时扫描 knowledge_base 目录，检测新增/变更的 PPTX 文件。
当发现新文件时，自动触发全量流水线（run_pipelines.py）。

使用方式：
  python file_watcher.py --once          # 单次扫描（检测到变更则触发流水线）
  python file_watcher.py --daemon        # 持续运行，每小时扫描一次
  python file_watcher.py --interval 600  # 自定义扫描间隔（秒）
  python file_watcher.py --dry-run       # 仅检测，不触发流水线
  python file_watcher.py --status        # 查看当前状态
  python file_watcher.py --reset         # 重置状态（下次扫描全部视为新文件）

状态文件 (watch_state.json):
  {
    "kb_root": "...",
    "last_scan": "ISO时间",
    "total_files": N,
    "known_files": {
      "rel/path/file.pptx": {
        "md5": "哈希值",
        "first_seen": "ISO时间",
        "size": 字节数
      }
    }
  }
"""

import sys
import os
import json
import time
import hashlib
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, List, Optional, Tuple

# ── 配置 ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "watch_state.json"
PIPELINE_SCRIPT = SCRIPT_DIR / "run_pipelines.py"
PROJECT_ROOT = SCRIPT_DIR.parent  # deepppt-main/
DEFAULT_INTERVAL = 3600  # 默认1小时

# ── 日志 ──────────────────────────────────────────
LOG_FILE = SCRIPT_DIR / "watcher.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("watcher")


# ══════════════════════════════════════════════════════════
# 文件哈希
# ══════════════════════════════════════════════════════════

def compute_md5(filepath: Path) -> str:
    """计算文件的 MD5 哈希（用于检测文件变更）"""
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


# ══════════════════════════════════════════════════════════
# 扫描与状态管理
# ══════════════════════════════════════════════════════════

def scan_knowledge_base(kb_root: Path) -> Dict[str, dict]:
    """扫描 knowledge_base 下所有 PPTX 文件，返回 {相对路径: 文件信息}"""
    files = {}
    for pptx_path in sorted(kb_root.rglob("*.pptx")):
        # 跳过临时文件（Office 锁文件）
        if pptx_path.name.startswith("~$"):
            continue

        rel_path = str(pptx_path.relative_to(kb_root))
        files[rel_path] = {
            "size": pptx_path.stat().st_size,
            "modified": datetime.fromtimestamp(
                pptx_path.stat().st_mtime
            ).isoformat(),
        }
    return files


def load_state() -> dict:
    """加载状态文件"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "kb_root": str(SCRIPT_DIR),
        "created": datetime.now().isoformat(),
        "known_files": {},
    }


def save_state(state: dict):
    """保存状态文件"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def detect_changes(kb_root: Path) -> Tuple[List[str], List[str], List[str]]:
    """扫描并检测变更。

    Returns:
        (new_files, modified_files, deleted_files): 三组相对路径列表
    """
    state = load_state()
    known = state.get("known_files", {})
    current = scan_knowledge_base(kb_root)

    current_paths = set(current.keys())
    known_paths = set(known.keys())

    new_files = sorted(current_paths - known_paths)
    deleted_files = sorted(known_paths - current_paths)

    # 检测已修改的文件（MD5 变更）
    modified_files = []
    for rel_path in sorted(current_paths & known_paths):
        filepath = kb_root / rel_path
        old_md5 = known[rel_path].get("md5", "")
        current_md5 = compute_md5(filepath)
        if current_md5 != old_md5:
            modified_files.append(rel_path)
            logger.info(f"  文件已变更: {rel_path} (MD5: {old_md5[:8]}... → {current_md5[:8]}...)")

    return new_files, modified_files, deleted_files


def update_state(kb_root: Path, new_files: List[str], modified_files: List[str],
                 deleted_files: List[str]):
    """更新状态文件，记录本次扫描结果"""
    state = load_state()
    known = state.get("known_files", {})

    # 移除已删除的文件
    for rel_path in deleted_files:
        known.pop(rel_path, None)

    # 添加新文件和更新已修改文件的哈希
    changed = set(new_files) | set(modified_files)
    now = datetime.now().isoformat()

    for rel_path in changed:
        filepath = kb_root / rel_path
        if filepath.exists():
            existing = known.get(rel_path, {})
            known[rel_path] = {
                "md5": compute_md5(filepath),
                "first_seen": existing.get("first_seen", now),
                "size": filepath.stat().st_size,
                "last_checked": now,
            }
            logger.info(
                f"  已记录: {rel_path} "
                f"({'新增' if rel_path in new_files else '变更'})"
            )

    state["known_files"] = known
    state["last_scan"] = now
    state["total_files"] = len(known)

    save_state(state)
    logger.info(f"  状态已保存: {len(known)} 个已知文件")


# ══════════════════════════════════════════════════════════
# 流水线触发
# ══════════════════════════════════════════════════════════

def trigger_pipeline(kb_root: Path, new_files: List[str],
                     modified_files: List[str]) -> bool:
    """触发 run_pipelines.py 全量流水线。

    Returns:
        bool: 是否全部成功
    """
    logger.info("▶ 触发全量流水线...")

    python_exe = sys.executable

    # 调用 run_pipelines.py
    # 注意：pipeline 会对整个 knowledge_base 做全量重建（最安全的方式）
    cmd = [
        python_exe,
        str(PIPELINE_SCRIPT),
        "--kb-root", str(kb_root),
    ]

    logger.info(f"  命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(kb_root),
            capture_output=False,  # 实时输出到 stdout
            text=True,
            timeout=3600,  # 最长1小时超时
        )

        if result.returncode == 0:
            logger.info("✓ 流水线执行成功")
            return True
        else:
            logger.error(f"✗ 流水线执行失败 (退出码: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        logger.error("✗ 流水线执行超时 (1小时)")
        return False
    except FileNotFoundError:
        logger.error(f"✗ 找不到 Python 解释器: {python_exe}")
        return False
    except Exception as e:
        logger.error(f"✗ 流水线执行异常: {e}")
        return False


# ══════════════════════════════════════════════════════════
# 单次扫描
# ══════════════════════════════════════════════════════════

def scan_once(kb_root: Path, dry_run: bool = False) -> Dict:
    """执行单次扫描。

    Returns:
        {"new": [...], "modified": [...], "deleted": [...], "triggered": bool, "success": bool}
    """
    logger.info("=" * 60)
    logger.info(f"📁 扫描 knowledge_base: {kb_root}")
    logger.info(f"   时间: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # 1. 检测变更
    new_files, modified_files, deleted_files = detect_changes(kb_root)

    # 2. 打印变更摘要
    current = scan_knowledge_base(kb_root)
    logger.info(f"当前文件: {len(current)} 个 PPTX")
    logger.info(f"新增: {len(new_files)} | 修改: {len(modified_files)} "
                f"| 删除: {len(deleted_files)}")

    for f in new_files:
        logger.info(f"  + [新增] {f}")
    for f in modified_files:
        logger.info(f"  ~ [修改] {f}")
    for f in deleted_files:
        logger.info(f"  - [删除] {f}")

    has_changes = bool(new_files or modified_files or deleted_files)

    # 3. 更新状态
    if has_changes:
        update_state(kb_root, new_files, modified_files, deleted_files)
    else:
        logger.info("  无变更")
        # 即使无变更也更新扫描时间
        state = load_state()
        state["last_scan"] = datetime.now().isoformat()
        save_state(state)

    # 4. 触发流水线（仅当有新文件或修改时）
    triggered = False
    success = True
    if has_changes and not dry_run and (new_files or modified_files):
        logger.info(f"\n🔔 检测到 {len(new_files)} 个新文件 + "
                    f"{len(modified_files)} 个修改文件")
        triggered = True
        success = trigger_pipeline(kb_root, new_files, modified_files)
    elif has_changes and dry_run:
        logger.info("\n🔍 [dry-run 模式] 跳过流水线触发")
    elif not has_changes:
        logger.info("\n✓ 无新增或修改，跳过流水线")

    return {
        "new": new_files,
        "modified": modified_files,
        "deleted": deleted_files,
        "triggered": triggered,
        "success": success,
    }


# ══════════════════════════════════════════════════════════
# 守护进程模式
# ══════════════════════════════════════════════════════════

def run_daemon(kb_root: Path, interval: int = DEFAULT_INTERVAL,
               dry_run: bool = False):
    """持续运行，按 interval 秒间隔扫描。"""
    logger.info(f"🔄 守护进程模式启动 — 间隔: {interval}s ({interval/60:.0f}分钟)")
    logger.info(f"   KB根目录: {kb_root}")
    logger.info(f"   Ctrl+C 停止")
    logger.info("=" * 60)

    scan_count = 0

    try:
        while True:
            scan_count += 1
            logger.info(f"\n{'─' * 40}")
            logger.info(f"第 {scan_count} 轮扫描 — {datetime.now().isoformat()}")
            logger.info(f"{'─' * 40}")

            scan_once(kb_root, dry_run=dry_run)

            # 等待下一次扫描
            next_scan = datetime.now().timestamp() + interval
            logger.info(
                f"\n⏰ 下次扫描: "
                f"{datetime.fromtimestamp(next_scan).strftime('%Y-%m-%d %H:%M:%S')} "
                f"({interval/60:.0f}分钟后)"
            )
            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("\n\n🛑 守护进程已停止 (Ctrl+C)")


# ══════════════════════════════════════════════════════════
# 状态查看
# ══════════════════════════════════════════════════════════

def show_status(kb_root: Path):
    """显示当前扫描状态"""
    state = load_state()

    print("\n" + "=" * 60)
    print("  knowledge_base 扫描器状态")
    print("=" * 60)
    print(f"  KB根目录:    {state.get('kb_root', 'N/A')}")
    print(f"  创建时间:    {state.get('created', 'N/A')}")
    print(f"  最后扫描:    {state.get('last_scan', '从未扫描')}")
    print(f"  已知文件:    {state.get('total_files', 0)} 个")

    known = state.get("known_files", {})
    if known:
        print(f"\n  已知文件明细:")
        for rel_path, info in sorted(known.items()):
            size_kb = info.get("size", 0) / 1024
            print(f"    [{size_kb:.0f}KB] {rel_path}")
            print(f"      首次发现: {info.get('first_seen', '?')}")
            print(f"      MD5: {info.get('md5', '?')[:16]}...")

    # 检查是否有文件已变更
    new, mod, deleted = detect_changes(kb_root)
    if new or mod or deleted:
        print(f"\n  ⚠ 待处理变更:")
        for f in new:
            print(f"    + [新增] {f}")
        for f in mod:
            print(f"    ~ [修改] {f}")
        for f in deleted:
            print(f"    - [删除] {f}")
    else:
        print(f"\n  ✓ 所有文件状态一致，无待处理变更")

    print()


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="knowledge_base 定时文件扫描器 — 检测新文件并触发全量流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python file_watcher.py --once              # 单次扫描
  python file_watcher.py --daemon            # 持续运行 (默认每小时)
  python file_watcher.py --daemon --interval 600  # 每10分钟扫描
  python file_watcher.py --dry-run           # 仅检测不触发
  python file_watcher.py --status            # 查看状态
  python file_watcher.py --reset             # 重置状态
        """,
    )

    parser.add_argument(
        "--kb-root",
        default=str(SCRIPT_DIR),
        help=f"knowledge_base 目录 (默认: {SCRIPT_DIR})",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="单次扫描后退出",
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="守护进程模式，持续运行",
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL,
        help=f"扫描间隔（秒），默认 {DEFAULT_INTERVAL} (1小时)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅检测变更，不触发流水线",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="显示当前扫描状态",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="重置状态文件（下次扫描全部视为新文件）",
    )

    args = parser.parse_args()
    kb_root = Path(args.kb_root)

    if not kb_root.exists():
        logger.error(f"目录不存在: {kb_root}")
        sys.exit(1)

    # --reset: 删除状态文件
    if args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            logger.info(f"状态文件已删除: {STATE_FILE}")
            logger.info("下次扫描会将所有文件视为新文件")
        else:
            logger.info("状态文件不存在，无需重置")
        return

    # --status: 查看状态
    if args.status:
        show_status(kb_root)
        return

    # 默认行为和 --once
    if args.daemon:
        run_daemon(kb_root, args.interval, dry_run=args.dry_run)
    else:
        result = scan_once(kb_root, dry_run=args.dry_run)

        # 输出最终摘要
        print(f"\n📊 扫描摘要:")
        print(f"  新增: {len(result['new'])}")
        print(f"  修改: {len(result['modified'])}")
        print(f"  删除: {len(result['deleted'])}")
        print(f"  触发流水线: {'是' if result['triggered'] else '否'}")
        if result["triggered"]:
            print(f"  流水线结果: {'成功' if result['success'] else '失败'}")

        sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
