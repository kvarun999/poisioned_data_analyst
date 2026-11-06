# Project explanation video script

This file is the full walkthrough for a short project demo or pitch video. It is written so you can speak naturally while clicking through the app and explaining the architecture.

## Goal

Show that this project is a security-focused sandbox for AI-driven CSV analysis. The core idea is: a user uploads a CSV, the app runs the analysis in a controlled execution environment, and dangerous or exfiltration-style behavior is blocked before it can affect the host system.

## Suggested runtime setup

Before recording or presenting:

1. Open the project root in a terminal.
2. Start the app:
   ```bash
   DATABASE_URL=sqlite:///./poisoned_analyst.db uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```
3. Open the browser to:
   - http://localhost:8080/
   - http://localhost:8080/health
   - http://localhost:8080/docs
4. Keep the following files open in the editor:
   - [README.md](../README.md)
   - [PROJECT_GUIDE.md](../PROJECT_GUIDE.md)
   - [app/main.py](../app/main.py)

## Opening script (30-45 seconds)

"Hi everyone. This project is a sandboxed data-analysis application for AI-agent workloads. The idea is simple: if an agent or LLM is asked to process an uploaded CSV, that code should be isolated from the real host environment, logged, and constrained before it can do anything destructive or exfiltrate secrets."

"The app accepts a CSV, runs analysis in a sandboxed execution layer, records the run in a database, and applies safety checks on commands before they are allowed to execute."

## Explain the problem (45-60 seconds)

"The real risk is that an LLM is often asked to work with data files that may contain hidden instructions or dangerous patterns. If the generated analysis code is allowed to run unrestricted on the host machine, it could access credentials, run destructive commands, or exfiltrate data."

"The project addresses that by separating the trusted control plane from the untrusted execution layer. The host keeps the app, secrets, and central logic, while the risky analysis runs in an isolated environment."

## Show the core app (1-2 minutes)

Open the homepage at http://localhost:8080/.

"Here is the main UI. The user uploads a CSV, provides an analysis prompt, and the app processes the file in a controlled execution setup."

"This is intentionally designed for a real-world AI-agent workflow: the user interacts with a clean interface, while the backend handles execution tracking, logging, and safety enforcement."

## Show the health check and runtime mode (30-45 seconds)

Open http://localhost:8080/health.

"This endpoint confirms the runtime execution mode. The app is built to detect whether Celesto is available and whether live sandboxing is actually provisioned."

"If Celesto is available, it can use the live microVM path. If not, it falls back to a local sandboxed execution flow so the application still remains usable and demonstrable."

## Explain the architecture (1-2 minutes)

Navigate to the project files in order:

1. [README.md](../README.md)
2. [PROJECT_GUIDE.md](../PROJECT_GUIDE.md)
3. [app/main.py](../app/main.py)
4. [logs/commands.jsonl](../logs/commands.jsonl)
5. [reports](../reports)

Speak like this:

"The architecture is intentionally simple but realistic. The FastAPI app receives the uploaded CSV and prompt, writes the run metadata to SQLite, and triggers the analysis pipeline."

"The safety hook checks command strings for destructive or exfiltration patterns such as `rm -rf /`, `mkfs`, or network exfiltration attempts. If a command matches a blocked pattern, it is denied and written to the audit log."

"The same pattern is used for the execution ledger: every run gets a run ID, sandbox name, problem ID, state, and execution target. That gives us a traceable, recoverable execution record for each job."

## Explain the Celesto integration (1 minute)

"The system is designed to support a real Celesto execution path for isolated microVM-style sandboxing. The project’s control plane stays on the host, while the risky analysis job is dispatched to the sandbox boundary."

"In this environment, the integration is present and the app is configured to use it when the provider is actually provisioned. The key nuance is that live cloud sandboxing depends on the Celesto account and runtime being active. If that is not available, the app stays in a safe fallback mode rather than pretending the microVM exists."

## Run the actual upload demo (1 minute)

Use the web app and upload a sample CSV.

"Now I’ll upload a CSV and run the analysis. The app will create a run record, validate the prompt, check the safety rules, and execute the pipeline."

After upload, point to the result card and summarize:

- run_id
- sandbox_name
- status
- summary information

Speak:

"The result is structured and human-readable. We get the summary, the dataset shape, the column names, and key metadata. That is the user-facing output from a process that started from an unsafe or untrusted input."

## Explain security controls and resilience (1 minute)

"This is not just a demo app. The project is designed around safety and recovery. It keeps an audit log of commands, blocks known harmful patterns, and records each run state through creation, readiness, execution, and cleanup."

"The goal is to keep the environment recoverable and observable. If the sandbox fails or the analysis code behaves badly, the system has enough trace data to diagnose what happened and reset the boundary without leaving the host compromised."

## Closing lines (30 seconds)

"What makes this project useful is that it combines a real AI workflow with security-aware execution boundaries. It is not just an LLM wrapper; it is a sandboxed control plane for untrusted analysis code."

"The result is a practical demo of how AI systems can be made more trustworthy when they handle user data, local files, and potentially risky code generation."

## Optional final pitch line

"This project turns a risky AI workflow into a controlled, auditable process with explicit execution boundaries, safety enforcement, and a clear fallback strategy."
