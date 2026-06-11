"""
PPT 内容质量检查器
===================
对 PPTX 文件进行基于内容的全面质量检查，8 项检查 + 文本聚类分析。

检查维度（C1-C8）：
  C1 - 占位符残留检测     ERROR   检测 {{TITLE}} 等模板占位符
  C2 - 空页检测           ERROR   页面几乎无实质文本
  C3 - 类型-内容匹配      WARNING 封面/目录/正文应有对应内容
  C4 - 内容冗余           WARNING 相邻页面高度重复
  C5 - 页码连续性         WARNING 文件名编号连续
  C6 - 源文档关键词覆盖   INFO    原始材料关键词是否出现
  C7 - 文本编码质量       ERROR   检测乱码/替换字符
  C8 - 首尾闭环           WARNING 有封面和结尾页
  C9 - 文本聚类/离群      WARNING 页面内词汇与其他内容不相关

用法：
  python content_quality_checker.py <pptx_file> [--sources <source_file>] [--report <output.json>]
"""

import re
import json
import math
import argparse
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional, Tuple, Set


# ───────────────────────────────────────────
# 文本分析工具
# ───────────────────────────────────────────

# 中文停用词（高频虚词，过滤后用于 TF 计算）
STOP_WORDS = set(
    '的 了 在 是 有 和 就 都 一 不 也 这 那 与 及 或 对 从 到 把 被 让 向 从 为 以 而 但 '
    '等 其 各 另 之 所 可 该 已 将 会 将 要 能 如 着 了 过 又 并 它 她 他 们 上 下 中 '
    '个 去 没 还 很 更 最 只 只 被 让 可以 需要 进行 通过 使用 采用 用于 提供 实现 包括 '
    '具有 同时 目前 已经 相关 一个 一些 所有 任何 其他 以及 其中 主要 根据 按照 除了 '
    '不仅 还是 然而 虽然 但是 因为 所以 因此 如果 例如 比如'.split()
)


def _tokenize(text: str) -> List[str]:
    """中文分词简化版：2-4 字 n-gram + 英文/数字保留。"""
    tokens = []
    # 先提取连续的字母/数字块
    text = text.lower()
    alpha_num = re.findall(r'[a-z0-9]+', text)
    tokens.extend(alpha_num)

    # 清理非中文字符
    clean = re.sub(r'[^\u4e00-\u9fff]+', '', text)
    # 2-gram
    if len(clean) >= 2:
        for i in range(len(clean) - 1):
            t = clean[i:i + 2]
            if t not in STOP_WORDS:
                tokens.append(t)
    # 3-gram (关键词级别)
    if len(clean) >= 3:
        for i in range(len(clean) - 2):
            t = clean[i:i + 3]
            tokens.append(t)
    return tokens


def _compute_tf(texts: List[str]) -> Counter:
    """计算多段文本的词频。"""
    counter = Counter()
    for text in texts:
        tokens = _tokenize(text)
        counter.update(tokens)
    return counter


def _cosine_similarity(vec1: Counter, vec2: Counter) -> float:
    """两个词频计数器的余弦相似度。"""
    all_keys = set(vec1.keys()) | set(vec2.keys())
    v1 = [vec1.get(k, 0) for k in all_keys]
    v2 = [vec2.get(k, 0) for k in all_keys]
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


# ───────────────────────────────────────────
# 检查函数
# ───────────────────────────────────────────

def _check_placeholder_residue(shapes_data: List[Dict]) -> List[Dict]:
    """C1: 检测残留的模板占位符 {{XXX}}、[XXX]、<XXX> 等。"""
    placeholder_re = re.compile(
        r'\{\{[^}]*\}\}|\[\[[^\]]*\]\]|'
        r'\{TITLE\}|{PAGE_TITLE}|{CHAPTER}|{SUBTITLE}|'
        r'<TITLE>|<SUBTITLE>|#\{[^}]*\}'
    )
    issues = []
    for shape in shapes_data:
        text = shape.get('text', '')
        matches = placeholder_re.findall(text)
        if matches:
            issues.append({
                'type': 'C1_PLACEHOLDER',
                'text': text[:100],
                'placeholders': list(set(matches)),
            })
    return issues


def _check_empty_page(shapes_data: List[Dict]) -> Optional[Dict]:
    """C2: 检测空页（文本总量极少）。"""
    all_text = ' '.join(s['text'] for s in shapes_data if s['text'].strip())
    # 去掉纯装饰字符
    clean = re.sub(r'[\s\d\.\,\;\:\!\?\(\)\[\]\{\}\-_\+\=\*\/\\\|]+', '', all_text)
    char_count = len(clean)

    if char_count < 10:
        return {'type': 'C2_EMPTY_PAGE', 'char_count': char_count, 'detail': '页面几乎无实质内容'}
    return None


def _check_type_content_match(shapes_data: List[Dict], page_num: int,
                               total_pages: int, all_pages_text: List[str]) -> Optional[Dict]:
    """C3: 类型-内容匹配。封面/目录/结尾页应有对应特征。"""
    all_text = ' '.join(s['text'] for s in shapes_data if s['text'].strip())

    # 封面页（第 1 页）: 应有标题，不应有过多正文
    if page_num == 1:
        if len(all_text) < 20:
            return {'type': 'C3_CONTENT_MATCH', 'role': '封面',
                    'issue': '封面内容过少，可能缺少标题'}
    # 结尾页（最后页）: 应有"谢谢"/"Q&A"/联系方式等信息
    if page_num == total_pages:
        closing_keywords = ['谢谢', '感谢', 'Q&A', '联系', 'THANK', 'Thank', 'END', '结束']
        has_closing = any(kw in all_text for kw in closing_keywords)
        if not has_closing:
            return {'type': 'C3_CONTENT_MATCH', 'role': '结尾',
                    'issue': '结尾页未检测到致谢/Q&A等典型结尾信息'}

    # 目录/章节页：标题下有列表
    if page_num == 2 and len(all_text) > 30:
        # 检测目录特征：多个编号项
        toc_pattern = re.findall(r'\d+[\.\s、\）\)]', all_text)
        if len(toc_pattern) >= 3:
            return None  # 可能是目录页，正常
        # 否则可能是内容，不报错

    return None


def _check_content_redundancy(page_texts_cleaned: List[str], threshold: float = 0.75) -> List[Dict]:
    """C4: 检测相邻页面内容高度重复。"""
    issues = []
    for i in range(len(page_texts_cleaned) - 1):
        t1 = page_texts_cleaned[i]
        t2 = page_texts_cleaned[i + 1]
        if not t1 or not t2:
            continue
        vec1 = _compute_tf([t1])
        vec2 = _compute_tf([t2])
        sim = _cosine_similarity(vec1, vec2)
        if sim > threshold:
            issues.append({
                'type': 'C4_REDUNDANCY',
                'page1': i + 1,
                'page2': i + 2,
                'similarity': round(sim, 3),
                'detail': f'页码 {i + 1} 和 {i + 2} 内容高度相似 (sim={sim:.2f})',
            })
    return issues


def _check_page_continuity(filenames_or_indices: List[str]) -> List[Dict]:
    """C5: 页码连续性。基于文件名或页面索引。"""
    issues = []
    nums = []
    for f in filenames_or_indices:
        m = re.search(r'(\d+)', str(f))
        if m:
            nums.append(int(m.group(1)))
    if len(nums) < 2:
        return issues
    for i in range(len(nums) - 1):
        if nums[i + 1] != nums[i] + 1:
            issues.append({
                'type': 'C5_PAGE_CONTINUITY',
                'page': i + 2,
                'expected': nums[i] + 1,
                'actual': nums[i + 1],
                'detail': f'页码不连续：期望 {nums[i] + 1}，实际 {nums[i + 1]}',
            })
    return issues


def _check_source_keyword_coverage(all_texts: List[str],
                                    source_text: Optional[str] = None,
                                    top_n: int = 20) -> Dict:
    """C6: 检查源文档关键词在最终 PPT 中的覆盖率。"""
    if not source_text:
        return {'type': 'C6_SOURCE_COVERAGE', 'covered': 0, 'total': 0,
                'missing': [], 'detail': '无可用的源文档'}

    source_tf = _compute_tf([source_text])
    ppt_tf = _compute_tf(all_texts)

    # 取源文档 top-N 关键词
    top_keywords = [kw for kw, _ in source_tf.most_common(top_n)]

    covered = []
    missing = []
    for kw in top_keywords:
        if kw in ppt_tf:
            covered.append(kw)
        else:
            missing.append(kw)

    return {
        'type': 'C6_SOURCE_COVERAGE',
        'covered': len(covered),
        'total': len(top_keywords),
        'missing': missing[:10],
        'coverage_rate': round(len(covered) / len(top_keywords), 2),
    }


def _check_text_encoding(all_texts: List[str]) -> List[Dict]:
    """C7: 检测乱码。仅检测 Unicode 替换字符（\ufffd = �）。"""
    issues = []
    replacement_char = '\ufffd'

    for text in all_texts:
        if not text or len(text) < 5:
            continue
        # 检测 Unicode 替换字符（这是编码错误的可靠标志）
        if replacement_char in text:
            issues.append({
                'type': 'C7_GARBLED',
                'text_sample': text[:100],
                'garbled_chars': text.count(replacement_char),
                'detail': f'文本包含 {text.count(replacement_char)} 个 Unicode 替换字符（乱码），可能是编码问题',
            })
    return issues


def _check_structure_completeness(all_shapes: List[List[Dict]]) -> Dict:
    """C8: 检查PPT结构完整性（封面+结尾）。"""
    total = len(all_shapes)
    if total < 2:
        return {'type': 'C8_STRUCTURE', 'has_cover': total > 0, 'has_closing': False,
                'detail': 'PPT 页数过少（< 2页）'}

    # 封面检测: 第1页有较大标题
    first_text = ' '.join(s['text'] for s in all_shapes[0] if s['text'].strip())
    has_cover = len(first_text) >= 10

    # 结尾检测: 最后1-2页有致谢语
    closing = False
    for page_data in all_shapes[-2:]:
        texts = ' '.join(s['text'] for s in page_data if s['text'].strip())
        if any(kw in texts for kw in ['谢谢', '感谢', 'Q&A', 'THANK', 'Thank', '联系']):
            closing = True
            break

    issues = []
    if not has_cover:
        issues.append('缺少封面页')
    if not closing:
        issues.append('缺少结尾页（致谢/Q&A）')

    return {
        'type': 'C8_STRUCTURE',
        'has_cover': has_cover,
        'has_closing': closing,
        'issues': issues,
        'detail': '; '.join(issues) if issues else '结构完整',
    }


def _check_text_clustering(shapes_data: List[Dict], outlier_threshold: float = 0.05) -> List[Dict]:
    """
    C9: 页面内文本聚类/离群检测。
    检测页面中是否有文本块与同页其他内容完全不相关。
    方法：对页面内每个 text block 计算与其他 block 的 TF 相似度，
    明显低于平均的即为离群。

    过滤策略：
      - 跳过过短的文本（< 4 字符，通常是标签/脚注）
      - 相对全局平均相似度过低（< 30%）才标记
    """
    # 过滤过短文本
    texts_raw = [(s['text'], s['top_emu'], s['font_size_pt'])
                 for s in shapes_data if s['text'].strip()]
    texts = [(t, top, fs) for t, top, fs in texts_raw if len(t) >= 4]
    if len(texts) < 3:
        return []  # 文本块太少，不检测

    # 计算每对文本的相似度矩阵
    tfs = [_compute_tf([t[0]]) for t in texts]
    n = len(tfs)
    similarities = []
    for i in range(n):
        sims = []
        for j in range(n):
            if i != j:
                sims.append(_cosine_similarity(tfs[i], tfs[j]))
        avg_sim = sum(sims) / len(sims) if sims else 1.0
        similarities.append(avg_sim)

    # 计算全局平均
    global_avg = sum(similarities) / len(similarities) if similarities else 0
    if global_avg == 0:
        return []

    # 计算标准差
    variance = sum((s - global_avg) ** 2 for s in similarities) / len(similarities)
    std_dev = math.sqrt(variance)

    # 标记离群：sim 显著低于同页其他文本
    #   - 绝对阈值: sim < 0.01（几乎零语义重叠）
    #   - 相对阈值: sim < global_avg * 0.15（远低于页面平均）
    #   - critical: sim < 0.003 或 sim < global_avg * 0.05（极端偏离）
    issues = []
    for i, sim in enumerate(similarities):
        # 必须同时满足绝对和相对阈值
        is_outlier = sim < 0.01 and (global_avg > 0.02 and sim < global_avg * 0.15)
        if not is_outlier:
            continue

        t, top_emu, fs_pt = texts[i]
        # 跳过脚注/水印（页面底部 + 字号小）
        if top_emu > 5800000 and fs_pt < 12:
            continue

        # 分级：极端偏离 → critical，一般偏离 → warning
        is_critical = sim < 0.003 or (global_avg > 0.03 and sim < global_avg * 0.05)

        issues.append({
            'type': 'C9_OUTLIER',
            'text': t[:120],
            'avg_similarity': round(sim, 3),
            'global_avg': round(global_avg, 3),
            'deviation_ratio': round(sim / global_avg, 4) if global_avg > 0 else 0,
            'tier': 'critical' if is_critical else 'warning',
            'detail': f'文本块与同页其他内容不相关 (相似度 {sim:.3f} vs 全局 {global_avg:.3f}, 偏离比 {sim/global_avg:.1%})'
                      if global_avg > 0 else f'文本块与同页其他内容不相关 (相似度 {sim:.3f})',
        })
    return issues


# ───────────────────────────────────────────
# 报告聚合与结论生成
# ───────────────────────────────────────────

# 折叠阈值：同类问题超过此数量时自动折叠
COLLAPSE_THRESHOLD = 10

# 警告阈值：同类问题超过此数量时，提示可能标准设置不当
HINT_THRESHOLD = 15

# 类型中文标签
TYPE_LABELS = {
    'C1_PLACEHOLDER': '占位符残留',
    'C2_EMPTY_PAGE': '空页',
    'C3_CONTENT_MATCH': '类型-内容不匹配',
    'C4_REDUNDANCY': '内容冗余',
    'C5_PAGE_CONTINUITY': '页码不连续',
    'C6_SOURCE_COVERAGE': '关键词覆盖',
    'C7_GARBLED': '文本乱码',
    'C8_STRUCTURE': '结构不完整',
    'C9_OUTLIER': '文本离群',
}


def _collapse_issues(issues: List[Dict]) -> Dict:
    """
    将 issues 按类型折叠。
    返回: {
        'collapsed': {'C1_PLACEHOLDER': {'count': 5, 'samples': [...], 'hint': str|None}, ...},
        'full': [原始 issues 列表]
    }
    - 数量 > COLLAPSE_THRESHOLD → 折叠，只保留前 5 条样本
    - 数量 > HINT_THRESHOLD → 附加阈值调整建议
    """
    by_type = {}
    for issue in issues:
        t = issue['type']
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(issue)

    collapsed = {}
    for t, items in by_type.items():
        entry = {
            'count': len(items),
            'label': TYPE_LABELS.get(t, t),
            'samples': items[:5],  # 最多展示 5 条
            'collapsed': len(items) > COLLAPSE_THRESHOLD,
            'hint': None,
        }
        if len(items) > HINT_THRESHOLD:
            entry['hint'] = f'同类问题出现 {len(items)} 次，建议检查 {TYPE_LABELS.get(t, t)} 的检测阈值是否合理'
        collapsed[t] = entry

    return collapsed


def _build_page_scorecard(all_issues: List[Dict], total_pages: int) -> List[Dict]:
    """生成每页评分卡。"""
    by_page = {}
    for issue in all_issues:
        p = issue.get('page')
        if p is None:
            continue
        if p not in by_page:
            by_page[p] = {'error': 0, 'critical': 0, 'warning': 0, 'top_issue_types': []}
        t = issue['type']
        if t in ('C1_PLACEHOLDER', 'C2_EMPTY_PAGE', 'C7_GARBLED'):
            by_page[p]['error'] += 1
        elif t == 'C9_OUTLIER' and issue.get('tier') == 'critical':
            by_page[p]['critical'] += 1
        else:
            by_page[p]['warning'] += 1
        by_page[p]['top_issue_types'].append(TYPE_LABELS.get(t, t))

    scorecard = []
    for p in range(1, total_pages + 1):
        info = by_page.get(p, {'error': 0, 'critical': 0, 'warning': 0, 'top_issue_types': []})
        # 健康分: 100 - error*30 - critical*15 - warning*3
        score = max(0, 100 - info['error'] * 30 - info['critical'] * 15 - info['warning'] * 3)
        top_types = list(set(info['top_issue_types']))[:3]
        scorecard.append({
            'page': p,
            'score': score,
            'errors': info['error'],
            'critical': info['critical'],
            'warnings': info['warning'],
            'top_issues': top_types,
        })
    return scorecard


def _build_conclusion(
    total_pages: int,
    collapsed: Dict[str, Dict],
    errors: List, warnings: List, infos: List,
    c9_critical: List, c9_warning: List,
    scorecard: List[Dict],
) -> str:
    """
    生成人类可读的综合结论。
    规则：
     - 错误优先展示
     - 同类问题 > HINT_THRESHOLD 时折叠并提示标准可能需调整
     - 无错误无严重离群 → 良好
    """
    lines = []

    # 评级
    poor_pages = [s for s in scorecard if s['score'] < 50]
    if errors:
        grade = '需修复'
    elif c9_critical or poor_pages:
        grade = '需人工复核'
    elif len(warnings) <= total_pages * 0.3:
        grade = '良好'
    else:
        grade = '一般'

    lines.append(f'质量等级: {grade}  |  共 {total_pages} 页  |  ERROR {len(errors)}  CRITICAL {len(c9_critical)}  WARNING {len(warnings)}')

    # ── 阻断问题（必须修复） ──
    if errors:
        lines.append('')
        lines.append('=' * 40)
        lines.append('[阻断] 以下问题必须修复:')
        for t, info in collapsed.items():
            if info['count'] == 0 or t not in ('C1_PLACEHOLDER', 'C2_EMPTY_PAGE', 'C7_GARBLED'):
                continue
            samples = info['samples']
            if info['collapsed']:
                lines.append(f'  {info["label"]}: {info["count"]} 处（已折叠，展示前 {len(samples)} 条）')
            else:
                lines.append(f'  {info["label"]}: {info["count"]} 处')
            for s in samples[:3]:
                page = s.get('page', '?')
                detail = s.get('detail', '')
                lines.append(f'    - 第{page}页: {detail}')
            if info.get('hint'):
                lines.append(f'  >>> {info["hint"]}')

    # ── 严重文本离群 ──
    if c9_critical:
        lines.append('')
        lines.append('=' * 40)
        lines.append(f'[严重] 文本离群 {len(c9_critical)} 处（内容与页面主题极不相关）:')
        c9_entry = collapsed.get('C9_OUTLIER', {})
        crit_samples = c9_entry.get('samples', c9_critical[:3])
        for c in crit_samples[:3]:
            page = c.get('page', '?')
            text = c.get('text', '')[:60]
            lines.append(f'  - 第{page}页: "{text}"')
        if c9_entry.get('collapsed'):
            lines.append(f'  ... 已折叠 {(c9_entry["count"]) - len(crit_samples)} 条')
        if c9_entry.get('hint'):
            lines.append(f'  >>> {c9_entry["hint"]}')

    # ── 一般警告 ──
    other_warnings = [w for w in warnings if w['type'] != 'C9_OUTLIER']
    if other_warnings:
        lines.append('')
        lines.append('=' * 40)
        lines.append(f'[警告] 建议关注:')
        w_types = Counter(w['type'] for w in other_warnings)
        for wt, cnt in w_types.most_common():
            label = TYPE_LABELS.get(wt, wt)
            entry = collapsed.get(wt, {})
            if entry.get('collapsed'):
                lines.append(f'  {label}: {cnt} 处（已折叠）')
            else:
                lines.append(f'  {label}: {cnt} 处')
                for s in entry.get('samples', [])[:2]:
                    page = s.get('page', '?')
                    detail = s.get('detail', '')
                    lines.append(f'    - 第{page}页: {detail}')
            if entry.get('hint'):
                lines.append(f'  >>> {entry["hint"]}')

    # ── 轻度离群 ──
    if c9_warning:
        lines.append('')
        lines.append(f'[参考] 轻度文本离群 {len(c9_warning)} 处（偏离较轻，仅供参考）')

    # ── 信息 ──
    if infos:
        for info in infos:
            if info['type'] == 'C6_SOURCE_COVERAGE' and info.get('coverage_rate', 0) > 0:
                lines.append('')
                lines.append(f'[信息] 源文档关键词覆盖率: {info["coverage_rate"]:.0%}')

    # ── 低分页提示 ──
    if poor_pages:
        lines.append('')
        lines.append(f'[提示] 以下页面健康分低于50，建议重点复核:')
        for s in poor_pages[:5]:
            lines.append(f'  第{s["page"]}页 (分值 {s["score"]}, 问题: {", ".join(s["top_issues"])})')

    return '\n'.join(lines)


# ───────────────────────────────────────────
# 主类：ContentQualityChecker
# ───────────────────────────────────────────

class ContentQualityChecker:
    """
    PPT 内容质量检查器。

    用法：
        checker = ContentQualityChecker()
        report = checker.check('path/to/file.pptx', source_text='...')
        print(report.to_json())
    """

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
        self.all_issues = []

    def check(self, pptx_path: str, source_text: Optional[str] = None) -> 'QualityReport':
        """
        执行全部内容质量检查。

        Args:
            pptx_path: PPTX 文件路径
            source_text: 可选的原始素材文本（用于 C6 关键词覆盖检查）

        Returns:
            QualityReport 对象（可序列化为 JSON）
        """
        # 动态导入 parser（避免循环依赖）
        from engine.parser import extract_all_texts

        all_shapes = extract_all_texts(pptx_path)
        total_pages = len(all_shapes)

        if total_pages == 0:
            return QualityReport(
                file=pptx_path,
                total_pages=0,
                summary={'error': '无法解析 PPTX 或文件为空'},
                issues=[],
            )

        all_issues = []

        # 收集每页全部文本
        page_all_texts = []
        for page_data in all_shapes:
            page_text = ' '.join(s['text'] for s in page_data['shapes'] if s['text'].strip())
            page_all_texts.append(page_text)

        # ── 逐页检查 ──
        for page_data in all_shapes:
            page_num = page_data['page']
            shapes = page_data['shapes']

            # C1: 占位符残留
            for issue in _check_placeholder_residue(shapes):
                issue['page'] = page_num
                all_issues.append(issue)

            # C2: 空页检测
            empty = _check_empty_page(shapes)
            if empty:
                empty['page'] = page_num
                all_issues.append(empty)

            # C3: 类型-内容匹配
            type_match = _check_type_content_match(
                shapes, page_num, total_pages, page_all_texts
            )
            if type_match:
                type_match['page'] = page_num
                all_issues.append(type_match)

            # C7: 文本编码
            for issue in _check_text_encoding([s['text'] for s in shapes]):
                issue['page'] = page_num
                all_issues.append(issue)

            # C9: 文本聚类/离群
            for issue in _check_text_clustering(shapes):
                issue['page'] = page_num
                all_issues.append(issue)

        # ── 整文件检查 ──
        # C4: 内容冗余
        for issue in _check_content_redundancy(page_all_texts):
            all_issues.append(issue)

        # C5: 页码连续性（从文件名）
        filenames = [str(p) for p in range(1, total_pages + 1)]
        for issue in _check_page_continuity(filenames):
            all_issues.append(issue)

        # C6: 源文档关键词覆盖
        if source_text:
            coverage = _check_source_keyword_coverage(page_all_texts, source_text)
            all_issues.append(coverage)

        # C8: 结构完整性
        structure = _check_structure_completeness([p['shapes'] for p in all_shapes])
        all_issues.append(structure)

        # ── 按严重级别分类 ──
        error_types = {'C1_PLACEHOLDER', 'C2_EMPTY_PAGE', 'C7_GARBLED'}
        warning_types = {'C3_CONTENT_MATCH', 'C4_REDUNDANCY', 'C5_PAGE_CONTINUITY',
                         'C8_STRUCTURE', 'C9_OUTLIER'}
        info_types = {'C6_SOURCE_COVERAGE'}

        errors = [i for i in all_issues if i['type'] in error_types]
        warnings = [i for i in all_issues if i['type'] in warning_types]
        infos = [i for i in all_issues if i['type'] in info_types]

        # C9 分级
        c9_critical = [i for i in all_issues if i['type'] == 'C9_OUTLIER' and i.get('tier') == 'critical']
        c9_warning = [i for i in all_issues if i['type'] == 'C9_OUTLIER' and i.get('tier') != 'critical']

        # 折叠 + 评分卡
        collapsed = _collapse_issues(all_issues)
        scorecard = _build_page_scorecard(all_issues, total_pages)

        # 生成结论
        conclusion_text = _build_conclusion(
            total_pages, collapsed, errors, warnings, infos,
            c9_critical, c9_warning, scorecard,
        )

        summary = {
            'total_pages': total_pages,
            'total_issues': len(all_issues),
            'error_count': len(errors),
            'warning_count': len(warnings),
            'info_count': len(infos),
            'critical_count': len(c9_critical),
            'passed': len(errors) == 0,
            'conclusion': conclusion_text,
            'check_types': {
                'C1_placeholder': any(i['type'] == 'C1_PLACEHOLDER' for i in all_issues),
                'C2_empty': any(i['type'] == 'C2_EMPTY_PAGE' for i in all_issues),
                'C3_type_match': any(i['type'] == 'C3_CONTENT_MATCH' for i in all_issues),
                'C4_redundancy': any(i['type'] == 'C4_REDUNDANCY' for i in all_issues),
                'C5_continuity': any(i['type'] == 'C5_PAGE_CONTINUITY' for i in all_issues),
                'C6_source_coverage': any(i['type'] == 'C6_SOURCE_COVERAGE' for i in all_issues),
                'C7_encoding': any(i['type'] == 'C7_GARBLED' for i in all_issues),
                'C8_structure': any(i['type'] == 'C8_STRUCTURE' for i in all_issues),
                'C9_outlier': any(i['type'] == 'C9_OUTLIER' for i in all_issues),
            },
        }

        return QualityReport(
            file=pptx_path,
            total_pages=total_pages,
            summary=summary,
            issues=all_issues,
            collapsed=collapsed,
            scorecard=scorecard,
        )


# ───────────────────────────────────────────
# 报告类
# ───────────────────────────────────────────

class QualityReport:
    """内容质量检查报告。"""

    def __init__(self, file: str, total_pages: int, summary: Dict, issues: List[Dict],
                 collapsed: Dict = None, scorecard: List[Dict] = None):
        self.file = file
        self.total_pages = total_pages
        self.summary = summary
        self.issues = issues
        self.collapsed = collapsed or {}
        self.scorecard = scorecard or []

    def to_dict(self) -> Dict:
        d = {
            'file': self.file,
            'total_pages': self.total_pages,
            'summary': self.summary,
            'collapsed_issues': self.collapsed,
            'page_scorecard': self.scorecard,
            'issues': self.issues,
        }
        # 顶级结论
        if self.summary and 'conclusion' in self.summary:
            d['conclusion'] = self.summary['conclusion']
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def print_summary(self):
        """打印人类可读的摘要。"""
        s = self.summary
        print(f"\n{'=' * 60}")
        print(f"  PPT 内容质量检查报告")
        print(f"{'=' * 60}")
        print(f"  文件: {self.file}")
        print(f"  页数: {s['total_pages']}")
        print(f"  总问题: {s['total_issues']}")
        print(f"    ERROR:   {s['error_count']}")
        print(f"    WARNING: {s['warning_count']}")
        print(f"    INFO:    {s['info_count']}")
        passed_text = '\u2705 是' if s['passed'] else '\u274c 否'
        print(f"  通过: {passed_text}")
        print(f"{'=' * 60}")

        if self.issues:
            print(f"\n  问题详情:")
            for issue in self.issues:
                page = issue.get('page', '-')
                level = '[ERROR]' if issue['type'] in ('C1_PLACEHOLDER', 'C2_EMPTY_PAGE', 'C7_GARBLED') \
                    else '[WARN]' if issue['type'] != 'C6_SOURCE_COVERAGE' else '[INFO]'
                detail = issue.get('detail', '')
                print(f"  {level} 第{page}页 [{issue['type']}] {detail}")


# ───────────────────────────────────────────
# CLI
# ───────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='PPT 内容质量检查 - 基于内容的全面分析',
    )
    parser.add_argument('pptx', help='PPTX 文件路径')
    parser.add_argument('--sources', '-s', help='源文档文本文件路径（用于 C6 关键词覆盖）')
    parser.add_argument('--report', '-r', help='报告输出 JSON 文件路径')
    parser.add_argument('--quiet', '-q', action='store_true', help='静默模式')

    args = parser.parse_args()

    # 读取源文档
    source_text = None
    if args.sources:
        source_path = Path(args.sources)
        if source_path.exists():
            source_text = source_path.read_text(encoding='utf-8')

    # 执行检查
    checker = ContentQualityChecker()
    report = checker.check(args.pptx, source_text=source_text)

    # 输出
    if not args.quiet:
        report.print_summary()

    # 保存报告
    output_path = args.report or Path(args.pptx).stem + '_quality_report.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report.to_json())
    if not args.quiet:
        print(f"\n报告已保存到: {output_path}")
