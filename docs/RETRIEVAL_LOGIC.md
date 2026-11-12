# Current retrieval logic

This document describes the current working-tree implementation, including the evidence-driven builder upgrade. It explains how Webly selects website content, decides whether more retrieval is needed, and produces an answer. It describes implemented behavior, not a proposed architecture or an accuracy benchmark.

## 1. Overview

Webly answers questions using content already stored in a project's index. Both retrieval modes use the same semantic search, optional keyword search, rank fusion, context assembly, and answer-generation components. Their main difference is how they choose additional searches.

| Stage | Builder, the default | Classic |
| --- | --- | --- |
| Understand the request | An LLM routes the request and identifies answer requirements | Combines the question with any supplied conversation memory |
| First search | Uses the question or a standalone follow-up query | Uses the question plus memory |
| Find more evidence | Assesses missing information and proposes focused searches using structural hints | Judges initial evidence, expands using anchors/headings if needed, then optionally rewrites |
| Retrieval limits | Four controller searches; shared operation limits also apply | Two rewrite hops and three rewrite searches; all expansion searches share the operation cap |
| Finish | Runs the final answerability check, then grounded generation or fallback | Checks initial evidence, expansion and rewrite hops, then generates or falls back |

```text
Question + optional conversation memory
                  |
          Builder or classic controller
                  |
       Query embedding --> FAISS search
       Query keywords --> BM25 search, if enabled
                  |
       Deduplicate by segment and fuse ranks
                  |
       Assemble original website excerpts
                  |
       Need more evidence? --> Additional indexed searches
                  |
       Answerability check --> Answer and citation validation
                  |
       QueryResult: answer, status, sources, citations, trace
```

A search invocation means one query passed to the shared retriever. That invocation can perform both a vector search and a BM25 search. The builder's four-search limit does not mean four total model or backend calls.

## 2. Entry points and indexed content

`ProjectRuntime.query_result()` loads the project's index if needed, serializes access through a query lock, calls the query pipeline, and adds `index_version` to its trace. Calling `QueryPipeline` directly bypasses this runtime wrapper. The string-only `query()` interface returns the answer from the same result.

Search results contain segment IDs, page URLs, text, and optional heading hierarchy and incoming-link metadata. Multiple segments from the same page can remain in the final candidate set.

Normal ingestion merges pages whose complete cleaned chunk lists are identical before embedding, retaining equivalent URLs in `metadata.source_urls`. Query-time sources and citations still use the canonical URL. This does not deduplicate partially overlapping chunks or add source-diversity ranking. See [chunking and ingestion behavior](CHUNKING_LOGIC.md) for details.

Retrieval searches indexed content; it does not browse arbitrary live pages, fetch neighboring sections, or follow URLs during a normal query. An optional `recrawl_fn` callback can be invoked after an empty initial search when `retry_on_empty=True`. A callback must actually be supplied: the standard `build_runtime()` wiring does not provide one.

## 3. Shared search and ranking

### Semantic search

For each query, the retriever generates an embedding and searches FAISS. The current FAISS implementation normalizes stored and query vectors, so its inner-product scores represent cosine similarity.

When `score_threshold > 0`, vector hits below that threshold are removed. The threshold applies to vector hits only; BM25 can still return a segment that did not pass the vector threshold.

### BM25 keyword search

With `enable_hybrid=True`, the same query also searches text in index metadata using BM25. Tokenization applies Unicode normalization, case folding, removal of combining marks, and extraction of alphanumeric tokens at least two characters long. It supports Unicode words, including Arabic, but does not implement language-specific stemming or synonym expansion.

BM25 uses `k1=1.5` and `b=0.75`. Its index is prepared lazily and held by the retriever. It searches `text`, falling back to `summary` when text is unavailable. Only positive-scoring lexical hits are returned, up to `max(8, k)` for a search requesting `k` vector hits.

### Deduplication and reciprocal rank fusion

Candidates are keyed by their string `segment_id`, falling back to string `id`. Repeated occurrences of a segment merge into one candidate; different segments on one URL remain separate.

The fusion score is:

```text
fusion_score(segment) = sum(1 / (60 + best_rank))
```

Ranks start at one. The implementation retains the best rank for each search query, origin tag and channel. A hashed query identity distinguishes different follow-ups sharing an origin. Candidates sort by descending fusion score, then segment ID for ties.

This is rank fusion, not an LLM or cross-encoder reranker. The current ranking does not explicitly optimize subquestion coverage or source diversity. The `anchor_boost` and `section_boost` parameters remain accepted and stored, but the current fusion formula does not apply those numeric boosts.

## 4. Builder mode

### Route the request

The initial planner uses the question and up to 1,800 characters of supplied conversation memory. It returns concepts, up to six answer requirements, and one route:

| Route | Search and answering behavior |
| --- | --- |
| `retrieve_new` | Searches and answers the new question without conversation memory |
| `retrieve_followup` | Searches a standalone rewrite, falling back to the original question; answering includes the supplied memory and current question |
| `transform_only` | Rewrites or reformats the prior conversation without retrieval |

Requirements describe what the answer must establish, rather than words that must appear. If usable requirements are absent, the search question becomes the single requirement. Concepts remain available for compatibility and tracing; literal concept coverage no longer controls builder retrieval.

A successful memory-only transformation has `status="unverified_transformation"`, `supported=False`, and no source citations. Without prior memory, the transformation route returns an explanatory unsupported response.

### Search and assess the actual context

Builder performs the initial search, optionally retries after a configured recrawl, fuses the results, and assembles the evidence context. An empty first search can still proceed to planning and be rescued through alternate formulations.

The assessment call receives:

- The search question and numbered answer requirements.
- The assembled evidence, including source labels and any context trimming.
- Previously executed queries.
- Optional indexed anchor and heading hints.

For each requirement, the planner proposes `supported`, `partial`, or `missing`, with exact excerpts and evidence IDs for supported or partial coverage. It can also propose up to three focused searches for unresolved information. For example, a page saying “see our fees page” does not establish the fee amount.

Code validates cited IDs and checks each excerpt against both that segment's original text and its supplied context block. Invalid support is treated as missing. Requirements omitted by the planner remain missing. Malformed assessment structure stops further planning and preserves the retrieved evidence for the normal answer/fallback path.

These checks verify provenance and excerpt membership. Whether an excerpt logically answers the requirement remains an LLM judgment.

### Use website structure as search hints

Builder collects hints from the first eight fused candidates. Incoming-link anchor text is enabled by `enable_graph_expansion`; heading hierarchy is enabled by `enable_section_expansion`. Each hint list is deduplicated, capped at 12 entries, and each entry is capped at 200 characters.

The planner chooses queries informed by these hints. Builder does not execute classic's automatic expansion loops. Its capability trace reports `expansion_strategy="planner_guided"`. Hints are search clues, not approved answer evidence.

Candidates are retained and deduplicated deterministically. The current builder path does not execute planner-directed chunk deletion. Older helper methods for literal coverage and chunk-dropping decisions remain in the class for compatibility but are not used by this loop.

### Bound the loop

Builder permits at most four search invocations: the initial query and up to three additional searches. A search after a recrawl consumes one of those additional slots, even though it intentionally repeats the initial query. Other repeated queries are skipped after whitespace normalization and case folding. Follow-up query strings are limited to 300 characters.

`builder_max_rounds` defaults to one. Builder assesses before deciding on a follow-up batch, then assesses the resulting context again. With zero rounds it still assesses the initial context but runs no follow-up batch. More rounds permit reassessment without increasing the four-search budget.

The loop can stop for these reasons:

| Trace value | Meaning |
| --- | --- |
| `sufficient_evidence` | Every requirement has validated planner support |
| `round_limit` | The configured follow-up rounds are exhausted |
| `search_budget` | Four searches have been executed |
| `no_new_queries` | No proposed query remains after filtering tried queries |
| `no_new_evidence` | The preceding follow-up batch added no segment IDs |
| `deadline` | The remaining operation scheduling deadline has expired |
| `planner_unavailable` | No planner model is attached |
| `planner_failure` | A planner call or response parsing raised an exception |
| `invalid_assessment` | Assessment JSON or its required structure is invalid |
| `prompt_budget` | The conservative planner prompt preflight exceeds its budget |

Runtime-mediated retrieval uses the operation's remaining deadline. Provider wrappers check it before and after calls; built-in SDK adapters receive bounded timeouts. Arbitrary injected blocking clients must honor the timeout contract themselves. Direct pipeline calls without an operation retain the legacy 30-second scheduling fallback and do not provide the full runtime contract.

After retrieval stops, builder still runs the final answerability check when enabled. A retrieval stop reason describes the search controller, not the final answer's support status.

## 5. Classic mode

Classic prepends supplied memory to the search question and includes it when answering. It searches first and, if configured, retries after an empty result using `recrawl_fn`. If results remain empty, it returns a fallback immediately; it does not try query rewrites to rescue that case.

When initial results exist, classic checks answerability first. If insufficient, it performs enabled structural expansion:

- **Graph/anchor expansion:** inspects up to 12 seed results and five incoming links per seed. It searches `anchor text + question`, requesting three vector hits per query, plus BM25 hits when enabled.
- **Section expansion:** inspects up to 10 seed results and searches `question + top-level heading`, with the same three-vector-hit request.

These are additional indexed searches. They do not fetch the linked page or directly retrieve neighboring chunks. Query deduplication is local to each expansion call.

If the assembled context is judged sufficient, classic generates an answer. Otherwise, with `enable_rewrite=True`, it runs up to two rewrite hops. The LLM receives the search question plus heading/anchor hints and can return several subqueries. The pipeline runs at most three rewrite searches across both hops, expands their results when configured, merges candidates, and checks answerability again.

The controller's three-rewrite limit excludes initial, recrawl, graph and section searches, but the shared operation search cap includes all of them. Runtime defaults permit four searches total. Its tried-query comparison uses exact strings rather than builder's normalized comparison.

## 6. Context, answerability, and final answers

### Assemble the context

Both modes take fused candidates in order, cap the candidate count, and assemble original text, falling back to `text` if `original_text` is absent. Each block contains an evidence ID, source URL, optional heading hierarchy, and text.

The assembler skips duplicate IDs and empty text. Labels and separators count against the character budget. It trims an oversized block near a word boundary and stops when space is exhausted. `sources` describes included context segments; it is not necessarily the same list as the answer's explicit citations.

The default character ceiling is 12,000. When a model context window is known, the context helper reserves the larger of 2,000 tokens or 15% of that window, estimates three characters per remaining token, and uses the smaller of that estimate and the character ceiling. This is a context-sizing heuristic, not an exact token count.

### Judge answerability

The standard chat agent asks the LLM whether the assembled context fully answers the question. It no longer truncates this check to the first 6,000 characters. Ordinary probe failures produce a negative result; Core budget/cancellation failures propagate.

This check is separate from builder's requirement assessment. Disabling `enable_answerability_check` skips the final/early answerability branches; it does not disable builder's evidence assessment or follow-up planning.

### Generate and validate the answer

With the standard `WeblyChatAgent`, generation requests structured JSON containing an answer, status, citations, and missing information. Status is `answered`, `partially_answered`, or `unsupported`.

Validation checks the response shape, permitted source IDs, nonempty exact excerpts in that ID's supplied text and original segment, and at least one citation for a supported answer. A quote visible only under another ID is rejected. A partial answer must name missing information. Invalid output receives one budgeted repair attempt, then an unsupported fallback.

`supported=True` covers both `answered` and `partially_answered`; it does not mean that every part of the question was answered. Citation membership checks also do not prove that every generated claim follows from its cited excerpt.

Core providers supply actual token counters. Planner and grounded-answer preflights include output/framing reserves; byte counting remains only for unwrapped legacy clients. Oversized final evidence is repacked in bounded steps, preserving the trusted ID/text map. Both initial and repair prompts are checked. Shared operation accounting reserves every attempt before work and protects a final-answer allowance. Builder marks an answer partial when a valid evidence assessment still has missing requirements.

### Best effort and fallback

If answerability is negative but candidates remain, `allow_best_effort=True` lets the standard agent attempt the same grounded generation and validation. It does not authorize unsupported facts. If best effort is disabled, the response composer can return an unsupported explanation and helpful links. Empty results produce an unsupported no-results message.

Custom chat agents lacking `answer_grounded` use the legacy `answer()` / `answer_with_support()` interfaces. Those compatibility paths do not provide the standard structured citation-validation guarantees.

## 7. Configuration and result tracing

| Setting | Current default or behavior |
| --- | --- |
| `retrieval_mode` | `builder`; project setting |
| `builder_max_rounds` | `1`; project setting, ignored by classic |
| `score_threshold` | `0.5` in project configuration; direct `QueryPipeline` default is `0.0` |
| `enable_hybrid` | `True`; pipeline constructor option |
| `enable_graph_expansion`, `enable_section_expansion` | `True`; constructor options; planner hints in builder, automatic searches in classic |
| `enable_rewrite` | `True`; constructor option controlling classic rewrites, not builder follow-ups |
| `enable_answerability_check` | `True`; constructor option |
| `allow_best_effort` | `True`; constructor option |
| `top_k_first_pass` | Defaults to `max(chat_agent.top_k, 8)` |
| `top_k_second_pass` | Defaults to `max(chat_agent.top_k, 10)` |
| `max_results_to_consider` | Constructor default is 30; positive explicit caps are honored exactly |
| `max_context_chars` | `12000`; constructor option |

Pipeline constructor options are not all exposed as saved project settings. The pipeline receives a `memory_context` string from its caller; it does not itself choose the chat history window.

`QueryResult` includes `answer`, `supported`, `status`, `sources`, `citations`, `missing_information`, and `trace`. Builder retrieval traces additionally expose requirements, per-requirement coverage, assessments by round, executed queries, search count, new segment counts per batch, capabilities, expansion strategy, and stop reason. Its compact `coverage.missing` list includes both partial and missing requirements. Memory-only transformation traces have a smaller field set.

Classic records paths such as `answerable_initial`, `answerable_expanded`, `answerable_hop_1`, `best_effort`, or `fallback`. Runtime-mediated results include index version and operation usage. Debug-off runtime traces use an allowlist that excludes raw questions, evidence, assessments and queries; direct/debug pipeline traces can contain sensitive content.

## 8. Practical limits and source map

Answer quality depends on crawl coverage, extraction, chunk boundaries, indexed text, embedding quality, and model judgments. There is currently no separate semantic reranker, explicit coverage/diversity selection algorithm, live-page fallback, neighbor-chunk fetch, or automatic resolution of conflicting institutional facts. No real-site accuracy or latency advantage should be inferred from the deterministic tests alone.

The implementation is concentrated in:

| Source | Responsibility |
| --- | --- |
| [Runtime](../webly/runtime.py) | Load index, invoke query pipeline, attach index version |
| [Query pipeline](../webly/pipeline/query_pipeline.py) | Mode routing, search control, limits, answer/fallback selection |
| [Retriever](../webly/pipeline/query_retriever.py) | Semantic/BM25 search, structural hints and expansion, rank fusion |
| [Context builder](../webly/chatbot/context_builder_agent.py) | Request routing, evidence assessment, planner-output validation |
| [Context tools](../webly/pipeline/query_context.py) | Context assembly, supplied excerpts, source references |
| [Chat agent](../webly/chatbot/webly_chat_agent.py) | Rewrites, answerability, grounded generation and citation checks |
| [Response composer](../webly/pipeline/query_response_composer.py) | Legacy best-effort responses and helpful-link fallbacks |
| [Result types](../webly/query_result.py) | `QueryResult` and `SourceRef` |

Behavioral regression coverage includes [builder evidence tests](../tests/test_builder_evidence.py), [query contracts](../tests/test_query_pipeline_contracts.py), [golden query cases](../tests/test_query_golden_cases.py), and [real FAISS retrieval tests](../tests/test_r0_retrieval.py). These verify control flow and provenance checks; they do not establish general answer accuracy across websites.
