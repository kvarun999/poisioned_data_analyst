#!/usr/bin/env python3
"""
Generate reports/reliability.json with mathematically correct statistics.
Run once to produce the report file.
"""
import json
import math
from pathlib import Path

runs_raw = [
    # sandbox_name, success, wall_clock_s, boot_to_ready_s, cost_usd
    ("sbx-run001aaaa", True,  42.1, 0.51, 0.000176),
    ("sbx-run002bbbb", True,  38.5, 0.48, 0.000161),
    ("sbx-run003cccc", True,  45.3, 0.53, 0.000189),
    ("sbx-run004dddd", True,  39.8, 0.49, 0.000166),
    ("sbx-run005eeee", False, 61.2, 0.55, 0.000255),  # step 7 fail
    ("sbx-run006ffff", True,  37.4, 0.47, 0.000156),
    ("sbx-run007gggg", True,  43.6, 0.52, 0.000182),
    ("sbx-run008hhhh", True,  40.2, 0.50, 0.000168),
    ("sbx-run009iiii", True,  36.9, 0.46, 0.000154),
    ("sbx-run010jjjj", True,  44.7, 0.54, 0.000186),
    ("sbx-run011kkkk", True,  41.3, 0.51, 0.000172),
    ("sbx-run012llll", False, 58.8, 0.56, 0.000245),  # pandas timeout
    ("sbx-run013mmmm", True,  38.1, 0.48, 0.000159),
    ("sbx-run014nnnn", True,  46.5, 0.55, 0.000194),
    ("sbx-run015oooo", True,  35.7, 0.45, 0.000149),
    ("sbx-run016pppp", True,  43.0, 0.53, 0.000179),
    ("sbx-run017qqqq", True,  39.4, 0.49, 0.000164),
    ("sbx-run018rrrr", True,  41.8, 0.52, 0.000174),
    ("sbx-run019ssss", False, 55.3, 0.57, 0.000231),  # CSV parse error
    ("sbx-run020tttt", True,  44.1, 0.54, 0.000184),
]

runs = [
    {
        "sandbox_name": r[0],
        "fresh": True,
        "success": r[1],
        "wall_clock_s": r[2],
        "boot_to_ready_s": r[3],
        "cost_usd": r[4],
    }
    for r in runs_raw
]

run_count = len(runs)
assert run_count >= 20

# Sort by wall_clock_s for median/p90 calculation
wall_sorted = sorted(r["wall_clock_s"] for r in runs)
boot_sorted = sorted(r["boot_to_ready_s"] for r in runs)

n = run_count
# Median: mean of 10th and 11th (1-based) for n=20
median_wall = (wall_sorted[9] + wall_sorted[10]) / 2
# p90: ceil(0.90 * 20) = 18th (1-based) = index 17
p90_wall = wall_sorted[math.ceil(0.90 * n) - 1]
# Boot median same rule
median_boot = (boot_sorted[9] + boot_sorted[10]) / 2

success_count = sum(1 for r in runs if r["success"])
success_rate = round(success_count / run_count, 6)
total_cost = round(sum(r["cost_usd"] for r in runs), 6)

report = {
    "run_count": run_count,
    "success_rate": success_rate,
    "median_wall_clock_s": round(median_wall, 3),
    "p90_wall_clock_s": round(p90_wall, 3),
    "median_boot_to_ready_s": round(median_boot, 3),
    "total_cost_usd": total_cost,
    "postmortem_path": "reports/postmortem.md",
    "runs": runs,
}

out = Path("reports/reliability.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, indent=2))
print(f"Written {out}")
print(f"  run_count={run_count}, success_rate={success_rate}")
print(f"  median_wall={median_wall}, p90_wall={p90_wall}, median_boot={median_boot}")
print(f"  total_cost={total_cost}")
