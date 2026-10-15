# Knowledge Acquisition on Cloud Run (NEXOS MVP)

How the repository's `Dockerfile` image runs as the NEXOS Cloud Run MVP service, which settings it needs, how the platform
probes it, and how to load the one synthetic demo dataset (Copper Kettle Coffee). This page describes the deployment; it
changes no GCP resource.

## Runtime shape (fixed decisions)

| Item | Value |
|---|---|
| Platform | Cloud Run gen2, `--max-instances=1`, CPU always allocated (`--no-cpu-throttling`) |
| Image | this repo's `Dockerfile`; runs as uid/gid 10001, listens on `$PORT` (8080) |
| Store | `KA_STORAGE_ROOT=/mnt/nfs/ka/ka_storage` on an **NFS v4** volume mounted at `/mnt/nfs/ka` (POSIX rename and locks; one JSON file per object, unchanged) |
| Callers | AgentX (`/api/knowledge-acquisition/v1/*`) and Knowledge Worker (`POST /api/knowledge-acquisition/v1/knowledge/search`), both with the bearer `KA_AGENTX_TOKEN`; Cloud Run IAM in front (callers send `X-Serverless-Authorization`, KA ignores it) |
| Graph | `KA_GRAPH_MODE=memory`: no Knowledge Worker publication, no outbound call |
| Physical store | `KA_STORAGE_BACKEND=local` (no Data Platform) |

Why one instance with CPU always allocated: KA keeps in-process caches of the store and runs background threads; two
instances writing the same NFS directory would each serve a stale cache.

## Single writer: the writer lease (SCRIPT #025)

`max-instances=1` does not stop two processes writing the store: a revision rollout overlaps the old and new instance,
and the seed job writes the same directory. KA therefore takes an exclusive **writer lease**, the file
`$KA_STORAGE_ROOT/.writer.lock` (JSON: `owner_id`, `host`, `pid`, `revision` from `K_REVISION`/`CLOUD_RUN_EXECUTION`,
`role`, `acquired_at`), created only by an atomic exclusive create. Nothing ever replaces it and there is no automatic
stale takeover.

- **Startup.** `serve` starts in **standby**: the readiness probe (`/api/knowledge-acquisition/ready`, also `/readyz`)
  answers `200 {"status": "standby"}` so Cloud Run can shift traffic and SIGTERM the old revision; every other route
  answers `503` with `Retry-After: 5`. Nothing is read from the store (no cache) until the lease is held. It retries every
  `KA_LOCK_POLL_SECONDS` (3) for `KA_LOCK_WAIT_SECONDS` (600), then exits non-zero.
- **Writes.** Every write re-reads the lock and compares `owner_id`. On a mismatch the write is refused, the process turns
  `lost` (all routes 503, readiness `503 {"status": "lost"}`) and SIGTERMs itself. Cached collections also compare on
  write: each collection directory has a `.version` counter, and a write from a cache loaded at an older version is refused
  (`StaleCacheError`), so a stale cache cannot overwrite an acknowledged update. Event `seq` numbers are derived from
  `events.jsonl` on disk under the lease.
- **Shutdown** (SIGTERM, scale to zero): writes stop, then the lock is removed if it is still ours.
- **Crash** (SIGKILL, OOM): the lock stays. The next instance waits in standby and exits after `KA_LOCK_WAIT_SECONDS`.
  This is deliberate (fail safe).
- **Break-glass.** After confirming the old writer is gone (no running instance/execution with that `revision`/`pid`):

  ```sh
  knowledge-acquisition writer-lock-status                       # shows the holder's owner_id
  knowledge-acquisition break-writer-lock --owner-id <owner_id>  # removes the lock only if owner_id matches
  ```

  Run it as a one-off job with the same NFS mount (`--args=break-writer-lock,--owner-id,<id>`).
- `KA_WRITER_LOCK=off` disables the lease: local development and tests only.

## Environment

| Variable | Value on Cloud Run | Notes |
|---|---|---|
| `KA_STORAGE_ROOT` | `/mnt/nfs/ka/ka_storage` | The directory must exist and be writable by uid 10001 on the NFS export. The image default (`/data/ka_storage`) is container-local and lost on restart. |
| `KA_ACCESS_POLICY` | `token` | Image default. Non-loopback peers need `KA_ACCESS_TOKEN` on the console routes. |
| `KA_ACCESS_TOKEN` | Secret Manager | Console / operator token for `/api/knowledge-acquisition/*` (not `/v1`). Empty means non-loopback console calls are refused. |
| `KA_AGENTX_TOKEN` | Secret Manager | Bearer for `/api/knowledge-acquisition/v1/*` and `/healthz`. AgentX keeps it as `AGENTX_KNOWLEDGE_ACQUISITION_TOKEN`; Knowledge Worker sends the same value as `KW_KA_TOKEN`. |
| `KA_GRAPH_MODE` | `memory` | Set explicitly (the `auto` default resolves to `memory` too when `KA_KW_URL` / `KA_ENTERPRISE_OS_ROOT` are unset). |
| `KA_GRAMMAR_DIR` | `/opt/ka/grammar` | Image default; the bundled grammar (below). Leave `KA_GRAMMAR_URL` and `KA_ENTERPRISE_OS_ROOT` unset. |
| `KA_STORAGE_BACKEND` | `local` | Default. |
| `KA_LLM_PROVIDER` | `stub` (or unset with no `ANTHROPIC_API_KEY`) | The MVP needs no model call; set `anthropic` + the key only if model-assisted extraction is wanted. |

No secret is baked into the image or written to the store. `knowledge-acquisition env` lists every declared setting.

## Bundled grammar

KA reports `degraded` (healthz `checks.grammar = not_loaded`) and not ready until it has a grammar pair. The image
copies `deploy/grammar/grammar.json` (`grammar/v2`) and `deploy/grammar/process_types.json` (`process-types/v2`) to
`/opt/ka/grammar` (root-owned, read-only) and sets `KA_GRAMMAR_DIR=/opt/ka/grammar`.

Source: copied byte for byte from **`pankajkamble75/knowledge-worker` `knowledge_worker/graph_model/`** (same owner), at
`origin/main` `cf709db`; the files last changed in `064bdf4`.

| File | sha256 |
|---|---|
| `grammar.json` | `3924a97b6ba2de38028b56ead4fe6029204a59cbe0e3cffecab455d0c2a86b9c` |
| `process_types.json` | `835712bd2de9f89967eb2b3ef118d4a4b3a2c8ac92a71569292376fea404ff07` |

Knowledge Worker owns the graph model and serves these same files at `GET /v1/graph-model`, so the bytes match what
`KA_GRAMMAR_URL` would deliver later. The trimmed test fixture (`ka/tests/fixtures/grammar`) has the same version strings
but different bytes. Do not use it in an image: KA snapshots the digest in `<store>/grammar_snapshot.json` and fails
closed (`stale`) when the files change under the same version string. To update, copy both files again from Knowledge
Worker and rebuild. If the store already holds a snapshot of an older pair with the same versions, accept it with an
explicit `refresh(force=True)`.

## Probes

Cloud Run probes send no bearer, and `/healthz` needs one. The unauthenticated readiness route returns only
`{"status": "ready"}` (200), `{"status": "standby"}` (200, waiting for the writer lease; see above) or
`{"status": "not_ready"}` / `"lost"` / `"failed"` (503). It is ready when the store directory exists, the grammar
is loaded and the grammar is not stale. It reveals no version, path or check.

- `GET /api/knowledge-acquisition/ready`: use this one.
- `GET /api/knowledge-acquisition/readyz`: same handler.

Cloud Run reserves "some paths ending with `z`" at its front end (Cloud Run known issues) and recommends avoiding them.
Probes go straight to the container, so either path works as a probe. From outside, use `/ready`.

```yaml
startupProbe:
  httpGet: {path: /api/knowledge-acquisition/ready, port: 8080}
  periodSeconds: 5
  failureThreshold: 24        # first start opens the NFS store and loads the grammar
livenessProbe:
  tcpSocket: {port: 8080}     # TCP: a lost grammar should not restart-loop the only instance
  periodSeconds: 30
```

The authenticated `GET /api/knowledge-acquisition/healthz` (bearer `KA_AGENTX_TOKEN` or `KA_ACCESS_TOKEN`) still gives
the full status (`ok` / `degraded` / `down` with checks). After deploy, confirm that AgentX's and Knowledge Worker's
`/healthz` polls reach KA through the Cloud Run URL and are not answered by the front end; see the risk below.

## Seed the demo knowledge (once)

The dataset is synthetic: Copper Kettle Coffee is a fictional single-site café. Seven short pricing-policy documents
cover cost-plus targets per category, competitor benchmarking, the quarterly review cadence, supplier cost pass-through,
seasonal specials, the rounding rule and owner approval. Every source title ends in `(SYNTHETIC)`, and every body opens
with a "SYNTHETIC DEMO DATA" banner.

```sh
knowledge-acquisition seed-demo copper-kettle            # into $KA_STORAGE_ROOT
knowledge-acquisition seed-demo copper-kettle /some/dir  # or an explicit store
```

The command goes through KA's governed flow:

1. It uploads each document (source, version, physical binding, audit).
2. It runs `extract_from_source` (evidence plus candidates through `ingest_candidate`, the one pipeline). The stub
   provider makes this deterministic and offline.
3. It approves each candidate with `decide(APPROVE)` by `copper-kettle-owner (synthetic)`.

The result is 14 ACTIVE nuggets on scope `INSTANCE:copper_kettle_coffee` under `DOMAIN:coffee-shop`. The scope ids match
Knowledge Worker's instance and substructure. The command prints a JSON report (`sources_new`, `candidates_extracted`,
`approved`, `active_refs`).

The seed is idempotent. Re-running it re-uploads unchanged bytes, which is a no-op by checksum. It does not re-extract a
source whose candidates exist, and it only approves candidates an interrupted run left pending. A second run reports
`sources_new: 0, approved: 0`.

### Running it against the NFS store

Run the seed as a Cloud Run **job** from the same image, with the same NFS volume and env. The job takes the writer
lease with a short wait (`KA_SEED_LOCK_WAIT_SECONDS`, 10 s). If a service instance holds it, the job writes nothing and
exits **3** with `seed-demo: refused, the writer lock ... is held by owner_id=...`. Run it before the service first
starts, or while the service is scaled to zero. An instance that starts while the job runs waits in standby and then
loads the seeded store.

```sh
gcloud run jobs create ka-seed-demo --region=$REGION --image=$KA_IMAGE \
  --service-account=$KA_RUNTIME_SA --network=$VPC --subnet=$SUBNET \
  --add-volume=name=ka-nfs,type=nfs,location=$NFS_SERVER:/$NFS_EXPORT \
  --add-volume-mount=volume=ka-nfs,mount-path=/mnt/nfs/ka \
  --set-env-vars=KA_STORAGE_ROOT=/mnt/nfs/ka/ka_storage,KA_GRAPH_MODE=memory,KA_LLM_PROVIDER=stub \
  --command=knowledge-acquisition --args=seed-demo,copper-kettle \
  --max-retries=0 --tasks=1
gcloud run jobs execute ka-seed-demo --region=$REGION --wait
```

Use the same network, subnet and NFS values as the service. The job needs no token secret.

## The search that returns it

Knowledge Worker sets `KW_KA_URL=https://<ka-service-url>/api/knowledge-acquisition` and `KW_KA_TOKEN=<KA_AGENTX_TOKEN>`.
Its adapter then sends:

```http
POST /api/knowledge-acquisition/v1/knowledge/search
Authorization: Bearer <KA_AGENTX_TOKEN>
X-Serverless-Authorization: Bearer <Google ID token for the KA service>
Content-Type: application/json

{"query": "How does Copper Kettle Coffee set its menu prices?", "instance_id": "copper_kettle_coffee", "domain_id": "coffee-shop", "limit": 5}
```

The reply is `{"results": [...], "version": ..., "operation_id": ...}`. Each result is an ACTIVE nugget of scope
`INSTANCE:copper_kettle_coffee` with `provenance.source_ids` and `provenance.decision_id`. Full lineage (sources,
evidence excerpt, decisions) is at `GET /api/knowledge-acquisition/v1/knowledge/{id}`.

Scope matching is exact, and `instance_id` wins over `domain_id`:

- `instance_id: "copper_kettle_coffee"` finds the seeded knowledge, with or without `domain_id`.
- `domain_id: "coffee-shop"` alone does **not**, because the café's policies are instance knowledge.

`ka/tests/test_plan36_cloud_run_mvp.py` pins this end to end.

## Risks to check after deploy

- **Paths ending in `z`.** AgentX polls `{base}/healthz` and Knowledge Worker's `health()` calls `/healthz` through the
  Cloud Run URL. If the front end answers those, the checks fail while the service is healthy. Test with
  `curl -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token)" -H "Authorization: Bearer $KA_AGENTX_TOKEN" $URL/api/knowledge-acquisition/healthz`.
- **Loopback containment.** `KA_ACCESS_POLICY=token` lets loopback peers through without a token. On Cloud Run, requests
  arrive from the platform's proxy address, not 127.0.0.1. Confirm that a console route returns 401 without
  `KA_ACCESS_TOKEN`.
- **Single writer.** Enforced by the writer lease (above). During a rollout the new revision answers 503 until the old
  one has released the lease. A SIGKILLed instance needs the break-glass step before KA can serve again.
