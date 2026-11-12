# Webly production readiness audit

For the post-fix assessment, completed CI matrix, freshly reproduced gaps and
Core/SaaS release gates, read [current Core readiness](CORE_READINESS_STATUS.md).
This document retains the original audit trail.

Audit date: 2026-11-12. Scope: the current working tree, including the uncommitted ingestion fixes, rather than only the last GitHub commit. This is an engineering assessment, not a penetration-test certification or a claim that every possible defect has been found.

Follow-up: the initial package import defect A16 was subsequently addressed by the
Core foundation batch. [Installed-package evidence](audit/2026-11-12-core-package-verification.json)
records successful Core-only integration and 16 installed-wheel service tests;
the repository suite now has 203 passing tests. Findings below retain the original
audit evidence. Dependency security, wider safety and retrieval quality are not
certified by this packaging fix. See the [updated roadmap](PRODUCTION_ROADMAP.md).

## Decision

Webly has a useful retrieval core and can support controlled local evaluations. **Webly Core is not yet production ready:** packaging, crawl safety, bounded resource usage, evidence preservation, answer grounding, and failure/concurrency behavior still need release gates. Authentication and multi-tenant business logic belong to the separate Webly Chatbot Platform; their absence is not a missing feature of an embedded core library.

The user clarified the product boundary after this audit: this repository is Webly Core; a separate chatbot SaaS consumes it and owns its dashboard, configuration panel, authentication, tenancy and billing. The [core/platform boundary](CORE_PLATFORM_BOUNDARY.md) and revised [core production roadmap](PRODUCTION_ROADMAP.md) govern future work. The factual probes below remain valid, but priorities must be interpreted by their owner rather than as a request to build SaaS inside Core.

## Ownership and release scope

| Findings | Core responsibility now | Platform responsibility later |
| --- | --- | --- |
| A01 | Explicit caller-selected resource scope; no accidental process-global corpus/cache/credential state; document internal adapters | Identity, tenant ownership, roles and authorization on every externally exposed operation |
| A02–A04 | Safe fetch/path boundaries and enforceable per-operation resource budgets | Validate client configuration, assign allowed budgets, rate-limit tenants, restrict network egress |
| A05–A06, A16 | Correct package, declared/maintained dependencies, reliable storage contract, clean example artifacts | Production image/deployment, persistent volumes, infrastructure monitoring and backups |
| A07–A11 | Discovery, evidence preservation, chunking, grounded retrieval and consistent budgeting | Select supported features and present truthful source/answer states |
| A12 | Atomic/versioned core artifact/config operations and honest errors | User/chat/business records, transactional tenant metadata and retention policy |
| A13 | Schedulable operations, progress/cancellation, safe publication and bounded runtime reuse | Durable queue, workers, leases, scheduling and fair sharing |
| A14 | Accurate request/provider usage events and explicit sink failure behavior | Pricing, quotas, allowance reservation, billing ledger and reconciliation |
| A15, A17 | Explicit provider identity, runtime invalidation, cache scope and concurrency | Secret storage, access grants, credential ownership and rotation workflow |
| A18 | Structured diagnostics, benchmarks, fault tests and versioned release evidence | Service SLOs, on-call, tenant dashboards and operational policies |

Core's resource scope is a technical namespace/storage handle supplied by trusted application code, not an authenticated tenant identity. Core must honor the supplied scope; the SaaS must prove the caller may use it. An unauthenticated local/internal adapter is not a public SaaS endpoint and must not be exposed directly.

## What was checked

- Read the UI/runtime, service routes and schemas, filesystem repositories, crawl adapter and actual imported crawler submodule, extraction/chunking/embedding, retrieval/generation, snapshots, usage tracking, packaging, deployment, CI, and existing design documents.
- The implementation validation completed with **195 tests passing**, one FAISS/NumPy deprecation warning, and repository Ruff passing. Those results validate the existing suite; they do not establish tenant safety or production capacity.
- Built `webly-0.1.0-py3-none-any.whl` and inspected its contents and dependency metadata.
- Ran temporary-data API and component probes. [Machine-readable evidence](audit/2026-11-12-evidence.json) records the outcomes. No private-network fetch or model API request was made by these probes.
- Queried public PyPI metadata for the 22 exact direct pins in `requirements.txt`. This is a limited advisory check, not a complete dependency/container audit. Some records share CVE/GHSA aliases; raw record counts must not be treated as unique vulnerability counts.
- Used the preceding real EUI rebuild as ingestion evidence: 1,082 crawl records, 770 canonical pages, 311 duplicate pages, one empty-content page skipped, 1,411 indexed segments, and 1,250 structural chunks avoided. A simple English question produced a cited answer; an Arabic equivalent failed the model budget check. Neither is a comprehensive quality evaluation.

Reproduction: from the repository root, build a wheel with `python -m pip wheel . --no-deps --no-build-isolation --wheel-dir <system-temp>/webly-production-audit`, then run `python -m scripts.audit_readiness` with API/test dependencies installed. The script overwrites the dated JSON evidence and uses temporary storage. Review its probes before running against changed APIs. The audit is a dated snapshot; reruns may produce different advisory results.

## Work already completed

The latest local ingestion changes address `issue.md` through a general empty-content policy, not a rule for `/ar/samllogin`. Valid HTML with no extractable evidence is reported and skipped; malformed records and extraction/provider failures still stop the build. All-empty input fails without replacing the active snapshot.

Exact page-content deduplication runs before embedding, hashes ordered structural headings/text, keeps source URL aliases, and avoids merging unrelated graph edges. The first matching page is canonical. Windows snapshot file syncing and bounded sharing-conflict retries were corrected. A failed ingest forces the runtime to reload the surviving active snapshot. UI summaries and `ingest_report.json` explain skips, duplicates, and failures.

These changes are local and not pushed. They do not address crawl completeness, near duplicates, tenant isolation, or the query failures below.

## Findings and fix list

Priority definitions in the original findings: **P0** blocks an internet-facing commercial release; **P1** blocks a dependable paid pilot or hosted workload; **P2** improves quality, maintainability, or expansion. These labels describe consequence, not implementation ownership. Core releases use the revised roadmap's core-specific gates; platform-only findings do not block an embedded Core release. A code-reviewed risk is distinguished from a reproduced probe. Each fix needs its own tests and acceptance evidence.

### A01 — Platform P0: Existing adapters have no authentication or tenant authorization

Evidence: [`service/app.py`](../webly/service/app.py), [`dependencies.py`](../webly/service/dependencies.py), all service routers, and the cached UI storage manager. The temporary API accepted project creation without credentials (`201`) and project listing (`200`). Projects and chats are addressed without tenant ownership. A session-specific Streamlit state does not isolate filesystem data.

Consequence: exposing this service permits unauthorized access to client data and actions, including paid provider usage. Project IDs and obscure URLs are not authorization.

Platform fix: establish authenticated identity and tenant context at the external API boundary; derive ownership server-side on every project/chat/job/query/export/delete operation. Add roles, tenant-scoped repositories and authenticated admin access. Core supplies explicitly scoped resources, isolated caches and provider clients; it does not implement login or authorization. Existing Streamlit/FastAPI surfaces are development/internal adapters until the platform wraps or replaces them.

Platform acceptance: anonymous requests fail; two-client tests cannot access each other's IDs, jobs, caches, sources, chats, exports, or deleted artifacts. Core acceptance: two explicitly supplied resource scopes do not mix artifacts, caches, credentials or query evidence. These are separate test obligations.

### A02 — P0: Crawler destinations are not a network security boundary

Evidence: [`webcreeper/.../base_agent.py`](../webcreeper/webcreeper/creeper_core/base_agent.py) fetch and robots paths; Atlas host allowlisting. The probe accepted `http://127.0.0.1/admin` when configured as the base host; it did not fetch it. Fetchers follow redirects automatically and do not validate resolved public addresses at each hop. Domain allowlisting controls crawl scope, not SSRF.

Fix: a shared fetch policy for pages, robots, sitemaps, and any future renderer/document fetch. Permit HTTP(S) only, reject credentials in URLs, validate all resolved IPv4/IPv6 addresses including mapped forms, restrict ports, and revalidate every redirect. Couple validation to the connection to address DNS rebinding, with outbound network controls blocking metadata/internal services. Avoid a blacklist of particular hosts. See [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

Acceptance: offline controlled tests for private/link-local/loopback ranges, mixed public/private DNS, redirect chains, IPv6, credentials, alternate ports, and rebinding. Browser rendering must inherit equivalent egress constraints.

### A03 — P0: User configuration can select paths outside a project

Evidence: [`project_repository.py`](../webly/storage/project_repository.py), [`project_service.py`](../webly/service/services/project_service.py), [`schemas.py`](../webly/service/schemas.py), and runtime path joins. A temporary absolute `results_file` outside the project directory was accepted and reported ready. `embedding_cache_dir` is also configurable. Name sanitization collapses basenames rather than establishing ownership and resolved containment.

Fix: Core accepts trusted storage handles/roots and enforces containment for subordinate artifact names. Explicit local import paths may be a separate trusted interface; accepting a caller-selected root is not itself an authorization defect. The platform keeps server paths out of public configuration, generates owned IDs and derives resource scopes. Reject traversal, drive/UNC forms and symlink escapes where a contained artifact name is required.

Acceptance: Windows and Linux path tests, including symlinks, traversal, absolute filenames, cache overrides, collisions, imports and deletion. Prove rejected input cannot read, overwrite, or remove outside data.

### A04 — P0: Crawl and query work lack enforceable global resource limits

Evidence: Atlas defaults have no global page cap; full-site mode removes the depth boundary. HTTP fetches buffer responses before checking optional content length. Async rate limiting uses shared timestamps without a concurrency-safe reservation. Query deadlines do not bound all subsequent provider calls and final generation.

Fix: Core enforces one operation budget covering wall time, pages, redirect hops, fetched/decompressed bytes, tokens, model calls and graph fan-out. Stream responses and stop at real byte limits independent of `Content-Length`. Add per-host concurrency/rate control, cancellation, and bounded provider retries/timeouts. Reuse HTTP clients. The platform assigns limits, enforces tenant rate limits and owns monetary reservations/reconciliation.

Acceptance: infinite pagination, absent/false length headers, oversized compressed content, slow servers, concurrent fetch bursts, repeated 429s, and generation after deadline all terminate within declared limits; reserved usage is reconciled.

### A05 — P0: Deployment can lose data or include client data in an image

Evidence: [`docker-compose.yml`](../docker-compose.yml) mounts `/app/websites_storage`; the UI uses package-relative `/app/webly/websites_storage`. [`Dockerfile`](../Dockerfile) uses `COPY . .`; [`.dockerignore`](../.dockerignore) excludes root `websites_storage/**`, not the nested storage directory used by the UI. This is a static build-context finding; no Docker image was built during the audit. Docker recursively includes context files unless excluded; see [Docker build-context documentation](https://docs.docker.com/build/concepts/context/).

Fix: one explicit storage-root setting shared by UI, API, worker and Compose; mount that path. Copy only required application artifacts. Exclude storage at every depth, local notes, caches, credentials and build output. Use a non-root process, supported patched base image, health/readiness probes, resource limits and documented backup/restore.

Acceptance: create data, replace the container and verify persistence; inspect image layers/context for sentinel client data and secrets; restore a backup into an empty deployment and query its index.

### A06 — P0: Pinned dependencies have published advisories

Evidence: the dated [JSON](audit/2026-11-12-evidence.json) includes public metadata URLs, advisory IDs, aliases and advertised fixed versions. Affected direct pins include Streamlit, python-dotenv, requests, lxml, lxml_html_clean, sentence-transformers, torch and transformers. Example metadata sources: [Streamlit 1.45.1](https://pypi.org/pypi/streamlit/1.45.1/json), [requests 2.31.0](https://pypi.org/pypi/requests/2.31.0/json). Presence in metadata does not prove that Webly exposes the vulnerable code path.

Fix: generate resolved locks for core/API/UI and optional local-model dependencies; deduplicate and triage advisories, update to compatible supported fixes, and scan the full resolved graph and container. Remove unnecessary ML/audio/vision packages from the normal API image. Record justified exceptions with owners and expiry dates. Keep `pyproject.toml`, installation instructions and deployment locks consistent.

Acceptance: clean-environment tests on the locked graph; no unreviewed applicable high/critical advisories; SBOM, dependency/secret/container scans and update automation in CI. Zero advisories in this narrow check would not establish overall security.

### A07 — P1: Crawl deduplication can hide discoverable pages

Evidence: actual Atlas [`atlas.py`](../webcreeper/webcreeper/agents/atlas/atlas.py) hashes visible text and returns on duplicates before extracting links. Two pages with identical labels but different `href` targets triggered the duplicate path in the probe. This can prevent discovery even though ingestion dedup is now correct for its own purpose.

Fix: separate URL discovery, page storage and evidence deduplication. Discover links from every fetched page, then avoid redundant indexing while preserving aliases/provenance. Do not globally remove pagination/query parameters; those can change real content.

Acceptance: same text/different links still discovers both targets; identical content avoids embedding duplication; changed query-string content and translations remain distinct.

### A08 — P1: Partial crawls can become apparently successful indexes

Evidence: [`ingest_pipeline.py`](../webly/pipeline/ingest_pipeline.py) checks `.crawl_incomplete` during crawl orchestration, but `index_only` can consume an existing partial results file without checking it. Crawl output is mutable, and no publication policy reconciles discovered/fetched/failed pages against the previous accepted corpus. The new index snapshot atomicity protects index files, not source completeness.

Fix: immutable crawl runs with completion manifests, explicit cancellation/failure state, source checksums, coverage statistics and a publish decision. Reject incomplete runs by default; allow a clearly labeled reviewed partial import. Define deletion/freshness rules so outages do not remove most of a client's knowledge base.

Acceptance: killed/failed crawler and partial output never silently replace a good corpus; suspicious page-count drops require review; last accepted sources and index remain queryable.

### A09 — P1: Chunking drops short facts and damages structured content

Evidence: [`text_chunkers.py`](../webly/processors/text_chunkers.py) filters some blocks to more than three words. A page containing `Deadline: June 1` and a longer introduction loses the deadline in the probe. Aggressive element removal and whitespace flattening can discard relevant sidebars/forms or table/code structure. Word windows are not semantic boundaries.

Fix: a block-based intermediate representation for headings, paragraphs, lists, tables and code, carrying URLs and document offsets. Preserve short factual blocks, attach them to nearby headings, split by tokenizer-aware limits, repeat table headers, and use extraction confidence rather than universal boilerplate deletion. Add duplicate/template handling after provenance preservation.

Acceptance: dates/prices/yes-no facts, sparse pages, nested lists, tables, code, RTL Arabic, mixed language, long unbroken text and malformed HTML retain answerable evidence. Golden fixtures must cover unrelated sites and layouts.

### A10 — P1: Citation validation can attach evidence to the wrong displayed block

Evidence: [`WeblyChatAgent.answer_grounded`](../webly/chatbot/webly_chat_agent.py) checks the supporting span against combined displayed context and the cited record's original text. The probe cited ID `a`, whose displayed block lacked the span, while ID `b` displayed it; validation still returned `answered`. Literal span presence also does not prove the answer's claims follow from that span.

Fix: pass structured visible evidence to generation/validation, bind each ID to its exact presented text and source version, and validate citations against that block. Apply the same contract in builder and classic. Add claim coverage/entailment checks where useful, with bounded repair and explicit unsupported/partial results; deterministic ID/span checks remain mandatory.

Acceptance: wrong-ID, hidden-text, invented-span and mixed-source answers fail; answers with valid quotes but unsupported conclusions are caught by evaluation; cited URLs/version resolve to retained evidence.

### A11 — P1: Budget logic rejects useful multilingual retrieval

Evidence: the actual Arabic EUI question returned `unsupported` with `prompt_budget`. Planner, context and generation use different estimates; byte-based conservative preflight can reject a prompt that character-based packing considered acceptable. Repairs and final calls need consistent accounting. Answerability previews take only the first 6,000 characters, which can miss later evidence.

Fix: a shared model-capability/tokenization service and total request ledger. Reserve generation and repair budget up front; shrink/repack relevant evidence before refusing, use cheaper deterministic retrieval when planning is too expensive, and assess selected evidence rather than a fixed prefix. Use real tokenizer limits for HF models instead of a universal 8,192-token assumption.

Acceptance: Arabic/English equivalent questions, long history, long sources, small contexts, unsupported models and repair attempts remain within budget and degrade usefully. Measure quality and total cost for builder versus classic on the same corpus.

### A12 — P1: Mutable project/chat files are not safe transactional storage

Evidence: [`project_repository.py`](../webly/storage/project_repository.py) and [`chat_repository.py`](../webly/storage/chat_repository.py) write JSON directly; create uses check-then-write; concurrent edits have no revision check. Malformed chat JSON can become an empty default. Deletion suppresses filesystem errors and is not coordinated with jobs/readers. These are code-reviewed failure modes, not a destructive production reproduction.

Fix: Core artifact/config persistence needs atomic replace, explicit corruption errors, per-resource locks and revision checks, with declared supported concurrency. Coordinate artifact deletion with active readers/writers and report failures honestly. The platform chooses transactional storage for users, chats, ownership and job metadata; PostgreSQL is not a prerequisite for a reusable Core library. Existing chat persistence is an adapter concern.

Acceptance: concurrent create/update, killed writes, corrupt files, disk-full, delete-during-query and delete-during-ingest cannot silently overwrite data or report false success; migrations and restores are exercised.

### A13 — P1: Jobs and runtime loading do not fit a hosted workload

Evidence: [`routes/jobs.py`](../webly/service/routes/jobs.py) runs ingestion synchronously; [`runtime_service.py`](../webly/service/services/runtime_service.py) builds project runtimes per request. Snapshot validation and runtime loading can load the same FAISS artifact twice, then rebuild in-memory retrieval state. There is no durable job lease/cancellation or bounded service cache.

Fix: Core exposes operations that an external worker can run, with progress, cancellation, safe retry/publication semantics and bounded caches keyed by resource scope/snapshot/provider configuration. Pin in-flight snapshots and evict safely. The platform implements durable jobs, leases, scheduling and worker deployment. Keep FAISS until measured requirements justify a different store. Earlier [architecture decisions](implementation/ARCHITECTURE_DECISIONS.md) are historical proposals and must be interpreted through the current core/platform boundary.

Acceptance: process restart recovers jobs without duplicate publication/charges; repeated queries reuse a loaded snapshot; refresh/delete cannot invalidate an active reader; memory stays bounded at declared client sizes.

### A14 — P1: Usage tracking is not a billing ledger

Evidence: [`cost_tracker.py`](../webly/observability/cost_tracker.py) clears events before durable file append. A forced write failure left zero buffered tokens in the probe. Locks are per tracker instance; separate request runtimes do not share a durable transaction. No billable idempotency, allowance reservation or reconciliation exists.

Fix: Core emits request/provider usage events with operation/call IDs, model, measured or estimated tokens and retry/outcome information; failed sink writes must not silently discard events. The platform persists a durable billing ledger and owns monetary reservations, pricing, idempotent reconciliation and retention. Core telemetry must not be presented as a completed billing implementation.

Core acceptance: sink failure, retries and cancellation are observable and attributed correctly; failed writes retain pending events or return an explicit failure under a documented policy. Platform acceptance: retries, duplicate webhooks and crashes do not double charge usage; allowances and invoices reconcile.

### A15 — P1: Credential changes can leave a stale runtime

Evidence: [`ui/sidebar.py`](../webly/ui/sidebar.py) Connect/Forget changes session key state while [`ui/project.py`](../webly/ui/project.py) can retain already-built clients. Runtime reuse does not reliably compare credential identity. This is a plausible source of restart-dependent behavior; it does not prove the earlier billing incident's exact cause. Provider retries also need to distinguish transient rate limits from exhausted quota/auth failures.

Fix: central provider-client factory with explicit configuration generation and credential identity; invalidate dependent runtimes on key/provider/model changes and Forget. Clarify server-key fallback in a hosted policy. Add typed provider errors, deadlines, capped jittered retries and circuit breaking. Keep secrets out of traces, configs and client-visible error bodies.

Acceptance: replace A with B and forget B without restarting; subsequent requests use only the intended identity/policy. Auth/quota errors fail promptly with actionable redacted diagnostics; transient errors respect the request budget.

### A16 — P1: Wheel and CI smoke tests do not prove a standalone installation

Evidence: the built wheel contains `webly/webcreeper/` but lacks the top-level `webcreeper` package imported by [`_webcreeper.py`](../webly/_webcreeper.py); no crawler dependency is declared. Importing the extracted wheel in an isolated subprocess outside the checkout failed with the missing-sibling-crawler ImportError. The repository checkout supplies the sibling submodule and can hide this gap. CI installs `requirements-dev.txt` without explicitly installing the API extra; optional service tests may skip. Its wheel smoke test stays in the checkout and uses `--no-deps`; Windows is absent.

Fix: pick one supported crawler distribution/import location, declare/package it correctly, remove the unused duplicate, and test the wheel in an empty working directory with its declared dependencies. Lock and test API/UI/core extras explicitly; require service tests rather than silently skipping. Add Windows snapshot/path coverage and a real container smoke/restore test.

Acceptance: a fresh supported machine installs the released artifact and runs crawl/index/query/API without the source checkout or undeclared packages; all required suites report executed counts.

### A17 — P1: Embedding cache lacks a clear concurrency/isolation contract

Evidence: [`embedding_cache.py`](../webly/embedder/embedding_cache.py) should be reviewed alongside provider wrappers: a shared SQLite connection with cross-thread use enabled does not itself serialize access; cache identity uses text/model without a full provider/model-revision/dimension namespace. Configuration permits arbitrary cache roots. Concurrency and cross-client correctness are not established by the current tests.

Fix: connection-per-thread or serialized cache access, tenant-scoped roots, versioned keys including provider/model revision/dimensions/normalization, and bounded eviction/deletion. Separate shared public-data optimization from private-client caches through an explicit policy.

Acceptance: concurrent cache writers, model changes, dimension changes and tenant deletion do not corrupt, reuse incompatible vectors or reveal client data.

### A18 — P1/P2: Operational and evaluation coverage is incomplete

Evidence: `/healthz` is process liveness, not storage/provider/worker readiness. Existing tests and evaluation fixtures are valuable but do not demonstrate multilingual answer quality, tenant isolation, sustained concurrency, restore objectives or cost per successful answer. `ROADMAP.md` and older implementation status documents contain stale next/done labels.

Fix: structured request/job IDs and redacted traces; stage timings, queue age, coverage, token/cost and unsupported-answer metrics; alerts and incident runbooks; readiness probes that do not require a paid provider call. Maintain versioned retrieval evaluations and release evidence. Reconcile stale documentation with this audit rather than interpreting old task labels as implemented security.

Acceptance: staging detects broken storage, stuck jobs, provider failures and suspicious cost/coverage changes; a restore drill and load test meet declared targets; a release records corpus/model/prompt/index versions and evaluation results.

## General solutions versus special-case behavior

| Existing behavior | Assessment | General replacement |
| --- | --- | --- |
| Empty-page skip and structural page fingerprint | General policy; no production EUI/login URL exception found in the reviewed source | Keep reporting and strict handling of malformed/provider failures; extend with run-level coverage gates |
| Windows-only directory fsync behavior and sharing-error retry | Appropriate OS capability handling, bounded and tested | Keep explicit platform contract and Windows CI; do not swallow arbitrary I/O failures |
| URL length greater than 200 / any query parameter named `state` skipped by default | Heuristics can discard valid content; neither proves a page is a login/session loop | Make optional documented policies; prefer observed loop detection, crawl budgets and site-specific configuration |
| More-than-three-word text filter | Unsupported universal assumption; reproduced fact loss | Preserve typed factual blocks and use extraction confidence |
| Text-only crawler hash before link extraction | Conflates content redundancy with discovery equivalence | Discover links first, deduplicate evidence separately |
| Fixed context prefix and inconsistent token estimates | Treats long and multilingual evidence unevenly | Shared capability-aware accounting and evidence packing |
| Minimum 40 results despite a lower configured maximum | Configuration does not mean what its name promises | Validate explicit limits and honor them; tune defaults with evaluation |
| Stored anchor/section boost knobs unused by current fusion | Misleading configuration and maintenance risk | Remove/deprecate or implement measured weighting with regressions |
| Reciprocal-rank fusion grouped by origin/channel rather than distinct query | May lose intended independent-query evidence | Define fusion identity explicitly and benchmark alternatives |
| Fixed model capability fallbacks | Unknown models can receive incorrect dimensions/context assumptions | Explicit provider capability configuration; fail clearly on incompatible indexes |

Domain-specific extraction should be an optional adapter with an explicit contract and tests. Core behavior must not accumulate conditions for individual client URLs, university faculties or question wording. Near-duplicate merging should remain conservative: similar pages can differ in the one price/date a customer needs.

## Product capability boundaries

Current crawl/extraction is principally public HTML. “Any website” is not a supportable promise: JS-rendered pages, PDFs, scanned files, authenticated sources, paywalls and anti-bot systems need separate ingestion capabilities and access policies. Do not bypass third-party access controls. Add content types only when their fetch safety, extraction, provenance and evaluation meet the same contracts.

Retrieved pages are untrusted model input. Prompts alone do not provide a security boundary against instructions embedded in source content. Separate instructions from evidence, constrain any tools, avoid exposing credentials to model context, and test poisoned/encoded/multilingual pages. No successful prompt-injection exploit is claimed by this audit. See [OWASP prompt-injection guidance](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).

Before commercial rollout, also establish retention/deletion/export, customer content rights, provider data handling, incident response, license/SBOM notices and contractual support limits. Root Apache-2.0 and crawler MIT notices are present; this observation is not a complete dependency-license or legal review.

## Limits and follow-up

No shared SaaS was deployed, no client messages were sent, and no GitHub push was performed for this audit. No destructive probes ran against customer storage. The live provider smoke checks belong to the earlier ingestion verification, not the temporary audit probes. Container runtime, DNS rebinding against a live test network, sustained load, full transitive scanning and external penetration testing remain release work. Resolve blockers through the roadmap and record evidence before changing this readiness decision.
