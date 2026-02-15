from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pr_rules import run_rules
from .task_spec import parse_task_issue


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sia")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_issue = subparsers.add_parser("parse-issue")
    parse_issue.add_argument("--file", required=True)

    check_pr = subparsers.add_parser("check-pr")
    check_pr.add_argument("--files", required=True)

    return parser


def _cmd_parse_issue(file_path: str) -> int:
    text = Path(file_path).read_text(encoding="utf-8")
    spec = parse_task_issue(text)
    payload = {
        "title": spec.title,
        "goal": spec.goal,
        "requirements": spec.requirements,
        "constraints": spec.constraints,
        "acceptance": spec.acceptance,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _cmd_check_pr(files_arg: str) -> int:
    changed_files = [part.strip() for part in files_arg.split(",") if part.strip()]
    result = run_rules(changed_files, forbidden_prefixes=[])
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse-issue":
        return _cmd_parse_issue(args.file)
    if args.command == "check-pr":
        return _cmd_check_pr(args.files)

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
