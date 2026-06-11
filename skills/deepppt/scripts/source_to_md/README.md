# source_to_md — 源文档处理模块

将各类源文档转换为 Markdown，供 PPT 生成流水线使用。

## 脚本清单

| 脚本 | 用途 | 输入格式 |
|------|------|----------|
| `pdf_to_md.py` | PDF → Markdown（含矢量图提取） | `.pdf` |
| `doc_to_md.py` | Office 文档 → Markdown | `.docx` `.html` `.epub` `.ipynb` |
| `excel_to_md.py` | Excel → Markdown | `.xlsx` `.xlsm` |
| `ppt_to_md.py` | PPTX → Markdown | `.pptx` |
| `web_to_md.py` | 网页 → Markdown | `http(s)://...` |
| **`pdf_splitter.py`** | **长PDF智能裁剪** | `.pdf` |

## PDF 智能裁剪 (pdf_splitter.py)

当 PDF 过长（>10页）时，自动按章节边界裁剪为多个上下文安全的块，防止生成 PPT 时信息丢失。

### 自动触发

在 Step 1 处理 PDF 时，如果 PDF > 10 页，`pdf_to_md.py` 会自动调用 `pdf_splitter.py` 进行裁剪。

手动调用：
```bash
# 分析 PDF 结构（不裁剪）
python3 scripts/source_to_md/pdf_splitter.py "白皮书.pdf" --analyze

# 裁剪（自动检测模型+章节边界）
python3 scripts/source_to_md/pdf_splitter.py "白皮书.pdf" --max-pages 10

# 指定模型
python3 scripts/source_to_md/pdf_splitter.py "白皮书.pdf" --model deepseek-v4-pro

# JSON 输出
python3 scripts/source_to_md/pdf_splitter.py "白皮书.pdf" --json
```

### 工作原理

1. **模型嗅探** — 自动识别后端模型，估算安全上下文预算
2. **章节检测** — 识别"第X章"标记 + 字体大小启发式
3. **智能拆分** — 在章节/子节边界处裁剪，保留专题完整性
4. **输出清单** — `_chunks/split_manifest.json` 记录所有块信息

### 安全预算公式

```
ctx_available = context_window × 0.9          (10% 安全余量)
working_budget = ctx_available − 50,000        (固定开销: skill+脚本+prompt)
safe_pages = working_budget ÷ 1,200            (每页约1200 tokens)
```

## 常见用法

### PDF 文件
```bash
python3 scripts/source_to_md/pdf_to_md.py <file.pdf> --render-vector-figures
```
> ⚠️ 必须携带 `--render-vector-figures`，否则 PDF 中的矢量图表会丢失。

### Word 文档
```bash
python3 scripts/source_to_md/doc_to_md.py <file.docx>
```

### 网页
```bash
python3 scripts/source_to_md/web_to_md.py <URL>
```

### Excel
```bash
python3 scripts/source_to_md/excel_to_md.py <file.xlsx>
```

### PPTX
```bash
python3 scripts/source_to_md/ppt_to_md.py <file.pptx>
```

## 依赖

`PyMuPDF>=1.23.0` — 已包含在顶层 `requirements.txt` 中。
