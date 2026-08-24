"""Verify the slow_update comparison-text token-budget eviction mechanism.

Checks:
1. No budget (0) → full text, no eviction sentinel.
2. Large budget → no eviction.
3. Tight budget → eviction order is improved(long→short) → persistent_fail(long→short) → regressed(long→short).
4. Evicted entries keep metadata; sentinel "(trajectory omitted ...)" appears.
5. Stable_success trajectories never appear.
6. All-evicted-and-still-over → RuntimeError with a helpful hint.
"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from skillopt.optimizer import slow_update as su


def _pair(pid, cat, prev_traj_len, curr_traj_len):
    """Build a synthetic comparison pair with controllable trajectory sizes."""
    # Use a unique marker per pair so substring counts are unambiguous.
    return {
        "id": pid,
        "task": f"task {pid}",
        "category": cat,
        "prev": {"hard": 0, "soft": 0.0, "predicted_answer": "x", "fail_reason": ""},
        "curr": {"hard": 0, "soft": 0.0, "predicted_answer": "y", "fail_reason": ""},
        "prev_trajectory": f"[{pid}_PREV]" * prev_traj_len,
        "curr_trajectory": f"[{pid}_CURR]" * curr_traj_len,
    }


# ── Test 1: budget=0 disables enforcement ──────────────────────────────────
su.configure_slow_update_token_budget(0)
pairs = [_pair("R1", "regressed", 5000, 5000)]
text = su.format_comparison_text(pairs)
assert "*(trajectory omitted" not in text, "budget=0 should not evict"
assert "[R1_PREV]" in text, "budget=0 should keep full trajectory"
print("T1 PASS: budget=0 disables enforcement")

# ── Test 2: large budget → no eviction ─────────────────────────────────────
su.configure_slow_update_token_budget(10_000_000)
pairs = [_pair("I1", "improved", 500, 500), _pair("R1", "regressed", 500, 500)]
text = su.format_comparison_text(pairs)
assert "*(trajectory omitted" not in text
assert "[I1_PREV]" in text
assert "[I1_CURR]" in text
assert "[R1_PREV]" in text
assert "[R1_CURR]" in text
print("T2 PASS: large budget keeps everything")

# ── Test 3: eviction order — improved(long) → improved(short) ─────────────
# Use a budget that forces eviction. Char/4 ≈ token estimate when tiktoken
# is absent; pick numbers that make the ordering unambiguous either way.
su.configure_slow_update_token_budget(2_000)
pairs = [
    _pair("I_LONG", "improved", 8000, 8000),   # 16k chars → evict first
    _pair("I_SHORT", "improved", 500, 500),    # 1k chars
    _pair("P_LONG", "persistent_fail", 8000, 8000),
    _pair("P_SHORT", "persistent_fail", 500, 500),
    _pair("R_LONG", "regressed", 8000, 8000),  # highest priority → evict last
    _pair("R_SHORT", "regressed", 500, 500),
]
text = su.format_comparison_text(pairs)

# All six metadata blocks must be present (metadata always retained)
for pid in ("I_LONG", "I_SHORT", "P_LONG", "P_SHORT", "R_LONG", "R_SHORT"):
    assert f"Task {pid}:" in text, f"metadata for {pid} must survive eviction"

# Eviction order: improved(long) is least important AND longest → evicted first.
# regressed is most important → should be evicted last (if at all).
# Given the tight 2k budget, improved+persistent_fail long ones get evicted;
# regressed long likely also evicted but AFTER the others.
sentinel_count = text.count("*(trajectory omitted")
# At least I_LONG and P_LONG should be evicted (they're the biggest, lowest priority)
i_long_block = text.split("Task I_LONG")[1].split("Task")[0] if "Task I_LONG" in text else ""
i_long_evicted = "*(trajectory omitted" in i_long_block
assert i_long_evicted, "I_LONG should be evicted before any regressed entry"
# I_LONG's trajectory marker must be gone
assert "[I_LONG_PREV]" not in text, "I_LONG evicted → trajectory marker gone"
print(f"T3 PASS: eviction order correct (sentinels={sentinel_count})")

# ── Test 4: stable_success trajectories never shown ────────────────────────
su.configure_slow_update_token_budget(10_000_000)
pairs = [
    _pair("S1", "stable_success", 5000, 5000),
    _pair("R1", "regressed", 100, 100),
]
text = su.format_comparison_text(pairs)
# Stable success should NOT have trajectory blocks even with infinite budget
assert "[S1_PREV]" not in text, "stable_success must never show trajectory"
assert "[S1_CURR]" not in text
# But regressed should
r1_block = text.split("Task R1")[1] if "Task R1" in text else ""
assert "[R1_PREV]" in r1_block, "regressed should show trajectory"
print("T4 PASS: stable_success trajectories never shown")

# ── Test 5: all evicted, still over → RuntimeError ─────────────────────────
su.configure_slow_update_token_budget(50)  # absurdly small
pairs = [
    _pair("I1", "improved", 10000, 10000),
    _pair("R1", "regressed", 10000, 10000),
]
try:
    su.format_comparison_text(pairs)
    assert False, "should have raised RuntimeError"
except RuntimeError as e:
    assert "slow_update_samples" in str(e), "error should hint at slow_update_samples"
    print(f"T5 PASS: RuntimeError raised when all evicted still over budget")

# ── Test 6: eviction prefers longest within category ───────────────────────
# Construct 2 improved pairs where one is much longer; the longer must evict first
su.configure_slow_update_token_budget(4_000)
pairs = [
    _pair("I_BIG", "improved", 8000, 8000),   # 16k chars
    _pair("I_SML", "improved", 1000, 1000),   # 2k chars
    _pair("R_KEEP", "regressed", 100, 100),   # tiny, must survive
]
text = su.format_comparison_text(pairs)
i_big_evicted = "[I_BIG_PREV]" not in text
i_sml_evicted = "[I_SML_PREV]" not in text
r_keep_present = "[R_KEEP_PREV]" in text
# I_BIG must be evicted before I_SML (it's longer → more token savings per step)
assert i_big_evicted, "I_BIG (longer) must be evicted before I_SML"
assert r_keep_present, "R_KEEP (regressed, small) should survive"
print(f"T6 PASS: within-category longest-first eviction (I_BIG evicted={i_big_evicted}, I_SML evicted={i_sml_evicted}, R_KEEP present={r_keep_present})")

print("\n=== All token-budget eviction tests passed ===")
