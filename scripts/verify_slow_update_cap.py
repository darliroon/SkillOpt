"""Verify slow_update truncation bounds on real officeqa conversations."""
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from skillopt.optimizer.slow_update import _read_trajectory, format_comparison_text

import glob

convs = sorted(glob.glob("outputs/skillopt_officeqa_gpt-5.2_20260824_102707/**/conversation.json", recursive=True))
assert convs, "no conversation.json found"
pairs_traj = []
for c in convs[:20]:
    task_id = os.path.basename(os.path.dirname(c))
    rollout_dir = os.path.dirname(os.path.dirname(os.path.dirname(c)))  # .../<rollout_dir>/predictions/<id>/conversation.json
    traj = _read_trajectory(rollout_dir, task_id)
    assert len(traj) <= 12000, f"{task_id}: {len(traj)} chars exceeds cap"
    pairs_traj.append(traj)

pairs = []
for i, traj in enumerate(pairs_traj):
    pairs.append({
        "id": f"T{i}",
        "task": f"task {i}",
        "category": "persistent_fail",
        "prev": {"hard": 0, "soft": 0.0, "predicted_answer": "x", "fail_reason": ""},
        "curr": {"hard": 0, "soft": 0.0, "predicted_answer": "y", "fail_reason": ""},
        "prev_trajectory": traj,
        "curr_trajectory": traj,  # same -> dedup path
    })

text = format_comparison_text(pairs)
est_tokens = len(text) // 4
print(f"tasks={len(pairs)}  raw_traj_chars={sum(len(t) for t in pairs_traj)}  formatted_chars={len(text)}  est_tokens~{est_tokens}")
assert est_tokens < 150000, "still too big"
print("OK: comparison text bounded under context limit (272k)")
