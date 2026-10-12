# Rollback: KA's VPN-only bind (plan-35, 2026-10-12)

**Change:** KA moved from `0.0.0.0:8011` (every interface, including public 2.25.98.235) to `10.77.0.2:8011` (WireGuard) plus
`127.0.0.1:8011` (loopback). This was done through two lines in `/root/ka/.env` (gitignored):

    KA_BACKEND_HOST=10.77.0.2,127.0.0.1
    KA_PUBLIC_BASE_URL=http://10.77.0.2:8011

The previous `.env` was copied to `/root/ka-env-backup-<UTC>` (mode 600, outside the repository) before editing. Auth is unchanged: AgentX
needs `KA_AGENTX_TOKEN`; console callers on another host need `KA_ACCESS_TOKEN`.

## Roll back (about 1 minute)

1. Remove both lines from `/root/ka/.env`, or restore the backup: `cp /root/ka-env-backup-<UTC> /root/ka/.env`.
2. `systemctl restart enterprise-os-ka`
3. Verify: `ss -ltn | grep 8011` shows `0.0.0.0:8011`, and `curl -s http://127.0.0.1:8011/api/knowledge-acquisition/healthz` returns
   `status: ok`.

Without `KA_BACKEND_HOST`, KA binds `0.0.0.0`, which was the behaviour before plan-35.

## If WireGuard is down

KA keeps serving on `127.0.0.1:8011`. If `10.77.0.2` is missing at start-up, binding to it fails and the service doesn't start.
`systemctl status enterprise-os-ka` shows `Cannot assign requested address`. In that case, roll back (or set `KA_BACKEND_HOST=127.0.0.1`)
until `wg0` is up again.
