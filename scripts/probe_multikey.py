"""Test multi-key round-robin with 3 keys.

1. Verify each key individually works
2. Run 12 concurrent requests through the round-robin pool
3. Check if each key has its own rate limit
"""
import concurrent.futures
import json
import os
import time
import urllib.request

URL = "https://yibuapi.com/v1/"
KEYS = [
    "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex",
    "sk-lIrl5wFYbH36sV23pwnd6lqWcC2xXEgfPWQoqFCzYH2OIgXU",
    "sk-p7FxYTorCAJpl8F4haJ9ERMzCyxPNdlTWGRNCGu3ASCY2Lu8",
]
MODEL = "gpt-5.6-sol"
N_CONCURRENT = 12

print("=" * 70)
print("Phase 1: Verify each key individually")
print("=" * 70)

for i, key in enumerate(KEYS):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "reply with exactly: pong"}],
        "max_tokens": 100,
    }).encode()
    req = urllib.request.Request(
        URL + "chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        elapsed = time.perf_counter() - t0
        content = data["choices"][0]["message"].get("content", "")[:50]
        model_ret = data.get("model", "?")
        print(f"  key {i}: OK  {elapsed:.1f}s  model={model_ret}  reply={content!r}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        detail = ""
        if hasattr(e, "read"):
            try:
                detail = e.read().decode("utf-8", "replace")[:150]
            except Exception:
                pass
        print(f"  key {i}: FAIL  {elapsed:.1f}s  {e}  {detail}")

print()
print("=" * 70)
print(f"Phase 2: {N_CONCURRENT} concurrent requests, round-robin across 3 keys")
print("=" * 70)

key_usage = [0, 0, 0]  # count requests per key


def call_with_key(call_id: int) -> dict:
    key_idx = call_id % 3  # round-robin
    key = KEYS[key_idx]
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": f"reply with exactly: pong {call_id}"}],
        "max_tokens": 100,
    }).encode()
    req = urllib.request.Request(
        URL + "chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        elapsed = time.perf_counter() - t0
        content = data["choices"][0]["message"].get("content", "")[:60]
        finish = data["choices"][0].get("finish_reason", "?")
        return {
            "call_id": call_id,
            "key_idx": key_idx,
            "elapsed": elapsed,
            "ok": True,
            "content": content,
            "finish": finish,
            "model": data.get("model", "?"),
        }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        detail = ""
        if hasattr(e, "read"):
            try:
                detail = e.read().decode("utf-8", "replace")[:150]
            except Exception:
                pass
        return {
            "call_id": call_id,
            "key_idx": key_idx,
            "elapsed": elapsed,
            "ok": False,
            "error": str(e)[:120],
            "detail": detail,
        }


t_start = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
    futures = [pool.submit(call_with_key, i) for i in range(N_CONCURRENT)]
    results = [f.result() for f in futures]
total_elapsed = time.perf_counter() - t_start

print(f"\nTotal wall time: {total_elapsed:.1f}s")
print()

# Per-key stats
for ki in range(3):
    key_results = [r for r in results if r["key_idx"] == ki]
    ok = sum(1 for r in key_results if r.get("ok"))
    fail = sum(1 for r in key_results if not r.get("ok"))
    times = [r["elapsed"] for r in key_results if r.get("ok")]
    avg_t = sum(times) / len(times) if times else 0
    print(f"  key {ki}: {ok} ok, {fail} fail, avg={avg_t:.1f}s")

print()
print("Per-call detail:")
for r in results:
    cid = r["call_id"]
    ki = r["key_idx"]
    if r.get("ok"):
        print(f"  call {cid:2d} key{ki}: OK  {r['elapsed']:5.1f}s  "
              f"finish={r['finish']}  reply={r['content']!r}")
    else:
        print(f"  call {cid:2d} key{ki}: FAIL {r['elapsed']:5.1f}s  {r.get('error', '')}")
        if r.get("detail"):
            print(f"           detail: {r['detail']!r}")

# Summary
ok_count = sum(1 for r in results if r.get("ok"))
fail_count = sum(1 for r in results if not r.get("ok"))
print()
print("=" * 70)
print("=== SUMMARY ===")
print(f"  total: {N_CONCURRENT}, ok: {ok_count}, fail: {fail_count}")
print(f"  wall time: {total_elapsed:.1f}s")
print(f"  per-key distribution: {[sum(1 for r in results if r['key_idx']==ki) for ki in range(3)]}")
if fail_count == 0:
    print("\n  ✓ ALL 12 CALLS SUCCEEDED")
    print("  → 3 keys + round-robin works, no rate limit hit at 12 concurrent")
    print("  → can safely use workers=12 or higher")
else:
    print(f"\n  ✗ {fail_count} CALLS FAILED")
    print("  → check individual errors above for rate limit type")
