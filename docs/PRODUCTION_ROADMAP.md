# Webly Core production roadmap

Updated: 2026-11-12 following the product boundary clarification. This repository is **Webly Core**, the reusable website ingestion and retrieval engine. A separate **Webly Chatbot Platform** will consume Core and own authentication, multi-tenancy, dashboards, configuration screens, subscriptions and billing.

This roadmap supersedes the earlier combined core/SaaS launch plan. See the [boundary and integration contract](CORE_PLATFORM_BOUNDARY.md) and [audit with ownership mapping](PRODUCTION_READINESS_AUDIT.md). Work below is proposed unless explicitly marked completed. No production-readiness claim is made by documenting it.

## Current baseline

Implemented locally: empty-content reporting/skips, pre-embedding exact page deduplication with source aliases, Windows snapshot fixes and runtime reload after ingest failure. A real EUI rebuild succeeded. The subsequent foundation batch repaired independent packaging, removed the duplicate crawler and path workaround, preserved URL authorities in the crawler adapter, and added isolated package verification plus Windows/Linux CI.

Validation: **203 repository tests passed**, Ruff passed, and clean Windows/Python 3.12 wheel verification completed the real fixture crawl/index/reopen/query with optional dependencies absent. API/UI installation and **16 service tests passed without skips** against the installed wheel. Review added fault coverage so failed report publication/cleanup cannot mask an ingest error or fail successful indexing. See [verification evidence](audit/2026-11-12-core-package-verification.json) and [integration instructions](CORE_INTEGRATION.md). The new CI matrix has not been run on GitHub. Short-fact, citation, Arabic budgeting and other safety/reliability findings remain open.

## Phase 1 — Make Core independently installable and usable

Audit: A05, A06, A16; interface aspects of A18.

Status: the agreed first packaging/integration batch is complete locally. This broader phase remains open for explicit environment/resource policies, dependency locking/advisory triage, typed errors and full deployment storage fixes. Package verification alone does not satisfy all production gates below.

- Repair crawler distribution/import ownership and remove the unused duplicate implementation after compatibility review.
- Define the supported Python API and typed configuration/results/errors. Keep UI/service adapters optional; Core must run without Streamlit, FastAPI, a SaaS database or user accounts.
- Eliminate implicit production storage roots and ambient runtime credentials from the Core entry point. Use explicitly supplied resources/provider configuration; adapters may resolve environment defaults.
- Unify dependency definitions, lock supported installation profiles and triage published advisories. Keep local-model dependencies optional.
- Test the built wheel outside the source checkout with declared dependencies. Add Windows and Linux release checks; distinguish executed suites from optional skips.
- Fix storage-root/image issues for retained demo adapters and exclude source/client artifacts from distributions. Document adapter deployment separately from Core installation.

Exit: a clean environment installs Core and crawls/indexes/queries a synthetic site without the repository checkout, UI, web server or undeclared packages. Configuration and error contracts have compatibility tests. Applicable dependency risks are reviewed and resolved.

## Phase 2 — Make Core operations safe and bounded

Audit: A02–A04, A15, A17.

- Introduce one fetch policy covering page/robots/sitemap requests, redirects and address resolution. Default to public HTTP(S); any private-network capability must be an explicit trusted-host policy, never a client URL bypass. Test DNS/redirect behavior and document host egress requirements.
- Stream responses with actual/decompressed byte limits; bound pages, time, redirects, host concurrency and crawl loops.
- Enforce a shared request budget for tokens, calls, fan-out, deadlines, retries and cancellation. The platform chooses allowances; Core enforces the supplied operation limits.
- Contain generated artifact names within the caller-supplied root, with Windows/Linux traversal and symlink tests. Separate explicit trusted imports from contained artifact lookup.
- Make provider clients explicit, invalidate runtimes on provider configuration changes and classify auth/quota/transient errors. Keep secrets out of diagnostics.
- Establish cache identity and concurrency contracts: resource scope, provider/model revision/dimensions and preprocessing version. Prevent accidental state mixing between independent Core instances.

Exit: hostile URLs/content, infinite pagination, oversized responses and failing providers terminate within declared limits. Concurrent operations in distinct scopes cannot mix evidence, artifacts, cache results or credentials. This is resource correctness, not tenant authorization.

## Phase 3 — Preserve evidence from crawl through answer

Audit: A07–A11 and configuration/fusion observations.

- Discover links before suppressing duplicate evidence; preserve aliases without losing differing link targets. Do not globally strip meaningful query parameters.
- Add immutable crawl manifests and explicit completion/coverage status. Reject incomplete input by default; retain the last accepted corpus on failed refreshes.
- Preserve short factual blocks, lists, tables and code through structural extraction. Use tokenizer-aware segmentation with source offsets and headings. Avoid individual-site URL/question exceptions.
- Bind citations to the exact evidence ID/text/version displayed to generation in both builder and classic. Reject hidden-text, wrong-ID and invented-span citations.
- Unify model capability/token accounting and reserve final-answer/repair budget. Repack evidence before refusing; remove fixed-prefix answerability assumptions.
- Honor configured limits and remove or implement dead ranking knobs. Define fusion identity explicitly and verify any change against retrieval evaluations.

Builder improvement: start with hybrid retrieval, answer directly when evidence is sufficient, plan only for missing facets, stop on low information gain, and retain enough budget for final generation. Compare with classic using the same corpus and total call/token limits.

Exit: regressions reproduce and fix short-fact loss, link-discovery loss, citation misbinding and inconsistent Arabic budget rejection. Coverage and claim support are measured, not inferred from a successful response status.

## Phase 4 — Make Core reliable under failures and concurrency

Audit: Core portions of A08, A12–A15, A17–A18.

- Atomic/versioned artifact and config writes, explicit corruption errors and supported reader/writer concurrency. Prevent conflicting publishers and coordinate deletion with active operations.
- Snapshot pinning, rollback and bounded runtime reuse keyed by resource scope/version/provider configuration. Avoid duplicate FAISS loads and define cleanup/close behavior.
- Progress events, cancellation checks and operation IDs so any host worker can execute Core. Define which failures are retryable and when publication has committed.
- Structured usage events and a pluggable sink. Preserve pending telemetry on sink failure or return an explicit documented failure; mark estimates separately from provider measurements. Do not add prices, invoices or subscriptions.
- Redacted diagnostics with stage timing, source coverage, budget consumption, stop reasons and version metadata. Keep telemetry content minimal by default.
- Document backup/restore/export of Core artifacts and supported filesystem/storage assumptions. Test process death, disk-full, corruption and interrupted publication.

Exit: failures cannot silently replace a good snapshot, corrupt another operation or lose reported work. Repeated calls reuse bounded resources; cancellation and retries have documented semantics; artifact restore yields equivalent query behavior.

## Phase 5 — Demonstrate Core production readiness

Create a versioned release evidence bundle containing the exact wheel/lock/source versions, fixture corpus, evaluation configuration, test counts, quality metrics, performance envelope and known limitations.

| Test layer | Required evidence |
| --- | --- |
| Clean installation | Wheel works outside checkout with Core-only dependencies; optional adapters tested separately |
| Deterministic regressions | Discovery, short facts, structured content, aliases, budgets, citations, provider errors and snapshot state covered with meaningful fixtures |
| Fetch/path safety | Controlled tests for redirects, DNS/address variants, byte limits, traversal and symlinks; no live private-network probes |
| Resource separation | Two resource scopes with overlapping IDs/URLs and different provider configurations never mix state, including concurrent access |
| Fault injection | Provider outage, malformed data, cancelled crawl, process crash, disk-full, failed telemetry sink and competing publication |
| Retrieval quality | Human-reviewed questions across at least five unrelated HTML sites, Arabic/English, missing facts, lists, follow-ups, contradictions and adversarial content |
| Performance | Cold/warm load, concurrent queries, refresh during reads, memory growth and total provider cost under a declared corpus/workload |
| Recovery | Restore retained artifacts, reopen the index and validate provenance and answers; document any unsupported crash durability |
| Compatibility | Versioned API/config/artifact formats, migration/rebuild rules and invalid model/index mismatch tests |

Proposed quality targets, pending corpus/workload agreement: at least 100 reviewed questions with a held-out subset; at least 95% supported-claim precision on answered cases and 95% correct abstention on curated unanswerable cases. Require 100% deterministic visible-ID/span/source-version validation. Report coverage and false abstentions so refusing every query cannot pass. Report Arabic and English separately, with sample counts and uncertainty.

Do not declare universal latency/capacity from an arbitrary threshold. Benchmark the actual configured model and hardware; publish tested site size, concurrency, p50/p95 latency, peak memory, token/call usage and cost per successful answer. Security regression success is necessary but does not certify absence of vulnerabilities.

Exit: all Core gates pass on the released artifact, with reproducible evidence and an explicit supported workload. This enables platform integration; it does not certify the SaaS's access control, billing or deployment.

## Later Core capabilities

Add PDFs, JS rendering, OCR, authenticated connectors, alternate providers and rerankers only as evaluated adapters with the same safety/provenance/budget contracts. Near-duplicate and incremental indexing must preserve differing factual values and deletion semantics. Replace FAISS only for a measured storage/scaling requirement.

## Separate Webly Chatbot Platform backlog

The platform owns:

- Authentication, user/organization management, roles, multi-tenant authorization and secret ownership.
- Dashboard and configuration panel for chatbot identity, sources, models, permitted behavior, refresh settings and usage.
- Chat widget, branding, conversation storage, feedback, human handoff and source presentation.
- Durable job queue, workers, schedules, tenant fairness, rate limits and retries based on Core's operation contracts.
- Subscription plans, price tables, allowances, monetary reservations, durable billing ledger and invoice reconciliation using Core usage events.
- Tenant data lifecycle, domain authorization, deployment egress restrictions, backups, service monitoring, SLOs and support.

The platform must authorize a request before selecting a Core resource scope. Core must enforce that scope and operation budgets without depending on the platform's identity schema. Platform end-to-end tests must prove that caller identity cannot select another client's resources; Core tests prove that correctly selected resources remain separate.

## Next implementation order

Start with **independent packaging and explicit Core contracts**, then **fetch/path/resource safety**, then **short facts, citation binding and shared token budgeting**, then **fault/concurrency behavior and release evaluation**. Keep the dashboard/auth/tenant/billing work in the platform backlog. Implement a minimal adapter change only when needed to preserve compatibility or verify the Core contract.
