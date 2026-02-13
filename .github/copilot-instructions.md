# Repository-wide agent instructions

## Workflow
- Work only via Issue -> Branch -> PR.
- Default rule: one PR changes/creates one file. If more files are needed, state the reason in the PR.

## Safety / Constraints
- No refactors unless the Issue explicitly allows it.
- No unrelated formatting or cleanup changes.
- No side effects: do not add code that performs external network calls, touches secrets, or changes global state unexpectedly.

## Implementation style
- Prefer small, testable increments.
- Keep dependencies minimal.
- Add clear input/output contracts and error handling.

## Verification
- If available, run tests and report results in the PR.
- At minimum, ensure the code compiles/loads without syntax errors.
