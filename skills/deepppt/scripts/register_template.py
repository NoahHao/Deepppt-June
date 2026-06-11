#!/usr/bin/env python3
"""Backward-compatibility shim → scripts/tools/register_template.py"""
import sys, runpy; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
runpy.run_path(str(Path(__file__).parent / "tools" / "register_template.py"), run_name="__main__")
