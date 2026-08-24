"""Probe h:gpt-5.5 with 4-way concurrency, 5 calls, 8-traj analyst prompt.

Tests whether yibuapi returns empty/truncated content under concurrent load.
If all 5 calls return non-empty content with valid patches, the issue is
concurrency-level dependent (16 workers too many → 4 is safe).
"""
import concurrent.futures
import glob
import json
import os
import time
import urllib.request

URL = "https://yibuapi.com/v1/"
KEY = "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex"
MODEL = "h:gpt-5.5"
CONCURRENCY = 4
N_CALLS = 5

with open("skillopt/prompts/analyst_error.md", encoding="utf-8") as f:
    SYSTEM = f.read()

with open("skillopt/envs/officeqa/skills/initial.md", encoding="utf-8") as f:
    SKILL = f.read()

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
    return "\n".join(lines)[:3000]


trajs = [_fmt(c) for c in convs]
trajectory_text = "\n\n---\n\n".join(
    f"### Trajectory {i+1}\n{t}" for i, t in enumerate(trajs)
)
USER = (
    f"## Current Skill\n{SKILL}\n\n"
    f"## Edits Budget\nProduce at most L=4 edits.\n\n"
    f"## Failed Trajectories ({len(trajs)} total)\n{trajectory_text}"
)

print(f"Concurrency: {CONCURRENCY} workers, {N_CALLS} calls")
print(f"User prompt: {len(USER)} chars")
print("=" * 70)


def call_api(call_id: int) -> dict:
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
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
        elapsed = time.perf_counter() - t0
        msg = data["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")
        usage = data.get("usage", {})
        finish = data["choices"][0].get("finish_reason")
        return {
            "call_id": call_id,
            "elapsed": elapsed,
            "content_len": len(content),
            "reasoning_content_len": len(reasoning),
            "finish_reason": finish,
            "completion_tokens": usage.get("completion_tokens", 0),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
            "content_preview": content[:120],
            "content": content,
        }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "call_id": call_id,
            "elapsed": elapsed,
            "error": str(e)[:200],
            "content_len": 0,
        }


t_start = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
    futures = [pool.submit(call_api, i) for i in range(N_CALLS)]
    results = [f.result() for f in futures]
total_elapsed = time.perf_counter() - t_start

print(f"\nTotal wall time: {total_elapsed:.1f}s")
print()

# Print per-call summary
ok_count = 0
empty_count = 0
error_count = 0
edits_counts = []

from skillopt.utils.json_utils import extract_json

for r in results:
    cid = r["call_id"]
    if "error" in r:
        print(f"  call {cid}: ERROR after {r['elapsed']:.1f}s — {r['error']}")
        error_count += 1
        continue
    cl = r["content_len"]
    rl = r["reasoning_content_len"]
    fn = r["finish_reason"]
    ct = r["completion_tokens"]
    rt = r["reasoning_tokens"]
    preview = r["content_preview"][:80]
    print(f"  call {cid}: {r['elapsed']:5.1f}s  content={cl:5d}  reasoning_content={rl:5d}  "
          f"finish={fn}  compl_tok={ct}  reason_tok={rt}")
    print(f"           preview: {preview!r}")

    if cl == 0:
        empty_count += 1
        print(f"           ✗ EMPTY CONTENT")
    else:
        ok_count += 1
        result = extract_json(r["content"])
        if result is None:
            print(f"           ✗ extract_json FAILED (content not valid JSON)")
        elif "patch" not in result:
            print(f"           ✗ no 'patch' field in JSON")
        else:
            n_edits = len(result["patch"].get("edits", []))
            edits_counts.append(n_edits)
            print(f"           ✓ parsed OK, {n_edits} edits")

print()
print("=" * 70)
print("=== SUMMARY ===")
print(f"  total:   {N_CALLS}")
print(f"  OK:      {ok_count}")
print(f"  empty:   {empty_count}")
print(f"  error:   {error_count}")
if edits_counts:
    print(f"  edits:   {edits_counts}  (mean={sum(edits_counts)/len(edits_counts):.1f})")
if empty_count == 0 and error_count == 0:
    print("\n  ✓ ALL CALLS RETURNED NON-EMPTY CONTENT")
    print("  → 4-way concurrency is SAFE for h:gpt-5.5 on yibuapi")
    print("  → the 0-edits issue was caused by 12-16 way concurrency (limit)")
else:
    print(f"\n  ✗ {empty_count + error_count} CALLS FAILED")
    print("  → even 4-way concurrency triggers empty content")
    print("  → try lowering to 2 workers or check yibuapi quota")
