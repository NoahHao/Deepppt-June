#!/usr/bin/env python3
"""Backward-compatibility shim → scripts/tools/update_spec.py"""
import sys, runpy; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
_target_path = str(Path(__file__).parent / "tools" / "update_spec.py")
if __name__ == '__main__':
    runpy.run_path(_target_path, run_name="__main__")
else:
    # Imported by downstream tools (e.g. svg_quality_checker.py):
    # run silently without triggering argparse.
    _target = runpy.run_path(_target_path, run_name="update_spec")
    parse_lock = _target.get("parse_lock")

