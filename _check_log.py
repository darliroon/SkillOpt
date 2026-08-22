import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "outputs/searchqa_gpt52opt_prox_console.log"
raw = open(path, "rb").read()
for enc in ("utf-16", "utf-8-sig", "utf-8"):
    try:
        text = raw.decode(enc)
        if "\x00" not in text[:1000]:
            break
    except UnicodeDecodeError:
        continue
else:
    text = raw.decode("utf-8", errors="replace")
lines = text.splitlines()
print(f"total lines: {len(lines)}")

steps = [l.strip() for l in lines if re.search(r"STEP \d+ done", l)]
print(f"completed steps: {len(steps)}")
for s in steps[-5:]:
    print("  ", s[:120])

pat = re.compile(r"PROX|EPOCH \d/4|baseline result|\[baseline|BEST|TEST|FINAL|final result|shrunk", re.I)
keys = [l.strip() for l in lines if pat.search(l)]
print(f"key lines: {len(keys)}")
for k in keys[-15:]:
    print(" *", k[:120])

print("last non-empty line:", next((l.strip()[:120] for l in reversed(lines) if l.strip()), ""))
