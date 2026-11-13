# Readiness review and SaaS entry

Reviewed 2026-11-13 against Core implementation `ddc94ce` and its pinned crawler
`2594a7b`. This assessment separates tested engine behavior, findings from code
inspection, and work that belongs in the separate SaaS repository. It supersedes
older readiness documents where they describe gaps that Core 0.2 has since fixed.

## Decision

**Start building the SaaS integration now. Do not declare the paid service
production-ready yet.** The engine has a usable boundary, deterministic regression
coverage and meaningful recovery evidence. The largest remaining unknown is actual
answer quality and cost on representative customer websites with selected models.
There are also two confirmed operational edge cases below to resolve before
unattended operation and complete usage reconciliation.

| Stage | Assessment | Condition |
| --- | --- | --- |
| SaaS development | Ready to start | Consume the pinned Core package behind a host adapter; keep auth and tenancy in the SaaS. |
| Internal end-to-end demonstration | Ready with fixture providers | Prove authorized resource selection, queued ingest, grounded query and operation tracking. |
| Controlled live pilot | Conditional | Review the client corpus, authorize bounded model spend, enforce tenant isolation and hard worker limits, and rehearse recovery. |
| General paid launch | Not demonstrated | Pass quality, capacity, billing reconciliation, backup/restore, security and product acceptance gates. |

## What is implemented

| Area | Current capability | Practical limit |
| --- | --- | --- |
| Public website capture | Robots-aware HTTP(S), scope checks, validated/pinned destinations, redirect checks and network/page/byte/deadline limits | HTML only. No universal coverage, JavaScript browser, authenticated connector, PDF/OCR or office document promise. |
| Extraction | Headings, short facts, published navigation/footer/form text, lists, tables and code; bounded table fallback | Heuristics need client-content acceptance checks. Excluded input values are intentional. |
| Deduplication | Exact cleaned whole-page evidence is compared before summary, embedding and indexing; aliases retain duplicate URLs | Duplicate pages can still be fetched/stored. No near-duplicate, cross-project or independent shared-chunk dedup. |
| Retrieval | Hybrid lexical/vector retrieval, classic expansion and builder-directed evidence follow-ups | Builder superiority, multilingual accuracy and live latency have not been established. |
| Grounding | Structured answered/partial/unsupported results; literal citations checked against the exact supplied evidence ID/text | Valid quotes do not establish entailment for every generated claim. Human claim review remains necessary. |
| Publication | Immutable FAISS snapshots, checksums, embedding identity, atomic active pointer, compare-and-swap publication and rollback | Supported on local persistent filesystems; this is not distributed storage coordination. |
| Refresh safety | Frozen captures, capture-policy compatibility, source inventories and exact removal approval | A scope change does not revoke an already published snapshot immediately; the host must suspend serving when required. |
| Operations | Explicit IDs, deadlines, counters, cancellation, typed outcomes, replay and post-publication recovery | Some boundaries remain incomplete; see confirmed findings. A Python deadline cannot terminate every injected client. |
| Isolation | Explicit resource roots, identity manifests, contained subordinate paths, scoped embedding cache and caller-owned clients | The host must authorize roots and credentials. This is not user authentication or protection against a hostile process with filesystem access. |
| Packaging | Core-only wheels, optional API/UI/HF extras, installed-package checks and pinned crawler source | Broad dependency ranges require a locked deployment artifact. The project metadata still identifies an alpha release. |

## Evidence and what it establishes

- The current checkout passes **302 tests** and Ruff. These include source policy,
  extraction, dedup, citation, resource isolation, provider retry/budget, fetch,
  publication and service contract tests. Test count is not an accuracy score.
- Installed Linux checks passed 87 tests with one platform-specific skip; isolated
  Windows packaging passed real fixture crawl/publish/reopen/query and all 17 API
  tests. Optional UI/API imports were blocked during the Core-only smoke test.
- The single-host Linux harness exercised live readers against competing writer
  processes, process death immediately after pointer publication, cancellation,
  export/restore and actual ENOSPC on a small filesystem. The previous snapshot
  remained valid after disk exhaustion.
- Separate containers reopened the same disposable persistent volume and queried
  the same snapshot. This proves local restart persistence, not cross-host disaster
  recovery or a production restore-time objective.
- A synthetic 2,000-page/20,000-segment/1,536-dimension benchmark ran concurrency
  1/4/10 against one and four resource roots. One-resource p95 was approximately
  46/188/492 ms; four resources at concurrency 10 reached approximately 595 ms,
  with final RSS around 1.07 GB. These are fixture-provider WSL2 engine results,
  excluding live model latency and production resource contention.
- Five real website captures produced 100 bilingual draft cases. They are
  unreviewed, contain 52 duplicate draft questions and correctly fail readiness
  validation. There has been no paid evaluation or measured builder/classic quality
  comparison on the proposed reviewed corpus.
- The recorded advisory scans returned zero records at their scan time. This
  does not establish license approval, container safety or the absence of unknown
  vulnerabilities. The committed package report is a development-build record,
  explicitly marked `source_clean: false`, not a release certificate.

Evidence: [Linux fault checks](audit/2026-11-13-single-host-linux.json),
[benchmark](audit/2026-11-13-benchmark-linux.json),
[package verification](audit/2026-11-13-saas-readiness-package-verification.json),
and [additional offline probes](audit/2026-11-13-saas-entry-probes.json).
All nine jobs in the implementation CI run
[43434855824](https://github.com/Y-Elsayed/Webly/actions/runs/43434855824)
passed for `ddc94ce`, including the new Linux single-host checks and all four
OS/Python combinations for tests and installed packaging. This proves that
candidate's automated gates, not the unrun live-quality or SaaS acceptance gates.

## Confirmed gaps and follow-up work

These are general implementation findings, not exceptions for particular websites.
They were not silently treated as fixed by this documentation review.

| Priority | Finding and evidence | Owner and acceptance condition |
| --- | --- | --- |
| P1, before automated recovery | `SnapshotStore.active_version` and `CrawlRuns.inspect/validate` assume decoded JSON is an object. Replacing a temporary pointer or run manifest with valid JSON `[]` produces `AttributeError`, which `core_boundary` does not normalize. | Core: validate artifact types and required fields explicitly before access, including journals and nested publication metadata. Tests must produce sanitized `ArtifactError` for non-object/missing/wrong-type data while preserving the prior valid snapshot. Do not hide programming mistakes by broadly catching every exception. |
| P1, before usage-complete billing | A sink failure on the final `usage` event can coexist with a committed snapshot. Recovery returns the committed outcome before loading/redelivering prior journal events. The offline probe observed committed-with-pending-usage, followed by recovery delivering zero events to a replacement sink. | Core plus host: define a supported durable event export/replay and acknowledgement contract, deduplicated by operation ID/sequence. Recovery must retain committed state and reconcile missing usage without another provider call. The host must not infer zero usage from an empty recovery context. |
| P1, before unattended workers | `ResourceScope` acquires `.resource.lock` without an explicit timeout, during construction outside an operation context. Ingest/publication locks are bounded, but this startup lock is not. This is a code-inspection finding, not a timed hang experiment. | Core: add a finite startup-lock policy and typed timeout. Host: enforce a process deadline that includes resource/client/runtime creation. Test with another process holding the resource lock. |
| P1, before public traffic | The reference FastAPI service has no tenant authorization, synchronous ingest, per-request runtime construction, process-environment credentials and file-backed project/chat state. Some non-Core error handlers return raw exception messages. | SaaS: implement its own authorized API and job host. Do not expose the reference adapter directly or treat it as the production control plane. |
| P1, before client promises | Quality, live cost, real-provider tail latency and deployed-host capacity are unmeasured. Existing tests exercise logic with scripted providers. | Joint: run the reviewed evaluation and deployment trials below. Record failures and coverage; do not choose builder because it sounds smarter. |
| P2, before generated-client integration | Reference `ErrorResponse` documents only `detail`; actual Core errors include code, retryability, operation ID/outcome and sometimes changed fields. Core errors mostly map to HTTP 400, including provider/internal cases. | SaaS API: publish an explicit error schema and map validation/policy, conflict, throttling, provider and internal failures intentionally. Clients must handle stable codes and publication outcomes. |
| P2, before sustained storage growth | Snapshots, runs, journals and caches accumulate; automatic safe garbage collection is not implemented. Export is a validated copy and must be tested under the target backup process. | Host plus Core retention contract: apply quotas, track reader/worker ownership, protect active versions and required recovery journals, test deletion and full-disk recovery. |
| P2, release maintenance | Dependency ranges and current CI actions/runner labels can resolve to changing environments. Same version numbers alone do not prove the exact reviewed crawler artifact. | Release: publish internal wheel/image hashes, lock runtime dependencies, retain license/advisory inventories and update CI runtime dependencies through reviewed changes. |

The pending-usage case does not imply duplicate indexing or an invalid snapshot.
Publication success and event delivery are separate facts; the production host
must preserve both rather than retrying a committed job to repair accounting.

## Recommended SaaS architecture

Use a **separate SaaS repository** and a small adapter around Core's Python API.
Start with one Linux host and local persistent Core resource storage. The SaaS API,
workers and database are separate responsibilities even if deployed together at
first. Core does not need its own network microservice for the initial product.

```text
Dashboard / embedded chat
          |
SaaS API: identity, authorization, limits, input policy
          |
          +--> SaaS database: tenants, bots, configs, jobs, conversations, usage
          |
          +--> durable job dispatcher --> bounded ingest worker
          |                                |
          +--> bounded query worker -------+--> pinned Webly Core package
                                                   |
                                       authorized ResourceScope + ProviderBundle
                                                   |
                                       local immutable snapshots / scoped cache
```

The diagram is proposed host architecture, not infrastructure already supplied
by this repository. A single-host durable database-backed job dispatcher is
sufficient to start; a distributed queue is not a prerequisite or a Core feature.

### Resource and version mapping

Create server-owned identifiers for tenant, bot, knowledge base and Core resource.
Store the authorized mapping in the SaaS database. A client supplies a bot ID;
the server resolves that bot to its permitted resource, root, configuration and
credential reference. Never accept a filesystem path, provider endpoint, raw
resource ID or private-network fetch allowance as proof of authorization.

Give each independently managed corpus its own `ResourceScope`. Derive roots from
trusted IDs under a host-controlled storage directory. Bind embedding model,
dimension, revision and endpoint identity to the resource's index compatibility.
Keep configuration versions immutable for each submitted job. Record Core version,
crawler revision, run ID, policy digest and published snapshot ID with the job.

Do not reuse the reference adapter's constant `resource_id="project"` as a global
SaaS identity. Distinct roots remain isolated there, but its naming and credential
bootstrap are reference-application choices rather than a tenant mapping contract.

### Public API and data model

The following are proposed platform interfaces; they are not existing Core routes.

| Platform surface | Minimum host-owned records and behavior |
| --- | --- |
| Tenant/bot management | Tenant membership, role, bot ownership, lifecycle and tenant-filtered access to every record |
| Source/config panel | Versioned start/scope policy, retrieval settings and approved model profile; server-enforced limits and robots policy |
| `POST /bots/{id}/ingestions` | Create a durable job, preserve a host idempotency key and return a job ID promptly |
| `GET /jobs/{id}` | Authorized progress, typed error/outcome, run/snapshot identity, pending approval and cancellation state |
| `POST /jobs/{id}/approve` | Authorize the exact source-removal proposal; pass its token with a new logical Core operation ID |
| `POST /bots/{id}/messages` | Resolve permitted resource, construct trusted conversation context, execute bounded query and persist response/citations/version |
| Widget access | Separately scoped public chat credential and abuse limits; no administration permission or storage access |
| Usage and audit | Unique event identity, reservation/settlement distinction, immutable job attempts and administrative audit records |

An allowed widget origin can assist abuse control but is not a replacement for
an appropriately scoped credential and server-side limits. Conversational memory
is host-provided input, not approved source evidence. Filter access to the stored
conversation before building it.

### Ingestion flow

1. Authenticate and authorize the bot; validate source policy and subscription
   limits. Freeze configuration, credential profile and Core artifact versions.
2. Persist a job and its logical operation ID before enqueueing. Acquire a host
   lease allowing one ingest per resource; use bounded worker processes.
3. Construct `ProviderBundle`, `ResourceScope` and `build_runtime(...)` inside
   the worker. Close runtime and caller-owned providers deterministically.
4. Supply `OperationContext` with server-selected limits and a durable usage sink;
   call `run_ingest(mode="both", ...)`, or explicitly split crawl/index using
   the returned `run_id`.
5. Persist `approval_required` without changing the active corpus. A changed
   capture policy requires fresh capture; approval cannot override it.
6. Persist outcome and snapshot identity. On timeout/death, reconcile the stable
   operation ID before retrying. Do not treat a client disconnect as proof that
   publication failed. Repair event delivery separately from provider execution.

Use a fresh context per attempt, but preserve the logical operation ID and frozen
inputs for recovery. Changed inputs require a new operation. Explicit resume
retains Core's counters and elapsed budget, so an exhausted job may need a new,
authorized logical operation rather than an endless resume loop.

### Query flow and runtime ownership

Authorize before selecting storage or credentials. Apply per-tenant and per-bot
rate/concurrency limits and reserve allowance before calling Core. Call
`query_result` and persist the structured answer, citations, snapshot ID, status
and usage correlation. Handle partial/unsupported and unverified transformations
explicitly in the product. Do not present every response as source-verified.

One runtime serializes its work. Avoid sharing a single runtime across all bots,
or running long ingest on the exact query runtime. Start with bounded worker-owned
runtimes per authorized resource. If caching them, bound the count/RSS and evict
with `close()`; also close caller-owned provider bundles. Configuration/credential
changes must invalidate the appropriate cached ownership. Loading a runtime per
HTTP request can produce repeated index loads and is not a capacity strategy.

Select queue/concurrency limits after measurement. Separate runtimes permit
concurrent work but can duplicate loaded FAISS/metadata memory. Do not multiply
the synthetic 1.07 GB figure into a client-count guarantee.

### Storage, security and observability

Use local persistent storage with tested locking/atomic replacement. Back up both
SaaS metadata and Core artifacts, and retain their resource/snapshot mapping.
Restore onto a separate empty scope and verify a grounded query before accepting
the backup procedure. Do not edit active pointers by hand to implement a UI action.

Apply worker memory/CPU/filesystem quotas and a hard deadline. Restrict network
egress against private/metadata destinations as defense in depth; keep fixture
`FetchPolicy` allowances out of tenant config. Keep provider secrets in host-managed
secret storage and never return raw config/artifact paths or debug traces publicly.

Correlate request, job, Core operation, resource and snapshot IDs. Monitor queue
wait, ingest duration/failures, unsupported rate, provider errors, retries,
reservation/usage-delivery backlog, disk headroom, worker memory and query p95.
Define separate liveness and readiness checks; file/pointer existence alone does
not establish index validity or provider availability.

## Delivery sequence and acceptance gates

| Step | Concrete deliverable | Done when |
| --- | --- | --- |
| 1. Pin engine and add adapter | Private wheel/image artifacts and a platform-owned `CoreGateway`; fix the three Core edge cases above | Deterministic install; typed artifact/lock failures; durable event recovery demonstrated without reembedding |
| 2. First vertical slice | Authenticate, create a bot, configure one source, enqueue ingest, show job progress and ask a cited question | Works after API/worker restart; a second tenant cannot access its bot, job, conversation or artifacts |
| 3. Recovery and cost control | Stable IDs, leases, cancellation, reservation, event dedup/replay and approval UI | Duplicate requests, worker death and sink failure cannot duplicate committed work or silently erase usage |
| 4. Quality and host pilot | Independently reviewed corpus, authorized live comparison and target-host load/restore trials | Both language/mode gates pass; source-specific misses are triaged; measured capacity/cost fit the intended service |
| 5. Paid launch | Subscription enforcement, widget security, retention/deletion, support procedures and release evidence | Tenant/security, billing, recovery and product acceptance suites pass on the deployed pinned candidate |

The first integration acceptance test should exercise the entire path: tenant A
creates and ingests a bot, tenant B is denied access, A gets a cited answer,
the worker restarts, the same snapshot remains queryable, and retrying the ingest
operation does not repeat embeddings. Add sink-failure reconciliation before
converting usage into customer charges.

The quality target is at least 95% supported-claim precision, 95% citation
accuracy, 95% correct abstention and 80% answerable coverage, separately for
English/Arabic and builder/classic. These remain targets, not results. Follow
[the evaluation procedure](evaluation/README.md); report sample counts, site
strata, errors, latency and conservative costs. Keep live model spend separately
authorized and capped.

Do not block the first supported HTML product on browser rendering, new vector
databases, advanced near-duplicate detection or a distributed Core service.
The immediate work is a secure host integration, the confirmed operational gaps,
and evidence that the chosen retrieval/model configuration serves actual clients.
