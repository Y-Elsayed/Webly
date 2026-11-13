# Preserve HTML Regions and Table Semantics

Status: implemented; validation results are recorded below.

## Summary

Replace blanket container deletion and first-row header assumptions with
deterministic, structure-aware extraction. Preserve useful evidence across
websites without domain checks, customer-specific selectors or additional LLM
calls. Preserve first; defer cross-page boilerplate deduplication and region-based
ranking penalties until measurements justify them.

## 1. HTML cleanup and region preservation

- Retain `nav`, `footer` and `form` containers while removing scripts, styles and
  `noscript`. Extract nested blocks once.
- Add block `region` metadata: `main`, `navigation`, `footer`, `form` or `unknown`.
  Use the nearest semantic ancestor or equivalent explicit ARIA landmark.
- Preserve addresses, contact details, hours, navigation text, form instructions,
  legends, labels and option labels.
- Exclude input values, hidden controls, textarea contents, button text and HTML
  comments. Never submit forms or execute JavaScript.
- Keep links available for discovery and extraction. Carry region metadata into
  indexed evidence without automatic ranking penalties or region exclusions.
- Prevent whole-body fallback from reintroducing removed control contents.

## 2. Structured table extraction

- Replace Markdown generation/reparsing with a bounded table representation.
  Preserve captions, rows, empty cells, cell types, groups, spans and header IDs.
- Resolve explicit `headers` first, including an explicitly empty association.
  Otherwise use `scope`, row/column groups and cell coordinates.
- Infer column headers only from leading all-`th` rows and row headers from a
  leading unscoped `th` in a mixed data row. Mark inferred relationships.
- Keep an ordinary first `td` row as data. Do not invent column meanings.
- Resolve merged cells and `rowspan="0"` within the current row group. Process
  nested tables independently, without duplicating their text in parent cells.
- Limit each table to 100,000 occupied grid positions, 1,000 columns and 100,000
  header associations. Bound accounted expanded evidence/provenance text to
  10,485,760 characters (including repeated values, captions and header labels).
  Invalid references, malformed/conflicting spans and excessive structures fall
  back to original ordered text with `structure_status="uncertain"`.
- Render associated source header text where available, otherwise neutral row
  positions. Preserve original values and labels without LLM inference.

## 3. Chunking, provenance and compatibility

- Pack row evidence with only the associated headers and caption. Oversized rows
  use existing word/token limits and retain bounded context on continuation slices.
- Store table identity, source row/cell coordinates, span geometry and header
  associations in block metadata. Keep ordinary rows' original cell text.
- For split rows, retain only intersecting cell descriptors and header references;
  full values survive in evidence slices and frozen source HTML rather than being
  copied into every slice. Mark descriptor text basis as `source_table`.
- Keep character/word offsets relative to the extracted section representation;
  added continuation context does not alter source slice offsets.
- Introduce shared `EXTRACTION_VERSION="blocks-v2"` for embedding/cache identity,
  new crawl-run stamps, transformation fingerprints, approval candidates and
  published transformation provenance.
- Keep runtime signatures unchanged. Old snapshots require rebuilding from
  validated raw HTML under a new operation ID; recrawling is unnecessary when a
  complete frozen run already exists. Never rewrite old run manifests or indexes.
- Reject old operation replay and stale approvals when the transformation revision
  changes. Prevent incompatible cache entries or snapshots from being reused.

## 4. Test and acceptance plan

Use deterministic English, Arabic and mixed-language fixtures covering footer-only
facts, factual navigation, form instructions/options, excluded values, nested
regions, fallback safety, headerless first rows, row/column/group headers, explicit
references, empty cells, captions, merged cells, nested tables, malformed markup,
extreme spans and bounded evidence expansion.

Verify facts survive chunk boundaries; offsets describe the canonical extracted
representation; metadata does not amplify large rows; facts can be indexed,
retrieved and cited in both builder and classic; extraction changes invalidate
old replay/approval/cache/snapshot identities while frozen HTML remains reusable.

Acceptance: repository tests and lint pass, installed-wheel fixture crawl/index/
query succeeds, and no website-specific rules or additional provider calls are
introduced. Real-site quality/performance evaluation remains a separate gate.

## Implementation map and validation

- Region preservation and packing: `webly/processors/text_chunkers.py`.
- Table interpretation: `webly/processors/table_extraction.py`.
- Shared revision: `webly/processors/extraction_version.py`, consumed by runtime,
  cache and ingestion operation provenance.
- Regression coverage: `tests/test_html_extraction.py` and `tests/test_core_v2.py`.

The full repository suite passes 280 tests, including 36 extraction-related cases
and one additional Windows regression. A repeated publication/read check exposed
Windows sharing errors that Python reports as plain `EACCES` without `winerror`;
the existing bounded read retry now covers that platform-specific variant too.
Ruff and diff-whitespace checks pass. One upstream FAISS/NumPy
deprecation warning remains. Tests use deterministic providers and controlled
fixtures; they do not establish real-site retrieval quality.

Isolated verification passed the Core-only crawl/index/reopen/cited-query fixture
with optional imports blocked, then all 16 installed API tests. The fixture keeps
its answer exclusively in a footer, preserves form instructions, indexes a
headerless table, excludes control values and checks that ingestion makes zero
chat-model calls. An additional 72 extraction/Core tests passed against the wheel
outside the checkout with isolated Python and copied tests.

Evidence: [wheel hashes and source provenance](audit/2026-11-13-html-extraction-package-verification.json)
and [installed regression results](audit/2026-11-13-html-extraction-installed-tests.xml).
The wheel check used `--allow-dirty`; it records development validation rather than
release certification. The implementation and validation evidence are tracked in
the repository. No paid model calls or customer-data rebuilds were performed.
