# MindScale Studio

## Vision

Build an AI-powered visual storytelling engine that transforms ideas into beautiful educational Pinterest content.

## Mission

Help people understand complex concepts through simple, beautiful visuals.

## Current Version

v0.0.1

## First Milestone

Project setup complete.
Python environment ready.
Application running.
## Project Architecture

MindScale Studio is organized into:

- app: Core application logic
- content_engine: AI storytelling and text generation
- image_engine: Visual generation workflow
- prompts: AI prompt library
- assets: Templates and design resources
- output: Generated Pinterest content
- data: Analytics and project data

## Daily Content Automation

Run the local Pinterest content automation with Python 3.10 or newer:

```bash
python3 main.py
```

The runner selects today's calendar topic, generates and saves one Pinterest content package
under `output/content_packages`, and exits with status `0`. Running it again on the same day is
a successful no-op. It only prepares local content; it does not publish to Pinterest.

Automation V1 can also be run directly for a specific date:

```bash
.venv/bin/python -m app.automation_runner --date 2026-08-17
```

Use `--dry-run` to validate an existing completed package, or preview the next topic when no
package exists, without writing content or images. Automation uses the local deterministic Pillow
provider and never contacts Pinterest.

## Pinterest Publishing (API v5)

Publishing is a separate, explicit operation and is never performed by daily automation. A Pin
has no destination link by default. To add one, explicitly set a public HTTP(S) `destination_url`
in the saved package's `content_package.pinterest` object. Configure:

```bash
export PINTEREST_APP_ID='...'
export PINTEREST_APP_SECRET='...'
export PINTEREST_ACCESS_TOKEN='...'
export PINTEREST_REFRESH_TOKEN='...'
export PINTEREST_BOARD_ID='...'
```

The Pinterest application must be approved for `boards:read`, `boards:write`, `pins:read`, and
`pins:write`. Validate the complete payload offline (no credentials or Pinterest request) with:

```bash
.venv/bin/python -m app.pinterest.cli --date 2026-08-17 --dry-run
```

After Trial approval, remove `--dry-run` to look up the configured board and create the Pin.
The content package records the status, Pin ID, board ID, UTC timestamp, and any API error.
