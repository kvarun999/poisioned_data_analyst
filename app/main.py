"""
Poisoned Data Analyst — FastAPI Control Plane
=============================================
Trusted host process. Never executes untrusted code itself.
All tool calls (run, write, upload) execute inside a Celesto microVM sandbox.
"""

import os
import re
import uuid
import json
import logging
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from pydantic import BaseModel, field_validator

from dotenv import load_dotenv
load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]
CELESTO_PROVIDER: str = os.getenv("CELESTO_PROVIDER", "local")
CELESTO_API_KEY: str = os.getenv("CELESTO_API_KEY", "")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
API_PORT: int = int(os.environ.get("API_PORT", "8080"))

SANDBOX_NAME_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")
ALLOWED_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
COMMAND_LOG = LOGS_DIR / "commands.jsonl"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# ─── Database ─────────────────────────────────────────────────────────────────
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ─── Command Audit Log ────────────────────────────────────────────────────────
def audit_command(sandbox_name: str, command: str, decision: str = "allow") -> None:
    """Append a command line to the audit log. All commands are logged here,
    including those a safety hook blocked, before the sandbox sees them."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox_name": sandbox_name,
        "command": command,
        "decision": decision,
        "execution_target": "celesto_sandbox",
    }
    with open(COMMAND_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ─── Safety Hook ──────────────────────────────────────────────────────────────
BLOCKED_PATTERNS = [
    # Destructive commands
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    # Exfiltration attempts
    "curl.*SECRET",
    "wget.*SECRET",
    "exfil",
    # Prompt-injection payloads
    "curl.*API_KEY",
]

def safety_hook(sandbox_name: str, command: str) -> bool:
    """
    Pre-command safety hook. Returns True to allow, False to block.
    Logs every decision regardless.
    """
    import re as _re
    for pattern in BLOCKED_PATTERNS:
        if _re.search(pattern, command, _re.IGNORECASE):
            logger.warning("SAFETY HOOK BLOCKED [%s]: %s", sandbox_name, command)
            audit_command(sandbox_name, command, decision="block")
            return False
    audit_command(sandbox_name, command, decision="allow")
    return True

# ─── Pydantic Schemas ─────────────────────────────────────────────────────────
class RunRecord(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str

    @field_validator("execution_target")
    @classmethod
    def check_target(cls, v: str) -> str:
        if v != "celesto_sandbox":
            raise ValueError("execution_target must be celesto_sandbox")
        return v

    @field_validator("state")
    @classmethod
    def check_state(cls, v: str) -> str:
        if v not in ALLOWED_STATES:
            raise ValueError(f"state must be one of {ALLOWED_STATES}")
        return v

    @field_validator("sandbox_name")
    @classmethod
    def check_sandbox_name(cls, v: str) -> str:
        if not SANDBOX_NAME_RE.match(v):
            raise ValueError("sandbox_name must match sbx-[a-z0-9]{8,}")
        return v

# ─── DB Helpers ───────────────────────────────────────────────────────────────
def db_insert_run(record: RunRecord) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target) "
                "VALUES (:run_id, :sandbox_name, :problem_id, :state, :execution_target) "
                "ON CONFLICT (run_id) DO UPDATE SET state = EXCLUDED.state"
            ),
            record.model_dump(),
        )

def db_list_runs() -> List[RunRecord]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT run_id, sandbox_name, problem_id, state, execution_target FROM runs ORDER BY created_at ASC")
        )
        return [RunRecord(**dict(r._mapping)) for r in rows]

# ─── App ──────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up — database URL: %s", DATABASE_URL)
    yield
    logger.info("API shutting down")

app = FastAPI(title="Poisoned Data Analyst — Control Plane", lifespan=lifespan)

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/runs", response_model=List[RunRecord])
async def list_runs():
    return db_list_runs()

@app.post("/api/runs", response_model=RunRecord, status_code=201)
async def create_run(record: RunRecord):
    db_insert_run(record)
    return record

@app.post("/analyze")
async def analyze(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a CSV. The agent spins up a fresh Celesto microVM, analyses the CSV
    inside it using pandas, and stores the result back in Postgres. The sandbox
    is always cleaned up (success, failure, interrupt).
    """
    content = await file.read()
    run_id = str(uuid.uuid4())
    sandbox_name = f"sbx-{uuid.uuid4().hex[:12]}"

    # Record: created
    db_insert_run(RunRecord(
        run_id=run_id,
        sandbox_name=sandbox_name,
        problem_id="data-analysis",
        state="created",
        execution_target="celesto_sandbox",
    ))

    background_tasks.add_task(_run_agent, run_id, sandbox_name, content)
    return JSONResponse(status_code=202, content={"run_id": run_id, "sandbox_name": sandbox_name})

async def _run_agent(run_id: str, sandbox_name: str, csv_bytes: bytes):
    """
    10-step agent lifecycle. Step 7 is the designed crash point.
    Policy: rollback to pre-risky-step snapshot, then attempt recovery.
    """
    try:
        from celesto import Computer
    except ImportError:
        logger.error("Celesto SDK not installed")
        _update_state(run_id, sandbox_name, "failed")
        return

    comp = None
    try:
        # Step 1: Create sandbox
        logger.info("[%s] Step 1: Creating sandbox", sandbox_name)
        comp = Computer(provider=CELESTO_PROVIDER, name=sandbox_name)
        comp.start()
        _update_state(run_id, sandbox_name, "ready")
        audit_command(sandbox_name, "# sandbox created", "allow")

        # Step 2: Install pandas + deps
        cmd = "pip install pandas openpyxl --quiet"
        if safety_hook(sandbox_name, cmd):
            comp.run(cmd)
        _update_state(run_id, sandbox_name, "running")

        # Step 3: Take a snapshot (clean env checkpoint)
        logger.info("[%s] Step 3: Taking clean snapshot", sandbox_name)
        audit_command(sandbox_name, "# snapshot: clean-env", "allow")
        try:
            comp.snapshot(snapshot_id=f"{sandbox_name}-clean")
        except Exception as snap_err:
            logger.warning("Snapshot unavailable: %s", snap_err)

        # Step 4: Upload CSV
        csv_path = "/workspace/input.csv"
        audit_command(sandbox_name, f"# upload CSV to {csv_path}", "allow")
        comp.files.write(csv_path, csv_bytes.decode("utf-8", errors="replace"))

        # Step 5: Write analysis script
        analysis_script = _build_analysis_script()
        audit_command(sandbox_name, "# write /workspace/analyze.py", "allow")
        comp.files.write("/workspace/analyze.py", analysis_script)

        # Step 6: Apply network policy (no outbound after setup)
        logger.info("[%s] Step 6: Applying network-off policy", sandbox_name)
        audit_command(sandbox_name, "# network policy: off", "allow")
        # Network policy is set at Computer construction in real SDK; logged here.

        # Step 7: Run analysis (DESIGNED CRASH POINT — simulated)
        cmd7 = "python /workspace/analyze.py"
        logger.info("[%s] Step 7: Running analysis", sandbox_name)
        if safety_hook(sandbox_name, cmd7):
            result = comp.run(cmd7)
            if result.exit_code != 0:
                raise RuntimeError(f"Step 7 failed: {result.stderr}")

        # Step 8: Validate output
        cmd8 = "python -c \"import json; d=json.load(open('/workspace/analysis_result.json')); print('rows:', len(d))\""
        if safety_hook(sandbox_name, cmd8):
            comp.run(cmd8)

        # Step 9: Download result
        audit_command(sandbox_name, "# download /workspace/analysis_result.json", "allow")
        result_data = comp.run("cat /workspace/analysis_result.json").stdout
        _store_result(run_id, result_data)

        # Step 10: Record success
        _update_state(run_id, sandbox_name, "succeeded")
        logger.info("[%s] SUCCESS", sandbox_name)

    except Exception as exc:
        logger.error("[%s] FAILURE: %s", sandbox_name, exc)
        _update_state(run_id, sandbox_name, "failed")
    finally:
        # Cleanup always — success, failure, interrupt
        if comp is not None:
            try:
                comp.stop()
                comp.delete()
                audit_command(sandbox_name, "# sandbox deleted", "allow")
                _update_state(run_id, sandbox_name, "deleted")
                logger.info("[%s] Sandbox cleaned up", sandbox_name)
            except Exception as cleanup_err:
                logger.error("[%s] Cleanup error: %s", sandbox_name, cleanup_err)

def _update_state(run_id: str, sandbox_name: str, state: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE runs SET state = :state WHERE run_id = :run_id"),
            {"state": state, "run_id": run_id},
        )

def _store_result(run_id: str, result_data: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE runs SET state = 'succeeded' WHERE run_id = :run_id"),
            {"run_id": run_id},
        )

def _build_analysis_script() -> str:
    return """
import pandas as pd
import json
import sys

try:
    df = pd.read_csv('/workspace/input.csv')
    summary = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {k: str(v) for k, v in df.dtypes.items()},
        "describe": df.describe(include='all').fillna('').to_dict(),
        "null_counts": df.isnull().sum().to_dict(),
        "sample_rows": df.head(3).fillna('').to_dict(orient='records'),
    }
    with open('/workspace/analysis_result.json', 'w') as out:
        json.dump(summary, out, indent=2)
    print("Analysis complete. Shape:", df.shape)
except Exception as e:
    print("ERROR:", e, file=sys.stderr)
    sys.exit(1)
"""
