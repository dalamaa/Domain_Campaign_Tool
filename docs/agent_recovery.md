# Agent Recovery Procedure

## Purpose

Use this procedure whenever:

- the previous agent session ended unexpectedly
- the context limit was reached
- VS Code or the agent was restarted
- the user closed the agent
- a previous task may have been partially completed
- errors appeared after the previous task
- the user asks what should happen next
- the agent is unsure which phase is currently complete

The filesystem and Git state are the source of truth.

The agent must not rely on memory of the previous conversation.

---

# Recovery Rules

1. Do not modify any files during the initial recovery.

2. Inspect the actual current project state.

3. Read the relevant documentation before evaluating implementation.

4. Determine the current development phase from the actual project state.

5. Compare the implementation against the requirements for that phase.

6. Check for incomplete, partially generated, or conflicting code.

7. Check Git status and Git diff.

8. Run appropriate validation commands when safe.

9. Separate findings into:
   - Completed
   - Partially Completed
   - Broken
   - Missing
   - Not Yet Required

10. Do not start the next phase automatically.

11. Do not fix problems automatically during recovery.

12. Do not delete, reset, revert, or discard existing work.

13. At the end, provide the recommended next action and wait for user approval.

---

# Required Documentation

Read these files before evaluating the project:

- docs/project_scope.md
- docs/business_rules.md
- docs/database.md

Also read any other documentation relevant to the current phase.

If implementation conflicts with documentation:

- report the conflict
- identify the affected files
- do not silently change the specification
- do not silently change the implementation

---

# Project Inspection

Inspect:

- project directory structure
- app/
- migrations/
- tests/
- docs/
- config.py
- run.py
- requirements.txt
- AGENTS.md

Inspect the relevant files inside each directory based on the detected phase.

Do not assume a file exists because it was planned.

Do not assume a task was completed because a previous agent said it was completed.

---

# Git Inspection

Run:

git status

and:

git diff

Determine whether the previous task left:

- modified files
- untracked files
- partially completed files
- unexpected changes

Do not discard changes.

Do not use:

- git reset
- git checkout
- git restore

unless the user explicitly instructs you to do so.

---

# Phase Detection

Determine the current phase from the actual state of the project.

## Phase 1 - Application Foundation

Verify:

- Flask application factory
- config.py
- Flask extensions
- application startup
- blueprint registration
- project package structure

Do not assume Phase 1 is complete merely because the files exist.

Check that the application actually imports and starts.

---

## Phase 2 - Database Models

Verify:

- SQLAlchemy models
- model relationships
- foreign keys
- constraints
- indexes
- enums
- timestamps
- model imports
- circular import problems

Compare the models against:

- docs/database.md
- docs/business_rules.md where applicable

---

## Phase 3 - Database Migration

Verify:

- Alembic / Flask-Migrate configuration
- migration environment
- initial migration
- migration contents
- database connectivity
- migration status

Verify that the migration represents the current models.

Do not generate a new migration during recovery.

---

## Phase 4 - Seed Data

Verify:

- email account seed data
- settings seed data
- seed commands or scripts
- duplicate handling
- correct email ordering

Do not modify seed data during recovery.

---

## Phase 5 - Repositories

Verify:

- domain repository
- campaign repository
- email repository
- reservation repository
- settings repository

Check that repositories contain database access only.

Business rules should not be implemented inside repositories.

---

## Phase 6 - Services

Verify:

- CampaignService
- ReservationService
- PriorityService
- DashboardService
- ImportService

Check that business rules are implemented in the service layer rather than routes.

---

## Phase 7 - Scheduler

Verify:

- Today's Work
- Weekly Work
- Monthly Work
- first follow-up calculation
- normal follow-up calculation
- price reduction recommendations
- rest calculations
- restart recommendations
- expiry priority
- campaign age
- priority scoring
- email block suitability
- contiguous block preference
- reservation conflicts
- manual overrides

Compare all scheduler behavior against docs/business_rules.md.

Do not assume the scheduler is correct simply because tests pass.

---

## Phase 8 - CRUD Interfaces

Verify:

- Domain CRUD
- Campaign CRUD
- Email Account CRUD
- Settings CRUD

Check:

- validation
- update behavior
- delete behavior
- relationships
- error handling

---

## Phase 9 - Import / Export

Verify:

- new domain import
- active campaign import
- CSV validation
- duplicate detection
- campaign state preservation
- email block validation
- reservation conflict detection
- import preview / dry run if specified

---

## Phase 10 - Dashboard

Verify:

- overview cards
- suggested work
- reservation planner
- reservation board
- available email blocks
- campaign table
- sorting
- filtering
- recommendations
- manual overrides

The dashboard must answer:

"What should I work on today?"

---

## Phase 11 - Testing and Refinement

Verify:

- model tests
- repository tests
- service tests
- scheduler tests
- reservation tests
- import tests
- route tests
- integration tests

Run the relevant test suite.

Report failures without automatically rewriting tests to make them pass.

---

# Validation

Use validation appropriate to the current project state.

Possible checks include:

python -m compileall app

pytest

flask --app run.py routes

flask --app run.py run

flask db current

flask db check

alembic current

Only run commands that are appropriate for the actual project.

Do not install packages automatically.

Do not modify files during recovery.

---

# Recovery Report

Return the report using exactly this structure:

## CURRENT PHASE

State the detected phase and explain why.

## PROJECT STATUS

Give a short summary of the current state.

## COMPLETED

List work that is actually present and functional.

## PARTIALLY COMPLETED

List work that exists but is incomplete.

## BROKEN

List actual errors or broken behavior.

For each broken item include:

- file
- problem
- likely cause

## MISSING

List requirements that have not yet been implemented.

## DOCUMENTATION CONFLICTS

List anything where the code disagrees with the specification.

If none exist, say:

None found.

## GIT STATUS

Summarize:

- modified files
- untracked files
- whether the working tree is clean

## VALIDATION RESULTS

List the commands run and their results.

## RECOMMENDED NEXT STEP

Give exactly one recommended next action.

Explain why it should happen next.

## FILES THAT WOULD NEED CHANGES

List the files that the recommended next action would likely affect.

---

# Final Recovery Rule

Do not modify any files during recovery.

Do not start implementation.

Do not continue automatically.

Do not generate code.

Wait for the user to approve the recommended next step.