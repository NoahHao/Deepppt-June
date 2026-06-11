# Local TTS — 本地语音合成测试环境

Phase 1: 环境检测与基础验证。

## 运行测试

```bash
cd local_tts
python phase1_test.py              # 环境检测 + 生成测试音频
python phase1_test.py --env-only   # 仅环境检测
```

## 目录结构

```
local_tts/
├── phase1_test.py          # 环境检测 + 基础生成测试
├── models/                 # 本地模型文件存放
├── reference_audio/        # 声音克隆参考音频
├── test_output/            # 测试生成结果
└── README.md
```

## 后端支持矩阵

| 后端 | GPU | CPU | 声音克隆 | 安装 |
|------|:--:|:--:|:--:|------|
| Coqui XTTS v2 | ✅ 推荐 | ⚠️ 慢 | ✅ 6秒素材 | `pip install TTS` |
| F5-TTS | ✅ 必需 | ❌ | ✅ 15秒素材 | `pip install f5-tts` |
| Piper | ❌ | ✅ | ❌ 预设音色 | `pip install piper-tts` |
| edge-tts (fallback) | ❌ | ✅ | ❌ 云端 | `pip install edge-tts` |

## 当前环境状态

见 `phase1_test.py --env-only` 输出。
