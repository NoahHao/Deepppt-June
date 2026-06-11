#!/usr/bin/env python3
"""
LLM_Search 冒烟测试（无依赖）
==============================
仅验证代码结构和逻辑正确性，无需 numpy / faiss / sentence-transformers。

在完整依赖安装后运行 test_integration.py 进行完整测试。
"""

import sys
import json
import tempfile
from pathlib import Path

# 确保导入路径正确
# 确保能导入 LLM_Search 包
# 当前文件: scripts/LLM_Search/tests/test_smoke.py
# 需要:    scripts/ 在 sys.path 中
SCRIPT_DIR = Path(__file__).resolve().parent  # .../LLM_Search/tests/
PACKAGE_DIR = SCRIPT_DIR.parent               # .../LLM_Search/
SCRIPTS_DIR = PACKAGE_DIR.parent              # .../scripts/
sys.path.insert(0, str(SCRIPTS_DIR))


def test_imports():
    """测试模块导入（无外部依赖）"""
    print("=" * 50)
    print("  测试 1: 模块导入")
    print("=" * 50)

    # config 模块不应依赖外部库
    from LLM_Search.config import (
        VECTOR_STORE_DIR,
        DEFAULT_MODEL_NAME,
        EMBEDDING_DIM,
        DEFAULT_TOP_K,
        find_existing_json_index,
        get_project_root,
    )

    print(f"  向量存储目录: {VECTOR_STORE_DIR}")
    print(f"  默认模型: {DEFAULT_MODEL_NAME}")
    print(f"  向量维度: {EMBEDDING_DIM}")
    print(f"  默认 top-k: {DEFAULT_TOP_K}")
    print(f"  项目根目录: {get_project_root()}")
    print("  ✅ 配置导入成功")

    # 检查目录存在
    assert VECTOR_STORE_DIR.exists(), f"向量存储目录不存在: {VECTOR_STORE_DIR}"
    print("  ✅ 向量存储目录已创建")

    # find_existing_json_index
    result = find_existing_json_index([Path("/nonexistent.json")])
    assert result is None
    print("  ✅ find_existing_json_index 正常")

    print()


def test_text_extraction_functions():
    """测试文本提取函数（使用 mock 数据）"""
    print("=" * 50)
    print("  测试 2: 文本提取逻辑")
    print("=" * 50)

    from LLM_Search.indexer import _extract_ppt_texts, _extract_image_texts

    # Mock kb_index.json
    mock_kb = {
        "kb_root": "/tmp/kb",
        "last_scan": "2026-01-01T00:00:00",
        "total_pptx": 2,
        "total_slides": 3,
        "files": {
            "金融/业务方案.pptx": {
                "title": "金融业务方案",
                "slide_count": 2,
                "path_abs": "/tmp/kb/金融/业务方案.pptx",
                "slides": {
                    "1": "第一页：项目背景与目标 本文档描述金融行业数字化转型方案",
                    "2": "第二页：技术架构设计 采用微服务架构，支持高并发",
                },
                "slide_keywords": {
                    "1": ["金融", "数字化", "转型"],
                    "2": ["微服务", "高并发", "架构"],
                },
            },
            "科技/AI方案.pptx": {
                "title": "AI智能方案",
                "slide_count": 1,
                "path_abs": "/tmp/kb/科技/AI方案.pptx",
                "slides": {
                    "1": "AI赋能企业智能化转型 大模型技术的企业级应用",
                },
                "slide_keywords": {
                    "1": ["AI", "大模型", "智能化"],
                },
            },
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(mock_kb, f, ensure_ascii=False)
        kb_path = f.name

    try:
        entries = _extract_ppt_texts(Path(kb_path))
        assert len(entries) == 3, f"期望 3 条，实际 {len(entries)}"
        print(f"  ✅ PPT 文本提取: {len(entries)} 条")

        # 验证第一条
        e0 = entries[0]
        assert e0["source_type"] == "ppt_slide"
        assert "金融/业务方案.pptx::1" == e0["source_id"]
        assert "金融业务方案" in e0["text"]
        assert "金融" in e0["metadata"]["keywords"]
        print(f"     ✓ {e0['source_id']}: {e0['display_text'][:40]}")

        # 验证第三条
        e2 = entries[2]
        assert "科技/AI方案.pptx::1" == e2["source_id"]
        assert "AI" in e2["text"]
        print(f"     ✓ {e2['source_id']}: {e2['display_text'][:40]}")

    finally:
        Path(kb_path).unlink(missing_ok=True)

    # Mock image_extract_index.json
    mock_img = {
        "index_type": "image_extract",
        "version": "1.0",
        "kb_root": "/tmp/images",
        "images": {
            "img_001": {
                "archive_name": "img_001.jpg",
                "archive_path": "/tmp/images/archive/img_001.jpg",
                "source_file": "/tmp/kb/test.pptx",
                "source_filename": "test.pptx",
                "description_hint": "系统架构图 | 微服务架构方案",
                "context_text": "展示了微服务架构的核心组件：API网关、服务注册中心、配置中心",
                "search_tags": ["架构", "微服务", "系统"],
                "format": "jpg",
                "width": 1920,
                "height": 1080,
                "slide_number": "2",
                "slide_title": "技术架构",
            },
            "img_002": {
                "archive_name": "img_002.png",
                "archive_path": "/tmp/images/archive/img_002.png",
                "source_file": "/tmp/kb/test.pptx",
                "source_filename": "test.pptx",
                "description_hint": "数据流程图",
                "context_text": "数据从采集到分析的全流程",
                "search_tags": ["数据", "流程"],
                "format": "png",
                "width": 800,
                "height": 600,
                "slide_number": "3",
                "slide_title": "数据流程",
            },
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(mock_img, f, ensure_ascii=False)
        img_path = f.name

    try:
        entries = _extract_image_texts(Path(img_path))
        assert len(entries) == 2, f"期望 2 条，实际 {len(entries)}"
        print(f"  ✅ 图片文本提取: {len(entries)} 条")

        e0 = entries[0]
        assert e0["source_type"] == "image"
        assert "架构" in e0["text"]
        assert e0["source_id"] == "img_001.jpg"
        print(f"     ✓ {e0['source_id']}: {e0['display_text'][:40]}")

    finally:
        Path(img_path).unlink(missing_ok=True)

    print()


def test_hybrid_scorer_logic():
    """测试混合评分器逻辑（纯 Python，无 numpy）"""
    print("=" * 50)
    print("  测试 3: 混合评分器逻辑")
    print("=" * 50)

    from LLM_Search.search import HybridScorer, _tokenize

    # 测试分词
    tokens = _tokenize("金融行业数字化转型方案 AI")
    assert "金融" in tokens
    assert "数字化" in tokens
    assert "ai" in tokens
    print(f"  ✅ 分词: {tokens}")

    # 中文拆分
    tokens = _tokenize("微服务架构设计")
    assert "微服务" in tokens
    assert "架构" in tokens
    print(f"  ✅ 中文拆分: {tokens}")

    # 测试混合评分
    scorer = HybridScorer(vector_weight=0.7, keyword_weight=0.3)

    # 完美匹配
    s = scorer.score(
        query="金融架构",
        vector_score=0.9,
        entry_text="金融架构设计方案",
        entry_metadata={"keywords": ["金融", "架构"]},
    )
    assert s > 0.85, f"期望 >0.85, 实际 {s:.4f}"
    print(f"  ✅ 完美匹配: {s:.4f}")

    # 部分匹配（云 vs 云原生 — 注意"云计算"分词后只有"云计算"和"计算"，
    # "云原生部署方案"中有"原生"但没有"云计算"，所以关键词匹配为0，
    # 只有向量分 0.5 * 0.7 = 0.35）
    s = scorer.score(
        query="云计算",
        vector_score=0.5,
        entry_text="云原生部署方案",
        entry_metadata={"keywords": ["云原生"]},
    )
    assert s > 0.34, f"期望 >0.34, 实际 {s:.4f}"
    print(f"  ✅ 部分匹配: {s:.4f}")

    # 不匹配
    s = scorer.score(
        query="量子计算",
        vector_score=0.2,
        entry_text="传统金融方案",
        entry_metadata={"keywords": ["金融"]},
    )
    assert s < 0.4, f"期望 <0.4, 实际 {s:.4f}"
    print(f"  ✅ 不匹配: {s:.4f}")

    print()


def test_config_paths():
    """测试配置路径的自洽性"""
    print("=" * 50)
    print("  测试 4: 配置路径")
    print("=" * 50)

    from LLM_Search.config import (
        PPT_FAISS_INDEX,
        PPT_META_JSON,
        IMG_FAISS_INDEX,
        IMG_META_JSON,
        KB_INDEX_PATHS,
        IMG_INDEX_PATHS,
        VECTOR_STORE_DIR,
    )

    paths = [
        ("PPT向量索引", PPT_FAISS_INDEX),
        ("PPT元数据", PPT_META_JSON),
        ("图片向量索引", IMG_FAISS_INDEX),
        ("图片元数据", IMG_META_JSON),
    ]

    for label, p in paths:
        assert p.parent == VECTOR_STORE_DIR, f"{label} 父目录应为 {VECTOR_STORE_DIR}"
        print(f"  ✅ {label}: {p.name}")

    assert all(isinstance(p, Path) for p in KB_INDEX_PATHS)
    assert all(isinstance(p, Path) for p in IMG_INDEX_PATHS)
    print("  ✅ 所有候选路径类型正确")

    print()


def test_run_pure_python():
    """验证核心逻辑模块（无需 numpy）"""
    print("=" * 50)
    print("  测试 5: 纯 Python 逻辑")
    print("=" * 50)

    # 测试 vector store 元数据逻辑（不加载 FAISS）
    import sys
    import importlib

    # 确保 NumpyEngine 可以创建（即使没有 numpy）
    # 这个测试只验证导入和基本类型

    # 验证 config 中的向量维度可以被正确读取
    from LLM_Search.config import EMBEDDING_DIM
    assert EMBEDDING_DIM == 384
    print(f"  ✅ 向量维度: {EMBEDDING_DIM}")

    # 验证 store.py 中的 _create_engine 逻辑
    # 当没有 FAISS 和 numpy 时，这会失败（符合预期）
    try:
        from LLM_Search.store import _create_engine
        print("  ✅ _create_engine 函数可导入")
    except ModuleNotFoundError as e:
        print(f"  ⚠️  store.py 不可导入（缺少依赖: {e}），这是正常的")
        print("     安装 numpy 后可正常运行")

    print()


def run_all():
    tests = [
        test_imports,
        test_text_extraction_functions,
        test_hybrid_scorer_logic,
        test_config_paths,
        test_run_pure_python,
    ]

    print("\n" + "=" * 60)
    print("  LLM_Search 冒烟测试（无外部依赖）")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败")
    if failed > 0:
        print(f"\n  💡 提示: 部分测试需要 numpy 才能通过。")
        print(f"     运行: pip install numpy")
        print(f"     然后: python tests/test_integration.py")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
