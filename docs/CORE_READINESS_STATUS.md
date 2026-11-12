# Webly Core: current state and SaaS entry gate

> Historical baseline assessment. The Core 0.2 hardening implementation is now
> documented in [the implementation report](CORE_V2_IMPLEMENTATION.md). The gaps
> below describe the pushed pre-hardening commit; the old probe command now runs
> executable regression tests rather than recreating those obsolete defects.

Assessment: 2026-11-12, against pushed commit `2b7e890de153595aaf4779c3360c0cc12c70626f`. This is a current-state assessment after the packaging/ingestion work, not a repetition of the earlier pre-fix audit. New probes and this document are local analysis artifacts; no production implementation changes are included in this assessment.

## Decision

**We have an independently installable, functioning HTML retrieval engine with a tested foundation. We do not yet have a production-ready engine for untrusted client websites or a measured answer-quality guarantee.**

The next work is a bounded Core hardening release, followed by a release evaluation. The SaaS can be designed against the existing integration surface now, but its production ingestion/query workers should depend on that hardened release. Building dashboards first would leave the platform handling engine-specific exceptions, limits and failure recovery that belong in Core.

Authentication, tenant membership, subscriptions, billing and the dashboard are deliberately absent from the Core completion gate. Resource separation, explicit provider configuration, safe fetching, bounded execution and reliable operation outcomes remain Core obligations.

## Evidence and confidence

- **203 repository tests pass**, including two additional report I/O fault cases added during review. Ruff passes. The clean installed-package verification performs real fixture crawling, extraction, FAISS publication, reopening and a cited query, with deterministic providers and optional dependencies absent.
- Optional API/UI installation works; **16 service tests pass without skips against the installed wheel**. These test results establish integration behavior, not real-model accuracy.
- **All eight GitHub CI jobs passed**: unit/integration and installed-package checks on Windows/Linux, each using Python 3.11 and 3.12. [Completed CI run](https://github.com/Y-Elsayed/Webly/actions/runs/43306809716).
- The earlier real EUI rebuild processed 1,082 records into 770 canonical pages and 1,411 indexed segments; 311 duplicates and one empty-content page were handled. This validates one substantial ingestion case. The English smoke answer was not a completeness benchmark; the Arabic smoke query failed the prompt budget.
- [Fresh gap probes](audit/2026-11-12-core-gap-probes.json) reconfirm outstanding defects on the pushed code and add two newly reproduced failure cases. Run `python -m scripts.check_core_gaps` to reproduce with temporary data and fake providers. It makes no crawler/provider network requests.
- [Package verification evidence](audit/2026-11-12-core-package-verification.json) records the actual wheel hashes and resolved dependencies. Dependencies were resolved for that run; they are not a production lock or a full vulnerability scan.

There is no measured production capacity, supported-claim accuracy, cost-per-success baseline or tested recovery SLA yet. Passing scripted tests cannot supply those missing measurements.

## What we have

| Component | Implemented capability | Current practical limit |
| --- | --- | --- |
| Python integration | `ProjectConfig`, `build_runtime`, `ProjectRuntime`, structured `QueryResult`, compatibility `build_pipelines` | Configuration is typed, but operation results/errors/lifecycle are not yet a complete host contract |
| Distribution | Separate pinned WebCreeper dependency, Core wheel, optional UI/API/HF extras, clean install verification | Publish/release provenance and dependency locks still need a defined supported release process |
| Crawler | Domain/path/regex controls, robots support, seeds, async traversal internally, link graph, persisted HTML | Not a safe fetch boundary; no global page/byte/time contract; discovery can be cut off by text deduplication |
| Extraction/chunking | HTML structure and headings, nested-text handling, word windows, embedding-safe segmentation | Short facts can disappear; tables/code/layout and underlying model token limits are not generally preserved |
| Ingestion | Crawl-only/index-only/both, exact cleaned-page dedup before embeddings, source aliases, skip/failure reports | No accepted immutable crawl-run/coverage contract; incomplete index-only input can publish |
| Evidence metadata | Page/chunk/segment identity, original text, embedding text, headings, URLs, timestamps and graph links | No complete typed document/block/offset model or source freshness/deletion policy |
| Vector/lexical retrieval | Normalized FAISS similarity, BM25 with Arabic-aware normalization, reciprocal-rank fusion | Ranking knobs and limits have inconsistencies; performance envelope is unmeasured |
| Classic mode | Initial hybrid search, automatic graph/section expansion, rewrite passes, answerability and fallback | Expansion can issue many embedding searches; no shared request-wide budget/deadline |
| Builder mode | Request routing, requirements, visible-evidence assessment, focused follow-ups, duplicate-query avoidance, four-search cap and stop traces | Some budget/deadline controls are partial; no evidence yet that it outperforms classic on real clients |
| Answering | Answered/partial/unsupported states, exact quote checks, source links, bounded repair, unverified memory transformations | Final citation checks do not fully bind the quote to the shown block; literal quotes do not establish claim support |
| Index storage | Immutable version directories, checksums, embedding-space validation, atomic active pointer, publication lock/CAS, rollback | Local-filesystem contract only; post-commit failures are ambiguous; retention/GC and restore procedures incomplete |
| Runtime | Lazy snapshot loading, request-version consistency, per-runtime locking, reload after failed ingestion | Explicit resource lifecycle, provider identity, cache concurrency and bounded runtime reuse need work |
| Observability | Ingest reports, retrieval/coverage/stop traces, token usage recording | Not a durable event/sink contract; usage can be lost, errors masked, and runtime repr exposes the key |
| Reference adapters | Streamlit UI plus synchronous FastAPI projects/chats/query/ingest/status | Development surfaces, not the future authenticated multi-tenant SaaS |

### How the engine works today

The host builds a configured runtime. Crawling writes HTML records and a graph. Ingestion extracts structural chunks, skips valid pages without evidence, deduplicates whole cleaned pages, segments text for embeddings, and publishes a checked FAISS snapshot with source metadata. A query loads the active compatible snapshot, retrieves semantic/lexical hits, assembles evidence, and runs either classic expansion or builder-directed searches before generating a validated structured response.

Important details:

- Dedup is **exact page evidence dedup**, not near-duplicate detection or independent chunk dedup. A first matching page becomes canonical; aliases are retained. It does not guarantee crawl completeness or merge all graph information.
- Optional summarization changes embedding text while retaining original evidence. A failed summary can fall back to original text. It is not the only answer source.
- Builder already uses evidence assessment and follow-up planning. We need to correct and evaluate it, not replace it with another speculative agent layer.
- Old snapshots remain available and rollback is implemented. A query can use a consistent loaded version while a different writer publishes. That is useful existing behavior; future deletion/GC must preserve it.
- Same-runtime locking serializes queries and ingestion. Independent host workers/runtimes can be used, but a measured concurrency/lifecycle contract is still needed.

## Current gaps, ordered by release consequence

### G01 — Safe, bounded fetching and resource access

**Current:** the fresh policy probe accepts a loopback target; no request was sent. Automatic redirects and DNS resolution do not establish public-address safety. Responses are buffered before optional length checks, and crawl-wide caps are absent. A domain allowlist is not an egress security policy. Configurable subordinate file names/cache paths also need containment in hosted use.

**Needed:** one shared fetch contract covering pages, robots, sitemaps and future loaders; destination/address/redirect validation plus documented host egress controls; streaming/decompressed byte limits; global page/time/call/token/fan-out caps; cooperative cancellation and concurrency-safe per-host rate control. Core must constrain subordinate artifacts within a caller-supplied root. The SaaS selects authorized roots and allowances.

**Done when:** controlled private-address/DNS/redirect/path tests pass and infinite pagination, large responses, slow servers and provider retries terminate within declared limits. Implement shared crawler fixes in WebCreeper rather than creating another crawler copy in Core.

### G02 — Complete, accepted source runs

**Current:** two pages with identical visible text but different links are treated as duplicates before link discovery. `index_only` publishes even with `.crawl_incomplete` present. Mutable raw results and a checkpoint do not prove the intended website coverage was captured.

**Needed:** discovery independent of evidence dedup; immutable crawl-run input and completion manifest; fetched/failed/excluded coverage; explicit reviewed partial-import policy; safeguards for suspicious content drops and deletion/freshness semantics. Validate that indexed evidence corresponds to the frozen source version, including changes during transformation.

**Done when:** duplicate-looking pages still reveal different targets, failed/interrupted crawls cannot silently replace a complete corpus, and removed pages disappear only under the defined refresh policy.

### G03 — Evidence-preserving chunking

**Current:** the fresh fixture loses `Deadline: June 1` when a longer paragraph exists. Structural removal and word splitting can lose the one value needed to answer a client question. Table rows, code and sparse factual blocks need better preservation.

**Needed:** retain short factual blocks with heading context, represent paragraphs/lists/tables/code explicitly, preserve provenance/offsets, and split to the actual tokenizer contract. Use fixtures from unrelated sites and languages; avoid URL- or question-specific rules.

**Done when:** dates, prices, names, yes/no values, tables, lists, sparse pages, RTL/mixed-language text and large blocks retain retrievable supporting evidence.

### G04 — Grounded final answers

**Current:** final generation accepts a citation to ID `a` when its quote is visible only in ID `b`, provided the original full record for `a` also contains it. Builder's assessment validator is stricter than this final-answer validator. A valid copied quote also does not prove every factual claim in an answer follows from it.

**Needed:** a shared structured visible-evidence contract for both modes; exact ID/text/source-version binding; bounded repair; explicit partial/missing-answer semantics; human-reviewed claim support evaluation. Treat retrieved instructions as untrusted data and include poisoned-source cases.

**Done when:** wrong-ID, hidden-text, invented-span and unsupported-conclusion cases fail appropriately; complete and partial answers are classified honestly. Do not interpret `supported=True` as a semantic guarantee until this gate is measured.

### G05 — Consistent token, cost and deadline controls

**Current:** planner/final generation use conservative byte estimates while context packing uses other heuristics. The real Arabic smoke failure remains unresolved. `max_total_tokens` does not yet constitute one cumulative request ledger. Builder scheduling checks do not bound all calls; classic expansion lacks a global shared cap. A requested result maximum of 3 becomes 40 in the fresh probe.

**Needed:** common model-capability/token accounting, cumulative call/token/deadline limits, output/repair reservation, adaptive evidence repacking and useful fallback. Honor exposed limits; remove/deprecate unused boosts or implement measured behavior. Validate HF tokenizer/truncation limits rather than inheriting a generic ceiling.

**Done when:** Arabic/English equivalents and long-context requests fit or degrade predictably, both modes stay within the same declared resource envelope, and every advertised limit has a regression.

### G06 — Explicit runtime resources, secrets and cache lifecycle

**Current:** runtime construction loads `.env` and can use ambient keys. `repr(ProjectRuntime)` includes its API key; the fresh probe confirms this using a dummy marker, not a real credential. Cache identity omits parts of the provider/model contract, and enabling cross-thread SQLite access does not itself establish safe cache concurrency. There is no top-level close/context-manager contract.

**Needed:** explicit host-supplied resources/provider identity with environment resolution confined to compatibility adapters; redact repr/errors/events; validate cache namespace and model/dimension/preprocessing identity; safe connections and deterministic close. Define how provider/model changes invalidate clients and indexes.

**Done when:** two independently configured runtimes with overlapping document IDs cannot mix evidence, cache vectors or credentials; repr/logging/rotation/close tests pass. These are engine resource tests, not user/tenant authorization tests.

### G07 — Unambiguous publication and recovery outcomes

**Current:** pre-commit fault and stale-writer protections work. However, injecting a directory-sync failure after active-pointer replacement makes `publish()` raise while the new valid snapshot is already active. This models a POSIX post-replacement failure; native Windows directory syncing is intentionally skipped. A later checkpoint or telemetry failure can also make the outer operation fail after useful work committed.

**Needed:** explicit operation identity and committed-version/outcome information, retry classification, idempotent host retry semantics, and separation of publication from subsequent diagnostics. Define committed, not-committed and uncertain/durability outcomes; do not automatically roll back a potentially newer publication. Test process death and post-commit faults, not only failures before replacement.

**Done when:** a worker can determine whether retry is safe, inspect/reconcile the active version after uncertain outcomes, and retain a valid corpus across the declared fault scenarios. Document backup/restore, retention and supported filesystem assumptions before adding GC.

### G08 — Usable events and honest error reporting

**Current:** a failed usage append leaves zero buffered tokens in the fresh probe. A `finally` flush can replace the original operation error. Usage events are not fully correlated with operations/provider attempts, and diagnostics can contain source/question content. Report-file write/cleanup failure itself was corrected in the pushed changes; that correction does not fix usage persistence.

**Needed:** structured progress/usage/diagnostic events with operation/call IDs, outcome, retries and measured-versus-estimated tokens; a pluggable sink and explicit failure policy. Preserve pending events or return an observable failure without silently erasing them. Keep raw content out by default and retain original errors.

**Done when:** failed/cancelled/retried operations remain observable and correctly attributed. Core supplies usage facts; the SaaS owns durable billing, prices and monetary reconciliation.

### G09 — Measured performance and concurrency

**Current:** a reference API request creates a runtime; loading can validate/load FAISS twice and rebuild lexical state. BM25 scans tokenized documents and recomputes term counts during queries. Per-runtime locks serialize operations. There is no benchmark for client count, corpus size, refresh overlap or memory growth.

**Needed:** eliminate redundant loads, reuse bounded runtime/index/lexical state, define safe concurrency and close/eviction behavior, and benchmark cold/warm queries, concurrent reads and refreshes. Host-level runtime pools may belong in the platform; Core must provide safe reusable objects and lifecycle semantics.

**Done when:** a published workload report states tested index size, concurrency, memory, latency and total provider usage. Optimize measured bottlenecks. FAISS need not be replaced just to start SaaS.

### G10 — Reproducible, evaluated release

**Current:** CI demonstrates compatibility and scripted behavior. Golden retrieval cases use scripted planners/agents; they do not measure real-model recall or grounded accuracy. The legacy dependency profile has advisory evidence; the newly resolved Core profile has not undergone a complete applicable-advisory scan. A resolved package list is not a lock. Index format metadata exists, but the full package/config/model/prompt/extractor compatibility policy remains incomplete.

**Needed:** supported dependency locks/profiles, resolved-graph security/license inventory, unique crawler release provenance, versioned Core API/config/artifact/rebuild rules and release evidence. Evaluate actual builder/classic behavior on a held-out multi-site English/Arabic corpus. Define supported inputs and workload limits.

**Done when:** install, safety, fault, isolation and quality gates pass on the released artifacts; results can be reproduced and the platform can pin that release. Ordinary version equality is insufficient proof of crawler source identity; retain reviewed wheel provenance until a uniquely identified crawler release is available.

## What must happen before SaaS

### Gate A — Core contract is ready for platform integration

Complete G01–G08's minimum behavior contracts: safe bounded execution, accepted source runs, preserved short facts, correct visible-evidence binding, common budgets, explicit resources/secret handling, typed outcomes/retries, and usable events. Keep existing public entry points where practical and add missing contracts incrementally. The platform should not parse arbitrary `RuntimeError` strings to decide whether a charged job should retry.

Required demonstration: a host application with two resource scopes runs independent crawls/queries, applies its own limits, cancels work, rotates provider configuration, receives correlated progress/usage, and safely reconciles a failed or uncertain publication. No SaaS accounts or billing implementation is needed for this demonstration.

### Gate B — Core release is ready for a paid-client workload

Complete G09–G10 and the full fault/quality matrix. Proposed initial evaluation: at least 100 human-reviewed questions across at least five unrelated supported HTML sites, with held-out questions, Arabic/English, multi-part questions, missing facts, contradictory sources and hostile instructions. Report sample counts, errors and uncertainty.

Proposed quality gates remain at least 95% supported-claim precision on answered cases and 95% correct abstention on curated unanswerable cases, with explicit answer coverage/false-abstention results. Require 100% deterministic visible-ID/span/version validation. These are targets, not results. Agree the intended use case before treating them as sufficient.

For performance, publish measured p50/p95 latency, peak memory, query concurrency, corpus size, refresh duration and cost per successful answer for the chosen models/hardware. Do not manufacture a capacity promise from the current test count. Demonstrate artifact backup/restore and rollback under declared durability assumptions.

### Gate C — Separate SaaS is ready to launch

The SaaS consumes the pinned Core release and adds login, organizations/tenant authorization, dashboard/configuration panel, source onboarding, chatbot/widget, conversation persistence, durable jobs/schedules, fair sharing, subscription limits, billing and operational support. Its own integration/security tests prove authenticated users cannot select another client's Core resource scope.

Core readiness does not certify the SaaS, and SaaS identity does not repair unsafe Core fetching or inaccurate retrieval. The platform can be scaffolded after Gate A, while release evaluation finishes; paid traffic waits for both Gate B and platform launch checks.

## Recommended implementation sequence

| Batch | Work | Evidence required before the next batch |
| --- | --- | --- |
| 1. Host-safe execution | G01 plus G06 credential redaction/explicit resources; common operation limits from G05 | No unexpected network/path access; bounded work; separate runtime resources and secret-safe diagnostics |
| 2. Evidence correctness | G02–G04; finish G05 token/repacking behavior | No lost short facts/link targets; no incomplete silent publication or wrong-block citations; useful Arabic/English behavior |
| 3. Reliable operation contract | G06 cache/lifecycle, G07–G08; begin G09 reuse | Cancellation, retries, uncertain commit reconciliation, sink faults and concurrent resource tests pass |
| 4. Release proof | G09–G10 | Full CI plus locked-artifact quality, load, fault, restore and provenance report |
| 5. SaaS delivery | Platform-owned implementation using the pinned Core release | Tenant/security/product/operational acceptance gates pass |

Dependency work and evaluation fixtures should be prepared throughout, rather than leaving discovery of incompatibilities or accuracy failures until batch 4. No reliable calendar or completion percentage follows from the current evidence; scope and estimates should be assigned to these concrete batches.

## What can wait

PDF/office/OCR, browser rendering, authenticated connectors, enterprise SSO, multiregion deployment, new vector databases, cross-encoder reranking and sophisticated near-duplicate/incremental indexing are not prerequisites for the initial public-HTML product. Add them when needed and evaluate them against the same safety/provenance/budget contracts.

Do not describe current support as “any website.” Start with public HTML, explicit supported languages and source/refresh limits. We already have enough architecture and functionality to finish that focused engine; the remaining work is correctness, safety, reliability and measured behavior, not a rewrite.

## Relationship to existing documents

Use this status report for the current assessment; the [production roadmap](PRODUCTION_ROADMAP.md) remains the broader backlog and the [core/platform boundary](CORE_PLATFORM_BOUNDARY.md) owns responsibility decisions. The [earlier audit](PRODUCTION_READINESS_AUDIT.md) preserves historical findings; packaging A16 was fixed. [Core integration](CORE_INTEGRATION.md) documents the current API rather than the future proposed contracts. New findings here, particularly runtime repr and post-commit ambiguity, should become regression-backed implementation tasks before closing their gates.
