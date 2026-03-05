from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
from pathlib import Path

from .pr_rules import run_rules
from .task_spec import (
    TASK_TEMPLATE_REQUIRED_SECTION_KEYS,
    TASK_TEMPLATE_REQUIRED_SECTION_LABELS,
    parse_task_issue,
)


SIA_REQUIRED_SCHEDULE_KEYWORDS = [
    "15분",
    "15분 지연",
    "15min",
    "15 minute",
    "poll",
    "interval",
]

SIA_OPTIONAL_SCHEDULE_KEYWORDS = [
    "주기",
    "every",
    "분봉",
    "주기적",
    "분 간격",
    "분간격",
    "분단위",
    "정기",
]

SIA_REQUIRED_DATA_KEYWORDS = [
    "종가",
    "클로즈",
    "close",
    "finnhub",
    "marketaux",
    "polygon",
    "시세",
    "주가",
    "티커",
    "ticker",
]

SIA_OPTIONAL_DATA_KEYWORDS = [
    "price",
    "가격",
    "뉴스",
    "news",
    "데이터",
    "수집",
    "api",
    "국내",
    "해외",
]

SIA_REQUIRED_OPERATION_KEYWORDS = [
    "sqlite",
    "db",
    "telegram",
    "텔레그램",
    "알림",
]

SIA_OPTIONAL_OPERATION_KEYWORDS = [
    "로그",
    "log",
    "error",
    "오류",
    "운영",
    "rollback",
    "복구",
    "재시도",
    "에러",
    "환경",
    "예외",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sia")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_issue = subparsers.add_parser("parse-issue")
    parse_issue.add_argument("--file", required=True)
    parse_issue.add_argument(
        "--strict",
        action="store_true",
        help="방향성 충돌(자동매매/비의도 변경)이 있으면 비0 반환",
    )
    parse_issue.add_argument(
        "--allow-legacy-template",
        action="store_true",
        help="과거 PR 템플릿(비표준 섹션/알림 누락)을 경고로만 처리해 역사 검증 호환",
    )

    check_pr = subparsers.add_parser("check-pr")
    check_pr.add_argument("--files", required=True)

    return parser


def _join_issue_text(spec: object, raw_text: str = "") -> str:
    goal = getattr(spec, "goal", "") or ""
    requirements = getattr(spec, "requirements", []) or []
    constraints = getattr(spec, "constraints", []) or []
    acceptance = getattr(spec, "acceptance", []) or []

    return " ".join(
        [
            goal,
            " ".join(requirements),
            " ".join(constraints),
            " ".join(acceptance),
            raw_text,
        ]
    ).lower()


def _is_meaningful_text(value: str) -> bool:
    cleaned = re.sub(r"\[[ xX]\]\s*", "", value or "")
    cleaned = re.sub(r"^\s*[-*+]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned.replace("\n", " ").replace("\r", " ")).strip().lower()
    if not cleaned:
        return False
    tokens = [tok for tok in cleaned.split(" ") if len(tok) >= 2]
    return len(tokens) >= 2


def _count_keyword_matches(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _satisfies_keyword_policy(text: str, required: list[str], optional: list[str]) -> tuple[bool, bool]:
    required_hits = _count_keyword_matches(text, required)
    optional_hits = _count_keyword_matches(text, optional)
    return required_hits >= 1, optional_hits >= 1


def _add_guard_event(
    items: list[dict],
    code: str,
    message: str,
    *,
    level: str,
    severity: str,
    section: str | None = None,
) -> None:
    event = {
        "code": code,
        "level": level,
        "message": message,
        "severity": severity,
    }
    if section is not None:
        event["section"] = section
    items.append(event)


def _guard_event_code_list(
    events: list[dict], severity: str | None = None, *, level: str | None = None
) -> list[str]:
    out: list[str] = []
    for event in events:
        if severity is not None and event.get("severity") != severity:
            continue
        if level is not None and event.get("level") != level:
            continue
        out.append(event["code"])
    return out


def _direction_guard(
    spec: object, raw_text: str = "", *, allow_legacy_template: bool = False
) -> dict:
    text = _join_issue_text(spec, raw_text)
    title = (getattr(spec, "title", "") or "").strip()
    unknown_sections = list(getattr(spec, "unknown_sections", []) or [])
    goal = (getattr(spec, "goal", "") or "").lower()
    req = " ".join(getattr(spec, "requirements", []) or []).lower()
    cst = " ".join(getattr(spec, "constraints", []) or []).lower()
    acc = " ".join(getattr(spec, "acceptance", []) or []).lower()
    section_text = " ".join([goal, req, cst, acc]).strip()
    has_sections = any(_is_meaningful_text(chunk) for chunk in [goal, req, cst, acc])

    present_sections = {
        "goal": bool(_is_meaningful_text(goal)),
        "requirements": bool(_is_meaningful_text(req)),
        "constraints": bool(_is_meaningful_text(cst)),
        "acceptance": bool(_is_meaningful_text(acc)),
    }
    missing_required_sections = [
        label
        for label, ok in present_sections.items()
        if not ok
    ]
    blocked = []
    warnings = []
    high_impact_warnings = []
    events: list[dict] = []

    has_notify = any(keyword in text for keyword in ["telegram", "텔레그램", "알림", "notify"])
    if not has_notify:
        if allow_legacy_template:
            warnings.append("요구사항/수락조건에 텔레그램/알림 키워드가 부족합니다.")
            _add_guard_event(
                events,
                "SCOPE-MISSING-TELEGRAM",
                "요구사항/수락조건에 텔레그램/알림 키워드가 부족합니다.",
                level="warning",
                severity="WARN",
            )
        else:
            high_impact_warnings.append("요구사항/수락조건에 텔레그램/알림 키워드가 부족합니다.")
            _add_guard_event(
                events,
                "SCOPE-MISSING-TELEGRAM",
                "요구사항/수락조건에 텔레그램/알림 키워드가 부족합니다.",
                level="high",
                severity="CRITICAL",
            )

    if any(keyword in text for keyword in ["auto trade", "자동매매", "자동 주문", "auto-trading", "실시간 주문", "order execution"]):
        blocked.append("자동매매/자동 주문 관련 변경 의도가 감지되어 프로젝트 방향과 충돌할 수 있습니다.")
        _add_guard_event(
            events,
            "SCOPE-AUTO-ORDER",
            "자동매매/자동 주문 관련 변경 의도가 감지되어 프로젝트 방향과 충돌할 수 있습니다.",
            level="blocked",
            severity="BLOCKED",
        )

    if not any(keyword in text for keyword in ["sma", "rsi", "llm", "뉴스", "news", "sign", "signal", "신호"]):
        warnings.append("시그널/근거 산출 관련 조건이 약하게 드러납니다.")
        _add_guard_event(
            events,
            "SCOPE-WEAK-SIGNAL",
            "시그널/근거 산출 조건이 약하게 작성되어 있습니다.",
            level="warning",
            severity="WARN",
        )

    schedule_required = SIA_REQUIRED_SCHEDULE_KEYWORDS
    schedule_optional = SIA_OPTIONAL_SCHEDULE_KEYWORDS
    schedule_ok, schedule_soft = _satisfies_keyword_policy(
        section_text + " " + text,
        schedule_required,
        schedule_optional,
    )
    if has_sections and not (schedule_ok or schedule_soft):
        high_impact_warnings.append("수집 주기/실행 주기 관련 요구가 부족합니다.")
        _add_guard_event(
            events,
            "SCOPE-SCHEDULE-MISSING",
            "수집 주기/실행 주기 관련 요구가 부족합니다.",
            level="high",
            severity="CRITICAL",
        )
    elif has_sections and schedule_soft and not schedule_ok:
        warnings.append("수집 주기는 확인되나 실행 주기 수치(예: 15분)가 더 명시되면 좋습니다.")
        _add_guard_event(
            events,
            "SCOPE-SCHEDULE-SOFT",
            "수집 주기/실행 주기 수치가 약하게 작성되었습니다.",
            level="warning",
            severity="WARN",
        )

    data_required = SIA_REQUIRED_DATA_KEYWORDS
    data_optional = SIA_OPTIONAL_DATA_KEYWORDS
    data_ok, data_soft = _satisfies_keyword_policy(
        section_text + " " + text,
        data_required,
        data_optional,
    )
    if has_sections and not (data_ok or data_soft):
        high_impact_warnings.append("가격/뉴스 데이터 소스와 취득 근거가 부족합니다.")
        _add_guard_event(
            events,
            "SCOPE-DATA-MISSING",
            "가격/뉴스 데이터 소스와 취득 근거가 부족합니다.",
            level="high",
            severity="CRITICAL",
        )
    elif has_sections and data_soft and not data_ok:
        warnings.append("가격/뉴스 항목은 있으나 구체 소스(종가, Finnhub/Marketaux/Polygon) 기재가 있으면 더 명확합니다.")
        _add_guard_event(
            events,
            "SCOPE-DATA-SOFT",
            "가격/뉴스 항목은 있으나 구체 소스 표기가 부족합니다.",
            level="warning",
            severity="WARN",
        )

    ops_required = SIA_REQUIRED_OPERATION_KEYWORDS
    ops_optional = SIA_OPTIONAL_OPERATION_KEYWORDS
    ops_ok, ops_soft = _satisfies_keyword_policy(
        section_text + " " + text,
        ops_required,
        ops_optional,
    )
    if has_sections and not (ops_ok or ops_soft):
        high_impact_warnings.append("운영 안정성 항목(DB/로그/오류 대체/롤백)이 약합니다.")
        _add_guard_event(
            events,
            "SCOPE-OPS-MISSING",
            "운영 안정성 항목(DB/로그/오류 대응/롤백)이 약합니다.",
            level="high",
            severity="CRITICAL",
        )
    elif has_sections and ops_soft and not ops_ok:
        warnings.append("운영 안정성 키워드는 있으나 DB/로그/재시도/롤백 항목은 더 구체화하면 좋습니다.")
        _add_guard_event(
            events,
            "SCOPE-OPS-SOFT",
            "운영 안정성의 구체 대응 항목(재시도/롤백/로그)을 구체화하세요.",
            level="warning",
            severity="WARN",
        )

    if not has_sections:
        warnings.append("요구사항/제약/수락조건 본문이 비어 있거나 템플릿만 존재할 수 있어 strict는 section 기반 완화 적용")
        _add_guard_event(
            events,
            "SCOPE-EMPTY-SECTIONS",
            "요청 본문이 비어 있거나 템플릿만 존재합니다.",
            level="warning",
            severity="WARN",
        )

    if unknown_sections:
        unknown_sections_text = ", ".join(sorted(unknown_sections))
        if allow_legacy_template:
            warnings.append(
                f"템플릿 비표준 섹션 탐지: {unknown_sections_text}. "
                "과거 템플릿 호환 모드에서 경고로 기록."
            )
            _add_guard_event(
                events,
                "SCOPE-UNKNOWN-SECTIONS",
                f"템플릿 비표준 섹션 탐지: {unknown_sections_text}",
                level="warning",
                severity="WARN",
            )
        else:
            high_impact_warnings.append(
                f"템플릿 비표준 섹션 탐지: {unknown_sections_text}. "
                "핵심 섹션은 Goal/Requirements/Constraints (must obey)/Acceptance criteria만 사용하세요."
            )
            _add_guard_event(
                events,
                "SCOPE-UNKNOWN-SECTIONS",
                f"템플릿 비표준 섹션 탐지: {unknown_sections_text}",
                level="high",
                severity="CRITICAL",
            )
            if has_sections:
                blocked.append(
                    f"템플릿 외부 섹션 사용으로 가이드 이탈 가능성: {unknown_sections_text}"
                )
                _add_guard_event(
                    events,
                    "SCOPE-UNKNOWN-SECTIONS",
                    f"템플릿 외부 섹션 사용으로 가이드 이탈 가능성: {unknown_sections_text}",
                    level="blocked",
                    severity="BLOCKED",
                )

    if has_sections and missing_required_sections:
        required_label_map = dict(
            zip(
                TASK_TEMPLATE_REQUIRED_SECTION_KEYS,
                TASK_TEMPLATE_REQUIRED_SECTION_LABELS,
            )
        )
        section_names = ", ".join([required_label_map[k] for k in missing_required_sections])
        high_impact_warnings.append(f"핵심 섹션 누락: {section_names}")
        for key in missing_required_sections:
            _add_guard_event(
                events,
                "SCOPE-TEMPLATE-MISSING-SECTION",
                f"필수 섹션 누락: {required_label_map[key]}",
                level="high",
                severity="CRITICAL",
                section=key,
            )

    if has_sections and len(missing_required_sections) == len(TASK_TEMPLATE_REQUIRED_SECTION_KEYS):
        blocked.append(
            "요청 본문이 템플릿 핵심 섹션을 모두 비워 방향성 확인이 불가능합니다."
        )
        _add_guard_event(
            events,
            "SCOPE-TEMPLATE-BLANK",
            "요청 본문이 템플릿 핵심 섹션을 모두 비워 방향성 확인이 불가능합니다.",
            level="blocked",
            severity="BLOCKED",
        )

    if not title:
        high_impact_warnings.append("제목이 비어 있어 감사/추적이 어렵습니다.")
        _add_guard_event(
            events,
            "SCOPE-MISSING-TITLE",
            "제목이 비어 있어 추적이 어렵습니다.",
            level="high",
            severity="CRITICAL",
        )

    return {
        "ok": len(blocked) == 0,
        "blocked": blocked,
        "high_impact_warnings": high_impact_warnings,
        "warnings": warnings,
        "events": events,
        "event_codes": [event["code"] for event in events],
        "severity_codes": {
            "blocked": _guard_event_code_list(events, level="blocked"),
            "critical": _guard_event_code_list(events, severity="CRITICAL"),
            "warning": _guard_event_code_list(events, severity="WARN"),
        },
        "scope_lock": {
            "project_purpose": "텔레그램 알림형 시그널 보조",
            "goal_present": bool((getattr(spec, "goal", "") or "").strip()),
            "requirements_present": bool(getattr(spec, "requirements", [])),
        },
        "strict_ok": len(blocked) == 0 and len(high_impact_warnings) == 0,
    }


def _normalize_files(changed_files: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for path in changed_files:
        normalized = path.strip()
        if not normalized:
            continue
        normalized = normalized.replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _compile_violations(changed_files: list[str]) -> list[dict]:
    violations: list[dict] = []
    for path in changed_files:
        if not path.endswith(".py"):
            continue
        if not Path(path).exists():
            violations.append(
                {
                    "rule_id": "syntax_guard",
                    "file": path,
                    "message": "python 파일 경로가 존재하지 않습니다.",
                }
            )
            continue
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:  # syntax/runtime import safety checks
            violations.append(
                {
                    "rule_id": "syntax_guard",
                    "file": path,
                    "message": f"문법 컴파일 실패: {exc}",
                }
            )
    return violations


def _file_scope_guard(changed_files: list[str]) -> dict:
    blocked: list[str] = []
    warnings: list[str] = []

    for path in changed_files:
        lower = path.lower()
        if lower.startswith("../") or "/../" in f"/{lower}/":
            blocked.append(f"상위 디렉터리 경로 감지: {path}")
            continue
        if os.path.isabs(path):
            blocked.append(f"절대 경로 입력 감지: {path}")
            continue
        if lower.endswith("/.env") or lower.endswith("/secrets") or "secret" in lower:
            warnings.append(f"민감 경로 패턴 탐지: {path}")

    if "README.md" in changed_files and len(changed_files) > 1:
        warnings.append("README와 코드/스크립트 동시 수정 시 의도 변경 가능성 검토 권고")

    return {
        "ok": len(blocked) == 0,
        "blocked": blocked,
        "warnings": warnings,
    }


def _cmd_parse_issue(
    file_path: str, *, strict: bool, allow_legacy_template: bool = False
) -> int:
    text = Path(file_path).read_text(encoding="utf-8")
    spec = parse_task_issue(text)
    guard = _direction_guard(spec, text, allow_legacy_template=allow_legacy_template)
    payload = {
        "title": spec.title,
        "goal": spec.goal,
        "requirements": spec.requirements,
        "constraints": spec.constraints,
        "acceptance": spec.acceptance,
        "guard": guard,
    }
    print(json.dumps(payload, ensure_ascii=False))
    if strict:
        if guard["strict_ok"]:
            return 0

        print(
            "STRICT 가드 실패: 방향/품질 규칙 위반으로 자동 검토가 막혔습니다.",
            flush=True,
        )
        if guard["blocked"]:
            print("[핵심 누락] BLOCKED:", flush=True)
            for item in guard["blocked"]:
                print(f" - {item}", flush=True)
        if guard["high_impact_warnings"]:
            print("[핵심 누락] CRITICAL WARNINGS:", flush=True)
            for item in guard["high_impact_warnings"]:
                print(f" - {item}", flush=True)
        if guard["warnings"]:
            print("[권고] WARNINGS:", flush=True)
            for item in guard["warnings"]:
                print(f" - {item}", flush=True)
        print("STRICT_GUARD_REPORT=" + json.dumps(guard["severity_codes"], ensure_ascii=False))
        if guard["events"]:
            print("STRICT_GUARD_EVENTS=" + json.dumps(guard["events"], ensure_ascii=False))
        return 2

    if not guard["ok"]:
        return 2
    return 0


def _cmd_check_pr(files_arg: str) -> int:
    changed_files = _normalize_files([part.strip() for part in files_arg.split(",") if part.strip()])
    result = run_rules(changed_files, forbidden_prefixes=[])
    syntax_violations = _compile_violations(changed_files)
    scope_guard = _file_scope_guard(changed_files)

    merged = result["violations"][:]
    merged.extend(syntax_violations)

    if scope_guard["blocked"]:
        merged.append(
            {
                "rule_id": "scope_guard",
                "message": "Scope guard blocked risky path.",
                "files": scope_guard["blocked"],
            }
        )

    if merged:
        ok = False
    else:
        ok = True

    payload = {
        "ok": ok,
        "violations": merged,
        "summary": {
            "violation_count": len(merged),
            "file_count": len(changed_files),
            "syntax_violations": len(syntax_violations),
        },
        "guard": {
            "scope_guard": scope_guard,
            "retries": {
                "note": "권장: 파일 범위 1개 우선, 필요 시 사용자 승인으로 다중 파일 분할",
            },
        },
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse-issue":
        return _cmd_parse_issue(
            args.file,
            strict=args.strict,
            allow_legacy_template=args.allow_legacy_template,
        )
    if args.command == "check-pr":
        return _cmd_check_pr(args.files)

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
