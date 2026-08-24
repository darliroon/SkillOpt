#!/bin/bash
# Remote environment probe for agent-core-rust backend setup.
echo "=== toolchain ==="
for c in rustc cargo python3 pip3 git gcc make curl pkg-config openssl; do
  printf '%-10s: ' "$c"
  if command -v "$c" >/dev/null 2>&1; then "$c" --version 2>&1 | head -1; else echo MISSING; fi
done
echo "=== python ==="
python3 -c 'import sys; print(sys.version)' 2>/dev/null || true
echo "=== network ==="
for url in https://yibuapi.com/v1/models https://pypi.org/simple/ https://github.com https://atomgit.com; do
  printf '%-35s: ' "$url"
  timeout 8 curl -sS -o /dev/null -w '%{http_code}\n' "$url" 2>&1 | tail -1
done
echo "=== gpu ==="
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo no-gpu
echo "=== disk ==="
df -h "$HOME" | tail -1
echo "=== done ==="
