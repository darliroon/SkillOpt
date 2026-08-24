"""Probe h:gpt-5.5 with the REAL analyst prompt + a real failed trajectory.

This replicates the exact analyst call that produced 0 edits in training.
"""
import glob
import json
import os
import urllib.request

URL = "https://yibuapi.com/v1/"
KEY = "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex"
MODEL = "h:gpt-5.5"

# Load the REAL analyst system prompt
with open("skillopt/prompts/analyst_error.md", encoding="utf-8") as f:
    SYSTEM = f.read()

# Find a real failed trajectory from the v4 training run
convs = sorted(glob.glob(
    "outputs/skillopt_officeqa_h-gpt-5.5_20260824_150900/steps/step_0001/predictions/*/conversation.json"
))
if not convs:
    convs = sorted(glob.glob(
        "outputs/skillopt_officeqa_h-gpt-5.5_20260824_150900/**/conversation.json",
        recursive=True,
    ))
assert convs, "no conversation.json found in v4 output"

# Pick the first failed trajectory (keep it short for the probe)
with open(convs[0], encoding="utf-8") as f:
    conv = json.load(f)

# Format trajectory like fmt_minibatch_trajectories does
traj_lines = []
for entry in conv:
    if not isinstance(entry, dict):
        continue
    if entry.get("type") == "tool_call":
        traj_lines.append(f"[action] {entry.get('cmd', '')[:500]}")
        traj_lines.append(f"[obs]    {entry.get('obs', '')[:500]}")
    elif "action" in entry and "env_feedback" in entry:
        step = entry.get("step", "?")
        traj_lines.append(f"[step {step} action] {entry.get('action', '')[:300]}")
        traj_lines.append(f"[step {step} obs]    {entry.get('env_feedback', '')[:300]}")
    elif entry.get("role") == "system":
        traj_lines.append(f"[verification] {entry.get('content', '')[:200]}")
    else:
        traj_lines.append(f"[{entry.get('role', 'agent')}] {entry.get('content', '')[:300]}")

trajectory_text = "\n".join(traj_lines)[:4000]  # cap for probe

# Load the real initial skill
with open("skillopt/envs/officeqa/skills/initial.md", encoding="utf-8") as f:
    SKILL = f.read()

USER = (
    f"## Current Skill\n{SKILL}\n\n"
    f"## Edits Budget\nProduce at most L=4 edits.\n\n"
    f"## Failed Trajectories (1 total)\n{trajectory_text}"
)

print(f"Model:       {MODEL}")
print(f"System prompt: {len(SYSTEM)} chars (real analyst_error.md)")
print(f"User prompt:   {len(USER)} chars (real skill + real trajectory)")
print(f"Trajectory:    {convs[0]}")
print(f"Traj chars:    {len(trajectory_text)}")
print("=" * 70)

body = json.dumps({
    "model": MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ],
    "max_tokens": 16384,  # match training's optimizer_max_completion_tokens
}).encode()

req = urllib.request.Request(
    URL.rstrip("/") + "/chat/completions",
    data=body,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + KEY,
    },
)

import time
t0 = time.perf_counter()
with urllib.request.urlopen(req, timeout=180) as r:
    data = json.loads(r.read())
elapsed = time.perf_counter() - t0

msg = data["choices"][0]["message"]
content = msg.get("content", "")
reasoning = msg.get("reasoning_content", "")
usage = data.get("usage", {})
finish = data["choices"][0].get("finish_reason")

print(f"Elapsed:       {elapsed:.1f}s")
print(f"finish_reason: {finish!r}")
print(f"content len:    {len(content)}")
print(f"reasoning_content len: {len(reasoning)}")
print(f"usage: {json.dumps(usage, indent=2)}")
print()
print("=== content (first 1000 chars) ===")
print(content[:1000])
print()
print("=== content (last 500 chars) ===")
print(content[-500:] if len(content) > 500 else "(too short)")

# Try to parse like skillopt does
from skillopt.utils.json_utils import extract_json
result = extract_json(content)
print()
print("=== extract_json result ===")
if result is None:
    print("None — extract_json FAILED to parse")
    print("  → This is why training got 0 edits")
else:
    print(f"parsed OK, keys: {list(result.keys())}")
    if "patch" in result:
        patch = result["patch"]
        edits = patch.get("edits", [])
        print(f"patch.edits: {len(edits)} edits")
        for i, e in enumerate(edits):
            print(f"  edit {i}: op={e.get('op')} target={e.get('target', '')[:60]!r}")
    else:
        print("NO 'patch' field — analyst returned JSON but wrong shape")
