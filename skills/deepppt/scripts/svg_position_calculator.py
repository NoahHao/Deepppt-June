#!/usr/bin/env python3
"""Backward-compatibility shim → scripts/export/svg_position_calculator.py"""
import sys, runpy; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "export"))
sys.path.insert(0, str(Path(__file__).parent))
runpy.run_path(str(Path(__file__).parent / "export" / "svg_position_calculator.py"), run_name="__main__")
