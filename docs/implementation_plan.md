# Implementation Plan

## Phase 1: UI Prototype

Build the visual prototype with static/sample data.

### Dashboard
- Overview cards
- Today's Suggested Work
- Weekly Suggested Work
- Monthly Suggested Work
- First Follow-ups
- Normal Follow-ups
- Price Reduction Follow-ups
- Ready To Restart
- Expiring Soon
- Reservation Planner
- Reservation Board
- Available Email Blocks
- Campaign Table
- Domain detail view

### Purpose

The UI should allow the user to evaluate the workflow and layout before database integration.

Use realistic sample data based on the project specification.

Do not implement:
- PostgreSQL
- SQLAlchemy models
- migrations
- repositories
- scheduler logic
- real persistence

Stop for user review after the prototype is complete.


---

# Phase 2: Database Foundation

Implement the database based on `docs/database.md`.

### Models

- Domain
- Campaign
- EmailAccount
- CampaignEmailBlock
- Reservation
- ReservationEmailLink
- CampaignHistory
- Setting

### Relationships

Implement all relationships and foreign keys defined in `docs/database.md`.

### Validation

Verify:

- model imports
- relationships
- constraints
- indexes
- enums
- timestamps
- application startup

Do not implement scheduler logic yet.


---

# Phase 3: Database Migration

Set up Flask-Migrate / Alembic.

Create the initial migration from the approved SQLAlchemy models.

Apply the migration to PostgreSQL.

Verify that the database schema matches `docs/database.md`.

### Migration Rules

Database changes must be handled through migrations.

Never manually modify the database schema to fix an application problem.

Never delete migration history to solve an ordinary migration error.

If a migration fails, stop and report the error before making architectural changes.

If the schema needs to change, create a new migration.

After migration:

- verify database connection
- verify tables
- verify foreign keys
- verify indexes
- verify constraints

Stop for user approval.


---

# Phase 4: Seed Data

Create realistic development data.

Seed:

- domains
- campaigns
- email accounts
- campaign email blocks
- settings
- appropriate campaign history

The seed data should reflect the real workflow described in the business rules.

Use the sample data from the UI prototype where appropriate.

Verify that the dashboard can display real database data.


---

# Phase 5: CRUD

Implement CRUD for:

### Domains

- Create
- View
- Update
- Delete

### Campaigns

- Create
- View
- Update
- Delete

### Email Accounts

- Create
- View
- Update
- Delete

### Campaign Email Blocks

Allow campaigns to have their assigned email accounts added or removed.

### Settings

Allow configurable scheduler values to be viewed and modified.

CRUD must respect the business rules.

Do not place business logic directly inside Flask routes.


---

# Phase 6: Scheduler

Implement the campaign scheduling engine.

The scheduler should determine:

- First Follow-ups
- Normal Follow-ups
- Price Reduction Follow-ups
- Ready To Restart
- Expiring Soon
- Campaigns entering Rest
- Campaigns eligible for Restart
- Priority order
- Suggested email blocks
- Available email blocks
- Email block conflicts
- Contiguous block preference
- Manual overrides

The scheduler must follow:

`docs/business_rules.md`

The scheduler should produce recommendations.

It must not automatically send emails or automatically execute campaign actions.


---

# Phase 7: Reservation System

Implement:

- email block reservation
- reservation release
- reservation completion
- reservation cancellation
- reservation conflicts
- partial overrides
- force overrides
- daily reservation state

A reservation means:

"The user intends to work on this campaign today."

A reservation does not mean emails have been sent.

Only completion updates campaign progress.


---

# Phase 8: Dashboard Integration

Replace static UI data with real database and scheduler data.

The dashboard should answer:

"What should I work on today?"

Implement:

- overview cards
- suggested work
- priority ordering
- reservation planner
- reservation board
- available email blocks
- campaign table
- domain detail
- recommendations
- manual overrides


---

# Phase 9: Imports and Exports

Implement:

- new domain import
- active campaign import
- CSV validation
- duplicate detection
- campaign state preservation
- email block validation
- export

Imports must not silently overwrite existing records.

Invalid records should be reported before changes are committed.


---

# Phase 10: Reports

Implement useful reporting such as:

- campaign history
- price history
- domains by status
- active campaigns
- resting campaigns
- expiring domains
- email account usage
- campaign duration
- restart history


---

# Phase 11: Testing

Test each layer independently.

### Models
- relationships
- constraints
- validation

### CRUD
- create
- update
- delete

### Scheduler
- first follow-up
- normal follow-up
- price reduction
- expiry
- rest
- restart
- priority

### Reservations
- conflicts
- cancellation
- completion
- overrides
- partial overrides

### Imports
- valid records
- invalid records
- duplicates
- conflicts

### Integration

Test the complete workflow:

Dashboard
→ Select campaign
→ Review suggested email block
→ Modify if necessary
→ Reserve
→ Send emails externally
→ Complete
→ Update price / sequence / last contact
→ Scheduler recalculates
→ Dashboard refreshes


---

# Phase 12: Polish

Improve:

- responsive design
- loading states
- error messages
- empty states
- confirmation dialogs
- sorting
- filtering
- accessibility
- performance
- visual consistency
- usability

Do not introduce new business rules during the polish phase without updating the relevant specification.