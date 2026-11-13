# Current chunking logic

This describes Core 0.2. Both retrieval modes consume the same chunks and vectors;
choosing builder or classic does not change ingestion boundaries.

## HTML to structural chunks

`SemanticPageProcessor` passes original HTML to `SlidingTextChunker` (also named
`DefaultChunker`). The separate text extractor is invoked for compatibility but
its transformed text is not the chunker's input. BeautifulSoup parses the HTML
and removes `script`, `style`, `noscript`, input controls, textareas, buttons and
HTML comments. Navigation, footers and forms retain published text, including
form instructions, legends, labels and option labels. Input values, hidden values,
textarea contents and button text stay excluded even from the body fallback.
Headers and asides are retained because useful evidence can appear there. This is tag-based
cleanup, not a learned main-content detector or JavaScript renderer.

Heading tags `h1` through `h6` maintain a breadcrumb path. Each encountered heading
ends the preceding section; chunks do not cross these sections. Empty levels are
removed from the final breadcrumb. Heading text becomes metadata, while the body
blocks become evidence. Query context later prefixes that evidence with headings.

The DOM traversal recognizes paragraphs, list items, blockquotes, tables, table
cells and code/preformatted blocks. Descendants inside a recognized block are not
extracted again. Bare text in ordinary containers such as `div` or `span` is also
retained. There is no minimum word-count filter: `Deadline: June 1`, a name or a
single value survives even when longer paragraphs are present. If no structural
content exists, the cleaned body's plain text is a final fallback.

Ordinary text normalizes whitespace through BeautifulSoup. Tables are interpreted
from cells before rendering; the first ordinary data row is never promoted to a
header. Explicit `headers` associations take precedence, including an explicitly
empty association. Otherwise `scope`, row/column groups and span geometry determine
relationships. Leading all-`th` rows and a leading `th` in a mixed data row supply
conservative inferred relationships, marked in metadata. Headerless rows retain
all values with neutral row positions. Captions, empty cells, merged cells and
nested tables survive; nested text is extracted once.

Each table is bounded to 100,000 occupied grid positions, 1,000 columns, 100,000
header associations and 10,485,760 accounted expanded evidence/provenance characters. Malformed or
excessive structure falls back to its own ordered text, marked uncertain, rather
than guessing column meanings. No LLM is used for table interpretation.
Code uses original line breaks inside triple-backtick fences. Oversized code
slices retain fencing; syntax-aware parsing is not performed.

## Packing and overlap

Defaults are `max_words=350` and `overlap=50`. Consecutive complete blocks are packed
until the next block would exceed the target. Block boundaries and blank lines
are retained. A single oversized block is sliced by whitespace-token positions
with a 300-word step, preserving 50-word overlap. Overlap applies within an
oversized block; whole neighboring blocks are not copied into the next chunk.
Oversized table rows reserve part of the word budget for continuation context,
capped at 512 characters and one third of the word target. Full values survive in
the evidence slices; continuation descriptors retain intersecting cell coordinates
and header references without repeating full source rows. Added code fences can
make rendered text exceed the target slightly;
the later embedding tokenizer split enforces the actual provider ceiling.

`max_words` must be positive and `overlap` nonnegative. An overlap at least as large
as the window produces a one-word step. These parameters belong to the chunker
constructor; saved project configuration does not expose them.

```python
from webly.processors.text_chunkers import SlidingTextChunker

runtime.ingest_pipeline.page_processor.chunker = SlidingTextChunker(
    max_words=500, overlap=75,
)
```

Custom chunkers implement `chunk_html(html, url)` and return dictionaries containing
`text`; headings, blocks and links are optional supported metadata.

## Metadata and provenance

Each structural chunk carries its URL, heading `hierarchy`, text, deterministic
chunker ID, outgoing anchors, `tokens` (a historical name for whitespace word
count), and section-local `start_word` / `end_word` positions. The normal ingest
pipeline assigns URL-based chunk IDs and final segment IDs independently.

Every extracted block has a `region`: `main`, `navigation`, `footer`, `form` or
`unknown`, derived from its nearest semantic ancestor or explicit ARIA landmark.
This metadata does not exclude regions or apply ranking penalties. Table blocks
also carry `table_id`, `row_index`, cell coordinates/spans/header associations and
`structure_status`. Split-row descriptors use `cell_text_basis="source_table"`;
their full values remain in evidence slices and the frozen source HTML.

`blocks` contains rendered text, `kind`, deterministic `block_id`, anchors,
`start_char`, `end_char`, word positions and
`offset_basis="section_extracted_text"`. Character ends are exclusive. Positions
refer to the extracted section representation joined with two newlines. Table
rows in that representation include repeated headers. They are not raw HTML byte
offsets or DOM coordinates. Artificial code fences/headers added to a split are
presentation context and do not extend its underlying slice offsets. Do not use
these positions to cut raw HTML or assume they identify embedding-token slices.

Chunk-level anchors follow their source block and may repeat across overlapping
slices. Page-level incoming/outgoing links are also loaded from `graph.json` into
record metadata; these are separate structural hints for retrieval.

## Page deduplication and embedding segments

Ingestion fingerprints each page's complete ordered cleaned chunk list, including
headings and normalized text, before summaries or embeddings. Identical pages
share the first page's canonical vectors; equivalent URLs are retained in
`metadata.source_urls`. Different retained text/headings remain distinct. This is
exact whole-page evidence dedup, not near-duplicate detection or global chunk
dedup. Query citations still display canonical URLs. Discovery happens earlier in
the crawler, so identical visible pages with different links can both reveal
their destinations. Evidence dedup does not prune the crawl frontier.

The original structural chunk is saved as `original_text`. Optional summarization
can produce a different `embedding_text`; summary failure falls back to original
text unless it is a Core budget/cancellation failure. Final citation checks use
original evidence, not the summary as a factual source.

`chunk_text_for_embedding` uses the wrapped provider's declared input limit and
actual `count_tokens` implementation, with its safety ratio. It first groups
paragraphs, then sentences, then character slices, recounting and bisecting until
every part fits. A single unfit character fails explicitly. This stage adds no
overlap. The strict Core bundle requires token counters; byte-length fallback
exists only for direct legacy utility use. Hugging Face adapters use the selected
model's tokenizer/max sequence length and reject oversized input before encoding.

Each embedding part creates one vector and record. Normal ingestion stores:

- `embedding_text`: exactly the part embedded.
- `text` and `original_text`: the entire parent structural chunk.
- `metadata.chunk_id`, `seg_index` and `seg_count`: parent and segment identity.
- Parent headings, blocks, word positions, links, source aliases and crawl time.

Multiple vectors can therefore reference the same complete evidence chunk.
Block/word offsets describe the parent evidence, not the smaller embedding part.
The separate `EmbedAndStorePipeline` utility consumes already processed fields
and stores embedding parts as text; it does not reproduce this HTML pipeline's
full evidence record shape.

## Failure, inspection and publication

Valid pages without extractable text are skipped and reported. Malformed records,
invalid fields, extraction errors or embedding failures abort the build. An
all-empty build cannot replace the active corpus. `ingest_summary` records total,
canonical, skipped and duplicate pages, skipped chunks and indexed segments.
`ingest_report.json` beside the frozen results records skipped reasons and
duplicate-to-canonical aliases. Debug raw chunks can contain private website
content; enable them only under the host's access/retention policy.

Core indexes an explicitly completed immutable run, checks its hashes again
before publishing and requests exact-candidate approval for removed source URLs.
Snapshots publish through a checked atomic active pointer. Extraction identity is
now `blocks-v2`: caches, snapshots, operation replay and removal approvals use this
revision. Rebuild older snapshots with a new operation ID from validated saved HTML;
old crawl-run manifests remain unchanged and recrawling is unnecessary. Errors expose
`not_committed`, `committed` or `uncertain` outcomes; do not infer failure solely
from whether an exception was raised. See [integration and migration](CORE_INTEGRATION.md).

## Limits and validation

This remains HTML heading/block packing with word targets. It does not infer
semantic topics, render JavaScript, read PDFs/images, reconstruct every table,
automatically remove repeated site chrome or guarantee every fact survives any
website layout. Hidden or interactive control contents are deliberately excluded;
there is no automatic cross-page boilerplate removal or region-based ranking yet.
Overlapping or partially duplicate chunks can remain in an index. Summary-based
embeddings can emphasize different information from original evidence.

Regression fixtures cover nested blocks, short facts, bare containers, tables,
code, multilingual text, token limits and deduplication. General extraction and
answer quality require the real bilingual corpus described in the
[implementation report](CORE_V2_IMPLEMENTATION.md).

Sources: [chunker](../webly/processors/text_chunkers.py),
[table interpretation](../webly/processors/table_extraction.py),
[page processor](../webly/processors/page_processor.py),
[ingest pipeline](../webly/pipeline/ingest_pipeline.py),
[embedding splitter](../webly/pipeline/embedding_text.py),
[Core regressions](../tests/test_core_v2.py).
