"""Analyze hard vs soft score distribution on the selection set.

Reads results.jsonl from multiple evaluation checkpoints and compares
hard vs soft to see which has more discriminative power for OfficeQA.
"""
import json
import os
from collections import defaultdict

RUN = "outputs/skillopt_officeqa_h-gpt-5.5_w4_20260824_160500"

CHECKPOINTS = [
    ("baseline", os.path.join(RUN, "selection_eval_baseline", "results.jsonl")),
    ("step_1", os.path.join(RUN, "steps", "step_0001", "selection_eval", "results.jsonl")),
    ("step_2", os.path.join(RUN, "steps", "step_0002", "selection_eval", "results.jsonl")),
    ("step_3", os.path.join(RUN, "steps", "step_0003", "selection_eval", "results.jsonl")),
]


def load_results(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


print(f"{'checkpoint':<12} {'n':>3}  {'hard_mean':>9} {'soft_mean':>9}  "
      f"{'hard=1':>6} {'0<soft<1':>9} {'soft=0':>7}  {'hard=soft':>9}")
print("=" * 80)

all_data = {}
for name, path in CHECKPOINTS:
    results = load_results(path)
    if not results:
        print(f"{name:<12} {'(not found)'}")
        continue

    n = len(results)
    hard_vals = [r["hard"] for r in results]
    soft_vals = [r["soft"] for r in results]

    hard_mean = sum(hard_vals) / n
    soft_mean = sum(soft_vals) / n
    hard_1 = sum(1 for v in hard_vals if v >= 1.0)
    soft_mid = sum(1 for v in soft_vals if 0 < v < 1)
    soft_0 = sum(1 for v in soft_vals if v == 0.0)
    hard_eq_soft = sum(1 for h, s in zip(hard_vals, soft_vals) if abs(h - s) < 0.001)

    print(f"{name:<12} {n:>3}  {hard_mean:>9.4f} {soft_mean:>9.4f}  "
          f"{hard_1:>6} {soft_mid:>9} {soft_0:>7}  {hard_eq_soft:>9}")

    all_data[name] = results

# Detailed per-item comparison for the latest checkpoint
latest = CHECKPOINTS[-1][0]
results = all_data.get(latest, [])
if results:
    print(f"\n=== Per-item detail ({latest}) ===")
    print(f"{'UID':<10} {'hard':>5} {'soft':>6}  {'pred':>20} {'gold':>20}  gap")
    print("-" * 80)
    # Sort by soft descending to see where soft captures improvement hard misses
    sorted_results = sorted(results, key=lambda r: r["soft"], reverse=True)
    for r in sorted_results:
        uid = r["id"]
        h = r["hard"]
        s = r["soft"]
        pred = r.get("predicted_answer", "")[:20]
        gold = r.get("ground_truth", "")[:20]
        gap = s - h  # positive = soft captures more signal
        flag = " ← soft>hard" if gap > 0.01 else ""
        print(f"{uid:<10} {h:>5.1f} {s:>6.2f}  {pred:>20} {gold:>20}  {gap:+.2f}{flag}")

# Summary: how many items have hard=0 but soft>0?
if results:
    hard0_soft_pos = sum(1 for r in results if r["hard"] == 0 and r["soft"] > 0)
    hard0_total = sum(1 for r in results if r["hard"] == 0)
    print(f"\n=== Discriminative power summary ({latest}) ===")
    print(f"  hard=0 items:           {hard0_total}/{len(results)}")
    print(f"  hard=0 but soft>0:      {hard0_soft_pos}/{hard0_total}  "
          f"({hard0_soft_pos / max(hard0_total, 1) * 100:.0f}%)")
    print(f"  → soft captures partial signal in {hard0_soft_pos} items hard treats as total failures")

    # Distribution of soft scores for hard=0 items
    hard0_softs = sorted([r["soft"] for r in results if r["hard"] == 0 and r["soft"] > 0], reverse=True)
    if hard0_softs:
        print(f"\n  soft score distribution for hard=0 items (n={len(hard0_softs)}):")
        buckets = defaultdict(int)
        for s in hard0_softs:
            if s >= 0.5:
                buckets["0.5-1.0"] += 1
            elif s >= 0.3:
                buckets["0.3-0.5"] += 1
            elif s >= 0.1:
                buckets["0.1-0.3"] += 1
            else:
                buckets["0-0.1"] += 1
        for k in ["0.5-1.0", "0.3-0.5", "0.1-0.3", "0-0.1"]:
            print(f"    {k}: {buckets[k]}")
