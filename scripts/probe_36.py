"""Test 36 concurrent requests (12 per key) to check rate limits."""
import concurrent.futures
import json
import time
import urllib.request

KEYS = [
    "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex",
    "sk-lIrl5wFYbH36sV23pwnd6lqWcC2xXEgfPWQoqFCzYH2OIgXU",
    "sk-p7FxYTorCAJpl8F4haJ9ERMzCyxPNdlTWGRNCGu3ASCY2Lu8",
]
URL = "https://yibuapi.com/v1/"
MODEL = "gpt-5.6-sol"
N = 36


def call(i):
    ki = i % 3
    k = KEYS[ki]
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "reply: pong"}],
        "max_tokens": 50,
    }).encode()
    req = urllib.request.Request(
        URL + "chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + k},
    )
    t = time.perf_counter()
    try:
        r = urllib.request.urlopen(req, timeout=120)
        d = json.loads(r.read())
        e = time.perf_counter() - t
        return {"i": i, "ki": ki, "ok": True, "e": e}
    except Exception as ex:
        e = time.perf_counter() - t
        det = ""
        if hasattr(ex, "read"):
            try:
                det = ex.read().decode("utf-8", "replace")[:100]
            except Exception:
                pass
        return {"i": i, "ki": ki, "ok": False, "e": e, "err": str(ex)[:80], "det": det}


print(f"Testing {N} concurrent (12 per key)...")
t0 = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=N) as p:
    res = [f.result() for f in [p.submit(call, i) for i in range(N)]]
tot = time.perf_counter() - t0
ok = sum(1 for r in res if r["ok"])
fail = N - ok

for ki in range(3):
    kr = [r for r in res if r["ki"] == ki]
    ko = sum(1 for r in kr if r["ok"])
    print(f"  key{ki}: {ko}/{len(kr)} ok")

print(f"Total: {ok}/{N} ok, {fail} fail, {tot:.1f}s")
if fail:
    errs = [r for r in res if not r["ok"]][:5]
    for r in errs:
        print(f"  FAIL call{r['i']} key{r['ki']}: {r.get('err', '')} {r.get('det', '')}")
print("PASS" if fail == 0 else "FAIL")
