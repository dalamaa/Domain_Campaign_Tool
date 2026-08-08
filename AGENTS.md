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