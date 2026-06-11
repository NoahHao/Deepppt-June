# svg_editor — Web 预览编辑器

Flask 应用，提供 PPT 生成过程中的实时预览和协同批注功能。

## 文件结构

| 文件 | 用途 |
|------|------|
| `server.py` | Flask 主应用 (1108行) |
| `share.py` | 一键共享脚本 |
| `annotations.py` | SVG 注解管理库 |
| `static/index.html` | 编辑器前端页面 |
| `static/app.js` | 前端交互逻辑 (~2500行) |
| `static/style.css` | 编辑器样式 |
| `static/review.html` | 批注审核面板 |

## 启动方式

### 本地预览（仅本机）
```bash
python3 scripts/svg_editor/server.py <project_path>
# 浏览器自动打开 http://localhost:5050
```

### 共享模式（局域网/外网可访问）
```bash
python3 scripts/svg_editor/server.py <project_path> --share --token xxx --host 0.0.0.0
# 分享链接: http://<IP>:5050/?token=xxx
# 审核面板: http://localhost:5050/review?token=xxx
```

### Live 模式（Executor 阶段自动启动）
```bash
python3 scripts/svg_editor/server.py <project_path> --live --share --token xxx --host 0.0.0.0 --timeout 0
```

## 核心 API

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/slides` | GET | 列出所有 SVG 幻灯片 |
| `/api/slide/<name>` | GET | 获取单个 SVG 内容+注解 |
| `/api/slide/<name>/annotate` | POST | 添加元素注解 |
| `/api/slide/<name>/edit` | POST | 直接编辑 SVG 属性 |
| `/api/save-all` | POST | 持久化到磁盘(share模式→待审队列) |
| `/api/review/pending` | GET | 查看待审核批注 |
| `/api/review/approve` | POST | 批准批注 |
| `/api/review/reject` | POST | 驳回批注 |

## 编辑模式

- **直接编辑** — 点击元素 → 修改属性面板 → 暂存内存 → Apply changes 存盘
- **批注模式** — 点击元素 → 写 AI 指令 → Submit for review → 发布者审批 → AI 执行
