# mirror_fill — Search-then-replace XML-based PPTX content filling module
#
# This module inherits the XML-replacement strategy from style_convert's
# orchestrator.py. Instead of translating texts, it searches a KB corpus
# (local + web) for user-specified fields, then fills the gaps discovered
# during slide generation.
#
# Architecture:
#   search_and_fill.py  ─→  LLM_Search  ─→  filler.py (XML replace)
#                          ↕                         ↑
#                     regions.py           slide XML on disk
#
from .filler import MirrorFiller
from .regions import SlideRegion, PRESET_LAYOUTS, get_layout, custom_layout, SLIDE_W, SLIDE_H
from .search_and_fill import SearchAndFillFiller, ExecutorBase, SearchResultItem

__all__ = [
    "MirrorFiller",
    "SlideRegion", "PRESET_LAYOUTS", "get_layout", "custom_layout", "SLIDE_W", "SLIDE_H",
    "SearchAndFillFiller", "ExecutorBase", "SearchResultItem",
]
