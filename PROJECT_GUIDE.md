# Project Guide: Where everything is and how it works

This file is meant to help you learn the project quickly and revise it confidently. It explains the main idea, the major files, and how the features fit together.

## 1. What this project is

Poisoned Data Analyst is a sandboxed data-analysis app for AI agents.

The main idea is:

- a user uploads a CSV
- the app generates or receives analysis logic
- that logic may be unsafe or untrusted
- the code should not be allowed to access the host machine, secrets, or the internet
- instead, it runs inside a controlled sandbox
- the app logs the execution, keeps the run metadata, and returns analysis results

This is a realistic security pattern for LLM-assisted data work.

## 2. The system in one flow

The flow is simple but important:

1. User uploads a CSV through the web app or API
2. The API receives the file and creates a run record
3. The app checks the command and file flow through the safety layer
4. A sandbox is created or a local fallback is used
5. The analysis code runs
6. The result is summarized and returned
7. The run is logged in the database and audit log
8. Sandbox cleanup happens when appropriate

## 3. Main application file

### [app/main.py](app/main.py)

This is the heart of the project.

It contains:

- the FastAPI app setup
- database connectivity and schema
- the run ledger
- safety hook logic
- local sandbox fallback path
- Celesto-ready execution path
- result summarization logic

### Key functions inside the file

#### `db_ensure_schema()`
Creates the SQLite/Postgres ledger schema and seeds an initial demo run.

#### `audit_command()`
Writes audit log entries to [logs/commands.jsonl](logs/commands.jsonl).

#### `safety_hook()`
Rejects commands that look dangerous, such as destructive shell operations or exfiltration patterns.

#### `RunRecord`
Defines the valid schema for a run object: ID, sandbox name, state, target, and problem type.

#### `analyze()`
The main upload endpoint that accepts a file, records a run, and executes the task.

#### `_run_analysis_pipeline()`
Orchestrates the main flow: mark ready, check safety, run analysis, update status.

#### `_run_local_fallback()`
Runs the analysis locally if Celesto is unavailable.

#### `_run_celesto_job()`
Attempts the Celesto-powered execution path when credentials are present.

#### `_summarize_dataframe_with_prompt()`
Turns the raw analysis result into a cleaner summary object.

#### `_build_analysis_script()`
Creates the pandas script that inspects the uploaded CSV.

## 4. Front-end files

### [app/templates/index.html](app/templates/index.html)

This is the HTML page users see in the browser.

It is structured as an enterprise-grade AI security operations (SOC) dashboard. The layout includes:
- Topbar telemetry with runtime mode, egress policy enforcement, audit logging status, and a 1-click Dark/Light theme toggle.
- 4-pillar security architecture hero banner and pipeline stepper ribbon.
- Interactive attack simulation studio with 1-click test datasets (Clean, Prompt Injection, Command Exfil, Dev Mode Takeover).
- Real-time Threat Anatomy card breaking down the payload, attacker intent, and sandbox countermeasure.
- Drag-and-drop CSV dropzone, file preview details, and quick prompt chips.
- Result panel with a 4-dial Security Containment Scoreboard Matrix, KPI cards, and an AI executive summary.
- Multi-tab analysis inspector: formatted Data Sample Table with poison payload highlighting, column schema types, live execution console logs, containment telemetry, and raw JSON.
- Live, searchable, and filterable database run ledger explorer.
- Deep-dive Threat Architecture modal guide.

### [app/static/app.js](app/static/app.js)

This file handles the client-side interactivity and API communication:

- Theme management: toggles between Obsidian Dark and Crisp Light modes, persisting preference to `localStorage`.
- Attack simulation engine: populates `File` and `Blob` datasets and prompts on the fly for 1-click demo runs.
- Threat Anatomy controller: dynamically updates vulnerability classification, payload extracts, attacker goals, and defense countermeasures.
- Drag-and-drop file processing with file size formatting and preview cards.
- Multi-step execution stepper and live terminal console stream simulating microVM lifecycle events.
- Form submission to `/analyze` with comprehensive handling for successful containment and safety hook blocks.
- Real-time data table rendering with automatic poison keyword detection.
- One-click Markdown report export (`.md`) and clipboard copy utilities.
- Database ledger synchronization with `/api/runs`, featuring live search and state-filtering (`All`, `Succeeded`, `Failed`, `Deleted`).

### [app/static/styles.css](app/static/styles.css)

This is the visual design system for the platform:

- Dual-theme styling: Flagship Obsidian Dark theme (`#0a0e17`) with subtle cyber glow effects and Crisp Slate Light theme (`#f8fafc`).
- Clean CSS custom property system for rapid styling consistency.
- High-contrast typography combining Plus Jakarta Sans and JetBrains Mono.
- Glassmorphic card surfaces, refined hairline borders, and elevation drop shadows.
- Status indicator glow animations, keyframe spinners, and responsive layouts for desktop, tablet, and mobile viewports.

## 5. Security and containment features

### Safety hook
The safety system is implemented in [app/main.py](app/main.py) and checks command strings before execution.

It blocks patterns such as:

- destructive commands
- exfiltration patterns
- suspicious curl/wget behavior

Each decision is logged to the audit log.

### Audit log
The log file is [logs/commands.jsonl](logs/commands.jsonl).

Each line is a JSON object with:

- timestamp
- sandbox name
- command
- decision
- execution target

This is what makes the app traceable and auditable.

## 6. Data ledger and state tracking

### [seeds/01_runs.sql](seeds/01_runs.sql)
Seeds the run ledger with sample run data.

### Database table
The table is created in [app/main.py](app/main.py) and holds:

- run ID
- sandbox name
- problem ID
- state
- execution target
- created timestamp

The main valid states are:

- created
- ready
- running
- succeeded
- failed
- deleted

This lets the app understand whether the execution is alive, failed, or completed.

## 7. Reports and evidence files

### [reports/problem.json](reports/problem.json)
Describes the problem the app solves.

### [reports/capabilities.json](reports/capabilities.json)
Lists the capabilities the project contains, such as sandboxing, safety hooks, and network policy.

### [reports/lifecycle.json](reports/lifecycle.json)
Explains the lifecycle and cleanup rules for sandboxes.

### [reports/reliability.json](reports/reliability.json)
Stores run metrics, success rates, timings, and totals.

### [reports/containment.json](reports/containment.json)
Documented containment evidence.

### [reports/failure_policy.json](reports/failure_policy.json)
Defines the failure-response policy.

### [reports/failure_trace.jsonl](reports/failure_trace.jsonl)
Records the exact failure path and rollback/retry behavior.

### [reports/postmortem.md](reports/postmortem.md)
Explains what failed, what was learned, and how the system recovers.

## 8. Validation and tests

### [tests/test_reports.py](tests/test_reports.py)
This file validates the whole project contract:

- report structure
- lifecycle rules
- command log assumptions
- reliability metrics
- failure and containment evidence
- API contract behavior

This is the quality gate for the project.

## 9. Docker and environment setup

### [docker-compose.yml](docker-compose.yml)
Starts the control-plane stack and the supporting services.

### [Dockerfile](Dockerfile)
Defines the runtime container for the app.

### [.env.example](.env.example)
Public template showing the environment variables expected by the app.

### [.env](.env)
Your real local secrets file. Keep this local only and do not commit it.

### [.gitignore](.gitignore)
Prevents runtime files and secret files from being accidentally committed.

## 10. Why the project matters

This project demonstrates a real security idea:

- do not run untrusted AI-generated code on the host
- isolate it
- keep credentials away from the execution space
- make the execution auditable
- recover gracefully from failures

That is the core lesson this project is teaching.

## 11. Best ways to study this project

If you want to learn the architecture quickly, do this:

1. Read [PROJECT_GUIDE.md](PROJECT_GUIDE.md) first
2. Read [app/main.py](app/main.py) next
3. Trace one user upload from start to finish
4. Open [logs/commands.jsonl](logs/commands.jsonl) to see the audit trail
5. Read [tests/test_reports.py](tests/test_reports.py) to see the expected behavior
6. Check the reports folder to understand the evidence and reliability story

## 12. Common learning questions

### Why is there a local fallback?
Because the project should still be usable even when a real Celesto environment is not available locally.

### Why do we keep a ledger?
To prove what ran, where it ran, and the resulting state.

### Why is the safety hook important?
Because it adds a second defense layer before commands reach the sandbox.

### Why are the report files important?
Because they make the project auditable and explain the security/reliability story in a formal way.

## 13. Final takeaway

This is a sandboxed AI-agent system for data analysis.

The important ideas to remember are:

- isolate risky execution
- keep secrets outside the execution boundary
- log every command
- recover cleanly on failure
- prove system behavior with evidence

That is the core of the project.
