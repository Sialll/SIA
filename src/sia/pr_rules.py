from dataclasses import dataclass, field


@dataclass
class RuleViolation:
    rule_id: str
    message: str
    files: list[str] = field(default_factory=list)


def check_one_file_changed(changed_files: list[str]) -> list[RuleViolation]:
    if len(changed_files) != 1:
        return [
            RuleViolation(
                rule_id="one_file_only",
                message="Exactly one file must be changed per PR.",
                files=changed_files,
            )
        ]
    return []


def check_forbidden_paths(
    changed_files: list[str], forbidden_prefixes: list[str]
) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    for file_path in changed_files:
        if any(file_path.startswith(prefix) for prefix in forbidden_prefixes):
            violations.append(
                RuleViolation(
                    rule_id="forbidden_path",
                    message=f"File path is forbidden: {file_path}",
                    files=[file_path],
                )
            )
    return violations


def run_rules(
    changed_files: list[str], *, forbidden_prefixes: list[str] | None = None
) -> dict:
    if forbidden_prefixes is None:
        forbidden_prefixes = []

    violations = check_one_file_changed(changed_files)
    violations.extend(check_forbidden_paths(changed_files, forbidden_prefixes))

    violation_payload = [
        {"rule_id": v.rule_id, "message": v.message, "files": v.files} for v in violations
    ]
    return {
        "ok": len(violations) == 0,
        "violations": violation_payload,
        "summary": {
            "violation_count": len(violations),
            "file_count": len(changed_files),
        },
    }
