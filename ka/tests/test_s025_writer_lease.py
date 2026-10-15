"""SCRIPT #025 — the exclusive-writer lease (spec item 7). Every scenario runs REAL separate processes (subprocess) on a temp store:
`python -m ka serve` for the service, `python -m ka seed-demo` for the job, and a small worker for a stale-cache writer."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import httpx
import pytest

from ka import writer_lock
from ka.api import PREFIX
from ka.repository import Collection, Repository

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "deploy" / "grammar"
READY = PREFIX + "/ready"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")


def _env(store: Path, **extra) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("KA_")}
    env.update(PYTHONPATH=str(ROOT), KA_STORAGE_ROOT=str(store), KA_GRAMMAR_DIR=str(BUNDLED), KA_GRAPH_MODE="memory", KA_LLM_PROVIDER="stub",
               ANTHROPIC_API_KEY="", KA_SEARCH_PROVIDER="none", KA_RESEARCH_INTERNET="0", KA_ACCESS_POLICY="open", KA_WRITER_LOCK="on",
               KA_LOCK_POLL_SECONDS="0.2", KA_LOCK_WAIT_SECONDS="60", KA_SEED_LOCK_WAIT_SECONDS="0.5", KA_BACKEND_HOST="127.0.0.1")
    env.update({k: str(v) for k, v in extra.items()})
    return env


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Serve:
    def __init__(self, store: Path, log: Path, **extra):
        self.port = _port()
        self.log = log.open("w")
        self.proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(ROOT), env=_env(store, KA_BACKEND_PORT=self.port, **extra),
                                     stdout=self.log, stderr=subprocess.STDOUT)
        self.base = f"http://127.0.0.1:{self.port}"

    def get(self, path: str) -> httpx.Response:
        return httpx.get(self.base + path, timeout=5)

    def post(self, path: str, body: dict) -> httpx.Response:
        return httpx.post(self.base + path, json=body, timeout=10)

    def wait_status(self, status: str, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(f"serve exited {self.proc.returncode}: {Path(self.log.name).read_text()}")
            try:
                r = self.get(READY)
                last = (r.status_code, r.text)
                if r.json().get("status") == status:
                    return
            except httpx.HTTPError as e:
                last = e
            time.sleep(0.1)
        raise AssertionError(f"never {status}: last {last}; log {Path(self.log.name).read_text()}")

    def stop(self, sig=signal.SIGTERM, timeout: float = 20) -> int:
        if self.proc.poll() is None:
            self.proc.send_signal(sig)
        try:
            return self.proc.wait(timeout)
        finally:
            self.log.close()


@pytest.fixture
def servers():
    started: list[Serve] = []
    yield started
    for s in started:
        if s.proc.poll() is None:
            s.proc.kill()
            s.proc.wait(10)
        s.log.close()


def _cli(store: Path, *args: str, **extra) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ka", *args], cwd=str(ROOT), env=_env(store, **extra), capture_output=True, text=True, timeout=120)


def _holder(store: Path) -> dict:
    cur = writer_lock.read_lock(store)
    assert cur, f"no lock in {store}"
    return cur


# ---- service: standby, hand-over, ownership loss ----------------------------------------------------------------------

def test_P1_second_service_waits_in_standby_and_takes_over_after_a_clean_exit(tmp_path, servers):
    store = tmp_path / "store"
    a = Serve(store, tmp_path / "a.log"); servers.append(a)
    a.wait_status("ready")
    owner_a = _holder(store)["owner_id"]
    assert a.post(PREFIX + "/scopes", {"scope_type": "DOMAIN", "scope_id": "from-a"}).status_code == 200

    b = Serve(store, tmp_path / "b.log"); servers.append(b)
    b.wait_status("standby")                                                   # probe 200 {"status": "standby"}
    r = b.get(READY)
    assert r.status_code == 200 and r.json() == {"status": "standby"}
    for path in (PREFIX + "/vocab", PREFIX + "/scopes", PREFIX + "/healthz", PREFIX + "/v1/capabilities", "/console/"):
        r = b.get(path)
        assert r.status_code == 503 and r.headers.get("retry-after"), path
    assert b.post(PREFIX + "/scopes", {"scope_type": "DOMAIN", "scope_id": "from-b-standby"}).status_code == 503
    assert _holder(store)["owner_id"] == owner_a                               # B never touched the lock

    a.stop()                                                                   # SIGTERM: stop writes, remove OUR lock
    b.wait_status("ready")
    assert _holder(store)["owner_id"] != owner_a
    scopes = json.loads((store / "scopes.json").read_text())
    assert "DOMAIN:from-a" in json.dumps(scopes) and "from-b-standby" not in json.dumps(scopes)
    assert b.post(PREFIX + "/scopes", {"scope_type": "DOMAIN", "scope_id": "from-b"}).status_code == 200
    assert b.stop() in (0, -signal.SIGTERM)
    assert writer_lock.read_lock(store) is None                                # clean exit leaves no lock


def test_N1_a_sigkilled_holder_is_not_taken_over_automatically_only_by_break_glass(tmp_path, servers):
    store = tmp_path / "store"
    a = Serve(store, tmp_path / "a.log"); servers.append(a)
    a.wait_status("ready")
    dead = _holder(store)["owner_id"]
    a.stop(signal.SIGKILL)
    assert _holder(store)["owner_id"] == dead                                  # the crash leaves the lock

    b = Serve(store, tmp_path / "b.log", KA_LOCK_WAIT_SECONDS="2"); servers.append(b)
    b.wait_status("standby")
    rc = b.proc.wait(30)                                                       # gives up after KA_LOCK_WAIT_SECONDS: exit non-zero
    assert rc != 0 and _holder(store)["owner_id"] == dead
    assert "gave up" in Path(b.log.name).read_text()

    wrong = _cli(store, "break-writer-lock", "--owner-id", "not-the-owner")
    assert wrong.returncode == 1 and "refused" in wrong.stderr and _holder(store)["owner_id"] == dead
    status = json.loads(_cli(store, "writer-lock-status").stdout)
    assert status["held"] and status["holder"]["owner_id"] == dead
    ok = _cli(store, "break-writer-lock", "--owner-id", dead)
    assert ok.returncode == 0 and writer_lock.read_lock(store) is None

    c = Serve(store, tmp_path / "c.log"); servers.append(c)
    c.wait_status("ready")
    assert _holder(store)["owner_id"] != dead


def test_N2_ownership_loss_refuses_the_write_turns_lost_and_exits(tmp_path, servers):
    store = tmp_path / "store"
    a = Serve(store, tmp_path / "a.log"); servers.append(a)
    a.wait_status("ready")
    assert a.post(PREFIX + "/scopes", {"scope_type": "DOMAIN", "scope_id": "before"}).status_code == 200
    before = (store / "scopes.json").read_text()
    events_before = (store / "events.jsonl").read_text() if (store / "events.jsonl").exists() else ""
    assert _cli(store, "break-writer-lock", "--owner-id", _holder(store)["owner_id"]).returncode == 0
    r = a.post(PREFIX + "/scopes", {"scope_type": "DOMAIN", "scope_id": "after-loss"})
    assert r.status_code == 503
    rc = a.proc.wait(20)                                                       # SIGTERMs itself
    assert rc != 0
    assert (store / "scopes.json").read_text() == before
    assert ((store / "events.jsonl").read_text() if (store / "events.jsonl").exists() else "") == events_before
    assert writer_lock.read_lock(store) is None                                # it did not recreate or remove anything
    assert "WRITER LEASE LOST" in Path(a.log.name).read_text()


# ---- seed job ------------------------------------------------------------------------------------------------------------

def test_N3_the_seed_job_fails_cleanly_while_the_service_holds_the_lock(tmp_path, servers):
    store = tmp_path / "store"
    a = Serve(store, tmp_path / "a.log"); servers.append(a)
    a.wait_status("ready")
    owner = _holder(store)["owner_id"]
    listing = sorted(str(p.relative_to(store)) for p in store.rglob("*"))
    seed = _cli(store, "seed-demo", "copper-kettle")
    assert seed.returncode == 3, seed
    assert "refused" in seed.stderr and owner in seed.stderr and "nothing was written" in seed.stderr
    assert sorted(str(p.relative_to(store)) for p in store.rglob("*")) == listing   # not one file created
    assert _holder(store)["owner_id"] == owner
    a.stop()
    seed = _cli(store, "seed-demo", "copper-kettle")                           # service gone: the job runs and releases
    assert seed.returncode == 0, seed.stderr
    assert json.loads(seed.stdout)["writer_lock"] == "held" and writer_lock.read_lock(store) is None


def test_P2_a_service_started_while_the_seed_runs_waits_then_sees_the_seeded_store(tmp_path, servers):
    store = tmp_path / "store"
    seed = subprocess.Popen([sys.executable, "-m", "ka", "seed-demo", "copper-kettle"], cwd=str(ROOT), env=_env(store),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 30
    while writer_lock.read_lock(store) is None and seed.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    a = Serve(store, tmp_path / "a.log"); servers.append(a)
    out, err = seed.communicate(timeout=120)
    assert seed.returncode == 0, err
    a.wait_status("ready")
    r = a.get(PREFIX + "/nuggets?status=ACTIVE")
    assert r.status_code == 200
    assert len(json.loads(out)["active_refs"]) >= 12
    # the cache was loaded after the lock, so it contains everything the seed acknowledged
    assert all(ref in r.text for ref in json.loads(out)["active_refs"])


# ---- stale cache (spec item 6) ---------------------------------------------------------------------------------------

WORKER = textwrap.dedent('''
    import json, sys, time
    from pathlib import Path
    from pydantic import BaseModel
    from ka import writer_lock
    from ka.repository import Collection, Repository, StaleCacheError

    class Thing(BaseModel):
        id: str
        value: str

    root, ctl, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    def wait_for(name):
        while not (ctl / name).exists():
            time.sleep(0.02)
    lease = writer_lock.WriterLease(root, role=mode)
    if not lease.acquire(float(sys.argv[4]), 0.05):
        print("LOCKED", json.dumps(writer_lock.read_lock(root))); sys.exit(3)
    writer_lock.register(lease)
    things = Collection(root, "things", Thing)
    repo = Repository(root)
    things.all()                                                # the cache is loaded only now, under the lock
    if mode == "stale":
        (ctl / "loaded").touch(); wait_for("go")
        out = {}
        for key, fn in [("guarded", lambda: things.put(Thing(id="X", value="stale-A"))),
                        ("after_loss_event", lambda: repo.append_event({"name": "a.after.loss"})),
                        ("after_loss_other", lambda: things.put(Thing(id="Y", value="stale-A")))]:
            try:
                fn(); out[key] = "WROTE"
            except Exception as e:
                out[key] = type(e).__name__ + ": " + str(e)
        out["state"] = lease.state
        writer_lock.unregister(lease)                           # simulate a bypass of the ownership check (spec item 6)
        try:
            things.put(Thing(id="X", value="stale-A-bypass")); out["bypassed"] = "WROTE"
        except StaleCacheError as e:
            out["bypassed"] = "StaleCacheError: " + str(e)
        (ctl / "result.json").write_text(json.dumps(out))
    elif mode == "update":
        things.put(Thing(id="X", value="B-ack"))
        repo.append_event({"name": "b.ack"})
        (ctl / "acked").touch(); wait_for("done")
        lease.release()
''')


def _worker(tmp_path: Path, store: Path, ctl: Path, mode: str, wait: float = 5.0) -> subprocess.Popen:
    script = tmp_path / "worker.py"
    script.write_text(WORKER)
    return subprocess.Popen([sys.executable, str(script), str(store), str(ctl), mode, str(wait)], cwd=str(ROOT), env=_env(store),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _until(p: Path, proc: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while not p.exists():
        if proc.poll() is not None:
            raise AssertionError(f"worker exited {proc.returncode}: {proc.communicate()}")
        assert time.monotonic() < deadline, f"timeout waiting for {p}"
        time.sleep(0.02)


def test_N4_a_stale_cache_in_process_a_cannot_overwrite_an_update_acknowledged_by_process_b(tmp_path):
    from pydantic import BaseModel

    class Thing(BaseModel):
        id: str
        value: str

    store, ctl = tmp_path / "store", tmp_path / "ctl"
    ctl.mkdir()
    Collection(store, "things", Thing).put(Thing(id="X", value="v0"))         # no lease registered here: plain setup write

    a = _worker(tmp_path, store, ctl, "stale")
    _until(ctl / "loaded", a)                                                  # A holds the lock and has X=v0 cached
    blocked = _worker(tmp_path, store, ctl, "update", wait=0.5)
    out, _ = blocked.communicate(timeout=30)
    assert blocked.returncode == 3 and out.startswith("LOCKED")              # B cannot acquire while A holds

    assert _cli(store, "break-writer-lock", "--owner-id", _holder(store)["owner_id"]).returncode == 0
    b = _worker(tmp_path, store, ctl, "update")
    _until(ctl / "acked", b)                                                   # B acknowledged X=B-ack and still holds the lock
    (ctl / "go").touch()
    _until(ctl / "result.json", a)
    a.wait(30)
    res = json.loads((ctl / "result.json").read_text())
    assert res["guarded"].startswith("WriterLockError") and "lost" in res["guarded"]
    assert res["after_loss_event"].startswith("WriterLockError") and res["after_loss_other"].startswith("WriterLockError")
    assert res["state"] == "lost"
    assert res["bypassed"].startswith("StaleCacheError")                      # even with the fence bypassed
    assert json.loads((store / "things" / "X.json").read_text())["value"] == "B-ack"
    assert not (store / "things" / "Y.json").exists()
    names = [json.loads(line)["name"] for line in (store / "events.jsonl").read_text().splitlines()]
    assert names == ["b.ack"]
    (ctl / "done").touch()
    b.wait(30)
    assert b.returncode == 0 and writer_lock.read_lock(store) is None


# ---- event sequence numbers ------------------------------------------------------------------------------------------

def test_P3_event_seq_is_derived_from_disk_so_writers_never_duplicate_it(tmp_path):
    root = tmp_path / "store"
    r1, r2 = Repository(root), Repository(root)                                # two handles on one store (e.g. old + new process)
    r1.append_event({"name": "a"}); r2.append_event({"name": "b"}); r1.append_event({"name": "c"})
    ts = [threading.Thread(target=lambda i=i: (r1 if i % 2 else r2).append_event({"name": f"t{i}"})) for i in range(40)]
    [t.start() for t in ts]; [t.join() for t in ts]
    seqs = [e["seq"] for e in Repository(root).events()]
    assert len(seqs) == 43
    assert seqs == list(range(1, 44)) or sorted(seqs) == list(range(1, 44))
    assert len(set(seqs)) == len(seqs)


def test_N5_in_process_compare_on_write_refuses_a_stale_collection_handle(tmp_path):
    from ka.repository import StaleCacheError
    root = tmp_path / "store"
    from pydantic import BaseModel

    class Thing(BaseModel):
        id: str
        value: str
    c1, c2 = Collection(root, "things", Thing), Collection(root, "things", Thing)
    c1.all(); c2.all()
    c2.put(Thing(id="X", value="acknowledged"))
    with pytest.raises(StaleCacheError):
        c1.put(Thing(id="X", value="stale"))
    assert json.loads((root / "things" / "X.json").read_text())["value"] == "acknowledged"
