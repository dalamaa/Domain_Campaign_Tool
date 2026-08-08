# Project Scope

## Purpose

This application helps manage domain outreach campaigns.

Its primary purpose is to suggest which campaigns should be worked on today based on campaign rules and available email blocks.

It also prevents email reservation conflicts and tracks campaign progress and history.

## The application IS

- Campaign planner
- Email block reservation system
- Campaign tracker
- Recommendation engine
- Campaign history tracker
- Domain lifecycle tracker

## The application IS NOT

- CRM
- Email sender
- Contact manager
- Lead scraper
- Marketing automation platform
- Email delivery platform

## Users

A single user managing domain outreach campaigns.

Future versions may support multiple users.

## Core Workflow

The application follows this workflow:

1. User opens the Dashboard.
2. Scheduler identifies campaigns that need attention.
3. Dashboard displays Today's Suggested Work.
4. User reviews the suggested campaigns.
5. User selects a campaign to work on.
6. System suggests a suitable email block based on availability and campaign continuity.
7. User accepts or modifies the suggested email block.
8. User reserves the email block.
9. User sends the emails externally.
10. User returns to the application and marks the action as completed.
11. User updates the price, sequence, or other campaign information when necessary.
12. System records the action in campaign history.
13. Scheduler recalculates campaign priorities.
14. Dashboard updates with the new campaign state.

## User Control

The application provides recommendations rather than making irreversible decisions automatically.

The user can:

- Modify suggested work
- Override email block recommendations
- Override reservation conflicts
- Cancel reservations
- Complete actions
- Correct campaign information
- Start campaigns early
- Restart campaigns before the normal rest period ends

The scheduler should assist the user, not replace the user's judgment.