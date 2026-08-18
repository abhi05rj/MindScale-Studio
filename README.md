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

## Hosted Runtime V1

`.github/workflows/hosted-runtime.yml` runs the existing pipeline unattended on a GitHub-hosted
Ubuntu runner. It supports both a daily UTC schedule and manual dispatch with an optional UTC
target date. The job uses one non-cancelling `mindscale-production` concurrency group, Python
3.12, and only `requirements.txt`. Hosted image generation uses the deterministic Pillow path;
Core ML is not installed or invoked. The compositor selects the open-source DejaVu or Liberation
system fonts available on Ubuntu and does not depend on macOS font paths.

The workflow separates durable metadata from binary outputs:

```text
runtime-state Git branch (state/)
  content_plans/*.json
  pipeline/*.json
  content_packages/*.json
  publication_queue.json
  manifest.json

GitHub Actions artifacts
  final 1000x1500 PNGs
  hosted execution log
```

At startup, the job checks out the dedicated `runtime-state` branch in a separate worktree,
validates and imports its JSON snapshot, and restores the prior image artifact named in the
manifest. It then ensures the target date has a deterministic plan and runs Pipeline Orchestrator
V1. At shutdown, it exports portable checkout-relative references, rejects non-JSON state files,
commits only the `state/` tree to the state branch, and uploads images and diagnostics as
artifacts. Generated PNGs are never committed to the runtime branch, and Actions cache is not
used as authoritative state.

Manual execution is available from the Actions tab with `target_date` in `YYYY-MM-DD` format.
Scheduled execution defaults to the current UTC date. The hosted runner never invokes the
publication queue processor or Pinterest publisher. Consequently Hosted Runtime V1 cannot make
a Pinterest API request or publish a Pin; queue items remain locally scheduled metadata for a
future, explicitly designed publishing phase.

The state adapter can also be exercised locally:

```bash
.venv/bin/python -m app.hosted_runtime.cli import-state --source /path/to/state
.venv/bin/python -m app.hosted_runtime.runner --date 2026-08-19
.venv/bin/python -m app.hosted_runtime.cli export-state --destination /path/to/state
```

The runtime-state branch is intentionally a V1 metadata store. Its serialized workflow prevents
concurrent writers, but branch history can grow and artifact retention can expire. Before live
publishing is enabled, retention, branch protection/recovery, failed artifact restoration, and
the durability of publication results must be reviewed explicitly.

## Production Readiness V1

The separate `.github/workflows/controlled-pinterest-publish.yml` workflow is the only hosted
path designed to reach the Pinterest publisher. It is manual (`workflow_dispatch`) only and
defaults to `preflight`. Selecting `live` is insufficient by itself: the operator must also set
the independent `confirm_live_publish` input to `true`. There is no scheduled live-publishing
trigger.

Configure the workflow through GitHub without placing credentials in the repository:

- Secrets: `PINTEREST_APP_ID`, `PINTEREST_APP_SECRET`, `PINTEREST_ACCESS_TOKEN`, and
  `PINTEREST_REFRESH_TOKEN`
- Repository/environment variable: `PINTEREST_BOARD_ID`

Live mode fails before publisher construction when any required value is absent. Preflight mode
does not require credentials and validates the selected queue item, due time, content package,
final PNG, publication status, and absence of a prior Pin ID without constructing or invoking the
Pinterest publisher.

Controlled attempts use durable JSON records under `.local-runtime/publication_attempts/`, which
Hosted Runtime exports to the `runtime-state` branch. The lifecycle is `ready` → `claimed` →
`publishing` → `published`, with `failed` for a safely retryable failure and
`publication_unknown` when a create request may have succeeded but no trustworthy result was
received. Safe failures are limited to three explicit manual attempts. A stale `claimed` state
can be recovered after 20 minutes; stale `publishing` becomes `publication_unknown` and is never
automatically retried. Queue status, content-package publication metadata, attempt count, error,
board ID, and eventual Pin ID persist in the JSON state snapshot.

Local preflight remains offline:

```bash
.venv/bin/python -m app.production_publication.cli \
  --queue-item-id QUEUE_ITEM_UUID \
  --mode preflight
```

Both preflight and live workflow runs write a sanitized GitHub Actions job summary. Generated
images continue to come only from the prior Hosted Runtime artifact; publication logs are stored
as a diagnostic artifact and neither is committed to the state branch.

## Content Quality V1

MindScale's default editorial generation remains deterministic, local, and zero-cost. New topics
rotate through seven curiosity-led frames: scale/comparison, counterintuitive fact, what-if
scenario, hidden mechanism, timeline/transformation, pattern discovery, and boundary/threshold.
The planner uses the same pattern library, so planned titles and angles remain aligned with the
content strategy that Automation and Pipeline Orchestrator consume.

Generic headings such as `What Makes X So Fascinating?`, `A Visual Guide to X`, and
`Understanding X at a Glance` are detected and rewritten before Pinterest copy is produced.
Descriptions now integrate topic-specific search phrases naturally and include a relevant
save/share prompt. Image directions specify the composition, visual sequence, focal hierarchy,
depth, scale cues, negative space, lighting, and exclusions needed by the existing Pillow/template
path; no image-generation service or model was added.

Content scoring now evaluates six independent editorial dimensions from 1–10:

- Curiosity
- Specificity
- Novelty
- Emotional impact/resonance
- Shareability/save potential
- Visual storytelling potential

The persisted score object also includes a rounded overall score. Generic language receives an
explicit penalty, allowing weak concepts to score materially below specific, visual, novel ideas.
Planner angle labels remain internal metadata; publish-facing hooks are stored separately as
natural prose. The planner also applies a headline-structure diversity penalty across each week.
Ideas below an overall score of 6 receive one deterministic rewrite pass. If the rewritten idea
still scores below 6, its day is persisted as `needs_review`, and Pipeline Orchestrator refuses to
generate or queue it until it has been editorially resolved.
