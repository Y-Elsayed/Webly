# R0/R1 requirement audit — 2026-10-17

Source: `Webly_Product_and_Engineering_Specification.md` v1.0. This is an audit of commit `46d616bd0bcc328e1e684f7aed7807023135d806` on `main` (`origin/main`); `webcreeper` is pinned at `8db4429e0a2b964eca634beed249a833e8934bb0`. The specification itself is an untracked user file and was preserved. No `AGENTS.md` exists in this checkout or its parent. All statuses below describe the hosted pilot requirement, even where a local feature already exists. Status vocabulary: **verified**, **partial**, **missing**, **conflicting**, **N/A**, **unverified**. P0 = release blocker, P1 = pilot feature, P2 = deferred. Types: C correctness, I integrity, S security, O operations, P product, A analytics, E evaluation, M maintainability. `Txx` refers to `IMPLEMENTATION_PLAN.md`; the acceptance column names a concrete test or gate.

## Baseline and evidence confidence

`python3 -m pytest -q`: **123 passed, 3 warnings** in 1.46 s. This tests the main `tests/` tree, not real provider quality or hosted deployment. `python3 -m ruff check .`: **18 pre-existing errors** (including import order, unused imports, long lines, and unreachable duplicate `math` references). `python3 -m pytest -q webcreeper/test`: **2 passed, 1 failed** because an external test domain could not resolve; it is an environment-dependent integration test, not a demonstrated crawler regression. The repo `.venv/bin/python` has neither pytest nor Ruff. `python3 -m build` and Twine are unavailable; Docker/CI build was not executed. CI (`.github/workflows/ci.yml`) tests Python 3.11/3.12, lint, builds, wheel smoke; it does not exercise PostgreSQL, browser, live providers, security, or concurrency. Docker runs Streamlit only (`Dockerfile`, `docker-compose.yml`), with no API, worker, DB, object store, migrations or backup deployment.

Real FAISS fixture, no model/network: adding `seg-a` and `seg-b` at the same URL produces `ntotal=2`, `metadata=2`, `_faiss_to_pos=1`; both vector hits resolve to `seg-b` before and after save/load. This confirms FIX-01/RET-01. The same fixture gives Arabic tokens `['2026']` for `رسوم الدراسة 2026`, and the ranker keeps only `seg-a` of two same-URL records. These are local execution, not retrieval-quality evaluation. The remaining findings below are code-path inspection unless explicitly labeled.

Runtime trace: `/v1/projects/{project}/query` → `RuntimeService.query_project` → new `build_runtime` → `ProjectRuntime.query_result` → `FaissDatabase.load` → `QueryPipeline` default builder → `QueryRetriever.search` → `QueryContextTools.assemble_context` → free-text `WeblyChatAgent.answer` → `QueryResult`. Ingest route → synchronous `RuntimeService.run_ingest` → new runtime → `IngestPipeline.run` → `Crawler` → `Atlas` async `BaseAgent.fetch_async` → transform/embed → `FaissDatabase.add/save`. Streamlit uses `StorageManager`/file repositories and the same framework runtime. The API has no auth dependency. This is a local developer application, not a hosted tenant service.

## Product requirements

| ID | Requirement; status | Evidence; exists / remaining; impact | Priority/type; scope; acceptance |
|---|---|---|---|
| PROD-01 | Project purpose, language, source scope, owner: **partial** | `ProjectConfig`, `config_validator.py`, `FileProjectRepository.create` validate local crawl settings; no tenant, owner, purpose, source approval or membership. Unapproved crawl can run. | P0 S/P R1; T04,T06. Authenticated create validates complete policy before job exists. |
| PROD-02 | Preview/approve crawl: **missing** | `Crawler.crawl` saves successes; `get_disallowed_report` is debug only; no review state/UI. Blind ingestion. | P1 P/O R1; T06,T07. UI lists discovered/excluded/failed/approved pages and reasons; approval gates build. |
| PROD-03 | Prepublish question testing: **missing** | `/{project}/query` uses current index; `tests/query_eval_harness.py` scripted only. No draft/version/outcome latency view. | P1 P/E R1; T09,T12. Authorized preview shows evidence, status, latency, version; not billable. |
| PROD-04 | Responsive, accessible, RTL widget: **missing** | `webly/ui` is local Streamlit admin/chat; no embeddable script. | P1 P R1; T11. Browser E2E desktop/mobile, keyboard, errors, Arabic RTL when enabled. |
| PROD-05 | Clickable grounded citations/fallback: **partial** | `QueryResult.sources` lists supplied chunks, `query_context.py:89`; free-text answer has no claim/citation binding. Fallback text exists. Users can mistake a source list for support. | P0 C/P R0+R1; T03,T09,T11. Every factual output citation references supplied original span; unsupported path offers action. |
| PROD-06 | Optional contact form and accepted confirmation: **missing** | No contact route/store/UI. | P1 P/S R1; T11,T13. Consent-bound form, idempotent accepted response, delivery status distinct. |
| PROD-07 | Conversation and feedback review: **partial** | File chat CRUD in `routes/chats.py`; no auth, outcome, feedback, filters/redaction. Sensitive chat is globally addressable. | P0 S, P1 P R1; T04,T13,T15. Role-scoped filter and negative feedback E2E. |
| PROD-08 | Source freshness/jobs view: **missing** | Crawl timestamp in JSONL; `status()` checks file existence, not successful publication or failures. | P1 O/P R1; T07,T15. Admin sees publication time, failures, expiry and pending changes. |
| PROD-09 | Approved correction → test → publish: **missing** | No approved answer, correction or draft workflow. | P1 P/I R1; T08,T12,T15. Editor-linked source correction and regression preview produce new version. |
| PROD-10 | Allowance/reset/state: **missing** | `CostTracker` records provider token use only; no unit ledger or UI. | P0 I, P1 P R1; T10,T15. Concurrent quota test plus visible reset/warnings. |
| PROD-11 | Immediate pause: **missing** | No hosted project state; queries continue while index/key exists. | P0 S/O R1; T10,T11. Pause blocks new spend and returns contact fallback. |

## Retrieval and reported fixes

| ID | Requirement; status | Evidence; exists / remaining; impact | Priority/type; scope; acceptance |
|---|---|---|---|
| RET-01 / FIX-01 | Exact vector/evidence mapping: **conflicting** | `faiss_db.py:77-84,158-183,205-212` chooses URL before segment ID, overwrites map, overwrites returned `id`; real fixture above. Wrong evidence can be cited. Existing indexes need full rebuild. | P0 C/I R0; T01. Same-URL vectors return distinct canonical original text before/after save/rebuild. |
| RET-02 / FIX-02 | Unified hybrid ID: **conflicting** | BM25 copies metadata string `id` (`query_retriever.py:199-207,261`), vector returns int (`faiss_db.py:211`); `combine_and_rerank:129` and builder drop `query_pipeline.py:383-389` use unequal IDs. Duplicate candidates/actions diverge. | P0 C R0; T01,T03. One candidate with both ranks; string segment IDs in drop and trace. |
| RET-03 / FIX-08 | Comparable fusion: **conflicting** | `query_retriever.py:126-162` may discard one channel then blends raw BM25 and cosine; channel evidence lost. | P1 C R0; T03. Deterministic RRF and offline comparison preserve channel ranks. |
| RET-04 / FIX-09 | Complementary same-page evidence: **conflicting** | `query_retriever.py:178-189`; fixture keeps one of two segments. | P1 C R0; T03. Two sections from one URL survive within budget. |
| RET-05 / FIX-11 | Arabic/English lexical support: **conflicting** if Arabic offered | `query_retriever.py:191-192` ASCII regex; fixture Arabic terms omitted. | P1 C R1 conditional Arabic; T03,T12. Mixed Arabic/English lexical benchmark, numerals/transliteration. |
| RET-06 / FIX-15 | Embedding compatibility: **partial** | `faiss_db.py:310-374` checks format only, not model, dimension contract, normalization or preprocessing. | P0 I R0; T02. Same-dimension wrong-model load rejected. |
| RET-07 / FIX-07 | Original evidence: **conflicting** | `ingest_pipeline.py:~260-320` replaces `content_to_embed` with summary, stores segment `text=part`; raw chunk retained only in debug file. Summary can become sole generation evidence. | P0 C R0; T01. Summary retrieval resolves exact original span and provenance. |
| RET-08 | Freshness/conflict: **missing** | Crawl time in JSONL; no effective/expiry, approved facts, conflict/critical filters. Stale fees/deadlines can answer. | P0 C R1 for critical facts; T08,T09. Expired excluded; contradictory approved facts abstain/clarify. |
| RET-09 / FIX-16 | Token accounting: **conflicting** | `query_context.py:37-49` truncates source label, `:74-87` can exceed requested char cap; no full prompt/output budget. | P1 C/O R0; T03. Count system/history/evidence/schema/output reserve under model and product ceilings. |
| RET-10 / FIX-18 | Grounded citations: **partial** | `QueryResult.sources` are context-used references, not answer citations; `WeblyChatAgent.answer` free text. | P0 C R0; T03,T12. Reject invented citation IDs; human review measures claim support. |
| RET-11 / FIX-10 | Planner schema/coverage/actions: **partial** | `context_builder_agent.py:31-45,126-163` loose JSON parsing, literal substring coverage, four unbounded queries; `query_pipeline.py:382-399` drops unvalidated IDs and repeats searches. | P1 C/S R0; T03. Malformed/unknown/duplicate actions fail safely; synonym/negation cases. |
| RET-12 | Bounded calls/deadline/cost: **partial** | `builder_max_rounds` only bounds rounds; no total deadline or model cost ceiling; classic rewrite may spawn many subqueries. | P0 O/S R1; T03,T10. Limits enforced in code under adversarial planner/provider. |
| FIX-03 | Atomic immutable publication: **missing** | `faiss_db.py:303-325` writes index then metadata in place; `IngestPipeline.load:348-366` swallows add errors then saves. Partial publication/corrupt load possible. | P0 I R0; T02. Kill between artifact writes; old snapshot still serves. |
| FIX-04 | Hosted auth/roles: **missing** | `service/dependencies.py` only injects services; all `routes/*` unguarded. | P0 S R1; T04. Every administrative resource denies cross-tenant access. |
| FIX-05 | Crawler network controls: **conflicting** | Actual path `Crawler`→`Atlas.crawl_async`→`BaseAgent.fetch_async`; `should_visit` scheme/domain checks, but `httpx.AsyncClient(follow_redirects=True)` and robots `requests.get(...allow_redirects=True)` have no IP/connect validation or byte streaming cap. DNS/redirect SSRF possible. | P0 S R1; T05. Private/metadata/redirect/rebinding tests plus egress restriction. |
| FIX-06 | Coordinated read/write: **missing** | Request constructs/loads runtime while synchronous ingest writes same directory; no lease or version pin. | P0 I R0; T02. Overlap and crash tests return only one valid version. |
| FIX-12 | Failed segments/publication gate: **conflicting** | `ingest_pipeline.py:303-313,333-359` continues on embed/add errors. Missing evidence silently published. | P0 I R0; T02. Required failure blocks publication and records retry manifest. |
| FIX-13 | Runtime cache: **missing** | `RuntimeService.query_project:39-44` builds per query, loads index each time. | P1 O R1; T02. Version-keyed bounded cache, pin/refcount, publication turnover. |
| FIX-14 | Durable ingest jobs: **missing** | `routes/jobs.py` invokes sync crawl, returns `completed`; no queue/state/cancel/recovery. | P1 O R1; T07. 202 job ID, restart/lease/idempotency tests. |
| FIX-17 | Real retrieval corpus: **missing** | `tests/query_eval_harness.py` uses scripted planner/results; no reviewed real corpus. | P1 E external launch prerequisite; T12. Human-reviewed held-out corpus and measured gates. |
| FIX-19 | Direct graph lookup: **missing** | `query_retriever.py:77-95` only searches anchor+question; does not fetch edge target. | P2 C later; D01. Benchmark benefit before implementing. |
| FIX-20 | Builder capability routing: **conflicting** | `query_pipeline.py:95-96` enters builder, `:265-460` never calls graph/section expansion despite enabled settings. | P1 M/C R0; T03. Mode capabilities exposed; unsupported setting rejected or disabled with notice. Direct graph action deferred. |
| FIX-21 | Lexical per-query scan: **partial** | `query_retriever.py:239-254` rescans all token arrays. Fine for tiny local corpus; pilot scale unmeasured. | P2 O later; D02. Benchmark threshold before changing. |
| FIX-22 | Embedding batch/retry: **partial** | `OpenAIEmbedder` has `embed_batch`, but `ingest_pipeline.py:305` calls `embed` per segment; no bounded retry manifest. | P1 O for reliability, P2 throughput later; T02,D02. Failed batches retry; mapping retained; speed measured before optimization. |
| FIX-23 | Duplicate ranking code: **conflicting** | `query_pipeline.py:488-~580` returns retriever result then contains unreachable duplicate implementation; Ruff `F821` there. | P2 M, but CI hygiene in T00; T00. One ranking implementation and lint green. |

## Additional specification requirements (stable IDs)

Each row captures prose/table requirements not already covered above. Acceptance tests are concise; full procedures are in `VERIFICATION_PLAN.md`.

| ID | Requirement; status | Evidence / impact | Priority/type; scope; acceptance; task |
|---|---|---|---|
| DATA-01 | Tenant/project-owned canonical entities and cross-project FKs: **missing** | File JSON only (`storage/*`), no migrations. Isolation cannot be proven. | P0 S R1; migration/negative FK tests; T04. |
| DATA-02 | Versioned source/page/section/segment/edge provenance: **partial** | `results.jsonl`, `graph.json`, chunk metadata have pieces, no version/offset/owner/content hash contract. | P0 I R0+R1; version/offset roundtrip; T01,T06. |
| DATA-03 | Source artifacts/retention, single authority: **missing** | In-place crawl/result and debug files; no immutable object manifest. | P0 I R0; durable checksum and restore; T02,T14. |
| DATA-04 | Conversation/turn/trace/feedback/contact/review/ledger/event schema: **missing** | File chat CRUD, token cost log only. | P0 S/I and P1 P/A R1; migrations/relationship tests; T04,T10,T13. |
| FLOW-01 | Managed onboarding, domain authority, source approval: **missing** | Config allows start URL/domain but no owner confirmation/approval. | P0 S R1; complete UI/API E2E; T06. |
| FLOW-02 | Crawler limits, errors, deletion semantics, refresh: **partial** | Atlas depth/robots exist; no durable per-page failures or repeated 404 policy. | P0 S/I R1; timeout retains prior approved page; T05,T07. |
| FLOW-03 | Extraction lists/tables/nesting, hard block ceiling: **partial** | `text_chunkers.py:114-240` sibling-only traversal; oversized block can exceed cap. Quantitative impact unmeasured. | P1 C R0; nested/oversized fixtures; T01. |
| FLOW-04 | Atomic publish, rollback, cache invalidation, query pin: **missing** | In-place files and new runtime. | P0 I R0; crash/overlap/rollback; T02. |
| FLOW-05 | Public session, routing, outcome and safe fallback: **missing** | Local query endpoint accepts arbitrary `memory_context`; no session/status. | P0 S, P1 P R1; browser/API E2E; T09,T11. |
| FLOW-06 | Feedback/contact delivery and improvement loop: **missing** | No routes, issue queue or delivery. | P1 P/O R1; submit/retry/resolve and republish E2E; T13,T15. |
| FLOW-07 | Retention, deletion, export, backup recovery: **missing** | File CRUD deletion only; no policy/tombstone/restore. | P0 S/O R1; deletion/restore exercise; T14. |
| PLAN-01 | Allowlisted search/drop/clarify/finish with authority and budgets: **partial** | Builder supports search/drop via untyped JSON, no explicit clarify/finish. | P1 C/S R1; invalid action and bounded tests; T03,T09. |
| PLAN-02 | `fetch_section`/`fetch_neighbors`: **N/A** for default pilot | No direct-ID retrieval; specification makes R2 optional pending benchmark. | P2 C later; benchmark-triggered tests; D01. |
| EDU-01 | Configurable admissions safeguards and structured approved facts: **missing** | Generic prompt modes only; no fact registry/expiry/conflict. | P0 C if admissions pilot, otherwise N/A; critical-fact set; T08. |
| EDU-02 | Arabic, RTL, ambiguity, child-sensitive policies: **missing** | No RTL widget; ASCII lexical. | P1 C/S conditional Arabic/education; per-language E2E and review; T08,T11,T12. |
| ANA-01 | Authoritative event envelope/catalog, origin and outbox: **missing** | `usage_log.jsonl` holds provider tokens only. | P0 I, P1 A R1; replay/dedup/spoof tests; T10,T13. |
| ANA-02 | Event-time timezone metrics, distinct windows, late corrections: **missing** | No analytics tables/processor. | P1 A R1; fixed clock late-event/zero-denominator tests; T13. |
| ANA-03 | Customer overview, review, sources, admissions, ops views: **missing** | Streamlit overview is local project status, no metrics. | P1 P/A R1; role-scoped UI E2E; T15. |
| ANA-04 | Weekly digest, advanced grouping: **missing** | No digest. Digest can be manual/opt-in in managed pilot; automated report later. | P1 O R1 manual; P2 automation; T15,D03. |
| ANA-05 | Privacy/redaction/deletion/export/access audit: **missing** | File chats and logs have no tenant/retention controls. | P0 S R1; redaction/deletion/export tests; T14. |
| BILL-01 | Reserve/finalize/refund exactly once, concurrent quota: **missing** | Cost tracker is not a transactional unit ledger. | P0 I R1; concurrency/retry/disconnect tests; T10. |
| BILL-02 | Pricing version, cost attempts, warnings/top-up approval, support time: **partial** | Provider token counts only; no money/period/support accounting. | P1 O/P R1; ledger reconciliation and UI; T10,T15. |
| API-01 | Versioned authenticated API, stable error codes/request IDs: **partial** | `/v1` exists; existing responses are local paths/detail without stable codes; destructive endpoints open. | P0 S R1; contract and compatibility tests; T04,T11. |
| SEC-01 | Tenant/artifact/cache/job/export/log isolation: **missing** | Project name identifies filesystem paths, no identity. | P0 S R1; negative matrix; T04,T14. |
| SEC-02 | Prompt injection, secrets, abuse, controlled spend: **partial** | Prompts instruct grounding; no enforced action policy/rates/cost ceilings; logging may include content. | P0 S R1; adversarial/burst/secret tests; T03,T05,T10. |
| OPS-01 | Timeouts/retries, health, alerts, audit logs: **partial** | Crawler retries; `/healthz` always ok; no DB/worker/snapshot health, action owners. | P1 O R1; outage and alert drill; T07,T14. |
| OPS-02 | Pilot workload/latency/recovery objectives: **unverified** | No load/restore measurements; target is not achievement. | P1 E external launch prerequisite; measured report; T16. |
| EVAL-01 | 100 reviewed questions, held-out evidence/critical facts, language counts: **missing** | Scripted golden cases only. | P1 E external launch prerequisite; signed corpus; T12. |
| EVAL-02 | Gate targets and live review with exact denominators: **unverified** | No real corpus/live pilot. | P1 E external launch prerequisite; report and human review; T12,T16. |
| MIG-01 | Existing project backup/rebuild/cutover/rollback: **missing** | Legacy format warning/load exists, but ambiguous vectors cannot be relabeled. | P0 I R0; representative migration/rollback drill; T02. |
| LEGAL-01 | Open-source obligations and commercial policy: **partial** | Apache-2.0 `LICENSE`/`NOTICE`; no hosted agreement or pricing policy. | P1 external launch prerequisite; owner review; T16. |

The event catalog and metric definitions are itemized below; workflow contracts and launch gates from spec §§9–14 remain acceptance requirements, with implementation semantics in `ARCHITECTURE_DECISIONS.md`. No live deployment, provider reliability, true answer quality, security boundary, capacity, or customer acceptance has been verified by the passing unit suite.

## Event and metric subrequirements

The following stable sub-IDs make the specification's long catalog executable. All events are **missing** as durable tenant-scoped events; `CostTracker` is only a local token log. All metrics are **missing** as hosted reports. Shared impact is absent auditability/customer reporting; shared scope is R1/P1 A except authoritative billing/delivery rows, which are P0 I. Shared acceptance: replay the exact producer event twice and verify one record/count; calculate each metric from a fixed, tenant-scoped event fixture with exact numerator/denominator, timezone/window, origin filtering and definition version. T10/T13/T15 own the work unless noted.

| ID | Event requirement and producer / specific acceptance |
|---|---|
| ANA-E01 | `widget_impression`, browser; optional eligible exposure, never authoritative demand. |
| ANA-E02 | `widget_opened`, browser; dedupe session/path open observation. |
| ANA-E03 | `question_accepted`, API; one unique accepted request, excludes preview/evaluation from billing. P0/T10. |
| ANA-E04 | `retrieval_completed`, runtime; canonical candidate/selected IDs, channel ranks and timings under restricted trace retention. |
| ANA-E05 | `planner_action`, runtime; allowlisted action/reason/budget/result count, no raw arbitrary tool input. |
| ANA-E06 | `answer_delivered`, API; emitted only at documented delivery boundary, retry does not duplicate. P0/T10. |
| ANA-E07 | `query_failed`, API; terminal stage/error/retriable state distinct from unsupported answer. |
| ANA-E08 | `feedback_submitted`, API; one current rating per turn and auditable replacement. |
| ANA-E09 | `citation_clicked`, browser; observation tied to issued citation, never proof of support. |
| ANA-E10 | `contact_offered`, API; route offered distinct from contact submission or staff availability. |
| ANA-E11 | `contact_submitted`, API; accepted lead ID/consent version, no PII in generic properties. |
| ANA-E12 | `contact_delivery_updated`, worker; terminal delivery per lead after retry dedupe. |
| ANA-E13 | `application_link_clicked`, browser; approved destination, admissions intent only. Conditional admissions scope. |
| ANA-E14 | `conversion_confirmed`, authorized admin/integration; audited external reference/attribution, browser cannot forge. Conditional enabled integration. |
| ANA-E15 | `ingest_state_changed`, worker; job stage/counts/errors even after failure. |
| ANA-E16 | `index_published`, publishing transaction; version/counts/approver and old active version. P0/T02,T07. |
| ANA-E17 | `usage_finalized`, ledger; unique request/charged units/cost/pricing version, independent of analytics consumer. P0/T10. |
| ANA-E18 | `review_issue_changed`, admin service; category/status/assignee/correction version. |

| ID | Metric requirement / specific acceptance |
|---|---|
| ANA-M01 | Active conversations: distinct accepted conversation IDs in period; inactivity policy version and no daily-distinct summation. |
| ANA-M02 | Engagement rate: queried widget sessions / eligible impression sessions; hide if impressions disabled, show blocking caveat. |
| ANA-M03 | Fallback rate: delivered unsupported / delivered substantive turns; transformations excluded. |
| ANA-M04 | Partial-answer rate: delivered partial / delivered substantive turns. |
| ANA-M05 | Negative feedback rate: negative / rated turns; show rated count and response rate. |
| ANA-M06 | Error rate: terminal failed accepted / terminal accepted; pending separately. |
| ANA-M07 | Contact request rate: conversations with accepted lead / active conversations; not a conversion. |
| ANA-M08 | Contact delivery success: leads successfully delivered / terminal lead delivery outcomes; pending separately. |
| ANA-M09 | Application click rate: conversations with click / active admissions conversations; intent only, conditional admissions scope. |
| ANA-M10 | Reviewed grounding: fully supported reviewed answers / reviewed answers; sampling, language and version visible; human review external T12. |
| ANA-M11 | Confirmed resolution: explicit resolved / recorded resolution outcomes; unknown separately, no inference from silence. |
| ANA-M12 | Latency: p50/p95 terminal end-to-end, by mode/cache/failure; time-to-first-token only if streaming later. |
| ANA-M13 | Delivery cost/question: attributed model+crawl/embedding+infra / chargeable questions; direct marginal cost separately. |
| ANA-M14 | Source freshness: last successful validation/publication plus expired count; failed crawl does not reset clock. |
| ANA-M15 | Gap recurrence: affected after correction / eligible after publication, with periods/volumes; no causal claim. |

Role permission subrequirements `ROLE-01` owner, `ROLE-02` project admin, `ROLE-03` editor, `ROLE-04` analyst, `ROLE-05` assigned support, `ROLE-06` visitor and `ROLE-07` Webly operator are all **missing** in hosted mode (`routes/*` have no auth). P0 S/R1/T04, with T11/T15 UI coverage. Acceptance is an explicit allow/deny matrix for every API and artifact: owner alone controls membership/billing/retention/deletion; admin handles source/publishing/widget; editor cannot publish or bill; analyst sees aggregates and authorized redacted review; support sees assigned contacts; visitor has only scoped widget actions; operator access is narrow and audited. Cross-tenant denies are mandatory.

API operation subrequirements `API-02` source management, `API-03` async ingest, `API-04` job inspect/cancel, `API-05` authorized draft preview, `API-06` publish/rollback, `API-07` widget session, `API-08` visitor query, `API-09` feedback/contact, `API-10` conversations, `API-11` analytics/review issues and `API-12` usage are **missing** for hosted behavior (though local ingest/query/chat routes partially overlap). P0 S/I for authorization, publication and usage; otherwise P1 P/R1. Ownership: T04–T15 by corresponding route. Acceptance for each is versioned request/response schema, role/tenant negative test, idempotent mutation, stable error code and request ID; T11/T15 exercise the user interface. Existing `/v1/projects` local callers require documented compatibility or explicit deprecation rather than silent change.
