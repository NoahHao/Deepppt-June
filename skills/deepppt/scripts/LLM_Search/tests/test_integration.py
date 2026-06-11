#!/usr/bin/env python3
"""
LLM_Search 集成测试
====================
测试核心功能：嵌入编码、向量存储、搜索。
独立于现有 JSON 系统，仅使用模拟数据。

运行：
  python tests/test_integration.py
"""

import sys
import tempfile
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_numpy_store():
    """测试 NumPy 向量存储（无需 FAISS）"""
    print("=" * 50)
    print("  测试 1: NumPy 向量存储")
    print("=" * 50)

    import numpy as np
    from LLM_Search.store import NumpyEngine

    dim = 128
    engine = NumpyEngine(dim)

    # 添加向量
    vecs = np.random.randn(10, dim).astype(np.float32)
    engine.add(vecs)
    assert engine.count == 10, f"期望 10，实际 {engine.count}"
    print(f"  ✅ 添加 {engine.count} 条向量")

    # 搜索
    query = vecs[0:1]  # 用第一条查询自己
    dists, indices = engine.search(query, k=3)

    assert dists.shape == (1, 3)
    assert indices[0][0] == 0  # 第 0 条应该最像自己
    print(f"  ✅ 搜索 top-3: indices={indices[0]}, scores={dists[0]}")

    # 保存和加载
    with tempfile.TemporaryDirectory() as tmp:
        save_path = Path(tmp) / "test_store"
        engine.save(save_path)

        loaded = NumpyEngine.load(save_path, dim)
        assert loaded.count == 10
        print(f"  ✅ 保存/加载: {loaded.count} 条")

    print()


def test_vector_store_with_metadata():
    """测试带元数据的 VectorStore"""
    print("=" * 50)
    print("  测试 2: VectorStore + 元数据")
    print("=" * 50)

    import numpy as np
    from LLM_Search.store import VectorStore

    dim = 128

    with tempfile.TemporaryDirectory() as tmp:
        store = VectorStore("test", dimension=dim, store_dir=Path(tmp))

        # 添加
        vecs = np.random.randn(5, dim).astype(np.float32)
        metas = [
            {
                "source_type": "ppt_slide",
                "source_id": f"file_{i}::slide_{i}",
                "text": f"这是第 {i} 页的内容",
                "display_text": f"页面 {i}",
                "metadata": {"title": f"标题{i}", "file": f"文件{i}.pptx"},
            }
            for i in range(5)
        ]
        store.add(vecs, metas)
        assert store.count == 5
        print(f"  ✅ 添加 {store.count} 条（引擎: {store.engine_type})")

        # 搜索
        query = vecs[0]
        results = store.search(query, k=3)
        assert len(results) == 3
        print(f"  ✅ 搜索 top-3: {len(results)} 条结果")
        for score, meta in results:
            print(f"     score={score:.4f} | {meta['source_id']}")

        # 统计
        stats = store.stats()
        assert stats["total"] == 5
        print(f"  ✅ 统计: {stats}")

        store.save()
        print(f"  ✅ 保存完成")

        # 重新加载
        store2 = VectorStore("test", dimension=dim, store_dir=Path(tmp))
        assert store2.count == 5
        print(f"  ✅ 重新加载: {store2.count} 条")

    print()


def test_hybrid_scorer():
    """测试混合评分器"""
    print("=" * 50)
    print("  测试 3: 混合评分器")
    print("=" * 50)

    from LLM_Search.search import HybridScorer

    scorer = HybridScorer(vector_weight=0.7, keyword_weight=0.3)

    # 完全匹配
    s = scorer.score(
        query="金融架构",
        vector_score=0.85,
        entry_text="金融架构设计方案",
        entry_metadata={"keywords": ["金融", "架构"]},
    )
    print(f"  完全匹配: {s:.4f}")
    assert s > 0.85

    # 部分匹配
    s = scorer.score(
        query="云计算部署",
        vector_score=0.6,
        entry_text="云原生架构与微服务部署方案",
        entry_metadata={"keywords": ["云原生", "微服务"]},
    )
    print(f"  部分匹配: {s:.4f}")
    assert s > 0.6

    # 不匹配
    s = scorer.score(
        query="量子计算",
        vector_score=0.3,
        entry_text="传统金融风控模型",
        entry_metadata={"keywords": ["金融", "风控"]},
    )
    print(f"  不匹配: {s:.4f}")
    assert s < 0.5

    print("  ✅ 混合评分正常\n")


def test_text_extraction():
    """测试 JSON 文本提取函数（mock 数据）"""
    print("=" * 50)
    print("  测试 4: 文本提取")
    print("=" * 50)

    import json, tempfile
    from LLM_Search.indexer import _extract_ppt_texts, _extract_image_texts

    # Mock kb_index.json
    mock_kb = {
        "kb_root": "/tmp/kb",
        "last_scan": "2026-01-01T00:00:00",
        "total_pptx": 1,
        "total_slides": 2,
        "files": {
            "test.pptx": {
                "title": "测试PPT",
                "slide_count": 2,
                "path_abs": "/tmp/kb/test.pptx",
                "slides": {
                    "1": "第一页内容：项目介绍",
                    "2": "第二页内容：技术方案",
                },
                "slide_keywords": {
                    "1": ["项目", "介绍"],
                    "2": ["技术", "方案"],
                },
            }
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(mock_kb, f)
        kb_path = f.name

    try:
        entries = _extract_ppt_texts(Path(kb_path))
        assert len(entries) == 2
        assert entries[0]["source_type"] == "ppt_slide"
        assert entries[0]["source_id"] == "test.pptx::1"
        assert "测试PPT" in entries[0]["text"]
        print(f"  ✅ PPT 文本提取: {len(entries)} 条")
        for e in entries:
            print(f"     {e['source_id']}: {e['display_text'][:50]}")
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
                "source_filename": "test.pptx",
                "description_hint": "架构图",
                "context_text": "系统架构设计方案",
                "search_tags": ["架构", "系统"],
                "archive_path": "/tmp/images/archive/img_001.jpg",
                "format": "jpg",
                "width": 1920,
                "height": 1080,
                "slide_number": "1",
                "slide_title": "架构概览",
            }
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(mock_img, f)
        img_path = f.name

    try:
        entries = _extract_image_texts(Path(img_path))
        assert len(entries) == 1
        assert "架构图" in entries[0]["text"]
        print(f"  ✅ 图片文本提取: {len(entries)} 条")
        print(f"     {entries[0]['source_id']}: {entries[0]['display_text'][:50]}")
    finally:
        Path(img_path).unlink(missing_ok=True)

    print()


def run_all():
    tests = [
        test_numpy_store,
        test_vector_store_with_metadata,
        test_hybrid_scorer,
        test_text_extraction,
    ]

    print("\n" + "=" * 60)
    print("  LLM_Search 集成测试")
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
            print(f"  ❌ {test.__name__} 失败: {e}\n")
            import traceback
            traceback.print_exc()

    print("=" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
