"""Probe average response latency for a model on the configured API endpoint.

Usage:
    python scripts/probe_latency.py --model gpt-5.2
    python scripts/probe_latency.py --model Qwen3.7-Plus --url http://113.46.219.251:8080/v1 --key sk-ICnSVVK7fRlxOCPa411PnQ
    python scripts/probe_latency.py --model gpt-5.5 --n 10 --max-tokens 2000

Defaults pull from configs/officeqa/default.yaml (yibuapi endpoint).
"""
import argparse   
import json
import statistics
import sys
import time
import urllib.request
import urllib.error


DEFAULT_URL = "https://yibuapi.com/v1/"
DEFAULT_KEY = "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, help="model name to probe")
    p.add_argument("--url", default=DEFAULT_URL,
                   help=f"API base URL (default: {DEFAULT_URL})")
    p.add_argument("--key", default=DEFAULT_KEY,
                   help="API key (default: shared key from config)")
    p.add_argument("--n", type=int, default=5, help="number of probe calls (default 5)")
    p.add_argument("--max-tokens", type=int, default=2000,
                   help="max completion tokens per call (default 2000)")
    p.add_argument("--warmup", type=int, default=1,
                   help="warmup calls not counted in stats (default 1)")
    p.add_argument("--prompt", default="Reply with exactly: pong",
                   help="probe prompt (default 'Reply with exactly: pong')")
    return p.parse_args()


def resolve_endpoint(url_alias: str, key_alias: str) -> tuple[str, str]:
    if url_alias == "relay":
        url, key = RELAY_URL, RELAY_KEY
    else:
        url, key = url_alias, key_alias
    if key_alias == "relay" and url_alias != "relay":
        key = RELAY_KEY
    return url.rstrip("/"), key


def call_once(url: str, key: str, model: str, prompt: str, max_tokens: int) -> tuple[float, str]:
    """Return (latency_seconds, status). Raises on error."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        url + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        latency = time.perf_counter() - t0
        content = (data["choices"][0]["message"].get("content") or "")[:60]
        usage = data.get("usage", {})
        return latency, f"OK model={data.get('model')} reply={content!r} usage={usage}"
    except urllib.error.HTTPError as e:
        latency = time.perf_counter() - t0
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} after {latency:.2f}s: {detail}") from None
    except Exception as e:
        latency = time.perf_counter() - t0
        raise RuntimeError(f"{type(e).__name__} after {latency:.2f}s: {e}") from None


def main():
    args = parse_args()
    url, key = resolve_endpoint(args.url, args.key)
    print(f"Endpoint:  {url}")
    print(f"Model:     {args.model}")
    print(f"Calls:     {args.n} (warmup={args.warmup})")
    print(f"Max tok:   {args.max_tokens}")
    print(f"Prompt:    {args.prompt!r}")
    print("-" * 60)

    latencies: list[float] = []
    errors: list[str] = []

    total_calls = args.warmup + args.n
    for i in range(total_calls):
        is_warmup = i < args.warmup
        label = "warmup" if is_warmup else f"call {i - args.warmup + 1:>3}"
        try:
            t, status = call_once(url, key, args.model, args.prompt, args.max_tokens)
            if not is_warmup:
                latencies.append(t)
            print(f"  [{label}] {t:6.2f}s  {status}")
        except Exception as e:
            if not is_warmup:
                errors.append(str(e))
            print(f"  [{label}] FAIL  {e}")

    print("-" * 60)
    if not latencies:
        print(f"RESULT: 0/{args.n} succeeded — cannot compute latency")
        sys.exit(1)

    mean = statistics.mean(latencies)
    med = statistics.median(latencies)
    p95 = (statistics.quantiles(latencies, n=20)[18]
           if len(latencies) >= 20 else max(latencies))
    mn, mx = min(latencies), max(latencies)
    success_rate = len(latencies) / args.n

    print(f"RESULT: {len(latencies)}/{args.n} succeeded ({success_rate*100:.0f}%)")
    print(f"  mean     {mean:6.2f}s")
    print(f"  median   {med:6.2f}s")
    print(f"  p95      {p95:6.2f}s" + (" (max fallback for n<20)" if len(latencies) < 20 else ""))
    print(f"  min/max  {mn:6.2f}s / {mx:6.2f}s")
    if errors:
        print(f"  errors:  {len(errors)}")
        for e in errors[:3]:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
