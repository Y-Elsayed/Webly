# Webly Core and Webly Chatbot Platform

Status: agreed product direction, proposed integration contracts. Updated 2026-11-12. This document defines ownership; it does not claim the interfaces below already exist.

## Product structure

**Webly Core** is the reusable engine in this repository: crawl/import, extract, chunk, deduplicate, embed, publish/load indexes, retrieve and produce grounded answers with provenance. It is developed and evaluated independently of a particular web application.

**Webly Chatbot Platform** is a separate SaaS that depends on Core. It provides the client dashboard, configuration panel, hosted chat experience, user accounts, organizations, multi-tenancy, billing and operations. The platform can call Core as a Python package from its application/worker processes. A separately deployed Core HTTP service is an option only if operational needs justify it.

| Concern | Core | Chatbot platform |
| --- | --- | --- |
| Website processing | Discovery, extraction, chunking, dedup, embeddings and provenance | Source onboarding, access authorization and refresh preferences |
| Retrieval/answering | Builder/classic execution, budgets, grounded results and citations | Chatbot behavior configuration, chat UI, customer experience |
| Resources | Explicit corpus/storage/cache/provider scope, safe paths and lifecycle | Map authenticated users/tenants to authorized Core resources |
| Safety | Fetch validation, byte/page/time/token caps, cancellation and secret redaction | Safe configuration policy, tenant quotas, external rate limits, network egress controls |
| Identity | No login/users/roles/tenant-membership model | Authentication, authorization, organizations and API keys |
| Persistence | Versioned immutable engine artifacts and storage contracts | Business/chat/job metadata, transactional database and retention policy |
| Background work | Operations, progress, cancellation and safe publication semantics | Queue, durable jobs/leases, schedules, worker orchestration and fairness |
| Usage | Provider/request events, estimates, measured counts and stage timings | Pricing, billing ledger, subscriptions, allowance reservation and reconciliation |
| Quality | Regression/fault/concurrency tests and reproducible retrieval benchmarks | Product acceptance, client-level evaluations and service SLOs |
| UI/API | Optional development/reference adapters | Public endpoints, dashboard, configuration panel and embedded chatbot |

## Proposed integration contracts

1. **Explicit resources.** The host supplies a corpus/storage handle, cache namespace and provider configuration. Core has no ambient current tenant/project or shared credentials. An opaque resource ID is a technical selector, not proof of authorization. The host selects it after authorization.
2. **Validated configuration.** Versioned typed options describe supported sources, chunking, models, retrieval and budgets. Reject incompatible combinations early, especially embedding model/dimension/index mismatches. The platform translates its configuration panel into this schema; Core owns validation semantics.
3. **Operations.** Crawl/import, build/refresh, query, inspect, export and artifact cleanup have explicit inputs, typed results, progress hooks and cancellation/deadline context. Public names/signatures should be chosen after reviewing current entry points; do not add speculative wrappers for every internal class.
4. **Results.** Ingest reports include completion state, coverage, skipped/duplicate counts, source aliases and committed snapshot version. Query results distinguish answered, partial and unsupported outcomes, with evidence IDs, visible spans, URLs/version, usage and stop reasons. Diagnostics must not include secrets or raw customer content by default.
5. **Errors and retries.** Distinguish invalid input, policy rejection, missing/corrupt artifacts, provider auth/quota/transient errors, exhausted budget, cancellation and concurrent publication conflict. State whether a snapshot committed; avoid catch-all retries that repeat expensive or completed work.
6. **Storage and concurrency.** Declare supported backends and writer/reader semantics. Core pins active snapshots, confines subordinate paths, isolates cache keys and closes resources deterministically. The platform coordinates infrastructure and long-running jobs; an in-process lock is not a distributed lease.
7. **Usage and observability.** Accept operation/correlation IDs and event sinks. Report model/provider call identity, retries and measured/estimated tokens accurately, with explicit sink-failure behavior. The platform decides durable persistence and commercial accounting.
8. **Compatibility.** Version the package, configuration and artifact schemas. Publish migration/rebuild rules and test the platform against a pinned Core release. UI dependencies must not be required to import or execute the engine.

## Isolation without SaaS identity inside Core

The platform authenticates a client, authorizes a chatbot/corpus, selects its storage and credentials, assigns limits, then calls Core. Core operates only on those supplied resources. It must never search a global corpus, reuse an incompatible cache or select a provider key from a different running instance.

Core regression tests use independent resource scopes, not fake user accounts, to catch accidental state leakage. The platform separately tests unauthorized access and cross-tenant enumeration. Both are necessary for the final service, but only resource separation belongs to the engine implementation.

## Existing repository surfaces

The existing Streamlit UI and FastAPI routes are development/reference adapters, not the intended SaaS product. Keep them working where practical, but do not grow them into a tenant/account/billing system as part of Core readiness. Their current lack of authentication is documented; do not expose them as public production endpoints. Production use of the engine does not require a web server.

Earlier `docs/implementation/` plans combine hosted-service and engine concerns. Treat them as historical proposals where they conflict with this boundary. The [revised roadmap](PRODUCTION_ROADMAP.md) is the active Core backlog; the [audit](PRODUCTION_READINESS_AUDIT.md) retains factual findings and maps ownership.
