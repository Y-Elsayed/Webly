# Integrating Webly Core 0.2

Core is the website ingestion and grounded retrieval engine. The separate SaaS
owns authentication, tenant authorization, billing, dashboards and job scheduling.
The Streamlit and FastAPI applications in this repository are reference adapters.
See [the current readiness review](SAAS_ENTRY_READINESS_REVIEW.md) for confirmed
remaining gaps and the proposed SaaS integration and launch sequence.

## Install and provenance

Use Python 3.11 or 3.12. Core 0.2 requires the separately packaged WebCreeper 0.3:

```sh
git submodule update --init --recursive
python -m pip install ./webcreeper
python -m pip install .
```

The parent submodule pointer records the corresponding WebCreeper 0.3 source
commit. Build release artifacts from clean sources matching that pointer; an
unrelated package with the same version does not establish source provenance.
Core requires neither Streamlit, FastAPI nor Torch. Optional extras are `ui`,
`api` and `hf`; `requirements.txt` is the older full application profile.

## Explicit providers and resources

```python
from pathlib import Path
from webly import (
    ModelCapabilities, OperationContext, OperationLimits,
    ProviderBundle, ResourceScope, build_runtime,
)

# Host-created clients implement count_tokens(text) and embed(text) / generate(text).
# SDK-backed clients should also implement *_with_limits(text, timeout=...,
# max_output_tokens=...) so network calls honor the supplied remaining budget.
providers = ProviderBundle(
    embedder=my_embedding_client,
    embedding=ModelCapabilities(
        "my-embedding", input_tokens=8192, dimensions=1536,
        revision="reviewed-revision", endpoint_id="my-provider",
    ),
    chat=my_chat_client,
    generation=ModelCapabilities("my-chat", input_tokens=128000, output_tokens=2048),
)
resources = ResourceScope("opaque-resource-id", Path("./data/customer-docs"))

with build_runtime(
    {"start_url": "https://example.com/docs", "retrieval_mode": "builder"},
    resources=resources, providers=providers,
) as runtime:
    ingest = runtime.run_ingest(
        mode="both",
        context=OperationContext(operation_id="host-job-001", limits=OperationLimits.ingest()),
    )
    if ingest.get("indexed"):
        answer = runtime.query_result(
            "What are the opening times?", context=OperationContext(),
        )
        print(answer.to_dict())

providers.close()  # caller owns injected clients; runtime closes its internal resources
```

Core never reads `.env` or chooses API credentials. `webly.adapters` is the
application-owned environment/provider bootstrap used by the reference apps.
An embedding-only bundle supports ingestion but cannot answer questions.
Unknown config fields fail rather than disappearing silently. Mapping config
cannot override resource paths, cache locations or crawl artifact filenames.
Scopes bind an immutable opaque ID to a root; the host must authorize that root
and prevent other OS users/processes from mutating it. This is filesystem
containment, not a hostile local-process sandbox or tenant authorization system.

## Operations, limits and outcomes

Pass one fresh `OperationContext` for each logical request. It supplies a deadline,
cancellation event, search/provider/token/page/network/byte limits and a usage
sink. Query defaults are 30 seconds, four searches, sixteen provider attempts and
32,000 reserved tokens. Ingest defaults are 30 minutes, 2,000 pages and five
million reserved tokens. Override limits through `OperationLimits`; values are
validated. Retries, redirects and robots requests share the operation budget.

Generation reserves worst-case input and output before making a provider call;
work calls preserve a final-answer allowance. Failed/uncertain calls are not
refunded. Usage events distinguish measured SDK usage from estimates. A sink
failure retains pending events and blocks the next paid reservation. Hosts must
deduplicate events by operation ID and sequence when delivering them again.
These conservative reservations and the compatibility cost log are not invoices.

Errors derive from `webly.contracts.CoreError` and expose `code`, `retryable`,
`operation_id` and `outcome`. The outcome is `not_committed`, `committed` or
`uncertain`, with a snapshot ID where available. Inspect it before retrying a
failed publication. A failure after the pointer changes may already have made
the candidate active. `IngestResult` is a mapping with `.outcome` and `.to_dict()`.

Built-in SDK adapters use bounded calls. Arbitrary injected Python clients must
honor cancellation/timeouts themselves; Python cannot forcibly stop a blocking
foreign function safely. Hosts should use worker process limits as an outer bound.
One runtime serializes its ingest/query work. Use separately scoped runtime
instances for independent workers; do not share a resource between customers.

## Crawl runs, refresh and retries

Each crawl gets a fresh `runs/<id>` directory and a completion manifest with
coverage, source hashes, graph/config identity and an extractor revision. Failed
or interrupted runs remain inspectable and cannot replace the active corpus.
Discovery runs before exact evidence dedup, so duplicate-looking pages can still
lead to different links. Query strings and `www` authorities are preserved.

`crawl_only` returns a completed `run_id`. `index_only` requires that explicit ID;
it never silently selects mutable legacy results. Use `runtime.inspect_run(id)`
to inspect a run. The snapshot builder validates frozen inputs again before
publication. Exact cleaned-page duplicates share canonical evidence and aliases;
this is not near-duplicate or global chunk dedup.

New format 2 run manifests seal a separate capture-policy digest and source
inventory. Changes to start URL, domains/subdomains, paths, URL patterns, seeds,
crawl coverage/depth or robots policy require fresh capture and raise
`run_policy_mismatch`. Query/model/rate changes can reuse compatible format 2
HTML. Format 1 runs require the exact original full configuration digest and
currently allowed source URLs. Inspect the derived `compatibility` field without
rewriting old manifests. Published query traces identify the snapshot's capture
policy digest; changing configuration alone does not revoke an active snapshot.

When a refresh removes any URLs, ingestion returns `status="approval_required"`
with an added/changed/removed proposal and `approval_token`. Review the exact
candidate, then resubmit `index_only` with its `run_id`, that token and a new
operation ID. Changes to the candidate or active version invalidate approval.
Nothing is removed from the active index before the approved snapshot publishes.

Completed operation IDs replay without embedding again. Reuse with changed
inputs conflicts. Explicit `resume=True` retries failed work with the same limits
and counters; a failed crawl starts a new run. Journaled provider reservations
survive process death. If a worker dies after publication, the snapshot operation
identity supports recovery without reembedding. Ambiguous states require
reconciliation rather than blind retries. Keep operation IDs stable in the host.

## Fetch boundary

WebCreeper uses a shared validated fetcher for pages and robots. It checks every
redirect, rejects credentials and non-HTTP schemes, defaults to ports 80/443,
validates all resolved addresses and connects to a validated numeric address while
preserving the original HTTP/TLS origin. Private, loopback, link-local, multicast
and transition addresses are rejected by default. Streaming wire and decoded
bytes, retries, redirects, deadlines and per-host concurrency/rate are bounded.
Environment proxies are not inherited.

Trusted hosts may pass a `FetchPolicy` with explicit private network/port allowances
for controlled fixtures. Never derive those allowances from untrusted customer
configuration. Deploy workers behind egress restrictions as an additional boundary.
This release extracts fetched HTML; JavaScript rendering, PDF/OCR and arbitrary
authenticated content are outside the supported ingestion contract.

## Evidence and query behavior

Chunks retain headings and typed paragraph/list/table/code blocks, including short
facts. Navigation, footers and forms retain published text and region metadata;
entered/hidden values, textareas and buttons are excluded. Tables use explicit or
conservatively inferred header relationships, preserve headerless data rows and
repeat only associated context across splits. Malformed/excessive table structure
falls back to ordered text with uncertain metadata. Code preserves line breaks.
Offsets refer to the extracted section representation, not byte positions in the
original HTML. Embedding segments obey the provider tokenizer and preserve the
original evidence separately from optional summaries.

Builder assesses visible evidence and performs focused follow-ups; classic checks
the initial hybrid evidence before optional expansion and rewrite passes. Both
share operation budgets and validate citations against the exact supplied ID and
text. A literal matching quote does not prove that every generated claim follows
from it; human claim review remains a release gate. Conversation-only edits are
marked `unverified_transformation`. Debug-off traces omit questions and source text.

## Migration, backup and lifecycle

Core 0.2 intentionally changes the factory signature and snapshot format. Reference
apps use a separate `core-v2` root, leaving existing project data untouched.
Old snapshots require a rebuild.

The current extraction contract is `blocks-v2`. Snapshots built with `blocks-v1`
also need rebuilding using a new operation ID. Completed frozen runs remain
usable as raw HTML input when capture compatibility permits it; their original
manifests are not rewritten. Format 1 policy mismatches require fresh capture.
Old cache identities, operation results and removal approvals are not
reused across extraction revisions. See the
[HTML extraction plan](HTML_EXTRACTION_IMPROVEMENT_PLAN.md) for the exact changes.

Import trusted saved JSON/JSONL explicitly:

```python
run_id = runtime.import_legacy("old/results.jsonl", acknowledge_complete=True)
result = runtime.run_ingest(mode="index_only", run_id=run_id)
```

Acknowledgement is the host's assertion of completeness, not proof from Core.
`export_snapshot(new_directory)` exports the active checked snapshot and resource
identity. `restore_snapshot(backup)` validates resource and embedding identity and
requires an empty destination scope. Restore republishes atomically. Backups
contain website evidence; apply the host's retention/access policy. Snapshot
rollback uses a compare-and-swap expected version. No automatic garbage collection
deletes versions that existing readers may still hold.

Call `close()` or use a context manager. Cache connections, fetch pools and
request-local state close with the runtime; injected providers remain caller-owned.

## Verification and release gates

```sh
python -m pytest -q
python scripts/verify_core_package.py --work-dir package-verification --extras --audit
```

The verifier requires clean reviewed sources, builds both wheels, installs them in
a fresh environment, rejects optional imports during Core smoke checks, then tests
API/UI extras and audits dependency profiles. `--allow-dirty` is explicitly local
development evidence and cannot qualify a release. Keep wheel hashes, source
digests and dependency reports with the release. Version constraints are profile-
specific, not universal hashed locks. See the [implementation report](CORE_V2_IMPLEMENTATION.md)
for observed tests and remaining external gates.
