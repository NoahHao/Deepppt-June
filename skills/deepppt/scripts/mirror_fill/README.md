# mirror_fill — PPTX 镜像文本填充引擎

**"Copy, don't fill"** — 复制整页 PPTX 幻灯片，仅替换指定区域内的文字，所有图形、图标、颜色、位置保持不变。

---

## 快速开始

### 安装

```python
# 确保 python-pptx 已安装
pip install python-pptx
```

### 基础用法

```python
from mirror_fill import MirrorFiller

# 方式1：从 PPTX 文件
filler = MirrorFiller("source.pptx", slide_num=1, layout="left_right")
filler.fill("left_right", {"right": {"旧文字": "新文字"}})
filler.save("output.pptx")

# 方式2：从 LLM_Search 自动定位
filler = MirrorFiller.from_search("DCS 数据中心 架构图")
filler.fill("left_right", {"right": {"安全可靠": "企业级稳定性"}})
filler.save("output.pptx")
```

---

## 核心概念

### 1. 区域 (Region)

幻灯片被划分为多个**区域**，每个区域对应一个矩形范围（以 EMU 坐标定义）。填充操作只替换**指定区域内**的 shape 文本。

预设布局：

| 布局名 | 区域划分 | 用途 |
|--------|----------|------|
| `left_right` | 左、右两栏 | 左右对比型幻灯片 |
| `left_center_right` | 左、中、右三栏 | 三分排版 |
| `top_bottom` | 上、下两栏 | 上下结构 |
| `top_middle_bottom` | 上、中、下三栏 | 三段式布局 |

也可使用 `custom_layout()` 自定义区域：

```python
from mirror_fill import custom_layout

layout = custom_layout(
    hero=(0, 12_192_000, 0, 3_000_000),    # 顶部横幅区域
    cards=(0, 12_192_000, 3_000_000, 6_858_000),  # 下方卡片区域
)
```

### 2. 填充 (Fill)

`filler.fill(layout, region_texts)` 接受两个参数：

- `layout`: 布局名称（预设字符串）或自定义的 `Dict[str, SlideRegion]`
- `region_texts`: 一个字典，键为区域名，值为 `{旧文本: 新文本}` 映射

**示例：**

```python
filler.fill("left_right", {
    "right": {
        "安全可靠": "企业级稳定性",
        "硬件亚健康自动迁移": "vSphere HA 自动故障切换",
    },
    "left": {
        "传统数据中心": "智能数据中心",
    },
})
```

---

## API 参考

### `MirrorFiller` 类

#### 构造函数

```python
MirrorFiller(src_pptx, slide_num=1, layout="left_right")
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `src_pptx` | str / Path | 源 PPTX 文件路径 |
| `slide_num` | int | 源幻灯片页码（从 1 开始） |
| `layout` | str | 布局预设名，如 `"left_right"` |

#### 工厂方法

```python
MirrorFiller.from_pptx(src_pptx, slide_num=1, layout="left_right")
MirrorFiller.from_search(query, layout="left_right", top_k=3)
```

- `from_pptx`: 从 PPTX 文件创建，等价于构造函数
- `from_search`: 从 LLM_Search 语义搜索结果自动定位源页

#### 区域探索

```python
filler.inspect()        # 打印 slide 区域内容概览
filler.find_text(keyword)  # 搜索包含关键词的 shape，返回 [(shape_index, text), ...]
```

#### 填充操作

```python
filler.fill(layout, region_texts)  # 按区域填充文本（链式调用，返回 self）
```

#### 输出

```python
filler.save(output_path)  # 执行填充并保存 PPTX，返回输出文件路径
```

#### 状态信息

```