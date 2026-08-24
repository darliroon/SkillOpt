"""Real-data regression: run format_comparison_text on officeqa's 20 pairs
with the default 200k budget and confirm it no longer crashes."""
import glob
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from skillopt.optimizer.slow_update import (
    _read_trajectory,
    format_comparison_text,
    configure_slow_update_token_budget,
    _count_tokens,
)

# Reset to default 200k budget (other tests may have mutated the state)
configure_slow_update_token_budget(200_000)

convs = sorted(glob.glob(
    "outputs/skillopt_officeqa_gpt-5.2_20260824_102707/**/conversation.json",
    recursive=True,
))
assert convs, "no conversation.json found"

pairs = []
for i, c in enumerate(convs[:20]):
    task_id = os.path.basename(os.path.dirname(c))
    rollout_dir = os.path.dirname(os.path.dirname(os.path.dirname(c)))
    traj = _read_trajectory(rollout_dir, task_id)
    # Pretend all 20 are persistent_fail (worst case: all carry full traj)
    pairs.append({
        "id": f"T{i}",
        "task": f"task {i}",
        "category": "persistent_fail",
        "prev": {"hard": 0, "soft": 0.0, "predicted_answer": "x", "fail_reason": ""},
        "curr": {"hard": 0, "soft": 0.0, "predicted_answer": "y", "fail_reason": ""},
        "prev_trajectory": traj,
        "curr_trajectory": traj,  # same → would have crashed before
    })

# Full unbounded size (what crashed before)
full_chars = sum(len(p["prev_trajectory"]) + len(p["curr_trajectory"]) for p in pairs)
print(f"Raw trajectory chars (unbounded): {full_chars}  (~{full_chars//4} tokens)")

text = format_comparison_text(pairs)
final_tokens = _count_tokens(text)
print(f"After eviction (budget=200000): {final_tokens} tokens, {len(text)} chars")
assert final_tokens <= 200_000, "must fit within budget"
print(f"PASS: real officeqa 20-pair regression — fits within 200k budget")
print(f"      (previously crashed at ~299k tokens, now bounded to {final_tokens})")
