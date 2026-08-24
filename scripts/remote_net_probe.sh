#!/bin/bash
echo "=== proxy env ==="
env | grep -i proxy || echo "no proxy env"
echo "=== DNS ==="
cat /etc/resolv.conf 2>/dev/null | grep -v '^#' | head -5
echo "=== try public IP directly (no DNS) ==="
timeout 6 curl -sS -o /dev/null -w '113.46.219.251:8080 -> %{http_code}\n' http://113.46.219.251:8080/v1/models 2>&1 | tail -1
timeout 6 bash -c 'echo > /dev/tcp/223.5.5.5/53' 2>/dev/null && echo "tcp 223.5.5.5:53 reachable" || echo "tcp 223.5.5.5:53 blocked"
echo "=== ping gateway/internal ==="
ip route | head -3
echo "=== apt mirror test ==="
timeout 8 apt-get update 2>&1 | tail -3
