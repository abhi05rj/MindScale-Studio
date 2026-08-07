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
