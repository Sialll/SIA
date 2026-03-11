# Codex AGENTS Instructions

## Workflow
- Work only via Issue -> Branch -> PR.
- Default: one PR changes/creates one file.
- If an issue requires multiple files, document the reason explicitly and split work intentionally.

## Constraints
- No refactors unless the Issue explicitly allows them.
- No unrelated formatting or cleanup changes.
- Avoid side effects: no new external network calls, no secret handling, and no unexpected global-state mutations.
- Before changing behavior, keep scope aligned with the project-direction guard in `~/.codex/skills/project-direction-guard/SKILL.md`.
- Before implementing, apply the error-prevention guard in `~/.codex/skills/sia-error-prevention-guard/SKILL.md`.
- 변경 전후 점검 원칙: `read settings -> bounded diff -> syntax-safe patch -> dry-run command` 3단계로만 진행한다.
- 방향성/오류 방지 규칙은 루트의 [`SKILL.md`](SKILL.md) 기준으로 고정하고, 작업 전/후에 해당 항목을 확인한다.

## Execution approach
- Prefer small, verifiable steps.
- If scope is large, propose a clear, step-by-step plan first.
