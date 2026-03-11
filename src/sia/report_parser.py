from __future__ import annotations

import re
from pathlib import Path


def read_html(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()


def strip_tags(text: str) -> str:
    return re.sub(r"<.*?>", "", text).strip()


def extract_label_value(text: str, label: str) -> str | None:
    match = re.search(
        rf'<div class="label">{re.escape(label)}</div><div class="value">(.*?)</div>',
        text,
        re.S,
    )
    if not match:
        return None
    return strip_tags(match.group(1))


def extract_first_label_value(text: str, labels: tuple[str, ...] | list[str]) -> str | None:
    for label in labels:
        value = extract_label_value(text, label)
        if value:
            return value
    return None


def extract_heading_paragraph(text: str, heading: str) -> str | None:
    match = re.search(rf"<h2>{re.escape(heading)}</h2>\s*<p>(.*?)</p>", text, re.S)
    if not match:
        return None
    return strip_tags(match.group(1))


def extract_chip_value(text: str, label: str) -> str | None:
    match = re.search(rf">{re.escape(label)}([^<]*)<", text)
    if not match:
        return None
    return match.group(1).strip()
