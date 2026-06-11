#!/usr/bin/env python3
"""
PPT Quality Check — 统一质量检查入口
=====================================
一次执行，完成全部检查：

  必检（始终运行）：
    内容质量检查 (C1-C9) — 占位符、空页、冗余、离群、编码等

  可选（通过参数启用）：
    框架匹配检查 (Gate Check) — 检查 PPT 是否遵循预设演示框架
    源文档覆盖检查 (C6)  — 验证原始材料关键要点是否出现

用法：
  python main.py <pptx_file>                              # 仅内容质量检查
  python main.py <pptx_file> -s source.md                 # 带源文档关键词覆盖
  python main.py <pptx_file> -t configs/product_pitch.yaml # 带框架匹配检查
  python main.py <pptx_file> -s source.md -t configs/product_pitch.yaml  # 全部检查

报告默认保存到 report/ 目录。
"""

import sys
import json
import argparse
from pathlib import Path

# 修复 Windows 控制台 GBK 编码输出乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() in ('gbk', 'cp936', 'cp950'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 确保引擎目录在 path 中
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPORT_DIR = _SCRIPT_DIR / 'report'
_REPORT_DIR.mkdir(parents=True, exist_ok=True)

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engine.content_quality_checker import ContentQualityChecker
from engine.gate_checker import GateChecker


def _run_gate_check(pptx_path: str, template_config: str) -> dict:
    """运行框架匹配检查。"""
    try:
        checker = GateChecker(str(Path(template_config).resolve()))
        return checker.check(pptx_path)
    except Exception as e:
        return {'error': str(e), 'detail': 'Gate check 执行失败'}


def _run_content_check(pptx_path: str, source_text: str = None) -> dict:
    """运行内容质量检查。"""
    try:
        checker = ContentQualityChecker()
        report = checker.check(pptx_path, source_text=source_text)
        return report.to_dict()
    except Exception as e:
        return {'error': str(e), 'detail': 'Content check 执行失败'}


def main():
    parser = argparse.ArgumentParser(
        description='PPT Quality Check — 内容质量 + 框架匹配全面检查',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py sample.pptx
  python main.py sample.pptx configs/product_pitch.yaml            # 位置传参
  python main.py sample.pptx -t configs/product_pitch.yaml         # 显式传参
  python main.py sample.pptx -s source.md -t configs/product_pitch.yaml
  python main.py sample.pptx -r my_report.json
        """,
    )
    parser.add_argument('pptx', help='PPTX 文件路径')
    parser.add_argument('template_pos', nargs='?', default=None,
                        help='Gate check 模板配置（可选位置参数，支持 .yaml/.yml）')
    parser.add_argument('--sources', '-s', help='源文档路径（用于 C6 关键词覆盖检查）')
    parser.add_argument('--template', '-t', help='Gate check 模板配置文件路径（显式指定，优先于位置参数）')
    parser.add_argument('--report', '-r', help='报告文件名（默认自动生成，保存到 report/ 目录）')
    parser.add_argument('--quiet', '-q', action='store_true', help='静默模式')

    args = parser.parse_args()

    # 模板路径：-t 显式 > 位置参数 > None
    template_arg = args.template or args.template_pos
    if template_arg and not template_arg.endswith(('.yaml', '.yml')):
        print(f'警告: 模板文件扩展名不是 .yaml/.yml，已忽略位置参数 "{template_arg}"')
        print(f'  如需指定模板请使用: python main.py <pptx> -t <template.yaml>')
        template_arg = None

    pptx_path = args.pptx
    if not Path(pptx_path).exists():
        print(f'错误: 文件不存在 - {pptx_path}')
        sys.exit(1)

    # 读取源文档
    source_text = None
    if args.sources:
        src_path = Path(args.sources)
        if src_path.exists():
            source_text = src_path.read_text(encoding='utf-8')
        else:
            print(f'警告: 源文档不存在 - {args.sources}')

    final_report = {
        'file': str(Path(pptx_path).resolve()),
        'file_name': Path(pptx_path).name,
        'checks': {},
    }

    # ── 1. 内容质量检查（始终执行） ──
    if not args.quiet:
        print('=' * 60)
        print('  [1/2] 内容质量检查 (C1-C9)')
        print('=' * 60)

    content_result = _run_content_check(pptx_path, source_text)
    final_report['checks']['content_quality'] = content_result
    # 将内容质量结论提升到报告顶层
    if 'conclusion' in content_result:
        final_report['conclusion'] = content_result['conclusion']

    if not args.quiet and 'summary' in content_result:
        s = content_result['summary']
        print(f"  总问题: {s['total_issues']}  (ERROR={s['error_count']}  CRITICAL={s.get('critical_count',0)}  WARNING={s['warning_count']}  INFO={s['info_count']})")
        passed = '通过' if s['passed'] else '未通过'
        print(f"  内容质量: {passed}")
        # 打印结论
        conclusion = content_result.get('conclusion', '')
        if conclusion:
            print(f"\n  ┌─ 综合结论 ──────────────────────")
            for line in conclusion.split('\n'):
                print(f"  │ {line}")
            print(f"  └──────────────────────────────────")
        else:
            print(f"")

    # ── 2. Gate Check（可选） ──
    if template_arg:
        template_path = Path(template_arg)
        if not template_path.exists():
            print(f'\n警告: 模板配置不存在 - {template_arg}')
        else:
            if not args.quiet:
                print(f'\n{"=" * 60}')
                print(f'  [2/2] 框架匹配检查 ({template_path.stem})')
                print(f'{"=" * 60}')

            gate_result = _run_gate_check(pptx_path, str(template_path.resolve()))
            final_report['checks']['gate_check'] = gate_result

            if not args.quiet and 'summary' in gate_result:
                gs = gate_result['summary']
                passed = '通过' if gs['passed'] else '未通过'
                print(f"  框架匹配: {passed}")
                print(f"  匹配页面: {gs.get('matched_pages_count', 0)}  缺失阶段: {gs.get('missing_count', 0)}")
                print(f"  弱标题: {gs.get('weak_titles_count', 0)}  空标题: {gs.get('empty_titles_count', 0)}  描述性: {gs.get('neutral_titles_count', 0)}")
                # 打印详细解释
                explanation = gs.get('explanation', '')
                if explanation:
                    print(f"\n  ┌─ 框架检查详情 ──────────────────")
                    for line in explanation.split('\n'):
                        print(f"  │ {line}")
                    print(f"  └──────────────────────────────────")

    # ── 3. 综合判定 ──
    all_passed = True
    reasons = []

    cs = content_result.get('summary', {})
    if not cs.get('passed', True):
        all_passed = False
        reasons.append(f"内容质量: {cs['error_count']} 个 ERROR")

    if template_arg and 'gate_check' in final_report['checks']:
        gs = final_report['checks']['gate_check'].get('summary', {})
        if not gs.get('passed', True):
            all_passed = False
            reasons.append(f"框架匹配: 未通过")

    final_report['overall_passed'] = all_passed
    if reasons:
        final_report['overall_reason'] = '; '.join(reasons)

    # ── 4. 保存报告 ──
    if args.report:
        report_name = args.report
        if not report_name.endswith('.json'):
            report_name += '.json'
        output_path = _REPORT_DIR / report_name
    else:
        # 自动生成报告文件名：{pptx_name}_{timestamp}.json
        from datetime import datetime
        stem = Path(pptx_path).stem
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = _REPORT_DIR / f'{stem}_{ts}.json'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        print(f'\n{"=" * 60}')
        print(f'  综合判定: {"通过" if all_passed else "未通过"}')
        if reasons:
            for r in reasons:
                print(f'    - {r}')
        print(f'  报告: {output_path}')
        print(f'{"=" * 60}')

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
