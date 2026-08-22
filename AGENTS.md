# Domain Campaign Planner - Agent Instructions

## Source of Truth

Before making implementation changes, read the relevant documentation in `docs/`.

The primary specification files are:

- docs/project_scope.md
- docs/business_rules.md
- docs/database.md

Do not invent business rules when the specification already defines the behavior.

If implementation conflicts with the documentation, report the conflict before changing the implementation.

## Development Workflow

Development is divided into phases.

Do not skip phases.

Do not begin a later phase until the current phase has been validated and approved.

The current development phases are:

1. Application Foundation
2. Database Models
3. Database Migration
4. Seed Data
5. Repositories
6. Services
7. Scheduler
8. CRUD Interfaces
9. Import / Export
10. Dashboard
11. Testing and Refinement

## Recovery

If the previous session ended unexpectedly, the context limit was reached, the agent was restarted, or the user asks to determine what to do next:

Read:

docs/agent_recovery.md

Follow the recovery procedure exactly.

Never assume that previous work completed successfully.

Inspect the actual project files and Git state.

During recovery, do not modify files.

Report the current state and wait for user approval.

## Implementation Rules

Work only on the requested phase.

Do not make unrelated changes.

Do not refactor unrelated code unless required to complete the current task.

Do not delete existing work without explicit approval.

Do not use git reset, git checkout, or other destructive Git operations unless explicitly instructed.

Keep business logic out of Flask routes.

Use this application flow:

Browser
→ Blueprint
→ Service
→ Repository
→ SQLAlchemy
→ PostgreSQL

Routes should handle HTTP concerns.

Services should contain business logic.

Repositories should handle database access.

Models should represent database entities and relationships.

## Approval Rule

After completing a requested phase:

1. Validate the work.
2. Report what was created or changed.
3. Report validation results.
4. Identify anything that remains incomplete.
5. Stop and wait for approval.

Never automatically begin the next phase.

## Python Environment

This project uses the existing `.venv` virtual environment.

Always use `.venv` for Python and pytest commands.

Use:

.venv/bin/python

For pytest:

PYTHONPATH=. .venv/bin/pytest

For a specific test:

PYTHONPATH=. .venv/bin/pytest tests/test_domain_campaign_regression.py

Do not create another virtual environment or use `python3 -m venv venv`.

Do not use system Python or a different virtual environment for this project.

If `.venv` does not exist, stop and report it. Do not create a replacement environment without approval.

## Git Safety

Before making changes, check the current Git status and preserve existing uncommitted work.

Do not use destructive Git commands such as `git reset --hard`, `git checkout -- .`, or `git restore .` unless explicitly instructed.

Do not commit or push unless explicitly requested.

## Scope

Only modify files and logic required for the requested task.

Do not rewrite unrelated application logic or refactor unrelated code.

If a test exposes an application bug, report the exact cause and wait for approval before changing production code.

## Approval

After completing a task:

1. Run the relevant tests.
2. Report what changed.
3. Report test results and any failures.
4. Stop and wait for approval before starting another task.

## Testing Rules

- Tests must verify existing application behavior. Do not modify production code just to make a test pass.
- Tests must not permanently modify or delete existing development data. Use isolated test data or test-created records and clean them up after tests.
- Do not assume a fixed number of existing records or depend on specific development database IDs.
- Do not weaken, skip, or remove a failing test to make the test suite pass.

### Test Failure Investigation

When a test fails:

1. Isolate the failing test first. Run only the affected test.
2. Do not modify code based only on the pytest failure summary.
3. Determine the exact exception, file, and line that causes the failure.
4. Determine whether the problem is in the test, environment, or application code.
5. Identify the smallest change that fixes the actual root cause.
6. If the cause is unclear, investigate further without modifying files.
7. Only modify code after the root cause is established.
8. After each fix, run only the affected test.
9. If the affected test passes, stop and report the result. Do not automatically continue fixing other failures.
10. Never modify unrelated production code.
11. Never change a test merely to make an application bug disappear.
12. Do not weaken an assertion simply because the application currently returns an unexpected result.
13. Do not modify production code to fix a failing test without approval.

## ENVIRONMENT RULE:

Before running ANY Python, Flask, pytest, migration, or project command:

1. Check whether `.venv` exists.
2. Use the project's `.venv` executables explicitly.
3. Prefer:
   `.venv/bin/python -m ...`
   over calling globally installed commands.
4. For pytest use:
   `PYTHONPATH=. .venv/bin/pytest ...`
5. For Flask use:
   `.venv/bin/python -m flask ...`
6. Do NOT run `pip install -r requirements.txt` merely because a package or command is missing from the system Python.
7. If a required package is missing from `.venv`, report that first. Do not reinstall the project environment without explicit approval.
