"""Probe h:gpt-5.5's actual API response structure.

Sends a prompt that asks for JSON output (mimicking the analyst/optimizer
call), then prints the FULL response structure to see where the content lands:
message.content vs message.reasoning_content vs usage.reasoning_tokens.
"""
import json
import urllib.request
import urllib.error

URL = "https://yibuapi.com/v1/"
KEY = "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex"
MODEL = "h:gpt-5.5"

# A prompt that mimics the analyst call: ask for structured JSON output.
SYSTEM = (
    "You are a skill optimizer. Analyze the failed trajectory and produce "
    "a JSON object with a 'patch' field containing suggested edits."
)
USER = (
    "## Current Skill\nUse read_file to answer questions.\n\n"
    "## Patch Budget\nProduce at most L=2 edits.\n\n"
    "## Failed Trajectories (1 total)\n"
    "[action] read_file(doc.pdf)\n"
    "[obs] Error: file not found\n\n"
    "Respond with ONLY a JSON object like:\n"
    '{"patch": {"reasoning": "...", "edits": [{"find": "...", "replace": "..."}]}}'
)

body = json.dumps({
    "model": MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ],
    "max_tokens": 2000,
}).encode()

req = urllib.request.Request(
    URL.rstrip("/") + "/chat/completions",
    data=body,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + KEY,
    },
)

print(f"Model: {MODEL}")
print(f"URL:   {URL}")
print(f"System: {SYSTEM[:80]}...")
print(f"User:   {USER[:80]}...")
print("=" * 70)

try:
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    raise SystemExit(1)
except Exception as e:
    print(f"Error: {e}")
    raise SystemExit(1)

# Print the full response structure
print("\n=== TOP-LEVEL KEYS ===")
print(list(data.keys()))

print("\n=== CHOICES[0].MESSAGE STRUCTURE ===")
msg = data["choices"][0]["message"]
print(f"message keys: {list(msg.keys())}")
print(f"message.role: {msg.get('role')!r}")

content = msg.get("content", "")
print(f"\nmessage.content type: {type(content).__name__}")
print(f"message.content len:  {len(content) if content else 0}")
print(f"message.content repr: {repr(content)[:500]}")

# Check reasoning_content (non-standard field used by some reasoning models)
reasoning = msg.get("reasoning_content", "")
print(f"\nmessage.reasoning_content type: {type(reasoning).__name__}")
print(f"message.reasoning_content len:  {len(reasoning) if reasoning else 0}")
print(f"message.reasoning_content repr: {repr(reasoning)[:500]}")

# Check reasoning_tokens in usage
print("\n=== USAGE ===")
usage = data.get("usage", {})
print(json.dumps(usage, indent=2, ensure_ascii=False))

# Check model field (yibuapi may alias it)
print(f"\n=== MODEL FIELD ===")
print(f"returned model: {data.get('model')!r}")

# Check finish_reason
print(f"\n=== FINISH REASON ===")
print(f"finish_reason: {data['choices'][0].get('finish_reason')!r}")

# Diagnosis
print("\n" + "=" * 70)
print("=== DIAGNOSIS ===")
if content and len(content) > 10:
    print(f"✓ content has substance ({len(content)} chars)")
    print(f"  → skillopt's extract_json will parse this")
    print(f"  → if 0 edits, the issue is JSON FORMAT, not missing field")
    # Try to see if it looks like JSON
    stripped = content.strip()
    if stripped.startswith("{") or stripped.startswith("```"):
        print(f"  → content starts with JSON/markdown fence (good)")
    else:
        print(f"  → content does NOT start with JSON (BAD — extract_json will fail)")
        print(f"  → first 200 chars: {stripped[:200]!r}")
elif reasoning and len(reasoning) > 10:
    print(f"✗ content is EMPTY, but reasoning_content has {len(reasoning)} chars")
    print(f"  → skillopt's fallback (line 222) WILL pick this up")
    print(f"  → but if reasoning_content is also not JSON, extract_json fails")
else:
    print(f"✗ BOTH content and reasoning_content are empty/near-empty")
    print(f"  → check finish_reason: {data['choices'][0].get('finish_reason')!r}")
    if data['choices'][0].get('finish_reason') == 'length':
        print(f"  → TRUNCATED by max_tokens — output never completed")
