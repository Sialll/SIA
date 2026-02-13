# Codex AGENTS Instructions

## Workflow
- Work only via Issue -> PR process.
- Each PR should change or create exactly one file.
- If an issue requires multiple files, document the reason explicitly and split work intentionally.

## Constraints
- No refactors unless the Issue explicitly allows them.
- No unrelated formatting or cleanup changes.
- Avoid side effects: no new external network calls, no secret handling, and no unexpected global-state mutations.

## Execution approach
- Prefer small, verifiable changes.
- If scope is large, propose a clear, step-by-step plan first.
