# LLM_Search — 基于向量嵌入的语义搜索引擎

> **版本**: 2.0 | **更新**: 2026-06-08 | **独立于** JSON 检索方案

## 一、这是什么

LLM_Search 是一个**完全独立**的向量语义搜索引擎，解决 JSON 索引文件过大导致上下文溢出的问题。

```
你的自然语言查询
      ↓
  ONNX 嵌入模型 (bge-small-zh-v1.5, 512维)
      ↓
  FAISS 向量检索 (余弦相似度)
      ↓
  混合评分 (向量 0.7 + 关键词 0.3)
      ↓
  Top-K 匹配结果 → pptx 页面 / 图片
```

**与现有系统的关系**：LLM_Search **不修改** PPT_Recall 和 image_extract 的任何代码，只读取它们生成的 JSON 索引或 kb_ai.db 数据库作为数据源。

## 二、核心能力

| 能力 | 说明 |
|------|------|
| **语义搜索 PPT 页面** | 自然语言查询，理解意图而非单纯关键词匹配 |
| **语义搜索图片** | 从 image_extract 索引中检索匹配的图片 |
| **多数据源支持** | JSON 索引 / kb_ai.db (sqlite-vec) / 未来新增 |
| **混合评分** | 向量相似度(70%) + 关键词增强(30%) |
| **双引擎** | FAISS (高性能) / NumPy (零依赖降级) |
| **轻量依赖** | ~40MB (onnxruntime + tokenizers)，无需 PyTorch |

## 三、环境准备

### 3.1 安装依赖

```bash
# 使用系统 Python 3.10 (推荐，兼容性最佳)
C:\Python310\python.exe -m pip install numpy onnxruntime tokenizers faiss-cpu

# 如网络慢，使用清华镜像
C:\Python310\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple numpy onnxruntime tokenizers faiss-cpu
```

依赖清单（约 40MB，对比 sentence-transformers 的 2GB+）：

```
numpy          # 向量运算
onnxruntime    # ONNX 模型推理 (~15MB)
tokenizers     # Rust 分词器 (~3MB)
faiss-cpu      # 向量索引（可选，自动降级 NumPy）
```

### 3.2 验证安装

```bash
cd skills/deepppt/scripts
C:\Python310\python.exe LLM_Search/cli.py info
```

预期输出：`Python: 3.10.x | NumPy: x.x | FAISS: x.x | ONNX: 512d`

## 四、快速开始

### 4.1 从 kb_ai.db 构建（最快，推荐）

如果已有 `kb_ai.db`（sqlite-vec 数据库），直接导入：

```bash
cd skills/deepppt/scripts
C:\Python310\python.exe LLM_Search/cli.py build --from-db
```

> 首次构建需编码所有文本为向量（~30秒/263条），之后增量极快。

### 4.2 从 JSON 索引构建

```bash
# 确保先运行过 PPT_Recall 和 image_extract 的 indexer
C:\Python310\python.exe LLM_Search/cli.py build --type ppt   # 仅 PPT
C:\Python310\python.exe LLM_Search/cli.py build --type img   # 仅图片
C:\Python310\python.exe LLM_Search/cli.py build              # 全部
```

### 4.3 语义搜索

```bash
# PPT 页面搜索（默认）
C:\Python310\python.exe LLM_Search/cli.py search "兴业银行真实客户案例"

# 图片搜索
C:\Python310\python.exe LLM_Search/cli.py search "架构拓扑图" --mode image

# 同时搜索
C:\Python310\python.exe LLM_Search/cli.py search "AI方案" --mode both

# 指定返回数量
C:\Python310\python.exe LLM_Search/cli.py search "金融大模型" --top-k 5
```

### 4.4 搜索结果示例

```
============================================================
  语义搜索: "华泰证券 DCS 虚拟化 金融核心"
============================================================

  [PPT 页面] 共 5 条结果

  #1 (向量: 0.760, 混合: 0.832)
     文件: 客户案例.pptx
     页码: 2
     内容: 华泰证券：选择稳定、高性能的 DCS 虚拟化承载金融核心...

  #2 (向量: 0.653, 混合: 0.591)
     文件: 客户案例.pptx
     页码: 3
     内容: 福州主中心 OceanStor Dorado 18500 双活方案...
```

### 4.5 查看统计

```bash
C:\Python310\python.exe LLM_Search/cli.py stats
```

## 五、编程接口

### 5.1 在 Python 中使用

```python
import sys
sys.path.insert(0, 'skills/deepppt/scripts')

from LLM_Search.search import SemanticSearcher

# 创建搜索引擎（自动加载 FAISS 索引 + ONNX 模型）
searcher = SemanticSearcher()

# 单次搜索
results = searcher.search("兴业银行真实客户案例", mode="ppt", top_k=5)

# 遍历结果
for item in results["ppt"]:
    meta = item["metadata"]
    print(f"[{item['score']:.3f}] {meta['file']} p{meta['slide_num']}: {item['display_text'][:80]}")
```

### 5.2 高级用法

```python
from LLM_Search.embedder import Embedder
from LLM_Search.store import VectorStore
import numpy as np

# 手动编码查询
embedder = Embedder()  # 自动选择 ONNX（优先）
query_vec = embedder.encode_single("语义搜索查询")

# 直接查询向量库
store = VectorStore("ppt_slides")
results = store.search(query_vec, k=10)
for score, meta in results:
    print(f"相似度: {score:.4f} | {meta['source_id']}")

# 批量编码
texts = ["文本1", "文本2", "文本3"]
vectors = embedder.encode(texts)
print(f"编码结果: {vectors.shape}")  # (3, 512)
```

### 5.3 从 kb_ai.db 读取已有数据

```python
import sqlite3, struct, numpy as np

db = 'skills/deepppt/scripts/LLM_Search/model/kb_ai.db'
c = sqlite3.connect(db)

# 读取所有 embedding
rows = c.execute("""
    SELECT s.source_name, s.slide_num, s.text_preview, e.embedding
    FROM slides s JOIN slide_embeddings e ON s.id = e.slide_id
""").fetchall()

embs = np.array([np.frombuffer(r[3], dtype=np.float32) for r in rows])

# 用已有 embedding 做相似度搜索
query = embs[0]
scores = np.dot(embs, query)  # 余弦相似度（已归一化）
top5 = np.argsort(-scores)[:5]
```

## 六、架构与文件组织

```
LLM_Search/                           # 主目录
├── __init__.py                       # 包入口，延迟导入
├── config.py                         # 全局配置（路径/模型/参数）
├── embedder.py                       # 嵌入模型：ONNX (主) + ST (备)
├── store.py                          # 向量存储：FAISS + NumPy 双引擎
├── indexer.py                        # 索引构建：JSON / kb_ai.db 多源
├── search.py                         # 语义搜索 + 混合评分
├── cli.py                            # 统一命令行 (build/search/stats/info)
├── run.bat                           # Windows 快速启动
├── requirements.txt                  # 依赖清单
├── model/                            # 模型目录
│   ├── kb_ai.db                     #   已有 sqlite-vec 数据库
│   ├── feedback.json                #   搜索反馈 & 超参调优
│   └── model/models--Qdrant--bge-small-zh-v1.5/  #   ONNX 模型
├── vector_store/                     # 向量索引持久化
│   ├── ppt_slides.faiss             #   FAISS 索引
│   └── ppt_slides_meta.json         #   元数据
└── tests/
    ├── test_smoke.py                 # 冒烟测试（无依赖，5/5 通过）
    └── test_integration.py           # 集成测试（需全部依赖）
```

## 七、技术参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 嵌入模型 | BAAI/bge-small-zh-v1.5 | 中文优化，ONNX 格式 |
| 向量维度 | 512 | float32，L2 归一化 |
| 最大文本长度 | 512 tokens | 中文约 256-512 字符 |
| 批处理大小 | 32 | 编码时的批量大小 |
| 向量权重 | 0.7 | 混合评分中向量相似度占比 |
| 关键词权重 | 0.3 | 混合评分中关键词匹配占比 |
| 默认 top-k | 10 | 单次搜索返回结果数 |

## 八、索引重建与更新

```bash
# 强制重建（清空旧索引，重新编码所有文本）
C:\Python310\python.exe LLM_Search/cli.py build --from-db --force

# 新增 PPTX 到 knowledge_base 后，先更新 JSON 索引，再重建向量：
cd scripts/PPT_Recall
C:\Python310\python.exe indexer.py ../knowledge_base  # 更新 kb_index.json
cd ..
C:\Python310\python.exe LLM_Search/cli.py build --type ppt --force
```

## 九、常见问题

### Q: onnxruntime 加载失败 (DLL load failed)

需安装 VC++ Redistributable：
```powershell
Invoke-WebRequest "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile vc_redist.exe
Start-Process vc_redist.exe -ArgumentList "/quiet","/norestart" -Verb RunAs -Wait
```

### Q: 提示 "未找到 kb_index.json"

LLM_Search 只是**读取** JSON 索引。需先用 PPT_Recall 的 indexer 生成：
```bash
cd scripts/PPT_Recall
python indexer.py ../../knowledge_base
```

### Q: FAISS 不可用，降级为 NumPy

FAISS 为可选依赖，NumPy 方案适用于 < 50K 向量规模。安装 FAISS 以获得更好性能：
```bash
pip install faiss-cpu
```

### Q: 如何清空并重建？

```bash
rm vector_store/ppt_slides.*   # 清空持久化文件
python LLM_Search/cli.py build --from-db --force
```

### Q: 编码速度

- 263 条文本编码：约 30 秒 (CPU: ONNX Runtime)
- 搜索延迟：< 0.1 秒 (FAISS IndexFlatIP)
- 内存占用：约 200MB (模型 + 索引)

## 十、与现有 PPT_Recall 的协同

```
┌─────────────────────────────────────────────────────┐
│                    PPT Master 检索体系                │
├─────────────────┬───────────────────────────────────┤
│  PPT_Recall     │  LLM_Search (NEW)                  │
│  ─────────      │  ─────────────                     │
│  JSON 索引      │  向量索引                           │
│  关键词匹配     │  语义理解                           │
│  Slide 级文本   │  512维嵌入                          │
│  轻量          │  ~200MB 内存                        │
│                 │                                    │
│  数据源 ────────┼──→ kb_index.json (读取)             │
│  数据源 ────────┼──→ kb_ai.db (读取)                  │
│                 │                                    │
│  互补关系：     │  PPT_Recall 适合精确关键词,          │
│                 │  LLM_Search 适合模糊语义            │
└─────────────────┴───────────────────────────────────┘
```

两个系统**独立运行，互不干扰**，可根据场景选择或组合使用。
