from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass
class TaskSpec:
    title: str = ""
    goal: str = ""
    requirements: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$")
_SECTION_MAP = {
    "goal": "goal",
    "requirements": "requirements",
    "constraints": "constraints",
    "acceptance criteria": "acceptance",
    "acceptance": "acceptance",
}


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().rstrip(":")).lower()


def _strip_list_marker(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^[-*+]\s+", "", value)
    value = re.sub(r"^\d+[.)]\s+", "", value)
    value = re.sub(r"^\[(?:\s|x|X)\]\s*", "", value)
    return value.strip()


def _parse_list(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        cleaned = _strip_list_marker(line)
        if cleaned:
            items.append(cleaned)
    return items


def _parse_goal(lines: list[str]) -> str:
    parts = _parse_list(lines)
    return " ".join(parts)


def parse_task_issue(markdown: str) -> TaskSpec:
    lines = markdown.splitlines()
    sections: dict[str, list[str]] = {
        "goal": [],
        "requirements": [],
        "constraints": [],
        "acceptance": [],
    }

    title = ""
    current_section: str | None = None

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            heading_text = match.group(1).strip()
            normalized = _normalize_heading(heading_text)
            mapped = _SECTION_MAP.get(normalized)
            current_section = mapped

            if not title and line.lstrip().startswith("# "):
                if normalized not in _SECTION_MAP:
                    title = heading_text
            continue

        if current_section is not None:
            sections[current_section].append(line)

    return TaskSpec(
        title=title,
        goal=_parse_goal(sections["goal"]),
        requirements=_parse_list(sections["requirements"]),
        constraints=_parse_list(sections["constraints"]),
        acceptance=_parse_list(sections["acceptance"]),
    )
