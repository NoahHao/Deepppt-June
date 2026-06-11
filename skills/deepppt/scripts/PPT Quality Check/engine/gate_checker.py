import yaml
from .parser import extract_title_and_body
from .matcher import StageMatcher

# ---------- 标题质量评估 ----------
# 中文断言动词（表达观点的常用动作词）
ASSERTION_VERBS = {
    '是', '有', '在', '成为', '增长', '下降', '提升', '降低', '增加', '减少',
    '推动', '促进', '导致', '实现', '达到', '超过', '占据', '占比', '具备',
    '提供', '解决', '采用', '应用', '需要', '面临', '处于', '分为', '包括',
    '涉及', '围绕', '针对', '基于', '通过', '利用', '借助', '依靠', '源于',
    '达成', '完成', '突破', '打造', '构建', '建立', '覆盖', '引入', '替代',
}

# 中性/描述性标题的典型结构词（不表达观点但仍是有效标题）
DESCRIPTIVE_MARKERS = {
    '架构', '方案', '产品', '平台', '能力', '优势', '特点', '背景',
    '概述', '概览', '总结', '展望', '规划', '路线', '流程', '模式',
    '团队', '组织', '案例', '指标', '数据', '分析', '对比', '评估',
    '策略', '目标', '计划', '预算', '资源', '时间', '里程碑',
    '技术', '服务', '功能', '特性', '场景', '价值', '成果', '效果',
    '现状', '趋势', '规模', '份额', '市场', '行业', '竞争', '生态',
    '体系', '框架', '结构', '模块', '层次', '组件', '系统', '网络',
    '运营', '管理', '治理', '安全', '合规', '风险', '质量', '成本',
    '收入', '利润', '投资', '融资', '估值', '测算', '预测',
    '全景', '总览', '一览', '全貌', '蓝图', '画像', '地图',
}

# 真正的不合格标题特征（标题过短、纯标号、无意义字）
NEUTRAL_STARTERS = {'关于', '对于', '概述', '分析', '报告', '介绍', '说明', '讨论', '审查'}


def title_quality(title: str) -> tuple:
    """
    评估标题质量，返回 (quality, reason)。

    quality 级别:
      'strong'   — 有动词的断言句，优秀
      'neutral'  — 描述性标题，可接受（不扣分）
      'weak'     — 开头中性词/标题过短，建议改进
      'empty'    — 无标题，需修复
    """
    if not title or not title.strip():
        return 'empty', '标题为空'

    title = title.strip()
    if len(title) < 3:
        return 'weak', f'标题过短 ({len(title)} 字符): "{title}"'

    # 检查中性开头
    for s in NEUTRAL_STARTERS:
        if title.startswith(s) and len(title) <= len(s) + 4:
            return 'weak', f'中性词开头: "{title}"'

    # 检查是否包含断言动词 → 强标题
    has_verb = any(v in title for v in ASSERTION_VERBS)
    if has_verb:
        return 'strong', f'断言标题: "{title}"'

    # 检查是否包含描述性标记 → 中性标题（可接受）
    has_descriptor = any(m in title for m in DESCRIPTIVE_MARKERS)
    if has_descriptor:
        return 'neutral', f'描述性标题: "{title}"'

    # 其他情况 → 弱标题（过短且无关键特征）
    if len(title) < 5:
        return 'weak', f'标题过短且无关键信息: "{title}"'

    return 'neutral', f'通用标题: "{title}"'


def is_assertion(title):
    """兼容旧接口：返回 True 仅当标题为 strong 或 neutral。"""
    quality, _ = title_quality(title)
    return quality in ('strong', 'neutral')



# ---------- Gate Checker ----------

class GateChecker:
    def __init__(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.matcher = StageMatcher(config_path)
        self.policy = self.config['gate_policy']
        self.stages = self.config['stages']

    def check(self, pptx_path):
        slides = extract_title_and_body(pptx_path)
        report = {
            'file': pptx_path,
            'template': self.config['meta']['name'],
            'template_description': self.config['meta'].get('description', ''),
            'total_pages': len(slides),
            'page_assignments': [],
            'missing_stages': [],
            'order_violations': [],
            'weak_titles': [],
            'empty_titles': [],
            'neutral_titles': [],  # 新增：描述性标题（不扣分）
            'unmatched_pages': [],
            'summary': {}
        }

        # 1. 为每页匹配阶段
        assigned_stages = {}  # page -> stage_id
        for slide in slides:
            title = slide['title']
            quality, reason = title_quality(title)

            if quality == 'empty':
                report['empty_titles'].append({
                    'page': slide['page'],
                    'title': title,
                    'reason': reason,
                })
                assigned_stages[slide['page']] = None
                continue

            if quality == 'weak':
                report['weak_titles'].append({
                    'page': slide['page'],
                    'title': title,
                    'reason': reason,
                })
            elif quality == 'neutral':
                report['neutral_titles'].append({
                    'page': slide['page'],
                    'title': title,
                })

            # 即使弱标题也尝试匹配阶段
            if quality in ('strong', 'neutral', 'weak'):
                stage_id, score = self.matcher.match(title)
                if stage_id is None:
                    report['unmatched_pages'].append({
                        'page': slide['page'],
                        'title': title,
                        'quality': quality,
                    })
                    assigned_stages[slide['page']] = None
                else:
                    assigned_stages[slide['page']] = stage_id
                    report['page_assignments'].append({
                        'page': slide['page'],
                        'title': title,
                        'stage_id': stage_id,
                        'match_score': score,
                        'title_quality': quality,
                    })

        # 2. 检查缺失的 required stages
        required_ids = [s['id'] for s in self.stages if s.get('required', False)]
        found_ids = set(v for v in assigned_stages.values() if v is not None)
        for rid in required_ids:
            if rid not in found_ids:
                label = next((s['label'] for s in self.stages if s['id'] == rid), rid)
                required_order = next((s.get('order', 0) for s in self.stages if s['id'] == rid), 0)
                report['missing_stages'].append({
                    'stage_id': rid,
                    'label': label,
                    'order': required_order,
                })

        # 3. 检查顺序
        if self.policy.get('strict_order', False):
            ordered_stages = [s['id'] for s in self.stages]
            seen_stages = [assigned_stages[p] for p in sorted(assigned_stages.keys()) if assigned_stages[p] is not None]
            last_order = -1
            for sid in seen_stages:
                current_order = next((s['order'] for s in self.stages if s['id'] == sid), 0)
                if current_order < last_order:
                    prev = next((s for s in self.stages if s['order'] == last_order), None)
                    curr = next((s for s in self.stages if s['id'] == sid), None)
                    report['order_violations'].append({
                        'stage_id': sid,
                        'stage_label': curr['label'] if curr else sid,
                        'expected_after': prev['label'] if prev else 'start',
                        'message': f"阶段 '{curr['label'] if curr else sid}' 应出现在 '{prev['label'] if prev else 'start'}' 之后"
                    })
                last_order = current_order

        # 4. 最终结论：折叠 + 生成人类可读解释
        total_issues = (
            len(report['missing_stages']) +
            len(report['order_violations']) +
            len(report['empty_titles']) +
            len(report['weak_titles'])
        )
        passed = len(report['missing_stages']) == 0 and len(report['empty_titles']) == 0

        # 生成解释文本
        explanation_lines = [f"框架模板: {self.config['meta']['name']}"]
        explanation_lines.append(f"检查模式: {'严格顺序' if self.policy.get('strict_order') else '仅阶段覆盖'}")

        if report['missing_stages']:
            explanation_lines.append(f"\n缺失阶段 ({len(report['missing_stages'])} 个):")
            for ms in report['missing_stages']:
                explanation_lines.append(f"  - [{ms['order']}] {ms['label']} ({ms['stage_id']})")

        if report['order_violations']:
            explanation_lines.append(f"\n顺序违规 ({len(report['order_violations'])} 处):")
            for ov in report['order_violations'][:5]:
                explanation_lines.append(f"  - {ov['message']}")

        if report['empty_titles']:
            explanation_lines.append(f"\n空标题 ({len(report['empty_titles'])} 页):")
            for et in report['empty_titles'][:5]:
                explanation_lines.append(f"  - 第{et['page']}页: {et['reason']}")

        if report['weak_titles']:
            explanation_lines.append(f"\n弱标题 ({len(report['weak_titles'])} 个, 建议优化):")
            for wt in report['weak_titles'][:3]:
                explanation_lines.append(f"  - 第{wt['page']}页: {wt['reason']}")
            if len(report['weak_titles']) > 3:
                explanation_lines.append(f"  ... 共 {len(report['weak_titles'])} 个弱标题")

        if report['unmatched_pages']:
            explanation_lines.append(f"\n未匹配页面 ({len(report['unmatched_pages'])} 页):")
            for up in report['unmatched_pages'][:5]:
                explanation_lines.append(f"  - 第{up['page']}页: \"{up['title'][:40]}\" ({up['quality']})")

        explanation_lines.append(f"\n有效匹配: {len(report['page_assignments'])} 页")
        explanation_lines.append(f"描述性标题: {len(report['neutral_titles'])} 个 (不扣分)")

        report['summary'] = {
            'passed': passed,
            'total_issues': total_issues,
            'missing_count': len(report['missing_stages']),
            'order_violations_count': len(report['order_violations']),
            'weak_titles_count': len(report['weak_titles']),
            'empty_titles_count': len(report['empty_titles']),
            'neutral_titles_count': len(report['neutral_titles']),
            'unmatched_pages_count': len(report['unmatched_pages']),
            'matched_pages_count': len(report['page_assignments']),
            'explanation': '\n'.join(explanation_lines),
        }

        return report