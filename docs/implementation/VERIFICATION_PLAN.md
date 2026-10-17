# Verification and launch evidence plan

This file separates checks we can automate locally from evidence requiring real services, paid calls or customer review. Never use production data or credentials in tests. Use synthetic sites/content, fake identities, and test-only provider keys. Store corpus labels and results with explicit version, date, numerator/denominator and environment. A passing mocked planner/provider test proves control flow only.

## Reproducible development environment

Current baseline: Python 3.11/3.12; initialize pinned submodule `git submodule update --init --recursive`; create a fresh virtual environment; install `pip install -e '.[api,ui,dev]'` plus `webcreeper/requirements.txt` as needed. The existing repo `.venv` is incomplete, while `/Users/Yassin/python311/bin/python3` has the test dependencies. Add a checked-in Compose development profile during T04–T07 with PostgreSQL, a local object-store-compatible artifact directory/service, FastAPI, worker, Streamlit/admin and static widget asset. Use explicit nonproduction `.env.example`, synthetic seed HTML/pages, test IdP fixture and local fake embedding/chat providers. `db migrate up`, `fixtures seed`, `worker start`, `api start`, `widget build`, and `verify all` should be documented scripts/Make targets introduced with those components. Keep the current file-backed local demo runnable without DB. Never seed customer transcripts into development.

Current reproducible commands and observed results on this checkout:

```sh
python3 -m pytest -q                     # 123 passed, 3 warnings
python3 -m ruff check .                  # 18 pre-existing failures
python3 -m pytest -q webcreeper/test     # 2 passed, 1 DNS-dependent failure
python3 -m build                        # unavailable in this Python installation
python3 -m twine check 'dist/*'         # unavailable in this Python installation
```

Do not treat the submodule's live-domain failure as a confirmed product defect; replace it with a local HTTP fixture. CI build and package tests remain unexecuted locally. No real provider, PostgreSQL, browser, concurrency, restore, egress, performance or customer test has passed yet.

## Gate matrix

| Layer | Procedure and acceptance evidence | Cannot establish |
|---|---|---|
| Unit/contract | Run complete pytest/Ruff/typing gates; test segment/vector bijection, collision, summary/original, Unicode tokenization, RRF channel ranks, same-page evidence, planner schema/action IDs/repetition, token ceiling, response citation membership, metric denominator arithmetic, ledger state machine and stable error codes. Pin deterministic clocks and seeded model fakes. | Real retrieval quality, provider reliability, DB locking, browser behavior. |
| Real database/vector | In disposable Compose PostgreSQL plus real FAISS, apply migrations from zero and upgrade fixture; build two-version corpus; test query search after reload, model-space rejection, checksum mismatch, orphan mapping, old snapshot retained, active CAS and rollback. Run row-policy/composite FK negative tests for two tenants/projects. | Live customer source correctness or production storage durability. |
| Concurrency/recovery | Ten parallel queries across publish, two concurrent ingest jobs same project, job lease expiry/worker kill, artifact write interruption, DB commit failure, cache pin/GC race, simultaneous last-unit reservations, duplicate key with same/different body, disconnect before/after response commit, outbox outage/replay, delayed analytics event, tombstone replay after restore. Use barriers/fault injection and exact ledger counts; no partial snapshot ever serves. | Internet/provider capacity unless exercised separately. |
| Authorization/network security | Test every project/source/job/index/conversation/trace/feedback/contact/review/usage/analytics/export/delete route and artifact access against tenant B, each role and visitor token. Inject private IPv4/IPv6, loopback, link-local, metadata host, DNS rebinding, cross-domain/private redirect, robots redirect, bad ports, oversized/chunked response, proxy bypass, prompt-injection pages and forged browser events. In staging verify egress firewall and secret/log redaction. Zero cross-tenant responses or internal connections. | Broad adversarial coverage beyond corpus; periodic review needed. |
| Browser/end-to-end | Playwright from clean stack: owner onboarding/approval, preview, job progress, draft evaluation, publish, widget install and desktop/mobile/keyboard/RTL query, clickable exact citation, fallback, feedback, consent/contact submission and delivery state, pause/quota, editor correction/regression/republish, analyst review/metrics, support assignment, deletion/export. Assert UI conveys pending vs delivered and zero-data semantics. | Human usability, accessibility audit, actual customer acceptance. |
| Real retrieval/evaluation | Minimum 100 approved human-reviewed questions, ≥20 unanswerable/ambiguous, same-page/multipage; ≥25 Arabic/mixed if Arabic offered. Label expected segment IDs, acceptable/prohibited claims, critical facts, current source/version and clarification. Reserve held-out set. Run actual crawl/extraction/embedding/FAISS/lexical/retrieval/generation; compare semantic-only, RRF, builder and optional graph. Record Recall@K/evidence coverage, fully supported answers, abstention, latency/model cost with exact counts by language/version. Proposed gates: answerable sufficient evidence ≥90%, reviewed fully supported ≥95%, unanswerable appropriate ≥95%, zero incorrect critical claims. Human reviewers adjudicate support; model self-confidence is not a pass. | Performance/generalization outside finite corpus. Paid model calls and content owner required. |
| Operational/capacity | In staging, five projects × up to 10k segments, ten simultaneous queries, one ingest/project. Measure p50/p95 terminal latency (target p95 <12 s), request technical success (target ≥99% during pilot), analytics lag (target <5 min), request/cost/queue/cached memory; run dependency outage, worker crash, backup restore (proposed RPO 24h/RTO 4h), alert drills and rollback. Record sample size, provider errors and environment; never state unmeasured target as achieved. | Contractual SLA or broad production capacity. |
| External acceptance | Customer approves source scope, critical facts/expiry, representative corpus, contact owner/destination, retention/PII, allowance and billing delivery policy. Agree live pilot review cadence; review all negative feedback/errors/critical questions/contact failures plus sampled positives. Confirm versioned reports and attribution baseline before claiming deflection/enrollment. | Automatic engineering pass cannot substitute for customer sign-off. |

## Traceability and completion records

For each task in `IMPLEMENTATION_PLAN.md`, save command, commit, environment, dataset/snapshot/prompt/policy version, result counts, failures, reviewer and evidence link in `PROGRESS.md` or linked CI artifact. A failed gate creates a linked review issue; no blanket “tests pass” statement hides skips/unavailable checks. CI must run offline deterministic gates on 3.11/3.12, clean install/wheel smoke, DB/vector integration and browser smoke on disposable services. Paid evaluation and staging drills are explicit controlled jobs, not default PR tests. Production launch requires signed review and rollback operator. A final engineering completion claim requires zero open applicable P0 defects; any waived P1 requirement must name approver, reason, risk, expiry and customer-facing limitation without changing the specification's targets.

## R0 gate addendum — 2026-10-17

The baseline commands/results above describe the pre-implementation state and remain as audit evidence. R0's deterministic scope is T00–T03, not the hosted R1 DB/security/browser or T12 customer-quality gates. `R0_RUNBOOK.md` contains install, rebuild and rollback instructions.

| R0 gate | Evidence / status |
|---|---|
| Baseline and regression | **Pass.** Pre-fix real FAISS reproduced same-URL metadata collapse before/after reload; new tests cover distinct same-page segments, Arabic words, nested chunk split, original evidence, invented citation and budget rejection. |
| FAISS integrity and compatibility | **Pass.** Real FAISS tests check canonical IDs, duplicate/collision rejection, persistence/reload, v1 refusal, embedding-space mismatch, count/checksum mismatch. Existing v1 files require rebuild from original HTML; no unsafe conversion. |
| Publication, concurrency, recovery | **Pass.** Fault injection before pointer, stale expected-version writer, source-copy digest mismatch, concurrent readers and a query pinned across publication preserve a complete version; rollback validates before pointer switch. Local shared-filesystem semantics only; hosted distributed CAS is R1. |
| Retrieval/answer contract | **Pass for deterministic behavior.** Real FAISS hybrid RRF keeps multiple same-page segments; Unicode Arabic tokens survive; builder/classic follow-up search caps, exact-span citation validation, one repair/fallback and conservative prompt budget are tested. Mocks do **not** prove semantic support or model latency. |
| Local workflow/packaging | **Pass.** Main `pytest`, Ruff, diff whitespace, compileall, wheel build and isolated wheel import. The submodule's live-DNS test is not hermetic and remains unavailable offline. |
| Human-reviewed answer quality / paid-provider reliability | **Not an R0 completion gate; unverified.** T12/R1 requires approved corpus, nonproduction credentials, paid calls and human support adjudication. No claim of answer quality or production capacity. |

Final local command record: `python3 -m pytest -q` 146 passed/3 warnings; `python3 -m ruff check .` pass; `git diff --check` pass; `python3 -m compileall -q webly` pass; `python3 -m pip wheel . --no-deps --no-build-isolation -w /private/tmp/webly-r0-wheel` pass; fresh-target wheel install/module import pass. No main-suite skips. Python 3.12 CI execution and a clean dependency-resolution install remain unobserved locally.
