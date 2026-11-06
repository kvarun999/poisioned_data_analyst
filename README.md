# Poisoned Data Analyst

A secure, demo-ready sandbox app for running untrusted CSV-analysis code safely. The system accepts a CSV upload, runs a pandas analysis in a controlled sandbox, records the execution metadata, and returns a structured summary while blocking common exfiltration and destructive patterns.

## Problem statement

This project is designed to answer a real problem:

- An LLM is asked to analyze a CSV
- The CSV may contain prompt-injection content or malicious instructions
- The generated code must not be allowed to access real host credentials or network resources
- The system must still return useful analysis results

The app isolates the risky analysis inside a sandbox and logs every command before it is allowed to run.

## Core features

- FastAPI web app with file upload and JSON API
- SQLite-backed run ledger for tracking execution state
- Safety hook that blocks dangerous commands
- Local execution fallback when the Celesto SDK is unavailable
- Celesto-ready execution path for isolated sandboxing
- Report package that captures reliability, lifecycle, failures, and containment evidence
- Front-end UI for uploading and inspecting results

## Safe environment handling

The project intentionally keeps local secrets in a developer-only [.env](.env). This file is not meant to be committed.

- Use [.env.example](.env.example) as the public template
- Keep real credentials in your local [.env](.env)
- Do not commit secret values
- The repo is configured to ignore local secret and runtime files in [.gitignore](.gitignore)

## Celesto status and execution model

This project supports both a live Celesto path and a local fallback path.

- If a valid Celesto API key is present and the SDK is installed, the app tries the live microVM execution path.
- If the runtime is not available or the provider rejects the request, the app falls back to a local sandboxed execution path so the demo remains usable.
- The app reports this mode clearly at startup and through the health endpoint.

This is the correct design for a real-world security boundary: the control plane stays on the host, while risky analysis code is isolated in a sandboxed execution zone. The important nuance is that live Celesto execution depends on provisioning at the provider level, not just on installing the SDK.

In this environment, the SDK is present and the app is wired correctly, but the provider is currently rejecting actual sandbox creation with an HTTP 402. That means the project is ready for live Celesto usage, but it is not yet successfully running a live cloud microVM here without a funded or trial-enabled Celesto account.

## Eval report

The project tracks performance and reliability using structured evaluation data in [reports/reliability.json](reports/reliability.json).

It includes:

- total run count
- success rates
- wall-clock timings
- boot times
- recovery and failure notes
- cost summary

## Containment test

The containment story is documented in [reports/containment.json](reports/containment.json) and backed by the evidence folder under [reports/evidence](reports/evidence).

The key idea is simple: if the analysis code attempts to exfiltrate data or run dangerous commands, the sandbox controls and audit path stop it before it can escape the execution environment.

## State and failure design

The app is intentionally designed around a failure boundary that can recover without leaving a corrupted environment behind.

The main pattern is:

1. create the sandbox
2. configure it
3. take a clean snapshot
4. run the risky analysis
5. detect failure if needed
6. reset or retry from a known-good state
7. clean up the sandbox afterward

This is the core resilience mechanism behind the project.

## Quick start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure local environment

```bash
cp .env.example .env
```

Then fill in the values you need locally. Keep all real secrets in the local [.env](.env) file.

### 3. Start the app

```bash
DATABASE_URL=sqlite:///./poisoned_analyst.db uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### 4. Open the app

- Homepage: http://localhost:8080/
- Health: http://localhost:8080/health
- API docs: http://localhost:8080/docs
- Runs API: http://localhost:8080/api/runs

### 5. Upload a CSV

```bash
curl -X POST http://localhost:8080/analyze \
  -F "file=@your_data.csv"
```

## Demo and video guidance

For a polished walkthrough and a structured explanation video, use:

- [demo/VIDEO_SCRIPT.md](demo/VIDEO_SCRIPT.md) — full spoken script and navigation flow
- [demo/DEMO_CHECKLIST.md](demo/DEMO_CHECKLIST.md) — pre-flight checklist for recording or live demo

These files are kept separate so the project documentation, demo narrative, and runtime notes stay easy to follow and easy to commit in clean chunks.

## Project structure

- [app/main.py](app/main.py) — main FastAPI app, safety logic, DB ledger, local fallback, Celesto orchestration
- [app/templates/index.html](app/templates/index.html) — browser UI
- [app/static/app.js](app/static/app.js) — front-end upload logic
- [app/static/styles.css](app/static/styles.css) — UI styling
- [tests/test_reports.py](tests/test_reports.py) — validation tests for the project contract
- [logs/commands.jsonl](logs/commands.jsonl) — audit log for commands and decisions
- [reports](reports) — challenge evidence, failure traces, reliability metrics, and capability docs
- [scripts](scripts) — helper scripts for report generation
- [seeds/01_runs.sql](seeds/01_runs.sql) — seeded run data for the ledger
- [docker-compose.yml](docker-compose.yml) — compose setup for the control plane
- [Dockerfile](Dockerfile) — container definition
- [requirements.txt](requirements.txt) — Python dependencies

## Setup

### Required tools

- Python 3.11+
- Docker and Docker Compose
- A local or Celesto-enabled execution environment

### Local environment and secrets

The project expects a user-local [.env](.env) file. This is where the real secrets live.

- Keep real credentials in [.env](.env)
- Use [.env.example](.env.example) as the public template
- Do not commit real keys or API tokens

### Run the app

```bash
DATABASE_URL=sqlite:///./poisoned_analyst.db uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Run the tests

```bash
pytest tests/test_reports.py -q
```

## Learn the project by reading in this order

1. [PROJECT_GUIDE.md](PROJECT_GUIDE.md) — the learning map for the codebase
2. [app/main.py](app/main.py) — main application flow and logic
3. [tests/test_reports.py](tests/test_reports.py) — what the app is expected to do
4. [reports](reports) — evidence and project narrative
5. [logs/commands.jsonl](logs/commands.jsonl) — command audit trail and safety decisions

## Validation

The project is validated with:

```bash
pytest tests/test_reports.py -q
```

Current verified result:

- 49 tests passed

## Important note

This is a local, safe demo system for untrusted analysis execution. It is not a replacement for a cloud security boundary by itself, but it is a strong educational and demo-ready sandbox architecture for AI-agent workloads.

The current project status is intentionally honest:

- the app is compatible with live Celesto execution when the provider is properly provisioned
- the code path is ready for that runtime
- the local fallback path keeps the demo usable when the provider rejects or does not provide a live sandbox

For a deeper explanation of the project, see [PROJECT_GUIDE.md](PROJECT_GUIDE.md).
