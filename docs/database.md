Database Design

Enums

campaign_status: ACTIVE, RESTING, SOLD, EXPIRED, ARCHIVED

action_type: CAMPAIGN_STARTED, FOLLOW_UP_SENT, PRICE_REDUCTION, REST_STARTED, CAMPAIGN_RESTARTED, CAMPAIGN_COMPLETED, FORCE_OVERRIDE, PARTIAL_OVERRIDE

reservation_status: RESERVED, COMPLETED, CANCELLED

Tables

domains

Purpose: Core entity representing a domain.

Fields:

id (PK)

domain_name (String, Unique)

expiry_date (Date)

notes (Text, Nullable)

created_at (Timestamp)

Indexes:

domain_name

campaigns

Purpose: Tracks an individual outreach effort for a domain.

Fields:

id (PK)

domain_id (FK to domains)

status (Enum)

start_date (Date)

last_contact_date (Date, Nullable)

current_price (Integer)

current_sequence (Integer)

rest_start_date (Date, Nullable)

rest_end_date (Date, Nullable)

handled_by (String, Nullable)

notes (Text, Nullable)

created_at (Timestamp)

updated_at (Timestamp)

Relationships:

Many Campaigns to One Domain

Indexes:

domain_id

status

email_accounts

Purpose: Represents the individual email accounts used for outreach.

Fields:

code (PK, e.g. M01)

group (String)

profile_order (Integer)

enabled (Boolean)

Indexes:

group

profile_order

Email Account Groups

The current email groups are:

D

M

ML

N

T

Y

Z

The group value must be stored explicitly for each email account.

The application must not parse the email code to determine its group.

Examples:

M01 belongs to group M

ML06 belongs to group ML

T01 belongs to group T

The group is relevant to email block selection and scheduler recommendations.

Email Account Ordering

profile_order represents the user's custom ordering of email accounts.

It does not necessarily correspond to the numeric portion of the email code.

Missing email codes are intentional.

For example:

M01 exists

M02 exists

M03 does not exist

M04 exists

The application must not automatically create missing codes.

The scheduler must use profile_order when determining email proximity,contiguous blocks, preferred blocks, available blocks, reservation conflicts,and alternative blocks.

The scheduler must not replace the custom ordering with alphabetical ornumeric sorting.

Contiguous Email Accounts

Email accounts are considered contiguous according to profile_order.

Contiguity is based on adjacent profile_order values, not on the numericportion of the email code.

For example, if:

M01 has profile_order = 5

M02 has profile_order = 6

M04 has profile_order = 7

then M01, M02, and M04 form a contiguous block even though M03 doesnot exist.

The scheduler must never require the email codes themselves to be numericallyconsecutive.

campaign_email_blocks

Purpose: Junction table that maps campaigns to the email accounts assigned to them.

A campaign may use multiple email accounts as part of the same outreach sequence.

The assigned accounts form the campaign's email block.

Fields:

id (PK)

campaign_id (FK to campaigns)

email_code (FK to email_accounts)

Unique Constraint:

(campaign_id, email_code)

The assigned email accounts must be ordered by profile_order.

The application must preserve the user's custom email ordering.

reservations

Purpose: Tracks daily reservations for email accounts assigned to campaigns.

A reservation represents the user's intention to work on a campaign that day.

A reservation does not mean that emails have been sent.

Fields:

id (PK)

campaign_id (FK to campaigns)

date (Date)

status (Enum: RESERVED, COMPLETED, CANCELLED)

is_override (Boolean)

created_at (Timestamp)

updated_at (Timestamp)

Unique Constraint:

(date, campaign_id)

Reservations apply only to their specified date.

reservation_email_links

Purpose: Links individual email accounts to a daily campaign reservation.

This table records the exact email accounts reserved for a campaign on aspecific date.

It also supports partial overrides when only part of an email block is used.

Fields:

id (PK)

reservation_id (FK to reservations)

email_code (FK to email_accounts)

Unique Constraint:

(reservation_id, email_code)

The same email account may not be added to the same reservation more than once.

The reserved email accounts must be ordered by profile_order.

campaign_history

Purpose: Append-only audit trail for campaign actions.

Every meaningful campaign action should create a history record.

Fields:

id (PK)

campaign_id (FK to campaigns)

action_type (Enum)

action_date (Timestamp)

price_before (Integer, Nullable)

price_after (Integer, Nullable)

sequence_before (Integer, Nullable)

sequence_after (Integer, Nullable)

notes (Text, Nullable)

Indexes:

campaign_id

action_date

Campaign history must not be automatically deleted.

Price history is represented by chronological history records.

The application stores only the numeric price.

The application does not store a separate price stage or price label.

For example, a campaign's price history may contain: 499, 499 399 399 299  Foreign Key Rules  The following relationships must be enforced:  campaigns.domain_id → domains.id campaign_email_blocks.campaign_id → campaigns.id campaign_email_blocks.email_code → email_accounts.code reservations.campaign_id → campaigns.id reservation_email_links.reservation_id → reservations.id reservation_email_links.email_code → email_accounts.code campaign_history.campaign_id → campaigns.id  Campaign history must not be automatically deleted through cascading deletes.  EMAIL ACCOUNT SEED DATA  The following email accounts represent the actual email profiles available to the application.  These are not generic sample accounts.  They must be created as initial records when the database is seeded.  The exact order below is significant.  The seed order determines profile_order.  The scheduler must use this order when determining:  Email proximity Contiguous blocks Preferred email assignments Available blocks Reservation conflicts Alternative blocks  The application must never replace these codes with generic names such as Account 1, Account 2, etc.  Email Account Codes D03 D04 D05 D07  M01 M02 M04 M05 M06 M07 M08 M09 M10 M11 M12 M13 M14 M15 M16 M17 M18 M19 M20  ML06 ML07 ML08  N04 N09 N10  T01 T03 T04 T05 T06 T07 T08 T09 T10 T12 T13 T14 T15 T16 T17 T18  Y01 Y02 Y03 Y04  Z00 Z01 Z04 Z08 Z09 Seed Rules The first account in the list has profile_order = 1. The second account has profile_order = 2. Continue sequentially through the entire list. The final account has profile_order = 54. All seeded accounts have enabled = true. The group value must be explicitly stored for every account. Missing codes are intentional and must not be created. The seed process must create exactly these 54 email accounts.