# Current chunking logic

This document explains the current ingestion implementation: how crawled HTML becomes chunks, how chunks become embedding segments, and which text and metadata retrieval receives. For the query-time flow, see [Current retrieval logic](RETRIEVAL_LOGIC.md).

## 1. Overview: two stages of splitting

Webly performs structural chunking first and embedding-size splitting second. A **chunk** is a window of words from a heading-delimited section. An **embedding segment** is one input to the embedding model, derived from that chunk or its optional summary.

```text
Crawled record: URL + HTML
            |
SemanticPageProcessor
            |
Clean HTML --> identify headings and content blocks
            |
SlidingTextChunker: section-local word windows
            |
Chunk text + heading hierarchy + links + word offsets
            |
Deduplicate identical cleaned pages; retain source URL aliases
            |
Optional summary used as embedding input
            |
Split embedding input to fit the embedder's budget
            |
Embed each segment and attach original chunk evidence
            |
Index records: vectors + text + segment IDs + metadata
```

Both builder and classic retrieve from the same indexed records. Selecting a retrieval mode does not change chunk boundaries.

| Property | Current default or behavior |
| --- | --- |
| HTML chunker | `DefaultChunker`, an alias for `SlidingTextChunker` |
| Page processor | `SemanticPageProcessor` |
| Maximum initial chunk size | 350 whitespace-separated words |
| Word overlap | 50 words within one section |
| Default window step | 300 words |
| Crossing section boundaries | No overlap or merging across sections |
| Embedding split size | Depends on embedder limits and safety ratio |
| Evidence stored by normal ingestion | Full original chunk text, even when embedding input is a smaller segment or summary |

Despite names such as `SemanticPageProcessor`, the default chunker does not use embeddings or an LLM to discover topic boundaries. It uses HTML headings and fixed word windows.

## 2. HTML preparation and block extraction

`IngestPipeline` constructs a `SemanticPageProcessor` with the default text extractor and chunker. The semantic processor calls the extractor for compatibility but ignores its returned text. It passes the original HTML and URL into the chunker to preserve structural information.

Consequently, extractor-only transformations, such as its Cloudflare email preprocessing, are not automatically passed to this chunker. Chunking is not performed on the cleaned text returned by Trafilatura.

### Remove selected HTML elements

The chunker parses HTML with BeautifulSoup's `html.parser` and removes these elements and their contents:

```text
script, style, noscript, form, nav, footer, header, aside
```

It then uses the page body when available, otherwise the parsed document. Removal is tag-based, not a learned main-content detector. Useful information inside one of the removed elements is also removed.

### Extract content blocks

The recognized block tags are:

```text
p, li, pre, code, blockquote, td, table
```

The chunker walks document descendants, so these blocks can be nested inside ordinary containers such as `div` or `section`. It skips a recognized block when another recognized block is an ancestor. For example, a `code` element inside `pre`, or a paragraph inside a list item, is represented through its outer block rather than being extracted twice.

Ordinary block text comes from `get_text(" ", strip=True)`. Only blocks containing **more than three whitespace-separated words** enter the normal sectioning path. A short standalone value such as “Deadline: June 1” can therefore be omitted.

This filter is per block, not a minimum final chunk size. A chunk can be small when its section is short or when it is the last window of a longer section.

### Tables, code, and links

Tables receive a lightweight Markdown-like conversion: cells form pipe-separated rows, and a separator is inserted after the first row when there are multiple rows. This is not a full table parser: the first row is treated as a header, and spans or complex layout are not reconstructed.

Code and preformatted blocks are extracted as text. Subsequent word splitting and joining collapses whitespace, including indentation and line breaks. Table row breaks are also flattened in the final chunk text, although pipe characters remain.

Anchors with an `href` and nonempty visible text are collected from each accepted block as `anchor_text` and `target`. The target remains the HTML `href`; this method does not resolve relative links into absolute URLs.

## 3. Heading-based sections

The chunker recognizes `h1` through `h6`. It maintains a heading breadcrumb as it walks the page in document order.

At **every heading**, it flushes any accumulated content blocks into a section, then updates the breadcrumb for the new heading level. A deeper heading extends the path; a heading at the same or higher level replaces the corresponding suffix. Missing heading levels are represented temporarily by empty placeholders and removed before chunk creation.

For example:

```html
<h1>Admissions</h1>
<p>General information about applying here.</p>
<h2>Fees</h2>
<p>Annual tuition costs five thousand dollars.</p>
<h2>Deadlines</h2>
<p>Applications must arrive before June first.</p>
```

Produces separate sections with these breadcrumbs:

```text
[Admissions]
[Admissions, Fees]
[Admissions, Deadlines]
```

The heading text is normally metadata, not part of the chunk body. It is later displayed as a breadcrumb during retrieval context assembly. Content preceding the first heading can form a section with an empty hierarchy. Headings without accepted content blocks do not create chunks by themselves.

If the document has no headings, accepted blocks are collected into one section with an empty hierarchy.

### Whole-body fallback

If section processing produces **no chunks at all**, the chunker takes all remaining body text and applies the word-window splitter with an empty hierarchy and no anchors. This can preserve text in unsupported tags or short blocks when nothing else was extracted.

The fallback is page-wide, not section-wide. If another section already produced chunks, omitted short blocks and text outside recognized blocks are not recovered by this fallback. If the cleaned body has no text, the chunker returns no chunks.

## 4. Sliding word windows

Within each section, accepted block texts are flattened into a single word list using Python's `split()`. The chunker then applies:

```text
effective_overlap = min(overlap, max_words - 1)
step = max(1, max_words - effective_overlap)
end = min(start + max_words, section_word_count)
```

It emits a window starting at zero, advances by `step`, and stops as soon as a window reaches the section's end. The default is 350 words per window, with a 300-word step.

For an illustrative section of 720 words:

| Window | `start_word` | `end_word`, exclusive | Word count |
| --- | --- | --- | --- |
| 0 | 0 | 350 | 350 |
| 1 | 300 | 650 | 350 |
| 2 | 600 | 720 | 120 |

Adjacent windows share 50 words. A section of 350 words or fewer produces one chunk, not an additional overlap-only tail. Windows can split sentences, list items, code, and table content; original block boundaries do not constrain window boundaries.

`start_word` and `end_word` are zero-based offsets into the **section's flattened word list**. They are not page-global offsets, HTML positions, model token offsets, or embedding-segment offsets. A new section starts its offsets at zero.

The chunker's `tokens` field actually counts whitespace-separated words. `SemanticPageProcessor` carries that value into its `length` field. It is not the number of tokens the embedding model will consume. Debug raw-chunk records instead write `length` as character count.

### Assign anchors to windows

Every anchor in a block is assigned that block's starting word offset. A window receives the anchor if this offset falls inside its `[start_word, end_word)` range.

This is approximate, not the link's exact word position. A link physically appearing late in a long block can be attached only to an earlier window containing the block's start. An anchor may also appear in two windows when its assigned offset lies in their overlap.

## 5. Chunk metadata and IDs

The raw chunker emits:

| Field | Meaning |
| --- | --- |
| `id` | Deterministic raw chunk identifier |
| `url` | Supplied page URL |
| `text` | Flattened window text |
| `tokens` | Word count, despite the name |
| `start_word`, `end_word` | Section-local window bounds |
| `hierarchy` | Heading breadcrumb |
| `outgoing_links` | Anchors assigned to this window |

The page processor adds `chunk_index`, a zero-based index across all chunks from that page, and maps the word count to `length`. This page-level index differs from the section-local index used by the raw ID generator.

The raw ID is a 10-byte BLAKE2b digest, encoded as 20 hexadecimal characters, of:

```text
URL | heading breadcrumb joined with " > " | section-local chunk index
```

The raw ID does not include the text. Repeated sections with the same breadcrumb and local index can produce the same raw ID. It should not be treated as a globally unique content hash.

Normal ingestion replaces the indexed `id` with a SHA-256 `segment_id`. Its inputs are:

```text
page_version_id = SHA256(URL + null byte + raw HTML)
segment_id = SHA256(page_version_id + page chunk_index + raw chunk ID
                    + embedding segment index + "chunker-v2")
```

The actual segment-ID serialization uses colon separators. The page-level chunk index distinguishes repeated same-named sections. Changes to the raw HTML change the page version and therefore its segment IDs, even if the visible chunk text is unchanged.

IDs are version-derived, not a complete fingerprint of every processing option. The numeric window settings, summary text, and summary model are not explicitly included in the segment-ID formula. Rebuild the index after changing chunking or embedding behavior rather than assuming IDs alone detect every processing change.

## 6. Embedding-size splitting and original evidence

### Deduplicate cleaned pages first

Before summarization or embedding, normal ingestion fingerprints each page's ordered list of chunk headings and whitespace-normalized text. URLs, IDs, links, and timestamps do not participate. The first matching page in crawl-file order becomes canonical; subsequent identical pages add their URLs to `metadata.source_urls` on every canonical segment rather than generating additional summaries, vectors, or records. Original evidence and canonical IDs are unchanged.

This catches cases such as EUI's `?page=6` and `?page=7`, whose retained chunks are identical even though their full-page crawler hashes differ. Real pagination with different retained text or headings remains distinct. Pages sharing only some chunks are not merged. Deduplication state resets on every transform and is not shared across projects or builds. Alias link graphs are not merged, and citations continue to display canonical URLs.

### Fit embedding input to the model budget

Before embedding, ingestion saves the chunk text as `original_text`. With summarization enabled and a summarizer available, a successful summary becomes the embedding input and is retained as `summary`. A missing or failed summary falls back to the original chunk text.

The shared `chunk_text_for_embedding()` helper then checks input size. It discovers the first positive integer limit among `max_input_tokens`, `max_tokens`, `context_size`, and `max_seq_len`, falling back to 8,192. It multiplies this by the embedder's `safety_ratio`, or the helper's default of 0.9, to obtain its effective ceiling.

If `count_tokens()` is available, the helper uses it; otherwise, or if counting fails, it uses UTF-8 byte length as a conservative estimate. The current OpenAI wrapper configures 7,000 and 0.8, giving a helper ceiling of 5,600 counted tokens. These are implementation settings, not a claim about a provider's published model limits. The Hugging Face wrapper inherits the base embedder's generic 8,192 limit without overriding it for the selected model, and exposes no token counter. The helper therefore uses that inherited limit, its default safety ratio, and the byte estimate; that does not guarantee alignment with the underlying model's tokenizer or truncation behavior.

Oversized input is split progressively:

1. Group paragraphs separated by blank lines while their counted sizes fit.
2. For oversized paragraphs, group sentences split after `.`, `!`, or `?` followed by whitespace.
3. For oversized sentences, split into fixed character slices.
4. Recount assembled pieces, including separators, and repeatedly bisect any remaining oversized piece until it fits.

A single character that exceeds the effective ceiling raises an error. This second stage adds no overlap. Since structural chunks are already whitespace-flattened, paragraph boundaries are generally unavailable unless a summary or another input source reintroduces them.

Each final input part gets its own vector and indexed record. In the normal ingestion path:

- `embedding_text` contains only the part sent to the embedder.
- `text` and `original_text` both contain the **entire original structural chunk**.
- `metadata.seg_index` and `metadata.seg_count` identify the part within its parent chunk.
- `metadata.chunk_id` is `URL#chunk_<page-level chunk_index>`.
- Heading hierarchy, chunk-level links, and section-local word offsets remain inherited from the parent chunk.

Therefore, multiple vectors can point to identical full chunk evidence. A segment's word offsets and `length` still describe its parent structural chunk, not its smaller embedding input. “Original text” here means cleaned, flattened chunk text, not a byte-for-byte excerpt of raw HTML.

Ingestion also attaches page-level outgoing and incoming links from `graph.json` under `metadata`, plus page URL and crawl time. These page-level links are distinct from the top-level window-assigned `outgoing_links`.

### Separate processed-record utility

`EmbedAndStorePipeline` also uses the embedding-size helper, but it starts from an existing processed-record field and does not perform HTML sectioning. Its records use `parent_id__seg_<index>` IDs and store the embedding part as `text`. It does not reproduce the normal ingestion path's full-original-evidence record shape. The two paths should not be assumed interchangeable.

## 7. Configuration, inspection, and failure behavior

`max_words` and `overlap` are chunker constructor parameters. The defaults reject nonpositive `max_words` and negative overlap. Overlap larger than the window is clamped internally to `max_words - 1`, producing a one-word step.

The standard ingestion constructor creates the default chunker directly; saved `ProjectConfig` and the UI do not expose window size or overlap. Existing application code can replace the chunker before ingestion, for example:

```python
from webly.processors.text_chunkers import SlidingTextChunker

# ingest_pipeline is an existing IngestPipeline instance.
ingest_pipeline.page_processor.chunker = SlidingTextChunker(
    max_words=500,
    overlap=75,
)
```

Custom strategies can implement `TextChunker.chunk_html(html, url)` and return structured chunk dictionaries. `SemanticPageProcessor` expects `text` and carries the supported metadata fields forward. The older `PageProcessor` is not the active default path and has a different calling/output convention.

With ingestion debug mode enabled, `raw_chunks.jsonl` records the page URL, page-level chunk index, raw chunk text, and character length. Summary debugging writes previews separately. The raw-chunk debug file does not contain every structural metadata field; use processed/index metadata when inspecting headings, links, or final segment IDs.

Valid pages with no extractable content are skipped and reported, so an empty login page does not abort otherwise usable ingestion. Missing or incorrectly typed URL/HTML, malformed crawl records, extraction exceptions, and embedding failures remain fatal. If no usable evidence remains, the attempt fails without publishing an empty replacement. Debug streams close on both success and failure.

Indexing returns an additive `ingest_summary` with `pages_total`, `pages_indexed` (canonical page records processed), `pages_skipped`, `duplicate_pages`, `chunks_skipped`, and `segments_indexed`. `ingest_report_path` points to `ingest_report.json` beside the crawl file when that report was written successfully. The JSON report contains timestamps, the summary, skipped URL/line/reason entries, and duplicate-to-canonical mappings. Its status is `transformed` for a direct transformation, `completed` after publication through `run()`, or `failed` when the attempt fails. Counters in a failed report describe attempted work, not a newly active index.

The Run tab displays the summary, skipped-page warning, report path, and actionable failure message. The report is replaced atomically per attempt; raw crawl files are not changed. Rebuild using **Index only** to apply deduplication to an existing project.

Snapshot publication syncs files using writable handles and replaces the active pointer atomically, with bounded retries for Windows sharing conflicts. POSIX directory syncing remains enabled; Windows explicitly skips unsupported directory syncing, giving weaker directory durability across power loss. Other write/sync errors still fail publication. Failed ingestion invalidates the runtime's cached database so the next query reloads the still-active snapshot.

## 8. Retrieval consequences and current limits

- Heading metadata helps builder formulate focused searches and classic generate expansion queries, even though headings are normally absent from embedded chunk text.
- Overlap can preserve information around window boundaries but also introduces repeated evidence. Different segment IDs with overlapping or identical text are not automatically deduplicated by content during rank fusion.
- Sentence, table, code, and list boundaries can be split or flattened. This is structure-aware word chunking, not semantic or format-preserving segmentation.
- Short facts and useful text in removed elements can be lost. The whole-body fallback only helps when the page otherwise yields no chunks.
- Chunk-level anchor assignment is approximate; graph-derived page-level incoming links provide a separate source of structural hints.
- Summary-based embeddings may emphasize different information from the original chunk, while final answer citation checks still use original evidence.
- Word limits are not model-token guarantees, and the embedding helper's fallback is not a model-aware tokenizer.

These are current behavior boundaries, not changes made by this document. Chunk quality must ultimately be checked against representative website content and questions.

## Source map

| Source | Responsibility |
| --- | --- |
| [HTML chunker](../webly/processors/text_chunkers.py) | HTML cleanup, sections, windows, anchors, raw IDs |
| [Page processors](../webly/processors/page_processor.py) | Feed raw HTML into the chunker and carry metadata forward |
| [Text extractor](../webly/processors/text_extractors.py) | Separate extraction path called by the semantic processor |
| [Ingestion pipeline](../webly/pipeline/ingest_pipeline.py) | Summaries, embedding parts, original evidence, segment IDs, graph metadata |
| [Embedding split helper](../webly/pipeline/embedding_text.py) | Input budgets and progressive splitting |
| [OpenAI embedder](../webly/embedder/openai_embedder.py) | Configured input limit, safety ratio, token counting |
| [Hugging Face embedder](../webly/embedder/hf_sentence_embedder.py) | Sentence-transformer embedding wrapper |
| [Processed-record utility](../webly/pipeline/embed_and_store.py) | Alternative embedding path with a different record shape |

Existing regression coverage includes [nested block/window checks](../tests/test_r0_retrieval.py), [embedding input limit checks](../tests/test_embedding_text_limit.py), and [ingestion integration tests](../tests/test_integration.py). These do not establish that every website's layout and facts survive extraction correctly.
