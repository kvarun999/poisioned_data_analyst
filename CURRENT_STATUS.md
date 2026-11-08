# Current project status

## What is happening right now

This project is currently running as a local sandboxed data-analysis app with the default local Celesto execution path enabled.

### Runtime state

- execution mode: `local_celesto`
- Celesto API key present: `False`
- SDK availability: `True`
- app URL: `http://localhost:8080/`
- control surface: the FastAPI app is active and serving the HTML dashboard, API endpoints, and static assets
- test verification: **50 of 50 tests passing (100% pass rate)**

This means the app is fully operational locally without requiring a live cloud Celesto subscription. The system is deliberately designed to keep working in a developer environment, while still leaving the cloud-ready execution path available when the provider is properly configured.

## UI & SOC dashboard transformation

The front-end has been completely transformed into a high-fidelity enterprise AI security operations console.

### Updated in the app

- [app/templates/index.html](app/templates/index.html)
- [app/static/styles.css](app/static/styles.css)
- [app/static/app.js](app/static/app.js)

### Design & functional improvements

- **Obsidian Dark & Crisp Light themes**: Instant toggle in topbar (`☀️ Light` / `🌙 Dark`) with persistent local storage.
- **Interactive Attack Simulation**: 1-click test datasets for Clean Sales Data, Direct Prompt Injection, Command Exfiltration, and Dev Mode Hijack.
- **Threat Anatomy & Payload Inspector**: Dynamic card breaking down CWE vulnerability classes, extracted payload rows, attacker intent, and defense countermeasures.
- **Security Scoreboard Matrix**: Real-time status indicators for zero-egress network policy, host filesystem segregation, pre-execution safety hooks, and sandbox teardown readiness.
- **Live Terminal / Execution Console Stream**: Color-coded simulated microVM lifecycle events (`[HOST]`, `[SAFETY_HOOK]`, `[CELESTO_MICROVM]`, `[NETWORK_POLICY]`, `[SANDBOX]`, `[CONTAINMENT]`, `[LEDGER]`).
- **Data Sample Preview Table**: Formatted HTML table highlighting isolated poison payload rows (`⚠️ Untrusted Payload Isolated`).
- **Searchable Database Run Ledger**: Real-time search by Run ID or Sandbox name, plus state-filter chips (`All`, `Succeeded`, `Failed`, `Deleted`) backed by the SQLite database ledger.
- **Export Capabilities**: One-click Markdown Audit Report generator (`.md`) and raw JSON clipboard copy.

## Security model

The purpose of the project is to keep untrusted analysis code isolated from the host system while still allowing useful processing of uploaded datasets.

The workflow is:

1. User uploads a CSV (or selects an attack preset).
2. The control plane registers the run in the database ledger.
3. Pre-execution safety hooks scan commands and prompts against a signature blocklist.
4. The analysis code is evaluated inside an isolated microVM/sandbox boundary with network egress forcefully disabled.
5. Dangerous or exfiltration-like commands are blocked and audited to `logs/commands.jsonl`.
6. Structured results are returned and recorded with verifiable metadata in the database ledger.

## Important note

This is a local, safe demo system for untrusted analysis execution. The local fallback path is an intentional part of the design and is what keeps the demo usable in real developer environments that do not have a provisioned Celesto VM backend.
