#!/usr/bin/env python3
"""
DCS → VMware 解决方案优势替换（使用 auto_fill 引擎）
====================================================
一行调用完成搜索→分组→映射→填充全流程。

用法:
    python run_dcs_vmware.py
    
输出:
    project/dcs_to_vmware.pptx
"""

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from mirror_fill.auto_fill import mirror_auto

# ══════════════════════════════════════════════
# 仅需两个输入：搜索查询 + 新内容
# ══════════════════════════════════════════════

VMWARE_CONTENT = [
    "企业级高可用\n"
    "vSphere HA 自动故障切换，vMotion 零停机迁移\n"
    "历经 25 年全球企业级验证",

    "智能统一运维\n"
    "vCenter 集中管控，vRealize AIOps 智能运维\n"
    "多云环境统一视图，自动化策略管理",

    "开放生态兼容\n"
    "500+ ISV 认证，Tanzu 容器平台\n"
    "混合云无缝迁移扩展，vSAN 超融合架构",
]

if __name__ == "__main__":
    mirror_auto(
        query="DCS数据中心解决方案架构图",
        new_blocks=VMWARE_CONTENT,
        output_name="dcs_to_vmware.pptx",
    )
