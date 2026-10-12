"""plan-35 (NEXOS v1, priority 1 of the ChatGPT review): KA listens only on the configured addresses — the WireGuard address plus loopback —
so it no longer answers on the public interface. Default unchanged (0.0.0.0)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from ka.__main__ import bind_hosts

ROOT = Path(__file__).resolve().parents[2]


def test_P1_bind_hosts_parses_a_list_and_defaults_to_every_interface():
    assert bind_hosts("10.77.0.2,127.0.0.1") == ["10.77.0.2", "127.0.0.1"]
    assert bind_hosts(" 127.0.0.1 , 127.0.0.1 ") == ["127.0.0.1"]
    assert bind_hosts("") == ["0.0.0.0"] and bind_hosts(None) == ["0.0.0.0"]


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def test_P2_two_listeners_serve_and_nothing_else_is_bound(tmp_path):
    """Two loopback addresses stand in for 10.77.0.2 + 127.0.0.1: both serve /healthz; the server is not on 0.0.0.0."""
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("KA_")}
    env.update({"KA_BACKEND_HOST": "127.0.0.1,127.0.0.2", "KA_BACKEND_PORT": str(port), "KA_STORAGE_ROOT": str(tmp_path / "s"),
                "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open", "ANTHROPIC_API_KEY": ""})
    proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        got = {}
        for host in ("127.0.0.1", "127.0.0.2"):
            for _ in range(80):
                try:
                    got[host] = urllib.request.urlopen(f"http://{host}:{port}/api/knowledge-acquisition/healthz", timeout=1).status
                    break
                except Exception:
                    time.sleep(0.25)
        assert got == {"127.0.0.1": 200, "127.0.0.2": 200}
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
        assert f"0.0.0.0:{port} " not in out and f"127.0.0.1:{port} " in out and f"127.0.0.2:{port} " in out
    finally:
        proc.terminate(); proc.wait(timeout=10)
