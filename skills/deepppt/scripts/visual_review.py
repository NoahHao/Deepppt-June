#!/usr/bin/env python3
"""Backward-compatibility shim → scripts/tools/visual_review.py"""
import sys, runpy; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
runpy.run_path(str(Path(__file__).parent / "tools" / "visual_review.py"), run_name="__main__")
