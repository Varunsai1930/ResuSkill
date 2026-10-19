"""Constrained presentation settings; never accept executable HTML or CSS."""
from __future__ import annotations

import copy
import re

from . import input_schema, store
from .util import ResuError

DEFAULT = {
    "font": "sans", "font_size_pt": 10.5, "name_size_pt": 19,
    "line_height": 1.38, "margin_mm": 15, "section_gap_pt": 9,
    "accent": "#1f3a5f", "rule": "#c9c9c9", "uppercase_name": False,
    "link_labels": False, "degree_first": False,
    "projects_heading": "Projects", "skills_heading": "Skills",
    "section_order": ["summary", "education", "experience", "projects", "skills", "certifications"],
}
RANGES = {"font_size_pt": (9, 12), "name_size_pt": (16, 30), "line_height": (1.1, 1.6),
          "margin_mm": (8, 25), "section_gap_pt": (4, 16)}


def normalize(data=None) -> dict:
    if data is None:
        data = {}
    schema = {k: (int, float) if k in RANGES else type(v) for k, v in DEFAULT.items()}
    schema["section_order"] = [str]
    input_schema.check(data, schema, "style")
    result = copy.deepcopy(DEFAULT)
    result.update(data)
    for key, (low, high) in RANGES.items():
        if not low <= result[key] <= high:
            raise ResuError(f"style.{key} must be between {low} and {high}")
    for key in ("accent", "rule"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", result[key]):
            raise ResuError(f"style.{key} must be a six-digit hex color")
    for key, choices in (("font", ("sans", "serif")), ("projects_heading", ("Projects", "Project Experience")),
                         ("skills_heading", ("Skills", "Technical Skills"))):
        if result[key] not in choices:
            raise ResuError(f"style.{key} must be one of {', '.join(choices)}")
    order = result["section_order"]
    if len(order) != len(DEFAULT["section_order"]) or set(order) != set(DEFAULT["section_order"]):
        raise ResuError("style.section_order must contain every section exactly once; omit content in the proposal, not the style")
    return result


def saved(folder) -> dict:
    return normalize(store.read_json(folder / "style.json"))


def css(data) -> str:
    s = normalize(data)
    font = 'Georgia, "Times New Roman", serif' if s["font"] == "serif" else '"Helvetica Neue", Arial, "Segoe UI", sans-serif'
    return f"""
@page {{ margin: {s['margin_mm']}mm; }}
:root {{ --accent: {s['accent']}; --rule: {s['rule']}; }}
body {{ padding: {s['margin_mm']}mm; font-family: {font}; font-size: {s['font_size_pt']}pt; line-height: {s['line_height']}; }}
h1 {{ font-size: {s['name_size_pt']}pt; text-transform: {'uppercase' if s['uppercase_name'] else 'none'}; }}
section {{ margin-top: {s['section_gap_pt']}pt; }}
@media print {{ body {{ padding: 0; }} }}
"""
