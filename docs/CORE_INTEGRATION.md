# Using and verifying Webly Core

Webly Core is an embeddable Python engine. It does not require Streamlit, FastAPI,
Torch, user accounts or a SaaS database. The UI and service are optional reference
adapters; the future chatbot platform owns authentication, tenants and billing.

## Install from source

Use Python 3.11 or 3.12. From a checkout with the submodule initialized:

```sh
git submodule update --init --recursive
python -m pip install ./webcreeper
python -m pip install .
```

Core declares `webcreeper==0.2.0`. The verified crawler source is submodule commit
`8db4429e0a2b964eca634beed249a833e8934bb0`. The verifier builds that exact commit,
rejects tracked source changes and installs its wheel explicitly: a package on an
index with the same version is not proof of the same source. Developer tests also
use the installed crawler rather than a sibling-directory path workaround.

The Core crawler adapter preserves URL authority (including `www.` and explicit
ports) because WebCreeper 0.2.0 incorrectly uses a host-comparison helper to
rewrite fetch addresses. Query normalization still delegates to WebCreeper.
This compatibility override can be removed after upgrading to a reviewed
dependency that fixes the issue; no crawler implementation is bundled in Core.

For development, `python -m pip install -r requirements-dev.txt` installs the
local crawler, editable Core, API/UI extras and test tools. `requirements.txt`
is the legacy full application profile, including local-model dependencies; it
is not the Core-only installation or a production dependency lock.

## Initial supported integration surface

```python
from webly import ProjectConfig, QueryResult, build_runtime

config = ProjectConfig.from_dict({
    "start_url": "https://example.com/docs",
    "output_dir": "./data/docs/crawl",
    "index_dir": "./data/docs/index",
    "retrieval_mode": "classic",  # builder is also supported
})
runtime = build_runtime(config, api_key="your-provider-key")
ingest_report = runtime.run_ingest(mode="both")
result: QueryResult = runtime.query_result("What does this website say about installation?")
print(result.to_dict())
```

- `ProjectConfig.from_dict` normalizes and validates existing configuration.
- `build_runtime(config, api_key=...)` returns a `ProjectRuntime`.
- `run_ingest(mode="crawl_only" | "index_only" | "both", force_crawl=False)`
  returns the existing ingest report. Inspect `indexed`/`empty_results` and the
  summary rather than assuming every return means a published index.
- `query_result(question, memory_context="", retry_on_empty=False)` returns
  `QueryResult`: answer/status, supported flag, sources, citations, missing
  information and diagnostics. `query(...)` remains a text-only convenience.
- A newly built runtime reopens an existing compatible active snapshot on query;
  incompatible/legacy indexes fail explicitly and may require rebuilding.
- `build_pipelines` remains a compatibility factory returning ingest/query pipelines.

This batch preserves existing signatures, result shapes and errors. Environment
and `.env` key fallback still exist; pass the intended key explicitly in hosts.
Explicit provider/resource policies, typed error taxonomy and stronger operation
limits remain later roadmap work. Do not treat this packaging milestone as a
production-safety or retrieval-quality certification.

## Installed-package verification

Install build tools in the invoking environment, then run:

```sh
python -m pip install "setuptools>=68" wheel
python scripts/verify_core_package.py --work-dir package-verification --extras
```

The work directory must be empty. Without `--work-dir`, temporary artifacts are
removed after verification. The command builds clean Core and pinned crawler
wheels, checks archive contents, creates a fresh virtual environment and installs
declared dependencies. Dependency downloads require an index connection; no real
model requests are used.

The Core-only subprocess runs outside the checkout with Python isolated mode and
rejects imports of optional UI/API/local-model modules. It crawls a loopback
two-page fixture, runs real extraction/chunking/FAISS publication, reopens the
snapshot, and queries through the public runtime using deterministic provider
doubles. It checks source/version provenance, citations, prompt files and the
compatibility factory. The fixture's loopback URL is test input, not a promised
production crawl policy.

With `--extras`, only after Core passes, the verifier installs API/UI dependencies,
checks the adapters and runs copied service tests against the installed wheel
without repository `conftest.py` path injection. Required service tests must run;
skips are a verification failure. The report records wheel hashes, the crawler
commit, test counts and the resolved dependency profiles.

CI runs the suite and installed-package verification on Windows/Linux and Python
3.11/3.12. CI execution is separate from local verification; adding a matrix does
not mean every matrix cell has already passed.

For deployment without the checkout, install the two verified wheel paths together:

```sh
python -m pip install /path/to/webcreeper-0.2.0-py3-none-any.whl /path/to/webly-0.1.0-py3-none-any.whl
```

`verification.json` captures dependency versions for the run. Dependency resolution
is not yet a cross-platform lock or security audit. Keep that evidence alongside
the release; dependency hardening and production readiness remain tracked in the
[Core roadmap](PRODUCTION_ROADMAP.md).
