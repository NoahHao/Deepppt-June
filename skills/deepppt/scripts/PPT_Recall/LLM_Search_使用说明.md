# LLM_Search --- 基于向量嵌入的语义搜索引擎

> **版本**: 2.0 | **更新**: 2026-06-08 | **独立于** JSON 检索方案

## 一、这是什么

LLM_Search 是一个**完全独立**的向量语义搜索引擎，解决 JSON 索引文件过大导致上下文溢出问题。

**核心特点：真正的零依赖自举** --- 即使没有 kb_index.json、没有 kb_ai.db，也能直接读取 knowledge_base 下的 PPTX 文件，提取文本、编码向量、建立索引。

## 二、数据源（自动降级）

LLM_Search 会按以下优先级自动寻找数据源：

| 优先级 | 数据源 | 命令 | 依赖 |
|--------|--------|------|------|
| 1 | kb_ai.db (sqlite-vec) | --from-db | 已有 st-vec 数据库 |
| 2 | PPTX 文件直接提取 | --from-pptx | **无 → 全自举** |
| 3 | kb_index.json | (默认) | PPT_Recall indexer |
| 4 | 最终兜底：PPTX 直接读取 | (自动) | **无** |

> 即使用户什么都没准备，把 PPTX 扔到 knowledge_base/ 目录下就行。

## 三、环境准备

### 安装依赖



约 40MB，无需 PyTorch。

### 验证



## 四、快速开始

### 场景 A：我有 kb_ai.db



### 场景 B：我只有 PPTX 文件（零依赖）



### 场景 C：我有 kb_index.json



### 搜索



## 五、编程接口



## 六、技术参数

| 参数 | 值 |
|------|-----|
| 模型 | BAAI/bge-small-zh-v1.5 (ONNX, 512维) |
| 引擎 | FAISS IndexFlatIP / NumPy 降级 |
| 混合评分 | 向量 0.7 + 关键词 0.3 |
| 编码速度 | ~30秒 / 263条 |
| 搜索延迟 | < 0.1秒 |

## 七、常见问题

**Q: 没有任何 index, 能直接用吗？**
A: 能。 直接读 PPTX 文件, 零依赖自举。

**Q: onnxruntime DLL 加载失败？**
A: 安装 VC++ Redist: 下载 vc_redist.x64.exe, 管理员运行。
