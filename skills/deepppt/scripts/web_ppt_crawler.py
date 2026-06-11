#!/usr/bin/env python3
"""Backward-compatibility shim → scripts/tools/web_ppt_crawler.py"""
import sys, runpy; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
runpy.run_path(str(Path(__file__).parent / "tools" / "web_ppt_crawler.py"), run_name="__main__")
