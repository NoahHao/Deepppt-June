"""
StageMatcher — 将PPT页面标题匹配到预定义演示阶段（病·药·效·行动等）。

匹配策略（多级）：
  1. 关键词精确匹配 → 最高分
  2. 语义近似（synonym）匹配 → 中等分
  3. 模糊子串匹配 → 低分
  4. 无匹配 → None
"""

import re


class StageMatcher:
    def __init__(self, config_path):
        import yaml
        import os

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        self.stages = config.get('stages', [])
        self.policy = config.get('gate_policy', {})
        self._build_index()

    def _build_index(self):
        """预编译所有阶段的关键词/近义词正则模式。"""
        self._stage_patterns = []  # [(stage_id, [(regex, weight), ...])]
        for stage in self.stages:
            patterns = []

            # 关键词: 权重 10
            for kw in stage.get('keywords', []):
                patterns.append((re.compile(re.escape(kw), re.IGNORECASE), 10))

            # 近义词: 权重 5
            for syn in stage.get('synonyms', []):
                patterns.append((re.compile(re.escape(syn), re.IGNORECASE), 5))

            self._stage_patterns.append((stage['id'], patterns))

    def match(self, title):
        """
        对标题进行多级匹配，返回 (best_stage_id, best_score)。

        匹配逻辑：
          - 遍历所有阶段的所有模式
          - 评分 = 命中模式权重 + 字符覆盖率奖励
          - 返回得分最高的阶段
          - 若所有阶段得分 <= 0，返回 (None, 0)
        """
        if not title or not self._stage_patterns:
            return None, 0

        best_stage = None
        best_score = 0

        for stage_id, patterns in self._stage_patterns:
            total_score = 0
            matched_chars = 0

            for regex, weight in patterns:
                matches = regex.findall(title)
                if matches:
                    total_score += weight
                    matched_chars += sum(len(m) for m in matches)

            # 字符覆盖率奖励 (max 3)
            if len(title) > 0:
                coverage = min(3, int(matched_chars / len(title) * 10))
                total_score += coverage

            if total_score > best_score:
                best_score = total_score
                best_stage = stage_id

        # 最低门槛
        if best_score < self.policy.get('min_match_score', 3):
            return None, 0

        return best_stage, best_score
