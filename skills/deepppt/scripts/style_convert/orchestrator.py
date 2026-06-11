#!/usr/bin/env python3
"""
Style Convert CLI — PPTX style and language conversion tool.

Commands:
    extract    Extract text for AI translation
    apply      Apply translation map to PPTX
    bg         Convert background color (white↔black)
    batch      Full pipeline: extract → translate → apply + bg

Usage:
    # Extract Chinese texts for translation
    python style_convert/orchestrator.py extract input.pptx -o texts.json

    # Apply translations
    python style_convert/orchestrator.py apply input.pptx output.pptx -m translations.json

    # Convert background
    python style_convert/orchestrator.py bg input.pptx output.pptx --to black

    # Full batch: extract + (AI translates) + apply + bg
    python style_convert/orchestrator.py batch input.pptx output_dir/ -l en -m translations.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent scripts/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from style_convert.core import (
    extract_texts, extract_unique_texts,
    apply_translations, convert_bg, batch_convert,
    verify_pptx,
)


def cmd_extract(args):
    """Extract Chinese text from PPTX for translation."""
    entries = extract_texts(args.input, args.lang if args.lang == 'zh' else 'zh')
    unique = extract_unique_texts(args.input, args.lang if args.lang == 'zh' else 'zh')

    print(f"📋 Extracted {len(entries)} text elements ({len(unique)} unique):\n")

    output = {"source": args.input, "total_elements": len(entries),
              "unique_texts": len(unique), "texts": unique}

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved to: {args.output}")
    else:
        for i, t in enumerate(unique):
            print(f"  [{i}] {t}")
        print(f"\n💡 Pass this list to AI for translation, then use 'apply' with the map.")

    return 0


def cmd_apply(args):
    """Apply translation map to PPTX."""
    if not args.map:
        print("❌ --map <file> is required (JSON: {\"Chinese\": \"English\", ...})")
        return 1

    with open(args.map, encoding='utf-8') as f:
        translation_map = json.load(f)

    result = apply_translations(args.input, args.output, translation_map)

    print(f"✅ Applied {result['applied']} translations → {args.output}")
    if result.get('unmapped'):
        print(f"⚠️  {len(result['unmapped'])} texts unmapped:")
        for u in result['unmapped'][:5]:
            print(f"    - {u}")
        if len(result['unmapped']) > 5:
            print(f"    ... and {len(result['unmapped'])-5} more")

    # Auto-verify translation completeness
    if not args.no_verify:
        _auto_verify(args.output, lang='zh', label="Translation Verification")
    return 0


def cmd_bg(args):
    """Convert background color."""
    direction = 'white_to_black' if args.to == 'black' else 'black_to_white'
    expected_bg = '000000' if args.to == 'black' else 'FFFFFF'
    convert_bg(args.input, args.output, direction)

    # Auto-verify background color on every slide
    if not args.no_verify:
        _auto_verify(args.output, expected_bg=expected_bg, label="Background Verification")
    return 0


def cmd_verify(args):
    """Run standalone verification on a PPTX file."""
    result = verify_pptx(args.input, expected_bg=args.bg, lang=args.check_lang)
    _print_verify_report(result, "Verification")
    return 0 if result['pass'] else 1


def cmd_batch(args):
    """Full batch pipeline."""
    if not args.map:
        print("❌ --map <file> is required for batch mode")
        return 1

    with open(args.map, encoding='utf-8') as f:
        translation_map = json.load(f)

    styles = []
    if args.convert_bg:
        styles.append('black')
    if args.translate:
        styles.append('english')

    results = batch_convert(args.input, args.output, tuple(styles), translation_map)

    print(f"\n{'='*50}")
    print(f"  Batch Complete")
    print(f"{'='*50}")
    for style, path in results.items():
        if style != 'translation_stats':
            print(f"  {style}: {path}")
    stats = results.get('translation_stats', {})
    if stats:
        print(f"  Translations: {stats.get('applied', 0)} applied, "
              f"{len(stats.get('unmapped', []))} unmapped")
    return 0


def _print_verify_report(result, label="Verification"):
    """Print a human-readable verification report."""
    if result.get('error'):
        print(f"[{label}] ERROR: {result['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  {label} Report — {result['total_slides']} slides")
    print(f"{'='*60}")

    summary = result['summary']
    bg_line = f"  Background:  {summary['bg_ok']}/{summary['bg_total']} OK"
    trans_line = f"  Translation: {summary['translation_ok']}/{summary['translation_total']} OK"
    overflow_line = f"  Overflow:    {summary['overflow_ok']}/{summary['overflow_total']} OK"

    if summary['bg_ok'] == summary['bg_total']:
        print(f"{bg_line}  [PASS]")
    else:
        print(f"{bg_line}  [FAIL]")

    if summary['translation_ok'] == summary['translation_total']:
        print(f"{trans_line}  [PASS]")
    else:
        print(f"{trans_line}  [FAIL]")

    if summary['overflow_ok'] == summary['overflow_total']:
        print(f"{overflow_line}  [PASS]")
    else:
        print(f"{overflow_line}  [WARN]")

    # Per-slide details for failed pages
    failed = [s for s in result['slides'] if not s['pass']]
    if failed:
        print(f"\n  [FAILED SLIDES]")
        for s in failed:
            print(f"  --- Slide {s['slide_num']} ---")
            if not s['bg']['ok']:
                if s['bg'].get('error'):
                    print(f"    BG: {s['bg']['error']}")
                else:
                    print(f"    BG: expected={s['bg']['expected']} actual={s['bg']['value']}")
            if not s['translation']['ok']:
                print(f"    Translation: {s['translation']['remaining_chinese']} "
                      f"Chinese chars remaining")
                for sample in s['translation']['samples'][:3]:
                    print(f"      -> \"{sample}\"")
            if not s['overflow_risk']['ok']:
                for lt in s['overflow_risk']['long_texts'][:3]:
                    print(f"    Overflow risk: len={lt['len']} \"{lt['text']}\"")

    overall = "PASS" if result['pass'] else "FAIL"
    print(f"\n  Overall: [{overall}]")
    print(f"{'='*60}\n")


def _auto_verify(output_path, expected_bg=None, lang=None, label="Auto-Verify"):
    """Run verification after conversion and print report."""
    if not os.path.exists(output_path):
        print(f"[{label}] Output file not found, skipping verification.")
        return
    result = verify_pptx(output_path, expected_bg=expected_bg, lang=lang)
    _print_verify_report(result, label)


def main():
    # Fix Windows GBK console encoding
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="PPTX Style & Language Conversion Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='command', help='Available commands')

    # extract
    p_extract = sub.add_parser('extract', help='Extract text for translation')
    p_extract.add_argument('input', help='Input PPTX file')
    p_extract.add_argument('-o', '--output', help='Output JSON file')
    p_extract.add_argument('-l', '--lang', default='zh', help='Source language (default: zh)')

    # apply
    p_apply = sub.add_parser('apply', help='Apply translation map')
    p_apply.add_argument('input', help='Input PPTX file')
    p_apply.add_argument('output', help='Output PPTX file')
    p_apply.add_argument('-m', '--map', required=True, help='Translation map JSON file')
    p_apply.add_argument('--no-verify', action='store_true',
                         help='Skip auto-verification after conversion')

    # bg
    p_bg = sub.add_parser('bg', help='Convert background color')
    p_bg.add_argument('input', help='Input PPTX file')
    p_bg.add_argument('output', help='Output PPTX file')
    p_bg.add_argument('--to', choices=['black', 'white'], default='black',
                      help='Target background (default: black)')
    p_bg.add_argument('--no-verify', action='store_true',
                      help='Skip auto-verification after conversion')

    # verify (standalone)
    p_verify = sub.add_parser('verify', help='Verify PPTX output quality')
    p_verify.add_argument('input', help='PPTX file to verify')
    p_verify.add_argument('--bg', help='Expected background color hex (e.g. 000000)')
    p_verify.add_argument('--check-lang', default='zh',
                          help='Source language to check for residual chars (default: zh)')

    # batch
    p_batch = sub.add_parser('batch', help='Full pipeline: extract + apply + bg')
    p_batch.add_argument('input', help='Input PPTX file')
    p_batch.add_argument('output', help='Output directory')
    p_batch.add_argument('-m', '--map', help='Translation map JSON file')
    p_batch.add_argument('--translate', action='store_true', default=True,
                         help='Apply translations (default: True)')
    p_batch.add_argument('--convert-bg', action='store_true',
                         help='Also convert background color')

    args = parser.parse_args()

    if args.command == 'extract':
        return cmd_extract(args)
    elif args.command == 'apply':
        return cmd_apply(args)
    elif args.command == 'bg':
        return cmd_bg(args)
    elif args.command == 'verify':
        return cmd_verify(args)
    elif args.command == 'batch':
        return cmd_batch(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
