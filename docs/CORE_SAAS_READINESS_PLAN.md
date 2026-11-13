# Core readiness and SaaS handoff

Updated 2026-11-13. This is the implementation and release checklist for the
single Linux host deployment. Core owns capture, transformation, retrieval and
atomic index publication. The SaaS owns authentication, tenant authorization,
durable scheduling, quotas, provider credentials and billing.

For the post-push assessment, newly confirmed operational gaps and the concrete
platform entry architecture, see [the SaaS entry review](SAAS_ENTRY_READINESS_REVIEW.md).

## Implemented in the current working tree

| Work | Result and verification |
| --- | --- |
| Capture policy compatibility | Format 2 capture manifests seal the policy, its digest and the complete URL/HTML inventory. Indexing checks compatibility before embedding and again before publication. |
| Shared URL scope | Crawling and imported captures share domain, path and pattern decisions. A capture with out-of-scope sources is rejected. No site-name exception is used. |
| Legacy compatibility | Format 1 requires the exact original full configuration digest and currently permitted URLs. A mismatch requires a new capture. |
| Typed host failures | Runtime boundaries normalize expected configuration, filesystem and lock failures into sanitized Core errors. Policy mismatch is nonretryable and maps to HTTP 409. |
| Bounded ingestion lock | Ingestion lock acquisition observes the operation deadline. Query/model deadlines remain cooperative; the host must terminate stuck workers. |
| Host example | `scripts/worker_example.py` demonstrates explicit resource/provider ownership and SQLite event deduplication by operation ID and sequence. |
| Evaluation tooling | Offline capture preparation, explicit paid execution, budget reservation, paired mode reporting, and reviews bound to corpus/run/source/response hashes. |
| Linux deployment checks | A Core-only Docker stage and a checks stage exercise process contention, recovery, restore and actual ENOSPC without real model calls. CI now contains the same checks. |

Capture-sensitive fields are `start_url`, `allowed_domains`, `allowed_paths`,
`blocked_paths`, `allow_url_patterns`, `block_url_patterns`, `allow_subdomains`,
`seed_urls`, `crawl_entire_site`, `max_depth`, and `respect_robots`.
Changing any of them requires a fresh capture. Query/model, transformation and
rate settings can reuse a compatible format 2 capture; reindexing still uses
the applicable embedding and transformation fingerprints. All configuration
fields are explicitly classified in code and checked by tests.

An existing published snapshot remains queryable when configuration changes.
New indexing cannot silently reinterpret the old capture as complete under a
new policy. For immediate access revocation, the SaaS must stop serving that
resource until a replacement snapshot is published. Inspect compatibility
through `runtime.inspect_run(run_id)`; responses expose the published capture
policy digest in sanitized diagnostics.

## Local evidence

- `docs/audit/2026-11-13-single-host-linux.json`: a reader completed 1,383 queries
  while two processes attempted publication; one committed and one received a
  publication conflict. Cancellation, export/restore and recovery after death
  immediately after pointer publication passed. A 1 MiB disposable filesystem
  produced real ENOSPC and preserved the previous snapshot.
- `docs/audit/2026-11-13-benchmark-linux.json`: 2,000 synthetic pages, 20,000
  segments and 1,536 dimensions; concurrency 1/4/10 on one and four independently
  owned resources. Single-resource p95 was approximately 46/188/492 ms. Four
  resources at concurrency 10 had p95 approximately 595 ms and final RSS around
  1.07 GB. Fixture providers and WSL2 Linux make this engine evidence, not a
  live-model latency or client-capacity guarantee.
- Installed Linux Core tests: 87 passed, one platform-specific skip. The complete
  checkout suite passes 302 tests; Ruff passes. The isolated Windows wheel check
  passed its crawl/publish/reopen contract, optional imports and all 17 API tests.
  `docs/audit/2026-11-13-saas-readiness-package-verification.json` records wheel
  hashes and source digests. Advisory inventories returned zero records at scan
  time; they do not establish license approval or absence of vulnerabilities.
- Two separate network-disabled, read-only-root containers using the disposable
  named volume `webly-readiness-20261113` queried the same snapshot
  `52db9c015e81485d941e7a1a2872fdc5`. The second reused the persisted index.
  Core-only Linux package smoke also passed with optional adapter imports blocked.
- `evaluation_artifacts/preparation.json` records five real website captures
  and 100 draft cases: 50 English, 50 Arabic, 40 held out and 20 unanswerable.
  Full captures and drafts are ignored local artifacts. They are **unreviewed**;
  no answer-quality gate has passed and no paid evaluation has run. Offline
  validation correctly rejects 52 repeated draft questions pending rewriting.

The local evidence above was captured from the development working tree and
retains that provenance. The implementation has since been pushed as Core
`ddc94ce`, with crawler `2594a7b`; all nine jobs in
[its CI run](https://github.com/Y-Elsayed/Webly/actions/runs/43434855824) passed.
Release artifacts must still identify exact parent/crawler revisions, wheel
hashes, container digest, Python/platform and dependency inventories. A green
implementation CI does not establish live-model quality or deployment readiness.

## Remaining release gates, in order

1. **Independent corpus review.** Follow `docs/evaluation/README.md`. Rewrite
   draft questions, verify evidence/answerability, include tables, short facts,
   ambiguous questions and adversarial content, and freeze the held-out split.
   Review website terms before sharing captures outside this machine.
2. **Approve the live evaluation.** Select exact embedding/chat models, review
   pricing, authorize a finite USD cap, then run both modes with the same frozen
   corpus. Include index setup in reservation. Never infer quality from fixtures.
3. **Review exact answers.** Claim precision and citation accuracy must each be
   at least 95%, correct abstention at least 95%, answerable coverage at least
   80%, separately for English and Arabic and for both modes. Investigate every
   source stratum; report latency, evidence recall, token usage and conservative
   reserved cost separately from provider invoice totals.
4. **Validate the target host.** Repeat the realistic benchmark with the chosen
   CPU/RAM/storage limits, real providers and independent worker processes.
   Establish concurrency and queue limits from measured tail latency and RSS.
   Rehearse container restart with persistent resource storage and restore onto
   a separate host. Test the deployed public-egress policy and provider timeouts.
5. **Freeze and verify the candidate.** Run all checkout tests, installed-package
   checks, container checks, dependency advisory and license inventories. Review
   findings rather than treating inventory generation as approval. Require clean
   source/submodule status and green CI on the exact release revisions.
6. **Connect the SaaS host.** Enforce tenant-to-resource authorization before
   Core access, lease one ingest worker per resource, persist operation IDs and
   events, reconcile unknown outcomes before retries, and set storage/retention
   limits. Test isolation using independent tenant-owned resource roots.

## Supported operational contract

- Input is HTTP(S) HTML captured under robots/scope/fetch policy, or a trusted
  host-imported complete HTML JSONL capture. PDF/OCR, browser rendering, login
  flows and arbitrary document ingestion are not covered by this release.
- A completed capture means the crawler completed under its limits and policy;
  it does not prove every useful fact on the website was reachable or extracted.
  Extraction is heuristic; measure the client's content before onboarding.
- Resource roots and imported files are trusted host inputs. Give each resource
  a separate root and restrict host filesystem permissions. Core is not the
  SaaS authorization boundary.
- Use local persistent filesystems with reliable atomic replacement and locking.
  Shared NFS/object storage and multi-host writers require a separate design.
  Snapshots are immutable and selected by an atomic pointer; do not edit them.
- Keep runs, operation journals and snapshots needed for recovery. Retention and
  deletion are host-managed maintenance tasks; do not remove active or leased
  snapshots. Schedule garbage collection only after readers and recovery needs
  have been accounted for.
- Persist events idempotently using operation ID and sequence. Event delivery
  and usage reservations support reconciliation; they are not exactly-once
  financial billing or provider-invoice accounting.
- Run workers with filesystem quotas, bounded CPU/memory, a hard process deadline
  and controlled network egress. Python cancellation cannot interrupt every
  blocking provider implementation. Never put a distributed queue into Core
  merely to implement the SaaS scheduler.

The Core can now be integrated and tested by the SaaS. Production certification
remains dependent on the review, model, host and exact-release gates above.
