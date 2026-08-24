#!/bin/bash
echo "=== sudo test ==="
echo liufeng | sudo -S whoami 2>/dev/null || echo "sudo FAILED"
echo "=== apt sources ==="
grep -rh '^deb ' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null | head -6
echo "=== pip conf ==="
cat /etc/pip.conf ~/.pip/pip.conf ~/.config/pip/pip.conf 2>/dev/null || echo "no pip conf"
echo "=== cargo/rustup conf ==="
ls ~/.cargo ~/.rustup 2>/dev/null || echo "none"
echo "=== internal http services on gateway? ==="
timeout 4 curl -sS -o /dev/null -w 'gateway:80 -> %{http_code}\n' http://10.126.62.1/ 2>&1 | tail -1
echo "=== existing conda/venvs with rust? ==="
ls ~/miniconda3 ~/anaconda3 2>/dev/null | head -3 || echo "no conda"
