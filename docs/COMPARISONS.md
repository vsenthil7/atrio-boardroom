# ATRIO Boardroom — Product comparisons + design choices

> Created 2026-05-19 ~05:30 BST in response to user questions during build night.
> NOT in the static spec set (BRD/Arch/etc) — sits alongside as ad-hoc reasoning record.

---

## 1. ATRIO vs AuditEx (Hack0014, March 2026)

| Dimension | **AuditEx** | **ATRIO Boardroom** |
|---|---|---|
| Product category | AI workflow compliance / audit-trail infra | Multi-agent voice-first boardroom |
| What it produces | Cryptographically ordered, multi-party-verified, human-readable audit trail for any AI workflow | Board-pack PDF + treasury action receipts + audit log |
| Primary user | Compliance / risk / regulator | Founder / exec / advisor |
| Sponsor stack | Vertex (Swarm Tashi) + foxmq MQTT + Mosquitto | Vultr + Gemini + Featherless + Speechmatics + Kraken |
| Consensus mechanism | **Vertex / Swarm Tashi** — 3-node BFT-style. `vertex-nodes/{node-a,node-b,node-c}` each with its own Mosquitto MQTT broker + per-node Ed25519 keys. Every AI workflow event is broadcast to 3 nodes; nodes agree on order; the ordered log is the audit trail. | **None at protocol level.** "Consensus" is *application-level* — the Facilitator agent surfaces agreement + dissent across CFO/CTO/CMO/COO/Counsel responses. Narrative consensus among LLM voices, not Byzantine-fault-tolerant ledger consensus. |
| Trust model | Multi-party — 3 independently keyed nodes; quorum required | Single-tenant — Postgres RLS + append-only audit triggers; one party signs everything |
| Tamper-evidence | Cryptographic ordering across multiple nodes (each node holds a verifiable copy) | Append-only Postgres triggers + RLS — single source of truth; can be tampered if you own the DB |
| Sweet spot | "Prove to a regulator nobody could have rewritten what the AI did, even me" | "Run a one-hour board meeting and walk out with a defensible board pack" |
| Composition | — | ATRIO could feed its `audit_log` events into an AuditEx-style ledger for tamper-evidence at the receipts layer (post-hackathon backlog) |

**Short answer:** AuditEx is **infrastructure**; ATRIO is **product**. AuditEx solves *can we trust the trail?* ATRIO solves *can we get a useful boardroom out of an hour of voice?* They could compose — ATRIO could feed its audit events into an AuditEx-style ledger — but they're not the same kind of thing.

## 2. Why no IOTA in ATRIO?

| Question | Answer |
|---|---|
| Could ATRIO use IOTA? | Yes, meaningfully — for treasury receipt anchoring + audit-log daily roots + multi-tenant signed streams. |
| Why isn't it in v1? | (1) None of the 5 sponsor pools award IOTA — no prize lift; (2) integration (PyOTA / IOTA SDK + tangle confirmation polling) cannot be validated before 16:00 BST deadline; (3) the producer didn't pick it. |
| What's the post-hackathon plan? | Backlog `NEW-P14.X.iota-anchoring` — hash each `treasury_actions` row and `audit_log` daily root, publish to IOTA Tangle. Free, feeless, no gas. Compliance buyers would buy it. |
| Where IOTA does NOT help ATRIO | The voice path / orchestrator / inference (latency-sensitive). Mandate enforcement (API-layer logic). |

## 3. API keys situation as of 2026-05-19 05:30 BST

Keys actually owned by the operator (scanned across AT-team projects):

| Provider | Owned? | Where | Used by ATRIO? |
|---|---|---|---|
| Anthropic (Claude) | ✅ | AuditEx, Verixa | No — ATRIO is Gemini-primary, Featherless-fallback |
| OpenAI | ✅ | AuditEx, Verixa | No |
| Gemini (Google AI Studio) | ✅ | Forensa (`FORENSA_GEMINI_API_KEY`) | **YES — wired into ATRIO `.env` at 05:25 BST**, ATRIO_MOCK_INFERENCE flipped to `false` |
| Featherless | ❌ | n/a | falls back to mock through inference registry |
| Speechmatics | ❌ | n/a (BRD mentions coupon `AIWEEK200`) | voice path runs in text-only fallback |
| Kraken | ❌ | n/a | `KRAKEN_PAPER_MODE=true` (no real key needed) |

Decision (05:25 BST): wire Gemini key only. Lowest-effort, highest-judge-impact change. Featherless + Speechmatics stay missing — both have working fallbacks in the registry.

## 4. Why the dual-mode health check + configurable ports?

Captured at the global-rules level — see `claude-memory/global/HEALTH_CHECK_RULES.md` (new at 05:15 BST) for the full pattern. Three legs:

1. **Docker first in Phase 0** — `make up` / `dev.ps1 up` is canonical; local-only is the second path.
2. **Every host-exposed port is env-var driven** with project-unique defaults. ATRIO uses `${VAR:-default}` for all 10 ports in `docker-compose.yml`. Registry of 4 projects (AuditEx, MendoraCI, Forensa, ATRIO) in HEALTH_CHECK_RULES.md prevents clashes when running multiple projects side-by-side.
3. **Dual-mode `tools/healthcheck.{ps1,sh}`** — modes `local` / `docker` / `both`. Hits `/healthz` + frontend + db state + inference providers; one-line summary on success; exit codes 0-5 for actionable diagnosis. Replaces ad-hoc curl loops in chat.

## 5. ATRIO health endpoint contract

| Endpoint | Auth | Returns |
|---|---|---|
| `GET /api/v1/healthz` | none | 200 + `{status, build_sha, version, db, inference_providers}` |
| `GET /api/v1/readyz` | none | 200 once migrations + seed applied (CP-EXTRACT verified) |
| `GET /api/v1/metrics` | none (network-restricted in prod) | Prometheus exposition |

Reference call sequence:

```
./tools/healthcheck.ps1 docker
→ [health docker] api=OK(200) db=ok inference=mock=configured,gemini=configured,featherless=configured frontend=OK(200) -- 0.3s
```

## 6. Document control

| Version | Date (BST) | Notes |
|---|---|---|
| 0.1 | 2026-05-19 05:30 | Created during build night to answer user questions about consensus / IOTA / API keys / health-check pattern. |
