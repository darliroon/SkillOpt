"""Probe h:gpt-5.5 with a FULL 8-trajectory minibatch (training-equivalent).

Checks whether h:gpt-5.5 returns empty edits list when given the real
training-size input (8 trajectories, full prompt).
"""
import glob
import json
import os
import time
import urllib.request

URL = "https://yibuapi.com/v1/"
KEY = "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex"
MODEL = "h:gpt-5.5"

with open("skillopt/prompts/analyst_error.md", encoding="utf-8") as f:
    SYSTEM = f.read()

with open("skillopt/envs/officeqa/skills/initial.md", encoding="utf-8") as f:
    SKILL = f.read()

# Find 8 failed trajectories from v4 training
convs = sorted(glob.glob(
    "outputs/skillopt_officeqa_h-gpt-5.5_20260824_150900/**/conversation.json",
    recursive=True,
))[:8]

def _fmt(c):
    with open(c, encoding="utf-8") as f:
        conv = json.load(f)
    lines = []
    for entry in conv:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "tool_call":
            lines.append(f"[action] {entry.get('cmd', '')[:500]}")
            lines.append(f"[obs]    {entry.get('obs', '')[:500]}")
        elif "action" in entry and "env_feedback" in entry:
            step = entry.get("step", "?")
            lines.append(f"[step {step} action] {entry.get('action', '')[:300]}")
            lines.append(f"[step {step} obs]    {entry.get('env_feedback', '')[:300]}")
        elif entry.get("role") == "system":
            lines.append(f"[verification] {entry.get('content', '')[:200]}")
        else:
            lines.append(f"[{entry.get('role', 'agent')}] {entry.get('content', '')[:300]}")
    return "\n".join(lines)[:3000]  # cap each traj

trajs = [_fmt(c) for c in convs]
trajectory_text = "\n\n---\n\n".join(
    f"### Trajectory {i+1}\n{t}" for i, t in enumerate(trajs)
)

USER = (
    f"## Current Skill\n{SKILL}\n\n"
    f"## Edits Budget\nProduce at most L=4 edits.\n\n"
    f"## Failed Trajectories ({len(trajs)} total)\n{trajectory_text}"
)

print(f"Trajectories: {len(trajs)}")
print(f"User prompt:  {len(USER)} chars")
print("=" * 70)

body = json.dumps({
    "model": MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ],
    "max_tokens": 16384,
}).encode()

req = urllib.request.Request(
    URL.rstrip("/") + "/chat/completions",
    data=body,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + KEY,
    },
)

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
print("=== content (first 1500 chars) ===")
print(content[:1500])
print()

from skillopt.utils.json_utils import extract_json
result = extract_json(content)
print("=== extract_json result ===")
if result is None:
    print("None — extract_json FAILED")
else:
    print(f"keys: {list(result.keys())}")
    if "patch" in result:
        patch = result["patch"]
        edits = patch.get("edits", [])
        print(f"patch.reasoning: {patch.get('reasoning', '')[:200]!r}")
        print(f"patch.edits: {len(edits)} edits")
        for i, e in enumerate(edits):
            print(f"  edit {i}: op={e.get('op')} content={e.get('content', '')[:80]!r}")
    else:
        print("NO 'patch' field — wrong JSON shape")
        print(f"full result: {json.dumps(result, indent=2)[:500]}")
