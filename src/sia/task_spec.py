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
    unknown_sections: list[str] = field(default_factory=list)


# 템플릿 기반 1회형 스펙 (여기만 수정하면 템플릿 키워드 정책을 통합 변경 가능)
TASK_TEMPLATE_SECTION_ALLOWLIST = {
    "goal": ("Goal", "goal"),
    "requirements": ("Requirements", "requirements"),
    "constraints": ("Constraints (must obey)", "constraints (must obey)", "constraints"),
    "acceptance": ("Acceptance criteria", "acceptance criteria", "acceptance"),
}

TASK_TEMPLATE_SECTION_DENYLIST = (
    "Work type",
    "Exceptions (only if needed)",
    "Exception reason",
)
TASK_TEMPLATE_REQUIRED_SECTION_KEYS = ("goal", "requirements", "constraints", "acceptance")
TASK_TEMPLATE_REQUIRED_SECTION_LABELS = (
    TASK_TEMPLATE_SECTION_ALLOWLIST["goal"][0],
    TASK_TEMPLATE_SECTION_ALLOWLIST["requirements"][0],
    TASK_TEMPLATE_SECTION_ALLOWLIST["constraints"][0],
    TASK_TEMPLATE_SECTION_ALLOWLIST["acceptance"][0],
)

_ALLOWED_SECTIONS = frozenset(
    alias for aliases in TASK_TEMPLATE_SECTION_ALLOWLIST.values() for alias in aliases
)
_DENIED_SECTIONS = frozenset(TASK_TEMPLATE_SECTION_DENYLIST)


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$")
_BOLD_FIELD_RE = re.compile(r"^\s*\*\*(.+?)\*\*:?(\s*)?(.*)?$")


def _section_to_canonical(text: str) -> str | None:
    normalized = _normalize_heading(text)
    for canonical, aliases in TASK_TEMPLATE_SECTION_ALLOWLIST.items():
        for alias in aliases:
            if normalized == _normalize_heading(alias):
                return canonical
    return None


def _is_denied_section(text: str) -> bool:
    normalized = _normalize_heading(text)
    return any(normalized == _normalize_heading(deny) for deny in _DENIED_SECTIONS)


def _add_unknown_section(unknown_sections: list[str], section_name: str) -> None:
    cleaned = section_name.strip().strip("#").strip()
    if not cleaned:
        return
    normalized = _normalize_heading(cleaned)
    if normalized in {_normalize_heading(x) for x in _ALLOWED_SECTIONS}:
        return
    if normalized in {_normalize_heading(x) for x in _DENIED_SECTIONS}:
        return
    if cleaned not in unknown_sections:
        unknown_sections.append(cleaned)




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
    unknown_sections: list[str] = []

    title = ""
    current_section: str | None = None

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            heading_text = match.group(1).strip()
            is_title_heading = (
                not title
                and line.lstrip().startswith("# ")
                and _section_to_canonical(heading_text) is None
                and not _is_denied_section(heading_text)
            )
            mapped = _section_to_canonical(heading_text)
            if mapped is not None:
                current_section = mapped
            else:
                if _is_denied_section(heading_text):
                    current_section = None
                else:
                    if not is_title_heading:
                        _add_unknown_section(unknown_sections, heading_text)
                    current_section = None

            if not title and line.lstrip().startswith("# "):
                mapped_title = _section_to_canonical(heading_text)
                if mapped_title is None and not _is_denied_section(heading_text):
                    title = heading_text
            continue

        label_match = _BOLD_FIELD_RE.match(line)
        if label_match:
            label = label_match.group(1).strip()
            inline_value = (label_match.group(3) or "").strip()
            mapped = _section_to_canonical(label)
            if mapped is not None:
                current_section = mapped
                if inline_value:
                    sections[current_section].append(inline_value)
                continue
            if not _is_denied_section(label):
                _add_unknown_section(unknown_sections, label)
                current_section = None
            else:
                current_section = None
            continue

        if current_section is not None:
            sections[current_section].append(line)

    return TaskSpec(
        title=title,
        goal=_parse_goal(sections["goal"]),
        requirements=_parse_list(sections["requirements"]),
        constraints=_parse_list(sections["constraints"]),
        acceptance=_parse_list(sections["acceptance"]),
        unknown_sections=unknown_sections,
    )
