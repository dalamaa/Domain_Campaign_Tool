# Business Rules

# Overview

These rules define how campaigns, reservations, email blocks, priorities, recommendations, and scheduling work.

The scheduler must follow these rules unless the user manually overrides a recommendation.

The scheduler never performs business actions automatically. It only makes recommendations.

The user always has final control.

---

# DOMAIN RULES

## D001

Each domain may have multiple campaigns over its lifetime.

Only one campaign may be ACTIVE at any given time.

---

## D002

A domain may exist without an active campaign.

---

## D003

Every domain must have an expiry date.

---

## D004

Days Until Expiry must always be calculated dynamically.

Do not store this value in the database.

---

## D005

Domains may have one of the following statuses:

- AVAILABLE
- SOLD
- EXPIRED

---

## D006

Sold and Expired domains must never appear in Suggested Work.

---

## D007

Expired domains remain in the system for historical purposes unless deleted by the user.

---

## D008

A Dormant (not-started) campaign uses sequence `0` to mean "has not started."

- Sequence `0` must never be presented to the user as a real sequence value in the UI.
- In the list/table, a Dormant domain's Sequence should display as "Not started."
- The first real outreach moves a campaign to sequence `1`.

---

# CAMPAIGN RULES

## C001

Every campaign stores:

- Start Date
- Last Contact Date
- Current Price
- Current Sequence
- Campaign Status (DORMANT, ACTIVE, RESTING)

---

## C002

Campaign Age must always be calculated dynamically.

---

## C003

Campaign history must never be deleted automatically.

---

## C004

Every campaign action creates a history record.

Examples:

- First Outreach
- First Follow-up
- Follow-up
- Price Reduction
- Rest Started
- Campaign Restarted
- Campaign Completed
- Force Override
- Partial Override

---

## C005

The scheduler must never automatically change a campaign status.

It may only recommend changes.

---

# PRIORITY SYSTEM

## PR001

The scheduler must calculate a Priority Score for every active campaign.

Suggested default weights:

- First Follow-up Due = +100
- Expiry within 14 days = +90
- Expiry within 30 days = +70
- Expiry within 60 days = +40
- Price Reduction Due = +50
- Normal Follow-up Due = +35
- Campaign Older than 35 days = +25
- Ready To Restart = +15

## The scheduler sorts Suggested Work by total Priority Score.

## PR002

## Priority weights should be configurable.

# FIRST FOLLOW-UP

## F001

## The first follow-up should occur between Day 2 and Day 5.

## F002

## First follow-ups should receive the highest scheduler weight.

## F003

## Day 2 through Day 5 should display as Due.

## F004

## After Day 5 the first follow-up becomes Overdue.

## F005

## Overdue first follow-ups should display an urgent color.

# NORMAL FOLLOW-UP

## N001

## Normal follow-ups should ideally occur between Day 14 and Day 21.

## N002

## The scheduler should increase priority as the campaign approaches Day 21.

## N003

## 22 through 35 days should display a warning color.

## N004

## 36 through 50 days should display a high priority warning.

## N005

Campaigns should generally not remain Active beyond 50 days.

## The scheduler should recommend moving the campaign into Rest.

# PRICE REDUCTION

## P001

## Price reductions are separate campaign actions.

## P002

Price reductions update:

- Current Price
- Last Contact Date
- Campaign History

---

## P003

## Price history must never be lost.

## P004

## The scheduler should recommend price reductions based on campaign progress.

# REST PERIOD

## R001

## Campaigns generally enter Rest after approximately 50 days.

## R002

The scheduler recommends moving a campaign into Rest.

## The user decides whether to accept the recommendation.

## R003

## Default Rest duration is 60 days.

## R004

## The scheduler recommends restarting after Rest ends.

## R005

## The user may restart a campaign before Rest ends.

# EXPIRY

## E001

## Domains expiring within 60 days receive increased priority.

## E002

## Domains expiring within 30 days become Critical.

## E003

## Domains expiring within 14 days become Highest Priority.

## E004

## The scheduler may recommend ending Rest early when expiry is approaching.

# EMAIL BLOCKS

## M001

## Every email account belongs to one ordered sequence.

## M002

## Email order must always be preserved.

## M003

Campaigns should use contiguous email blocks whenever possible.

Example:

M08

M09

M10

## M11

## M004

## Avoid scattered email assignments whenever possible.

## M005

## The scheduler should recommend the smallest suitable contiguous block.

## M006

Users may manually modify suggested email blocks.

---

## M007

The scheduler should preserve email block continuity across campaigns whenever possible.

Example:

If previous campaigns primarily use D and M blocks, the scheduler should continue recommending nearby blocks before jumping to distant blocks such as T or Z.

---

## M008

Campaigns should normally retain the same assigned email block throughout their lifetime.

---

## M009

Changing assigned email blocks is a manual user action.

## M010

An email account is Available when:

- It is enabled.
- It is not reserved.
- It was not completed today.

Otherwise it is Unavailable.

---

# RESERVATIONS

## V001

Selecting a campaign reserves its assigned email block.

---

## V002

Reserved email accounts cannot be reserved by another campaign unless the user overrides the conflict.

---

## V003

Reservations remain active until:

- Cancelled
- Completed
- The next day begins

---

## V004

Reservations only prepare work.

Reservations do not mean emails have been sent.

---

## V005

Completing a reservation updates campaign progress.

---

## V006

Reservations may be cancelled.

---

## V007

Reservations may be overridden by the user.

---

## V008

If two campaigns require overlapping email blocks, the scheduler should warn the user.

---

## V009

The user may approve the conflict manually via a Force Override.

## V010

The Reservation Board must allow the user to Force Override an existing reservation.

- The application must display the conflicting campaigns before the override occurs.
- The user must explicitly confirm the override.
- The override action must be recorded in the Campaign History.

## V011

The user may partially override an email block.

- Example: If Campaign A uses M01-M05 and Campaign B needs M04-M05, the user may assign M04-M05 to Campaign B for the day.
- The application must warn the user before the override.
- The override must be recorded in the Campaign History.

## V012

Reservations are campaign-based.

- Selecting a campaign automatically reserves its assigned email block.
- Users do not reserve individual email accounts manually under normal workflow.

## V013

An email account is considered:

- Unavailable if:
  - It is currently reserved by a campaign.
  - It was used to complete a campaign today.
  - It is disabled.
- Available if:
  - None of the above conditions apply.

## V014

The Reservation Board must display email blocks in the following states:

- Available (Green)
- Reserved (Yellow)
- Completed Today (Grey)
- Disabled (Red)

# COMPLETION

## A001

Completing a campaign updates:

- Last Contact Date
- Current Sequence
- Current Price
- Campaign History

---

## A002

Completed email blocks remain unavailable until the following day.

---

# SUGGESTED WORK

## S001

The scheduler automatically generates Today's Work.

---

## S002

The scheduler also generates:

- Weekly Work
- Monthly Work

---

## S003

Suggested Work includes:

- First Follow-ups
- Normal Follow-ups
- Price Reduction Follow-ups
- Ready To Restart
- Expiring Domains

---

## S004

Suggested Work must always be sorted by Priority Score.

---

# RECOMMENDATIONS

## G001

The scheduler may recommend:

- Follow-up Today
- Price Reduction
- Move To Rest
- Restart Campaign
- End Rest Early
- Start New Campaign

---

## G002

Recommendations are suggestions only.

The user may override any recommendation.

---

# DASHBOARD

## U001

The Dashboard is the application's homepage.

---

## U002

The Dashboard should answer one question:

"What should I work on today?"

---

## U003

The Dashboard should display:

- Overview Cards
- Suggested Work
- Reservation Board
- Reserved Email Blocks
- Available Email Blocks
- Campaign Table
- Recommendations

---

# IMPORTS

## I001

The application supports importing:

- New Domains
- Active Campaigns

---

## I002

Imported Active Campaigns must preserve:

- Current Price
- Current Sequence
- Email Blocks
- Last Contact Date
- Campaign Status (DORMANT, ACTIVE, RESTING)

---

## I005

Imported domains that have NOT been started must be created as a campaign with DORMANT status,
sequence `0` and price `0`.

Importing a domain into the campaign table does NOT, by itself, mark it as
ACTIVE. The domain stays with a DORMANT campaign (not started) unless the user explicitly
provides an ACTIVE status with a real sequence (1 or higher).

---

## I003

Duplicate domains require user confirmation.

---

## I004

Imported data must be validated before saving.

The application should report invalid rows before completing the import.

---

# COLOR RULES

## CL001

Green

Healthy or recently completed.

---

## CL002

Yellow

Approaching due.

---

## CL003

Orange

Overdue.

---

## CL004

Red

Critical.

Immediate attention required.

---

## CL005

Grey

Campaign is Resting.

---

# USER CONTROL

## UC001

The scheduler makes recommendations.

The user always has final control.

---

## UC002

Every recommendation may be modified.

---

## UC003

Every reservation may be modified.

---

## UC004

Every completed campaign action may be corrected by the user.

---

# GENERAL

## X001

The application should minimize manual calculations.

---

## X002

The scheduler should automate repetitive planning decisions.

---

## X003

The application should allow a user to complete daily planning within a few minutes.

---

## X004

The scheduler should maximize efficient email block usage while minimizing reservation conflicts.

---

## X005

The application should favor predictable email block assignments over random allocation.

This helps maintain campaign consistency and reduces future scheduling conflicts.
