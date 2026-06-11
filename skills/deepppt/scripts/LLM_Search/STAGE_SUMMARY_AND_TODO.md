# LLM_Search — 阶段性总结 & 后续 TODO

> 2026-06-08 | 当前版本 2.0

## 一、已有成果

### 1.1 模块清单

```
LLM_Search/
├── config.py         # 全局配置 (模型路径、维度512、评分权重)
├── embedder.py       # 双引擎嵌入 (ONNX 主 + ST 备)
├── store.py          # FAISS + NumPy 双引擎向量存储
├── indexer.py        # 多源索引构建 (kb_ai.db / JSON / PPTX)
├── search.py         # 语义搜索 + 混合评分 (向量0.7+关键词0.3)
├── cli.py            # 统一 CLI (build / search / stats / info)
├── model/            # ONNX 模型 + kb_ai.db (263 slides, 258 embeddings)
├── vector_store/     # FAISS 索引持久化
├── pic_to_vec/       # 图片向量库实验室 (67 张 LightAI 图片)
└── tests/            # 冒烟测试 (5/5 通过)
```

### 1.2 已验证的能力

| 能力 | 状态 | 数据源 |
|------|------|--------|
| PPT 页面语义搜索 | ✅ | kb_ai.db (263条) / kb_index.json / PPTX |
| 图片语义搜索 | ✅ | image_extract_index.json (67条) |
| 零依赖自举 (直接读 PPTX) | ✅ | knowledge_base/*.pptx |
| CLI 一键构建+搜索 | ✅ | build / search / stats / info |
| FAISS 精确搜索 | ✅ | IndexFlatIP, <0.1s |
| ONNX 轻量推理 | ✅ | bge-small-zh-v1.5, 512维, ~40MB |
| 混合评分 | ✅ | 向量0.7 + 关键词0.3 |

## 二、当前向量生成策略

### 2.1 现状：一页 PPT = 一个向量

```
输入: PPT 页面文本 (文件名 + 关键词 + 所有 <a:t> 标签内容)
  ↓ Tokenize (BGE tokenizer, 截断到 512 tokens)
  ↓ ONNX 推理 (4层 BERT, 512维输出)
  ↓ [CLS] 池化 + L2 归一化
输出: 1 个 512 维 float32 向量
```

### 2.2 文本构造方式

```python
# indexer.py _extract_ppt_direct() / _extract_ppt_texts()
embed_text = f"{title} {kw_str} {slide_text[:800]}"  # 截断到 1000 字符

# indexer.py _extract_image_texts()
embed_text = f"{desc} {tag_str} {filename} {context[:500]}"
```

### 2.3 核心局限

| 局限 | 影响 |
|------|------|
| **单向量表示整页** | 一页 PPT 通常包含多个语义块 (标题、图表、要点)，压缩成一个向量会丢失细粒度信息 |
| **512 token 截断** | 长页面后半部分直接被丢弃 |
| **纯文本，无视觉信息** | 架构图的拓扑关系、KPI 的数据趋势、色彩的视觉层次 — 全部不可搜索 |
| **无元数据过滤** | 即使知道要搜"架构图"，也必须全局搜索所有 263 页再人工筛选 |
| **全量重建** | 新增 1 个 PPTX 也需要重新编码全部文本 |

## 三、后续优化方向

### 3.1 P0 — 解决"一页=一向量"的精度问题

**方案 A: Late Chunking (推荐)**

```
一页 PPT → 按文本块拆分 (标题/段落/表格) → 多个独立向量
搜索时: 每个 chunk 独立匹配 → 聚合到 slide 级 → 返回最佳 slide
```

优势：无需改模型，改动量小，精度提升显著。

**方案 B: 分层向量**

```
Slide 级向量 (粗召回) + Chunk 级向量 (精排)
粗召 TOP-50 → Chunk 精排 → TOP-5
```

### 3.2 P0 — 图片向量化集成到主流程

目前 `pic_to_vec` 是独立实验室。应该：

- `cli.py build --type img --json <path>` 一键构建图片向量库
- 支持 `--from-pptx-images` 直接提取 PPTX 中的图片
- 图片搜索结果返回 `archive_path`，可一键定位

### 3.3 P1 — 元数据感知搜索

kb_ai.db 中有 `page_type` (kpi/architecture/chart/card...) 和 `topic` (AI/金融/能源...)。

```
"金融行业的架构图" 
  → 解析为: topic=金融, page_type=architecture
  → SQL 预过滤 → 向量搜索 → 返回
```

### 3.4 P1 — 增量索引

```python
# 当前: 每次 build --force, 全量重编
# 目标: 只编码新增/修改的 PPTX
indexer.update(kb_root)  # 自动检测变更, 增量添加
```

### 3.5 P1 — 多模态 (Text → Image, Image → Image)

```
"Atlas 800I A2 组网图" → 搜索图片库 → 返回架构图
"这张图" + 上传图片 → CLIP/BGE-V 编码 → 图片库中找相似图
```

可选模型: `BAAI/bge-visualized` (中英文图文), `clip-ViT-B-32`

### 3.6 P2 — 搜索质量提升

| 方向 | 具体 |
|------|------|
| Query 扩展 | 用 LLM 把短查询扩展为多个变体, 多路召回合并 |
| Re-rank | 粗召回后用更强的 Cross-Encoder 精排 |
| 负反馈学习 | 记录"选了/跳过了"哪些结果, 调整后续排序 |
| 领域微调 | 用华为 PPT 数据 fine-tune BGE 模型 |

### 3.7 P2 — 性能扩展

当前 FAISS IndexFlatIP 是 O(N) 精确搜索。数据量 > 10K 后考虑：

```
IndexFlatIP (精确) → IndexIVFFlat (聚类加速) → IndexHNSW (图索引)
```

## 四、TODO 优先级队列

```
┌──────────────────────────────────────────────────────────┐
│ 现在 (已完成)                                              │
├──────────────────────────────────────────────────────────┤
│ ✅ ONNX 嵌入引擎 + FAISS 存储 + 多数据源索引              │
│ ✅ CLI build/search/stats + kb_ai.db 兼容                 │
│ ✅ pic_to_vec 图片向量库 POC                              │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│ 下一步 (建议优先)                                          │
├──────────────────────────────────────────────────────────┤
│ ☐ Late Chunking: 一页多向量, 提升搜索精度                 │
│ ☐ 图片向量集成到 cli.py: build/search --mode image        │
│ ☐ 元数据预过滤: page_type + topic 加速                    │
│ ☐ 增量索引: 只重建变更的 PPTX            
  ☐    评分机制过于简单│
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│ 中期                                                      │
├──────────────────────────────────────────────────────────┤
│ ☐ 多模态: 以图搜图 / 文搜图 (CLIP/BGE-V)                  │
│ ☐ Cross-Encoder Re-rank 提升 Top-3 精度                   │
│ ☐ 搜索反馈闭环 (usage_log 投入使用)                       │
│ ☐ LLM Query 扩展: 短查询 → 多路召回                     │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│ 远期                                                      │
├──────────────────────────────────────────────────────────┤
│ ☐ ANN 索引: IVF / HNSW / DiskANN (> 10K 向量时)          │
│ ☐ 领域模型微调: BGE 用华为 PPT 数据 fine-tune             │
│ ☐ 可视化搜索界面                                          │
│ ☐ 分布式索引 (多项目共享向量库)                            │
└──────────────────────────────────────────────────────────┘
```

## 五、文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `config.py` | ~80 | 路径、模型、维度、权重 |
| `embedder.py` | ~370 | ONNX + ST 双引擎 |
| `store.py` | ~420 | FAISS + NumPy 双引擎 |
| `indexer.py` | ~500 | 3 数据源文本提取 + 向量构建 |
| `search.py` | ~300 | 语义搜索 + 混合评分 |
| `cli.py` | ~190 | 命令行入口 |
| `tests/` | ~500 | 冒烟 + 集成测试 |
