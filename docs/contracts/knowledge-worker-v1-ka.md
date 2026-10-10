# Knowledge Worker v1 — the KA intake contract (KA's side, published for Knowledge Worker to implement)

**Status:** PROPOSED v1, 2026-10-10. Written by KA (`pankajkamble75/ka`, research-05 R7, plan-31) at the Knowledge Worker session's request;
that session accepted the shape the same day and implements it in `pankajkamble75/knowledge-worker` (service on `http://127.0.0.1:8101`).
Conventions follow KW's `docs/contracts/agentx-knowledge-worker-v1.md` §2–§5 (headers, auth, envelope, statuses).
**Executable fixtures:** `ka/tests/fixtures/kw_contract/*.json` (request → expected response, run against `ka/knowledge_worker/fake.py`).

## 1. Why

KA governs knowledge; Knowledge Worker owns the Process / Domain / Instance graphs and decides graph updates. KA used to publish by importing
KW's private `graph_store.proposals`. This contract replaces that import: KA sends **only approved, versioned knowledge as graph change
proposals**, every node and edge carrying `props.knowledge_lineage`, and learns the outcome by polling.

## 2. Conventions

| | |
|---|---|
| Base | `{KW}/v1` (KA setting `KA_KW_URL`, e.g. `http://127.0.0.1:8101`) |
| Auth | `Authorization: Bearer <token>` — KW mints KA its own token (client id `ka`, stored hashed in `KW_SERVICE_TOKENS`) with scopes `graph-changes:propose` (intake) and `graphs:read` (grammar, versions). KA setting `KA_KW_TOKEN`. |
| Headers | `X-Correlation-ID` (KA sends the AgentX correlation id or KA's proposal id), `Content-Type: application/json` |
| Envelope | `{contract_version: "1", correlation_id, status: "ok" \| "error", result, error: {status, code, message, retryable, detail}, provenance}` |

## 3. Submit a change — `POST /v1/graph-changes` (scope `graph-changes:propose`)

```json
{
  "target": {"kind": "instance", "id": "acme", "base_digest": "<instance graph digest KA saw>"},
  "ops": [{"op": "add_node", "node": {"id": "n_refund_approval", "kind": "rule", "name": "Refund approval",
           "props": {"knowledge_lineage": [{"nugget_id": "KN-001", "nugget_version": 1, "nugget_ref": "KN-001:v1",
                                            "governance_decision_id": "GD-1a2b", "graph_change_id": "GCP-9f8e"}]}}}],
  "reason": "governed knowledge KN-001:v1 activated",
  "actor": "alice",
  "knowledge_refs": [{"nugget_ref": "KN-001:v1", "decision_id": "GD-1a2b"}],
  "idempotency_key": "ka:GCP-9f8e"
}
```

- `target.kind = "instance"` → KW's `propose_instance_change(instance_id, ops, base_digest=, idempotency_key=)` (EOS plan-1033 semantics).
- `target.kind = "substructure"` → `propose_promotion(substructure_id, base_version, ops)`; `base_version` instead of `base_digest`.
- `ops` are KW `ChangeOp`s (`add_node`, `update_node`, `remove_node`, `add_edge`, `update_edge`, `remove_edge`). **Every node and edge that is
  added or updated carries `props.knowledge_lineage`** (a list; each entry names the nugget version and its governance decision). KW may
  refuse an op without it (`INVALID_REQUEST`).
- **KW decides.** It may apply at once (its HOTL policy) or hold for its own approval.

Result (`200`, `status: "ok"`):

```json
{"proposal_id": "prop-1a2b3c", "status": "applied", "applied_digest": "<new instance digest>", "new_version": null,
 "pinned_instances": [], "lineage": ["KN-001:v1"]}
```

`status` is `awaiting_approval | applied | refused`. A repeat with the same `idempotency_key` **and the same body** returns the existing
proposal (no second change); the same key with a different body is `CONFLICT`.

Errors (`status: "error"`):

| HTTP | `error.code` | when |
|---|---|---|
| 409 | `STALE_BASE` | `base_digest` / `base_version` is not the current one |
| 422 | `INVALID_REQUEST` | malformed body, unknown op, missing `knowledge_lineage`, grammar violation (`detail.findings`) |
| 404 | `UNKNOWN_INSTANCE` | target instance or substructure does not exist |
| 403 | `FORBIDDEN` | token lacks `graph-changes:propose` |
| 409 | `CONFLICT` | same `idempotency_key`, different body |
| 503 | `UNAVAILABLE` | KW cannot take changes now (`retryable: true`) |

## 4. Outcome — `GET /v1/graph-changes/{proposal_id}` (scope `graph-changes:propose`)

Returns the same `result` object. KA polls until `applied` or `refused`. There is no webhook or event feed (KW, 2026-10-10).

## 5. Read — grammar and versions (scope `graphs:read`)

- `GET /v1/graph-model` → `{grammar, process_types, grammar_version, type_table_version, grammar_digest, type_table_digest, source}` — the
  specialist API's own shape (not wrapped in the envelope), same body as enterprise-os `GET /api/knowledge-worker/graph-model`. KA setting
  `KA_GRAMMAR_URL`. The digests are sha256 of the files' bytes on KW's side; KA uses them as the snapshot identity (a same-version digest
  change → stale, fail closed). KA cannot recompute a byte digest from parsed JSON; integrity of the body rests on the token and transport.
- `GET /v1/graph-versions` → each domain's (substructure's) latest version and digest, each instance's graph digest and pins. KA reads the
  base it sends in `target`.

## 6. Reverse direction (already live)

KW calls KA's `POST {KA}/api/knowledge-acquisition/runtime/graph-gap` (bearer `KW_KA_TOKEN`) for `found_new` gaps, and KW's preview adapter
calls KA's `POST {KA}/api/knowledge-acquisition/v1/knowledge/search {query, instance_id?, domain_id?, limit}` → `{results[], version}`.

## 7. KA's behaviour around this contract

- KA submits only after a person approved the knowledge (KA governance) and a person approved the graph change proposal (KA Q3).
- KA's AgentX `knowledge.publish` operation stays `running` until this contract reports `applied`; `refused` fails the operation with KW's
  code and leaves KA's proposal APPROVED for a person to retry.
- KA keeps a shadow copy of the elements it published (its read model for lineage, impact and the console); KW stays the source of truth.
