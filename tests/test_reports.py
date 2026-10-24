"""
tests/test_reports.py
=====================
Validates all required report files and the live API endpoints.
Run with: pytest tests/test_reports.py -v
"""
import json
import math
import os
import re
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"

SANDBOX_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")
ALLOWED_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}
ALLOWED_CAPABILITY_IDS = {
    "persistence", "snapshots", "celestofs", "browser", "published_ports",
    "network_policy", "safety_hooks", "host_mounts", "coding_agent_preset", "agentor_durable",
}

API_BASE = os.getenv("API_BASE", f"http://localhost:{os.getenv('API_PORT', '8080')}")


# ─── problem.json ─────────────────────────────────────────────────────────────
class TestProblem:
    def setup_method(self):
        self.data = json.loads((REPORTS / "problem.json").read_text())

    def test_keys_exist(self):
        for key in ("who", "agent_work", "proof_output", "idea_source"):
            assert key in self.data, f"Missing key: {key}"

    def test_idea_source(self):
        assert self.data["idea_source"] in ("idea_bank", "original")

    def test_min_lengths(self):
        assert len(self.data["who"]) >= 40
        assert len(self.data["agent_work"]) >= 40
        assert len(self.data["proof_output"]) >= 20


# ─── capabilities.json ────────────────────────────────────────────────────────
class TestCapabilities:
    def setup_method(self):
        self.data = json.loads((REPORTS / "capabilities.json").read_text())
        self.caps = self.data["capabilities"]

    def test_at_least_two(self):
        assert len(self.caps) >= 2

    def test_unique_ids(self):
        ids = [c["id"] for c in self.caps]
        assert len(ids) == len(set(ids)), "Capability IDs are not unique"

    def test_allowed_ids(self):
        for cap in self.caps:
            assert cap["id"] in ALLOWED_CAPABILITY_IDS, f"Unknown capability id: {cap['id']}"

    def test_why_length(self):
        for cap in self.caps:
            assert len(cap["why"]) >= 80, f"why too short for {cap['id']}"

    def test_evidence_paths_exist(self):
        for cap in self.caps:
            p = ROOT / cap["evidence_path"]
            assert p.exists(), f"evidence_path does not exist: {cap['evidence_path']}"


# ─── lifecycle.json ───────────────────────────────────────────────────────────
class TestLifecycle:
    def setup_method(self):
        self.data = json.loads((REPORTS / "lifecycle.json").read_text())

    def test_cleanup_flags(self):
        assert self.data["cleanup_on_success"] is True
        assert self.data["cleanup_on_failure"] is True
        assert self.data["cleanup_on_interrupt"] is True

    def test_sandbox_names_format(self):
        names = self.data["sandbox_names"]
        assert len(names) > 0
        assert len(names) == len(set(names)), "Sandbox names not unique"
        for name in names:
            assert SANDBOX_RE.match(name), f"Invalid sandbox name: {name}"

    def test_names_in_logs_or_reliability(self):
        names_in_lifecycle = set(self.data["sandbox_names"])
        names_in_commands = set()
        cmd_log = LOGS / "commands.jsonl"
        if cmd_log.exists():
            for line in cmd_log.read_text().splitlines():
                if line.strip():
                    obj = json.loads(line)
                    names_in_commands.add(obj["sandbox_name"])

        names_in_reliability = set()
        rel_file = REPORTS / "reliability.json"
        if rel_file.exists():
            rel = json.loads(rel_file.read_text())
            for r in rel["runs"]:
                names_in_reliability.add(r["sandbox_name"])

        known_names = names_in_commands | names_in_reliability
        for name in names_in_lifecycle:
            assert name in known_names, f"Lifecycle sandbox name not found in logs/reliability: {name}"


# ─── commands.jsonl ───────────────────────────────────────────────────────────
class TestCommandLog:
    def setup_method(self):
        raw = (LOGS / "commands.jsonl").read_text().splitlines()
        self.lines = [json.loads(l) for l in raw if l.strip()]

    def test_at_least_one_line(self):
        assert len(self.lines) >= 1

    def test_required_fields(self):
        for obj in self.lines:
            assert "ts" in obj
            assert "sandbox_name" in obj
            assert "command" in obj
            assert "decision" in obj
            assert "execution_target" in obj

    def test_execution_target(self):
        for obj in self.lines:
            assert obj["execution_target"] == "celesto_sandbox", \
                f"Bad execution_target: {obj['execution_target']}"

    def test_decision_enum(self):
        for obj in self.lines:
            assert obj["decision"] in ("allow", "block"), \
                f"Unknown decision: {obj['decision']}"

    def test_sandbox_name_format(self):
        for obj in self.lines:
            assert SANDBOX_RE.match(obj["sandbox_name"]), \
                f"Invalid sandbox name in log: {obj['sandbox_name']}"

    def test_at_least_one_blocked(self):
        blocked = [l for l in self.lines if l["decision"] == "block"]
        assert len(blocked) >= 1, "No blocked commands found in audit log"


# ─── reliability.json ─────────────────────────────────────────────────────────
class TestReliability:
    def setup_method(self):
        self.data = json.loads((REPORTS / "reliability.json").read_text())
        self.runs = self.data["runs"]

    def test_run_count(self):
        assert self.data["run_count"] >= 20
        assert self.data["run_count"] == len(self.runs)

    def test_all_fresh(self):
        for r in self.runs:
            assert r["fresh"] is True

    def test_unique_sandbox_names(self):
        names = [r["sandbox_name"] for r in self.runs]
        assert len(names) == len(set(names))

    def test_sandbox_name_format(self):
        for r in self.runs:
            assert SANDBOX_RE.match(r["sandbox_name"]), f"Invalid: {r['sandbox_name']}"

    def test_numeric_fields_non_negative(self):
        for r in self.runs:
            assert r["wall_clock_s"] >= 0
            assert r["boot_to_ready_s"] >= 0
            assert r["cost_usd"] >= 0

    def test_success_rate(self):
        n = len(self.runs)
        successes = sum(1 for r in self.runs if r["success"])
        expected = successes / n
        assert abs(self.data["success_rate"] - expected) <= 0.001

    def test_median_wall_clock(self):
        sorted_vals = sorted(r["wall_clock_s"] for r in self.runs)
        n = len(sorted_vals)
        if n % 2 == 0:
            expected = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        else:
            expected = sorted_vals[n // 2]
        assert abs(self.data["median_wall_clock_s"] - expected) <= 0.001

    def test_p90_wall_clock(self):
        sorted_vals = sorted(r["wall_clock_s"] for r in self.runs)
        n = len(sorted_vals)
        idx = math.ceil(0.90 * n) - 1
        expected = sorted_vals[idx]
        assert abs(self.data["p90_wall_clock_s"] - expected) <= 0.001

    def test_median_boot(self):
        sorted_vals = sorted(r["boot_to_ready_s"] for r in self.runs)
        n = len(sorted_vals)
        if n % 2 == 0:
            expected = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        else:
            expected = sorted_vals[n // 2]
        assert abs(self.data["median_boot_to_ready_s"] - expected) <= 0.001

    def test_total_cost(self):
        expected = sum(r["cost_usd"] for r in self.runs)
        assert abs(self.data["total_cost_usd"] - expected) <= 0.01

    def test_postmortem_exists_and_length(self):
        pm_path = ROOT / self.data["postmortem_path"]
        assert pm_path.exists()
        assert len(pm_path.read_text()) >= 200


# ─── containment.json ─────────────────────────────────────────────────────────
class TestContainment:
    def setup_method(self):
        self.data = json.loads((REPORTS / "containment.json").read_text())

    def test_attack_type(self):
        assert self.data["attack"] in (
            "prompt_injection_exfil", "destructive_command", "suspicious_package"
        )

    def test_blocked_and_untouched(self):
        assert self.data["blocked"] is True
        assert self.data["host_untouched"] is True

    def test_evidence_paths_exist(self):
        assert len(self.data["evidence_paths"]) >= 1
        for p in self.data["evidence_paths"]:
            assert (ROOT / p).exists(), f"Evidence path not found: {p}"


# ─── failure_policy.json ──────────────────────────────────────────────────────
class TestFailurePolicy:
    def setup_method(self):
        self.data = json.loads((REPORTS / "failure_policy.json").read_text())

    def test_step_values(self):
        assert self.data["failed_step"] == 7
        assert self.data["total_steps"] == 10

    def test_policy_enum(self):
        assert self.data["policy"] in ("resume", "rollback", "fresh")

    def test_rationale_length(self):
        assert len(self.data["rationale"]) >= 200

    def test_trace_has_policy_applied(self):
        trace_path = ROOT / self.data["trace_path"]
        assert trace_path.exists()
        policy = self.data["policy"]
        found = False
        for line in trace_path.read_text().splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("event") == "policy_applied" and obj.get("policy") == policy:
                found = True
                break
        assert found, f"No policy_applied line with policy={policy} in trace"


# ─── concurrency.json ─────────────────────────────────────────────────────────
class TestConcurrency:
    def setup_method(self):
        self.data = json.loads((REPORTS / "concurrency.json").read_text())

    def test_at_least_five_jobs(self):
        assert len(self.data["jobs"]) >= 5

    def test_unique_names(self):
        names = [j["sandbox_name"] for j in self.data["jobs"]]
        assert len(names) == len(set(names))

    def test_sandbox_name_format(self):
        for j in self.data["jobs"]:
            assert SANDBOX_RE.match(j["sandbox_name"]), f"Invalid: {j['sandbox_name']}"

    def test_started_at_non_empty(self):
        for j in self.data["jobs"]:
            assert j["started_at"] and len(j["started_at"]) > 0

    def test_breakage_notes_length(self):
        assert len(self.data["breakage_notes"]) >= 40


# ─── README.md ────────────────────────────────────────────────────────────────
class TestReadme:
    def setup_method(self):
        self.text = (ROOT / "README.md").read_text()

    def test_required_phrases(self):
        required = [
            "Problem statement",
            "How I used Celesto",
            "Eval report",
            "Containment test",
            "State and failure design",
            "Setup",
        ]
        for phrase in required:
            assert phrase in self.text, f"Missing phrase in README: '{phrase}'"


# ─── Live API Tests ───────────────────────────────────────────────────────────
class TestAPI:
    def test_health(self):
        r = httpx.get(f"{API_BASE}/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_list_runs_has_seed(self):
        r = httpx.get(f"{API_BASE}/api/runs", timeout=5)
        assert r.status_code == 200
        names = [row["sandbox_name"] for row in r.json()]
        assert "sbx-seeddemo1" in names

    def test_create_run_valid(self):
        import uuid
        body = {
            "run_id": str(uuid.uuid4()),
            "sandbox_name": "sbx-testapirun01",
            "problem_id": "test",
            "state": "created",
            "execution_target": "celesto_sandbox",
        }
        r = httpx.post(f"{API_BASE}/api/runs", json=body, timeout=5)
        assert r.status_code == 201

    def test_create_run_bad_target(self):
        import uuid
        body = {
            "run_id": str(uuid.uuid4()),
            "sandbox_name": "sbx-testapirun02",
            "problem_id": "test",
            "state": "created",
            "execution_target": "host",
        }
        r = httpx.post(f"{API_BASE}/api/runs", json=body, timeout=5)
        assert r.status_code == 400

    def test_create_run_bad_state(self):
        import uuid
        body = {
            "run_id": str(uuid.uuid4()),
            "sandbox_name": "sbx-testapirun03",
            "problem_id": "test",
            "state": "invalid_state",
            "execution_target": "celesto_sandbox",
        }
        r = httpx.post(f"{API_BASE}/api/runs", json=body, timeout=5)
        assert r.status_code == 422  # Pydantic validation error

    def test_create_run_bad_sandbox_name(self):
        import uuid
        body = {
            "run_id": str(uuid.uuid4()),
            "sandbox_name": "bad-name",
            "problem_id": "test",
            "state": "created",
            "execution_target": "celesto_sandbox",
        }
        r = httpx.post(f"{API_BASE}/api/runs", json=body, timeout=5)
        assert r.status_code == 422
