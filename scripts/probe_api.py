import json
import urllib.request


def probe(name: str, url: str, key: str, model: str) -> None:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "reply with exactly: pong"}],
        "max_tokens": 2000,
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        content = (d["choices"][0]["message"].get("content") or "")[:80]
        print(f"[{name}] OK   model={d.get('model')}  reply={content!r}")
    except Exception as e:  # noqa: BLE001
        detail = ""
        if hasattr(e, "read"):
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
        print(f"[{name}] FAIL {e} {detail}")


probe("yibuapi", "https://yibuapi.com/v1/", "sk-or4MGHJM8xbWKIilBP9Ube3S3s7D6guVBZQwyqI6fXnoZUex", "gpt-5.2")
probe("113-relay", "http://113.46.219.251:8080/v1", "sk-6Vi_7BS_IuofzkYt8t2B9w", "gpt-5.2")
