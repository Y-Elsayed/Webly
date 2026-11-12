# Core 0.2 implementation and release checklist

Implementation date: 2026-11-13. The changes are organized into descriptive Core
commits and the separately committed WebCreeper submodule. The older
[readiness assessment](CORE_READINESS_STATUS.md) describes the pre-hardening
baseline; use this document for the new contract and outstanding validation.

## Implemented work

| Plan batch | Implementation | Verification |
| --- | --- | --- |
| 1. Explicit Core contract | Required `ResourceScope` and `ProviderBundle`; declared model/tokenizer/revision/dimensions; contained paths; typed errors and publication outcomes; no Core credential discovery | Ownership/path/secret/lifecycle/config tests; installed Core without UI/API/Torch imports |
| 2. Safe bounded crawling | WebCreeper 0.3 validated DNS-to-socket fetcher, redirect checks, streaming wire/decoded limits, public HTTP policy, shared attempts/pages/deadlines and per-host controls | Mixed/private DNS, mapped addresses, pinned destination, compressed response, redirects, async host concurrency and finite retry tests |
| 3. Accepted immutable inputs | Fresh crawl-run manifests and coverage; hashes revalidated before publication; failed/incomplete inputs rejected; explicit legacy import; exact candidate approval for URL removals | Incomplete/tampered inputs, duplicate-page link discovery, removal approval and stale proposal tests |
| 4. Evidence preservation | Short facts and bare containers; heading context; typed blocks/offsets; table header repetition; preserved code; provider-tokenizer segmentation | Short facts, Arabic/mixed data, lists/tables/code and segment boundary fixtures |
| 5. Bounded grounded retrieval | Shared searches/calls/tokens; actual tokenizer accounting; reserved final-answer budget; exact visible-ID citation checks; classic initial judgement; builder remaining deadline; request-local diagnostics | Wrong-ID quotes, bounded repair, result limits, budget/cancellation, retry/quota and grounded query tests |
| 6. Publication and recovery | Format-2 immutable snapshots; CAS and bounded publication locks; committed/uncertain outcomes; fsynced operation reservations; idempotent replay; explicit resume; export/empty-scope restore | Post-pointer failure, stale CAS, model-revision mismatch, process kill after pointer publication, replay without embeddings, backup/restore |
| 7. Lifecycle and observability | Caller-owned providers; idempotent closure; concurrent namespace-safe embedding cache; correlated usage events; retained failed delivery; no credential repr; sanitized default query traces | Independent-resource concurrency, cache identity/concurrency, sink failure and failed flush retention tests |
| 8. Release tooling | Two-wheel fresh-environment verifier; Core/API/UI dependency inventories and advisory checks; CI matrix wiring; non-root minimal container; synthetic capacity runner; budgeted bilingual evaluation harness | Local wheel smoke and installed API tests; repository lint/tests; dependency reports and synthetic benchmark below |

Reference applications use the application adapter and separate `core-v2` storage.
The Run tab selects explicit completed runs and reviews removal proposals. API
ingest accepts `run_id`, `approval_token` and `resume`; Core errors serialize their
code and outcome. Existing project evidence and indexes are not overwritten.

## Evidence and its limits

The full local repository suite passes **243 tests**, including publication process-death and
Windows pointer-sharing regressions. Fresh two-wheel installation passes the
Core-only crawl/publish/reopen/cited-query smoke and 16 installed API tests without
skips. [Package provenance](audit/2026-11-13-core-v2-package-verification.json)
records the exact development source digests and wheel hashes from the pre-commit
verification. That run used dirty sources and explicitly does not certify a release. Tests use deterministic
providers and controlled fixtures; no real model calls were made here. Both
offline upstream WebCreeper async/hook tests also pass. Both wheel metadata checks
pass with Twine. Repository Ruff and diff-whitespace checks pass; the suite reports one upstream FAISS/NumPy
deprecation warning.

[Synthetic capacity report](audit/2026-11-13-core-v2-benchmark.json): 2,000 synthetic
pages, 20,000 segments and four-dimensional fixture embeddings. Observed snapshot
build/publication was approximately 0.49 seconds, cold query 0.55 seconds, and warm
p95 approximately 0.09/0.42/0.98 seconds at submitted concurrency 1/4/10. Peak RSS
was approximately 161 MiB. A runtime serializes work, so submitted concurrency
measures queueing. This does not predict real embedding dimensions, network/LLM
latency, client-site extraction quality or a production capacity SLA.

[Dependency inventory](audit/2026-11-13-core-v2-dependencies.json) records the local
Windows profile scan. No advisory records or unknown package responses were
reported in that scan. This is a dated automated observation, not a complete
security or license approval. Core and crawler licenses still require human
release review. Profile constraints freeze observed versions without wheel hashes;
the package verifier separately records built wheel hashes and source digests.

## Gates before a production Core release

- [x] Review the implementation diffs, commit WebCreeper first, and record that
  exact commit in Core's submodule pointer.
- [ ] Build from clean reviewed sources without `--allow-dirty`; retain the new
  artifact provenance alongside the earlier development verification report.
- [ ] Run the configured Windows/Linux and Python 3.11/3.12 CI matrix against those
  exact commits. The previously green baseline matrix does not validate new work.
- [ ] Build and smoke-test the container with persistent storage, non-root
  permissions, restart/backup recovery and host egress restrictions. Docker CLI
  is available locally, but its daemon was unavailable during implementation.
- [ ] Curate and independently review at least 100 real English/Arabic cases from
  five unrelated sites, including 40 held-out and 20 unanswerable cases. Include
  sparse facts, tables/code, repeated layout and adversarial evidence. Do not
  classify synthetic fixtures as real quality evidence.
- [ ] Agree a live model spending cap and reviewed pricing, then compare builder
  and classic with the same frozen sources/models. Review factual claims, correct
  abstention, completeness, latency and cost per successful answer. No live run
  or spending cap has been authorized here.
- [ ] Test production-size embeddings, the intended worker/process topology and
  long-running jobs on deployment hardware. Establish operational SLOs from those
  measurements and test storage-full/provider/network interruptions there.
- [ ] Review license obligations, dependency reports, vulnerability policy,
  artifact provenance and storage retention before publishing signed artifacts.

## Evaluation workflow

`python -m scripts.evaluate_core corpus.jsonl` validates without paid work.
Each case needs `id`, `site_id`, `language` (`en`/`ar`), `split`
(`development`/`held_out`), `question`, `answerable`, `reviewed`, `reviewer`,
`source_hash` and approved `supporting_spans` for answerable cases. Require at
least 40 cases in each language. `synthetic: true` disqualifies release readiness.
Freeze sources and split before tuning; the host runner determines the matching
resource and model configuration from each case.

Live execution additionally requires `--execute --cap-usd AMOUNT --prices FILE
--runner trusted.module:function`. The trusted runner takes `(case, mode, context)`
and returns `QueryResult`; it must use that context for all provider work. Pricing
JSON contains `version` and `models`, keyed by model ID with `input_per_million`
and `output_per_million` USD rates. Every retry reserves its maximum before the
provider call, and missing prices or failed reservation stop execution.

Human review JSONL, supplied through `--reviews`, uses `case_id`, `mode`,
`reviewer`, matching `source_hash`, `answerable`, `total_claims`,
`supported_claims`, `answered` and `correct_abstention`. Reviews must cover both
modes for every held-out case. The harness rejects duplicate/unknown identities,
mismatched sources and impossible claim counts. Default comparison thresholds
are 95% supported-claim precision, 95% correct abstention and 80% coverage of
answerable cases. These are initial gates for review, not measured achievements.
Passing citation syntax tests cannot substitute for that human claim assessment.

## SaaS handoff

The SaaS can integrate against [Core 0.2](CORE_INTEGRATION.md) now using opaque
resource IDs, explicit provider clients and operation IDs. Keep the engine behind
authorized worker jobs with durable event delivery and process/egress limits.
Auth, tenancy, scheduling, secrets, quotas/billing, UI and client administration
remain in the SaaS. Promote Core to a production dependency only after the gates
above are completed; broad support for arbitrary websites is not established by
HTML fixture tests.
