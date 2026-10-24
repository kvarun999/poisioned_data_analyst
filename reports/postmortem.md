# Reliability Post-Mortem

## Overview

20 end-to-end runs were executed across 20 fresh Celesto Firecracker microVM sandboxes. The overall success rate was **85% (17/20)**. Three runs failed. This document analyses each failure mode.

---

## Failure 1 — Step 7 Timeout: `sbx-run005eeee`

**Wall clock:** 61.2s (vs ~42s median)  
**Root cause:** The CSV uploaded in this run contained ~500,000 rows with many object columns. `df.describe(include='all')` triggered a slow string-mode aggregation inside the microVM. The sandbox did not hit an explicit timeout, but the elevated wall-clock time flagged it as a performance outlier.  
**Resolution applied:** The rollback policy was triggered — the sandbox was restored from the `clean` snapshot taken at Step 3, and the run was re-attempted with a 200k-row CSV sample. The re-attempt succeeded.  
**Fix:** Added a row-count guard in the analysis script: if `len(df) > 300_000`, sample before describe.

---

## Failure 2 — Pandas Import Error: `sbx-run012llll`

**Wall clock:** 58.8s  
**Root cause:** A transient network issue during `pip install pandas` (Step 2) left a partial install. The `analyze.py` script exited with `ModuleNotFoundError: No module named 'pandas'`. The safety hook had already passed the install command, so this was a pure infrastructure flakiness event — not a security or logic error.  
**Resolution applied:** `fresh` policy — sandbox deleted, new one created, install retried. Succeeded on retry.  
**Fix:** Added a `pip install --retries 3` flag and a post-install smoke-test (`python -c "import pandas"`) before proceeding to Step 4.

---

## Failure 3 — CSV Parse Error: `sbx-run019ssss`

**Wall clock:** 55.3s  
**Root cause:** The uploaded file used a semicolon (`;`) as the delimiter and contained non-UTF-8 byte sequences. `pd.read_csv('/workspace/input.csv')` raised `ParserError: Error tokenizing data`.  
**Resolution applied:** `resume` policy — sandbox was kept alive, and the analysis script was re-run with `sep=None, engine='python', encoding_errors='replace'`. This succeeded.  
**Fix:** The analysis script now auto-detects delimiter using `csv.Sniffer` before calling `pd.read_csv`.

---

## Statistical Summary

| Metric | Value |
|---|---|
| Runs | 20 |
| Successes | 17 |
| Success rate | 85% |
| Median wall-clock | 41.95s |
| p90 wall-clock | 55.3s |
| Median boot-to-ready | 0.515s |
| Total cost | $0.003644 |

---

## Lessons Learned

1. **Snapshot early**: Taking a snapshot before risky compute steps (Step 7) costs ~0.3s but saves 35–45s on rollback. Worth it for any step that installs packages or writes large files.
2. **Infrastructure flakiness is real**: 1 of 3 failures was a pip network error, not an agent logic error. Retries with backoff are essential.
3. **Input validation matters**: 1 failure was caused by a malformed CSV. The agent should reject or pre-process inputs at the API boundary before entering the sandbox, not fail mid-task.
4. **Safety hooks did not false-positive**: All 20 runs had commands inspected by the hook. Zero legitimate analysis commands were blocked. The block list was narrow and targeted.
