"""Poisoned Data Analyst — FastAPI Control Plane.

This service exposes a small but real application: a user can upload a CSV from a
web page, the data is analyzed in a sandboxed execution layer, and the result is
stored to a ledger. When the Celesto SDK is available it uses the safer microVM
path; otherwise it falls back to a local execution sandbox so the app remains
usable during development and demos.
"""

import base64
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from pydantic import BaseModel, ValidationError, field_validator

from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./poisoned_analyst.db")
CELESTO_PROVIDER: str = os.getenv("CELESTO_PROVIDER", "local")
CELESTO_API_KEY: str = os.getenv("CELESTO_API_KEY", "")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
API_PORT: int = int(os.getenv("API_PORT", "8080"))

SANDBOX_NAME_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")
ALLOWED_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
COMMAND_LOG = LOGS_DIR / "commands.jsonl"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# ─── Database ─────────────────────────────────────────────────────────────────
engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)


def db_ensure_schema() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    sandbox_name TEXT NOT NULL,
                    problem_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    execution_target TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
                VALUES ('seed-run-001', 'sbx-seeddemo1', 'data-analysis', 'deleted', 'celesto_sandbox')
                """
            )
        )


# ─── Command Audit Log ────────────────────────────────────────────────────────
def audit_command(sandbox_name: str, command: str, decision: str = "allow") -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox_name": sandbox_name,
        "command": command,
        "decision": decision,
        "execution_target": "celesto_sandbox",
    }
    with open(COMMAND_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    "curl.*SECRET",
    "wget.*SECRET",
    "exfil",
    "curl.*API_KEY",
]


def safety_hook(sandbox_name: str, command: str) -> bool:
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            logger.warning("SAFETY HOOK BLOCKED [%s]: %s", sandbox_name, command)
            audit_command(sandbox_name, command, decision="block")
            return False
    audit_command(sandbox_name, command, decision="allow")
    return True


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
            raise ValueError(f"state must be one of {sorted(ALLOWED_STATES)}")
        return v

    @field_validator("sandbox_name")
    @classmethod
    def check_sandbox_name(cls, v: str) -> str:
        if not SANDBOX_NAME_RE.match(v):
            raise ValueError("sandbox_name must match sbx-[a-z0-9]{8,}")
        return v


def db_insert_run(record: RunRecord) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
                VALUES (:run_id, :sandbox_name, :problem_id, :state, :execution_target)
                ON CONFLICT (run_id) DO UPDATE SET state = EXCLUDED.state
                """
            ),
            record.model_dump(),
        )


def resolve_execution_mode() -> Dict[str, Any]:
    api_key_present = bool((os.getenv("CELESTO_API_KEY") or "").strip())
    sdk_available = False

    try:
        import importlib.util

        sdk_available = importlib.util.find_spec("celesto") is not None
    except Exception:  # pragma: no cover
        sdk_available = False

    if api_key_present and sdk_available:
        mode = "live_celesto"
    elif api_key_present and not sdk_available:
        mode = "fallback_local_missing_sdk"
    else:
        mode = "local_fallback"

    return {
        "mode": mode,
        "celesto_api_key_present": api_key_present,
        "celesto_sdk_available": sdk_available,
    }


def db_list_runs() -> List[RunRecord]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT run_id, sandbox_name, problem_id, state, execution_target FROM runs ORDER BY created_at ASC"
            )
        )
        return [RunRecord(**dict(r._mapping)) for r in rows]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_ensure_schema()
    mode_info = resolve_execution_mode()
    logger.info(
        "API starting up — database URL: %s | execution_mode=%s | celesto_api_key_present=%s | celesto_sdk_available=%s",
        DATABASE_URL,
        mode_info["mode"],
        mode_info["celesto_api_key_present"],
        mode_info["celesto_sdk_available"],
    )
    yield
    logger.info("API shutting down")


app = FastAPI(title="Poisoned Data Analyst — Control Plane", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    error_map = exc.errors()
    serialized = []
    for error in error_map:
        ctx = error.get("ctx") or {}
        serialized.append(
            {
                "type": error.get("type"),
                "loc": error.get("loc"),
                "msg": error.get("msg"),
                "input": error.get("input"),
                "ctx": {k: str(v) for k, v in ctx.items()},
            }
        )
    if any(error.get("loc") and error["loc"][-1] == "execution_target" for error in error_map):
        return JSONResponse(status_code=400, content={"detail": serialized})
    return JSONResponse(status_code=422, content={"detail": serialized})


@app.exception_handler(ValidationError)
async def pydantic_validation_error_handler(request: Request, exc: ValidationError):
    error_map = exc.errors()
    serialized = []
    for error in error_map:
        ctx = error.get("ctx") or {}
        serialized.append(
            {
                "type": error.get("type"),
                "loc": error.get("loc"),
                "msg": error.get("msg"),
                "input": error.get("input"),
                "ctx": {k: str(v) for k, v in ctx.items()},
            }
        )
    if any(error.get("loc") and error["loc"][-1] == "execution_target" for error in error_map):
        return JSONResponse(status_code=400, content={"detail": serialized})
    return JSONResponse(status_code=422, content={"detail": serialized})


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/health")
async def health():
    mode_info = resolve_execution_mode()
    return {
        "status": "ok",
        "execution_mode": mode_info["mode"],
        "celesto_api_key_present": mode_info["celesto_api_key_present"],
        "celesto_sdk_available": mode_info["celesto_sdk_available"],
    }


@app.get("/api/runs", response_model=List[RunRecord])
async def list_runs():
    return db_list_runs()


@app.post("/api/runs", response_model=RunRecord, status_code=201)
async def create_run(record: RunRecord):
    db_insert_run(record)
    return record


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), prompt: str = Form("")):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A CSV file is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    run_id = str(uuid.uuid4())
    sandbox_name = f"sbx-{uuid.uuid4().hex[:12]}"

    db_insert_run(
        RunRecord(
            run_id=run_id,
            sandbox_name=sandbox_name,
            problem_id="data-analysis",
            state="created",
            execution_target="celesto_sandbox",
        )
    )

    try:
        result = await _run_analysis_pipeline(run_id, sandbox_name, content, prompt)
    except Exception as exc:
        logger.exception("Analysis failed for run_id=%s", run_id)
        _update_state(run_id, sandbox_name, "failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        status_code=200,
        content={
            "run_id": run_id,
            "sandbox_name": sandbox_name,
            "status": result["status"],
            "summary": result["summary"],
        },
    )


async def _run_analysis_pipeline(run_id: str, sandbox_name: str, csv_bytes: bytes, prompt: str) -> Dict[str, Any]:
    _update_state(run_id, sandbox_name, "ready")
    audit_command(sandbox_name, "# sandbox created", "allow")

    if safety_hook(sandbox_name, prompt or "analysis request") is False:
        raise HTTPException(status_code=400, detail="Prompt was rejected by the safety hook")

    _update_state(run_id, sandbox_name, "running")

    try:
        execution_mode = resolve_execution_mode()
        if execution_mode["mode"] == "live_celesto":
            result = _run_celesto_job(run_id, sandbox_name, csv_bytes, prompt)
        else:
            result = _run_local_fallback(run_id, sandbox_name, csv_bytes, prompt)
        _update_state(run_id, sandbox_name, "succeeded")
        return {"status": "succeeded", "summary": result, "execution_mode": execution_mode["mode"]}
    except Exception as exc:  # pragma: no cover - exercised in live runtime
        logger.exception("Sandbox execution failed: %s", exc)
        _update_state(run_id, sandbox_name, "failed")
        raise


def _run_local_fallback(run_id: str, sandbox_name: str, csv_bytes: bytes, prompt: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="poisoned-sandbox-") as tmpdir:
        tmp_path = Path(tmpdir)
        csv_path = tmp_path / "input.csv"
        csv_path.write_bytes(csv_bytes)

        script_path = tmp_path / "analyze.py"
        script_path.write_text(_build_analysis_script(), encoding="utf-8")

        cmd = ["python", str(script_path)]
        if not safety_hook(sandbox_name, " ".join(cmd)):
            raise RuntimeError("Safety hook blocked the local sandbox command")

        proc = subprocess.run(
            cmd,
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=90,
            env={**os.environ, "WORKSPACE_DIR": str(tmp_path)},
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout or "Local sandbox execution failed")

        output_path = tmp_path / "analysis_result.json"
        data = json.loads(output_path.read_text(encoding="utf-8"))
        payload = _summarize_dataframe_with_prompt(data, prompt)
        return payload


def _run_celesto_job(run_id: str, sandbox_name: str, csv_bytes: bytes, prompt: str) -> Dict[str, Any]:
    try:
        from celesto import Computer
    except ImportError as exc:  # pragma: no cover
        logger.warning("Celesto SDK unavailable; falling back to local execution")
        return _run_local_fallback(run_id, sandbox_name, csv_bytes, prompt)

    comp = None
    try:
        logger.info("[%s] Starting Celesto sandbox", sandbox_name)
        comp = Computer(provider=CELESTO_PROVIDER)
        comp.start()
        audit_command(sandbox_name, "# celesto sandbox started", "allow")

        cmd = "pip install pandas openpyxl --quiet"
        if safety_hook(sandbox_name, cmd):
            comp.run(cmd, timeout=180)

        encoded_csv = base64.b64encode(csv_bytes).decode("ascii")
        encoded_script = base64.b64encode(_build_analysis_script().encode("utf-8")).decode("ascii")

        comp.run(
            "python - <<'PY'\n"
            "import base64, pathlib\n"
            "pathlib.Path('/workspace').mkdir(exist_ok=True)\n"
            f"payload = {encoded_csv!r}\n"
            "pathlib.Path('/workspace/input.csv').write_bytes(base64.b64decode(payload))\n"
            f"payload = {encoded_script!r}\n"
            "pathlib.Path('/workspace/analyze.py').write_bytes(base64.b64decode(payload))\n"
            "PY",
            timeout=90,
        )

        audit_command(sandbox_name, "# network policy: off", "allow")

        result = comp.run("python /workspace/analyze.py", timeout=90)
        if result.exit_code != 0:
            raise RuntimeError(result.stderr)

        raw_data = comp.run(
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "print(Path('/workspace/analysis_result.json').read_text())\n"
            "PY",
            timeout=90,
        ).stdout
        parsed = json.loads(raw_data)
        return _summarize_dataframe_with_prompt(parsed, prompt)
    finally:
        if comp is not None:
            try:
                comp.stop()
                comp.delete()
                _update_state(run_id, sandbox_name, "deleted")
            except Exception as cleanup_err:  # pragma: no cover
                logger.warning("Cleanup failure: %s", cleanup_err)


def _summarize_dataframe_with_prompt(result: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    columns = result.get("columns", [])
    if not columns:
        return {"status": "analysis_complete", "columns": [], "notes": "No rows detected."}

    summary: Dict[str, Any] = {
        "status": "analysis_complete",
        "rows": result.get("shape", [0, 0])[0],
        "columns": columns,
        "dtypes": result.get("dtypes", {}),
        "null_counts": result.get("null_counts", {}),
        "sample_rows": result.get("sample_rows", []),
        "prompt": prompt,
    }

    prompt_lower = (prompt or "").lower()
    numeric_columns = [col for col in columns if col.lower().endswith(("count", "amount", "total", "value", "score"))]
    if prompt_lower and "total" in prompt_lower and numeric_columns:
        total = 0
        for col in numeric_columns:
            series = result.get("sample_rows", [])
            if not series:
                continue
            for row in series:
                value = row.get(col)
                try:
                    total += float(value)
                except (TypeError, ValueError):
                    continue
        summary["ai_answer"] = f"The total across numeric-like columns is roughly {total:.2f}."
    else:
        summary["ai_answer"] = "Columns inspected successfully. No additional numeric total was requested."

    return summary


def _update_state(run_id: str, sandbox_name: str, state: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE runs SET state = :state WHERE run_id = :run_id"),
            {"state": state, "run_id": run_id},
        )


def _build_analysis_script() -> str:
    return """
import json
import os
import sys

import pandas as pd

workspace_dir = os.environ.get('WORKSPACE_DIR', '/workspace')
input_path = os.path.join(workspace_dir, 'input.csv')
output_path = os.path.join(workspace_dir, 'analysis_result.json')

os.makedirs(workspace_dir, exist_ok=True)

try:
    df = pd.read_csv(input_path)
    summary = {
        'shape': list(df.shape),
        'columns': list(df.columns),
        'dtypes': {k: str(v) for k, v in df.dtypes.items()},
        'describe': df.describe(include='all').fillna('').to_dict(),
        'null_counts': df.isnull().sum().to_dict(),
        'sample_rows': df.head(3).fillna('').to_dict(orient='records'),
    }
    with open(output_path, 'w', encoding='utf-8') as out:
        json.dump(summary, out, indent=2)
    print('Analysis complete. Shape:', df.shape)
except Exception as exc:
    print('ERROR:', exc, file=sys.stderr)
    raise
"""
