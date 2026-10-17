# R0/R1 execution progress

Updated 2026-10-17 after R0 implementation. Source specification remains untracked and untouched. The work began on repository `main` at `46d616bd0bcc328e1e684f7aed7807023135d806`, `origin/main`; `webcreeper` remains at `8db4429e0a2b964eca634beed249a833e8934bb0`. The only pre-existing working-tree change before planning was untracked `Webly_Product_and_Engineering_Specification.md`. R0 code, tests and these documents are versioned; preserve the untracked specification. No R1 implementation, deployment, paid call or production credential was used.

## Completed investigation evidence

- Read full specification, implementation routes/pipelines/storage/index/crawler submodule, CI, package and deployment configuration. No applicable `AGENTS.md` found.
- Main tests: `python3 -m pytest -q` → 123 passed, 3 warnings. Ruff: `python3 -m ruff check .` → 18 pre-existing errors. Submodule tests: 2 passed, 1 DNS-dependent live-domain failure. Current `.venv` lacks pytest/Ruff; separate `python3` has pytest 8.3.5, Ruff 0.14.0, FAISS 1.11.0. Build/Twine unavailable. No hosted or paid provider integration executed.
- Isolated real-FAISS fixture: two records same URL yielded two vectors but one vector-to-metadata map; both hits returned second record before/after reload. Arabic token fixture omitted Arabic words; same-page ranker returned only one record. No application code was altered for these reproductions.
- Static code trace establishes in-place FAISS/metadata writes, no API authentication, sync ingest, builder graph setting bypass, summary evidence replacement when enabled, crawler auto redirects without destination IP validation, no hosted DB/worker/widget/billing/analytics.

## Task board

| ID | State | Evidence/blocker/next condition |
|---|---|---|
| T00 | Implemented; deterministic gates passed | Recursive submodule CI checkout, owned-code Ruff cleanup, offline local runbook, wheel smoke. Pinned submodule live-DNS test is explicitly outside main offline CI; no submodule code changed. |
| T01 | Implemented; real-FAISS gates passed | Canonical segment/vector bijection, duplicate/collision rejection, v1 load refusal, nested/oversized chunks, original vs embedding evidence, same-page save/reload tests. Rebuild instructions in `R0_RUNBOOK.md`. |
| T02 | Implemented; real-FAISS gates passed | Immutable checksummed snapshot, staging/atomic pointer CAS, lock, rollback, source digest, model compatibility, fail-before-pointer, stale writer, concurrent readers and in-flight pin tests. No automatic GC; old versions retained. |
| T03 | Implemented; deterministic gates passed | Unicode Arabic tokens, segment RRF, same-page evidence, capped planner searches, grounded structured citation/spans, budget rejection and one-repair fallback tests. Memory-only transform explicitly unverified. Real semantic answer quality remains unevaluated. |
| T04 | Not started | Depends T00/T02 design; hosted DB/auth. Live IdP details external. |
| T05 | Not started | Depends T04 source contract; crawler security. Deployment egress config external. |
| T06 | Not started | Depends T04/T05; onboarding/source approval. Customer approver external. |
| T07 | Not started | Depends T04/T05/T06; jobs/freshness. |
| T08 | Not started | Depends T04/T06/T07; structured facts conditional on admissions. Source/fact owner external. |
| T09 | Not started | Depends T02/T03/T04/T08; hosted query/preview. If general pilot, T08 may provide generic validity only. |
| T10 | Not started | Depends T04/T09; ledger. Delivery uncertainty and allowance need owner approval before billing. |
| T11 | Not started | Depends T04/T09/T10; widget. Target-site install external. |
| T12 | Not started | Depends T03/T08/T09; real evaluation. Human corpus and paid model budget external. |
| T13 | Not started | Depends T04/T10/T11; contact/feedback/analytics. Staffed destination external. |
| T14 | Not started | Depends T04/T07/T13; retention/recovery. Retention and infra external. |
| T15 | Not started | Depends T06–T10/T13; admin/analytics/ops UI. |
| T16 | Not started | Depends T05/T12/T14/T15; staged managed-pilot gate. Customer and live operations external. |
| D01–D04 | Deferred | See deferred backlog; not R0/R1 pilot commitments. |

## Resumption instruction

Before resuming, recheck `git status` and preserve the specification and any later user changes. Next executable work is **not R1 in this scope**: rerun the R0 gate commands after any edits, then prepare a reviewed real retrieval corpus/provider budget for T12 if authorized. T04 is the next implementation task only when R1 is explicitly authorized. Do not infer customer answer quality, hosted security or pilot readiness from R0 tests.

## R0 verification ledger

Environment: independent Python 3.11 with pytest 8.3.5, Ruff 0.14.0, FAISS 1.11.0; no network-dependent runtime tests. Baseline before edits: 123 passed/3 warnings, 18 Ruff failures, real-FAISS same-URL mapping defect reproduced (two vectors/one map, both hits second page chunk after reload), Arabic tokens omitted and same-page ranker collapsed results. After R0 edits, main suite and Ruff were green; final command/result is recorded in the R0 gate addendum in `VERIFICATION_PLAN.md`. The separate crawler submodule live-DNS test remains 2 passed/1 DNS failure in this environment, not an R0 deterministic gate. `python3 -m build` and Twine were unavailable, but `pip wheel --no-deps --no-build-isolation` succeeded. No real provider/reviewed corpus, browser, capacity, production restore or R1 security gate was executed.

Final commands on this worktree: `python3 -m pytest -q` → **146 passed, 3 SWIG deprecation warnings**; `python3 -m ruff check .` → pass; `git diff --check` → pass; `python3 -m compileall -q webly` → pass; `python3 -m pip wheel . --no-deps --no-build-isolation -w /private/tmp/webly-r0-wheel` → pass; install into a fresh `/private/tmp/webly-r0-wheel-smoke.*` target and isolated `webly`, snapshot and query module import → pass. No tests were skipped in main pytest. The wheel command does not prove dependency resolution on a clean machine; the runbook gives the intended editable install. The open question is real human-reviewed answer quality, not a deterministic R0 code gate.
