#!/usr/bin/env python3
"""Backward-compatibility shim → scripts/image/rotate_images.py"""
import sys, runpy; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "image"))
sys.path.insert(0, str(Path(__file__).parent))
runpy.run_path(str(Path(__file__).parent / "image" / "rotate_images.py"), run_name="__main__")
