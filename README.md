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

## Scheduling & Queue V1

The publication queue is an atomic, versioned JSON document stored locally at
`.local-runtime/publication_queue.json`. Queue timestamps are always persisted in UTC with an
explicit `+00:00` offset. Queue records move through `scheduled`, `processing`, `published`,
`failed`, or `cancelled` and retain their attempt count, last error, and Pinterest Pin ID.

Schedule a completed content package using an ISO 8601 datetime with an explicit timezone:

```bash
.venv/bin/python -m app.scheduling.cli schedule \
  --package output/content_packages/20260817T093523762269Z_time.json \
  --at 2026-08-20T09:30:00Z
```

Inspect and manage the queue:

```bash
.venv/bin/python -m app.scheduling.cli list
.venv/bin/python -m app.scheduling.cli get QUEUE_ITEM_ID
.venv/bin/python -m app.scheduling.cli cancel QUEUE_ITEM_ID
```

Process due items offline—the safe default—with a board placeholder used only to validate the
complete Pinterest payload:

```bash
PINTEREST_BOARD_ID=offline-board-placeholder \
  .venv/bin/python -m app.scheduling.cli process
```

Offline processing does not call Pinterest, increment attempt counts, change queue status, or
create a Pin ID. Live publishing remains disabled unless `--live` is supplied explicitly:

```bash
.venv/bin/python -m app.scheduling.cli process --live
```

The queue processor delegates payload validation and eventual publication to the accepted
Pinterest V1 publisher. Only a live attempt transitions an item to `processing`; success records
`published` and the Pin ID, while an exception records `failed` and the error for a later retry.

## Content Planner V1

Content Planner V1 creates a deterministic seven-day editorial plan before content or images are
generated. Plans are stored atomically under `.local-runtime/content_plans/YYYY-MM-DD.json` and
survive application restarts. Each day records its publish date, content pillar, working title,
angle, objective, and `planned` status.

Create a plan with the balanced default pillars:

```bash
.venv/bin/python -m app.planning.cli --start-date 2026-08-19
```

Show the already-persisted plan without regenerating it:

```bash
.venv/bin/python -m app.planning.cli --start-date 2026-08-19 --show
```

A second create command for the same start date fails safely. Replacement must be explicit:

```bash
.venv/bin/python -m app.planning.cli --start-date 2026-08-19 --replace
```

Override the default pillar set by repeating `--pillar` at least twice:

```bash
.venv/bin/python -m app.planning.cli --start-date 2026-08-19 \
  --pillar Science --pillar Mindfulness --pillar Creativity
```

The planner rotates pillars without consecutive repetition and compares normalized titles and
angles against recent `output/content_packages` history and prior local plans. It uses fixed local
templates and deterministic date-based selection; it does not call an AI model or any network API.

## Pipeline Orchestrator V1

Pipeline Orchestrator V1 connects the accepted offline production components without publishing:

```text
Content Planner → Automation V1 → Content + Pillow PNG → Publication Queue
```

Run the planned item for a specific date:

```bash
.venv/bin/python -m app.pipeline.cli --date 2026-08-19
```

The target date must exist in exactly one persisted weekly plan. The orchestrator applies that
day's planned pillar, working title, and angle to the existing deterministic content pipeline,
runs the accepted 1000×1500 Pillow image workflow, and schedules the completed package in the
local publication queue at 09:00 UTC.

Per-date pipeline state is written atomically to `.local-runtime/pipeline/YYYY-MM-DD.json` using
`planned`, `generating`, `generated`, `queued`, and `failed` transitions. Generated packages and
images remain under the existing ignored `output` directories, and queue data remains under
`.local-runtime`. Repeating a completed date reuses its package, PNG, and queue item. A failed
image or queue stage can be retried without corrupting earlier completed work.

The orchestrator never invokes the Pinterest publisher or queue processor. It only creates a
local scheduled queue item, so running this command cannot publish a Pin or contact Pinterest.
