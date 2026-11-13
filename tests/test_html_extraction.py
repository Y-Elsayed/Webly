"""Content- and structure-based extraction across unrelated HTML layouts."""

import pytest

from webly.processors import table_extraction
from webly.processors.page_processor import SemanticPageProcessor
from webly.processors.text_chunkers import SlidingTextChunker


def blocks(html, **kwargs):
    return [b for ch in SlidingTextChunker(**kwargs).chunk_html(html, "https://unrelated.test/") for b in ch["blocks"]]


def test_semantic_and_aria_regions_keep_facts_and_links_once():
    html = (
        '<main><p>Main fact.</p><nav><p>Visitor desk opens at nine.</p><a href="/hours">Hours</a></nav>'
        '<footer><p>Call 123456.</p></footer><section role="contentinfo"><p>بريد التواصل</p></section></main>'
    )
    found = blocks(html)
    assert {b["text"]: b["region"] for b in found} == {
        "Main fact.": "main",
        "Visitor desk opens at nine.": "navigation",
        "Hours": "navigation",
        "Call 123456.": "footer",
        "بريد التواصل": "footer",
    }
    assert [a["target"] for b in found for a in b["anchors"]] == ["/hours"]


def test_forms_keep_published_instructions_labels_and_options_only():
    html = (
        "<form><fieldset><legend>Apply before June.</legend><p>ارفق المستندات المطلوبة</p>"
        '<label>Name<input value="PRIVATE_INPUT"></label><input type="hidden" value="SECRET_TOKEN">'
        "<textarea>PRIVATE_TEXTAREA</textarea><button>SECRET_BUTTON</button>"
        '<select><option value="SECRET_OPTION_CODE">Engineering</option><option>طب</option></select>'
        "</fieldset></form><!-- PRIVATE_COMMENT -->"
    )
    found = blocks(html)
    text = " ".join(b["text"] for b in found)
    for value in ("Apply before June.", "ارفق المستندات المطلوبة", "Name", "Engineering", "طب"):
        assert text.count(value) == 1
    assert "PRIVATE" not in text and "SECRET" not in text
    assert all(b["region"] == "form" for b in found)


@pytest.mark.parametrize(
    "html",
    [
        '<form><input value="SECRET"><textarea>SECRET</textarea><button>SECRET</button></form>',
        '<h1><input value="SECRET"></h1><script>SECRET</script><!-- SECRET -->',
    ],
)
def test_empty_content_fallback_does_not_restore_excluded_values(html):
    assert not blocks(html)


def test_heading_only_fallback_has_explicit_unknown_region():
    found = blocks("<h1>Office information</h1>")
    assert found[0]["text"] == "Office information"
    assert found[0]["region"] == "unknown" and found[0]["kind"] == "text"


def test_headerless_rows_keep_first_row_empty_cells_and_no_fabricated_headers():
    found = blocks("<table><tr><td>Engineering</td><td>50000</td></tr><tr><td>Medicine</td><td></td></tr></table>")
    assert len(found) == 2
    assert found[0]["text"] == "Row 1: Engineering | 50000"
    assert found[1]["cells"][1]["text"] == ""
    assert all(not c["header_cells"] for b in found for c in b["cells"])
    assert all(b["structure_status"] == "resolved" for b in found)


def test_explicit_headers_caption_and_row_headers():
    found = blocks(
        '<table><caption>الرسوم الدراسية</caption><thead><tr><th id="program" scope="col">البرنامج</th>'
        '<th id="fee" scope="col">الرسوم</th></tr></thead><tbody><tr>'
        '<th id="eng" scope="row">هندسة</th><td headers="eng fee">50000</td></tr></tbody></table>'
    )
    cell = found[1]["cells"][1]
    assert cell["association_method"] == "explicit"
    assert [h["text"] for h in cell["header_cells"]] == ["هندسة", "الرسوم"]
    assert all(not h["inferred"] for h in cell["header_cells"])
    assert "الرسوم الدراسية" in found[1]["text"]


def test_inferred_headers_are_marked_and_header_labels_are_preserved():
    found = blocks("<table><tr><th>Program</th><th>Fee</th></tr><tr><th>Engineering</th><td>900</td></tr></table>")
    headers = found[1]["cells"][1]["header_cells"]
    assert {h["text"] for h in headers} == {"Fee", "Engineering"}
    assert all(h["inferred"] for h in headers)
    assert "Program" in found[0]["text"]


def test_multi_level_headers_and_spans_preserve_coordinates():
    found = blocks(
        '<table><thead><tr><th scope="colgroup" colspan="2">Costs</th></tr>'
        '<tr><th scope="col">Annual</th><th scope="col">Monthly</th></tr></thead>'
        "<tbody><tr><td>1200</td><td>100</td></tr></tbody></table>"
    )
    annual, monthly = found[-1]["cells"]
    assert [h["text"] for h in annual["header_cells"]] == ["Costs", "Annual"]
    assert [h["text"] for h in monthly["header_cells"]] == ["Costs", "Monthly"]
    assert [(c["row"], c["column"]) for c in found[-1]["cells"]] == [(2, 0), (2, 1)]


def test_column_group_scope_and_explicit_empty_headers():
    found = blocks(
        '<table><colgroup span="2"></colgroup><tr><th scope="colgroup">Costs</th></tr>'
        '<tr><td headers="">900</td><td>100</td></tr></table>'
    )
    assert found[1]["cells"][0]["header_cells"] == []
    assert found[1]["cells"][0]["association_method"] == "explicit"
    assert [h["text"] for h in found[1]["cells"][1]["header_cells"]] == ["Costs"]


def test_rowspan_zero_stays_within_its_row_group():
    found = blocks(
        '<table><tbody><tr><th scope="row" rowspan="0">Engineering</th><td>900</td></tr>'
        "<tr><td>800</td></tr></tbody><tbody><tr><td>Medicine</td><td>700</td></tr></tbody></table>"
    )
    assert found[0]["cells"][0]["rowspan"] == 2
    assert found[1]["cells"][0]["column"] == 1
    assert found[1]["cells"][0]["header_cells"][0]["text"] == "Engineering"
    assert all(not c["header_cells"] for c in found[2]["cells"])


def test_nested_tables_are_independent_without_duplicating_nested_values():
    found = blocks("<table><tr><td>Outer<table><tr><td>Inner</td><td>42</td></tr></table></td></tr></table>")
    assert len({b["table_id"] for b in found}) == 2
    assert all(b["structure_status"] == "resolved" for b in found)
    assert sum(b["text"].count("Inner") for b in found) == 1
    assert found[0]["cells"][0]["text"] == "Outer"


@pytest.mark.parametrize(
    "table",
    [
        '<table><tr><td colspan="1000000000">Retained</td></tr></table>',
        '<table><tr><td rowspan="-1">Retained</td></tr></table>',
        '<table><tr><td headers="missing">Retained</td></tr></table>',
        "<table><td>Retained</td></table>",
        "<table>Retained<tr><td>Data</td></tr></table>",
        '<table><tr><td>A</td><th rowspan="2">Header</th></tr><tr><td colspan="2">Retained</td></tr></table>',
    ],
)
def test_uncertain_tables_retain_ordered_text_without_invented_headers(table):
    found = blocks(table)
    assert found[0]["structure_status"] == "uncertain"
    assert "Retained" in found[0]["text"]
    assert found[0]["cells"] == []


def test_table_grid_and_header_association_limits_fall_back(monkeypatch):
    monkeypatch.setattr(table_extraction, "MAX_GRID_POSITIONS", 2)
    found = blocks("<table><tr><td>A</td><td>B</td><td>C</td></tr></table>")
    assert found[0]["structure_reason"] == "grid_limit" and "C" in found[0]["text"]
    monkeypatch.setattr(table_extraction, "MAX_GRID_POSITIONS", 100_000)
    monkeypatch.setattr(table_extraction, "MAX_HEADER_ASSOCIATIONS", 1)
    found = blocks("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")
    assert found[0]["structure_reason"] == "header_limit" and "2" in found[0]["text"]


def test_repeated_headers_and_captions_cannot_amplify_evidence_without_limit(monkeypatch):
    monkeypatch.setattr(table_extraction, "MAX_EVIDENCE_CHARACTERS", 100)
    found = blocks(
        "<table><caption>A long explanatory caption</caption><tr><th>Long header</th></tr>"
        "<tr><td>First value</td></tr><tr><td>Last value</td></tr></table>"
    )
    assert found[0]["structure_reason"] == "evidence_limit"
    assert "Last value" in found[0]["text"]


def test_large_rows_do_not_repeat_complete_cell_values_in_slice_metadata():
    html = "<table><tr>" + "".join(f"<td>cell{i}</td>" for i in range(100)) + "</tr></table>"
    found = blocks(html, max_words=12, overlap=2)
    assert len(found) > 10
    assert all(len(b["cells"]) <= 7 for b in found)
    assert all("text" not in c for b in found for c in b["cells"])
    assert any("cell99" in b["text"] for b in found)


def test_table_slice_offsets_refer_to_the_canonical_extracted_row():
    html = "<table><caption>Fees</caption><tr><th>Course</th><th>Amount</th></tr><tr><td>Physics</td><td>"
    html += " ".join(f"v{i}" for i in range(40)) + "</td></tr></table>"
    chunker = SlidingTextChunker(max_words=12, overlap=2)
    section = chunker._iter_sections(chunker._clean_html(html), "https://unrelated.test/")[0]
    canonical = "\n\n".join(b["text"] for b in section["blocks"])
    found = blocks(html, max_words=12, overlap=2)
    for block in found:
        original_slice = canonical[block["start_char"] : block["end_char"]]
        assert block["text"].endswith(original_slice)


def test_large_row_splits_repeat_only_relevant_headers_and_preserve_tail():
    html = "<table><caption>Fees</caption><tr><th>Course</th><th>Amount</th></tr><tr><td>Physics</td><td>"
    html += " ".join(f"v{i}" for i in range(45)) + "</td></tr></table>"
    found = blocks(html, max_words=15, overlap=2)
    slices = [b for b in found if b.get("row_index") == 1]
    assert len(slices) > 2
    assert all("Fees" in b["text"] and "Amount" in b["text"] for b in slices)
    assert any("v44" in b["text"] for b in slices)
    assert all(b["offset_basis"] == "section_extracted_text" for b in slices)


def test_table_inside_list_item_not_duplicated_and_metadata_reaches_processor():
    html = "<footer><ul><li>Contact<table><tr><td>Phone</td><td>12345</td></tr></table></li></ul></footer>"
    chunks = SemanticPageProcessor(lambda *args: {}, SlidingTextChunker()).process("https://other.test/", html)
    assert sum(c["text"].count("12345") for c in chunks) == 1
    assert all(b["region"] == "footer" for c in chunks for b in c["blocks"])


def test_option_display_attributes_and_groups_do_not_index_internal_values():
    found = blocks(
        '<form><select><optgroup label="Programs"><option label="Engineering" value="SECRET">'
        "INTERNAL_CODE</option><option>طب</option></optgroup></select></form>"
    )
    text = " ".join(b["text"] for b in found)
    assert "Programs" in text and "Engineering" in text and "طب" in text
    assert "INTERNAL_CODE" not in text and "SECRET" not in text


def test_caption_links_and_ragged_rows_remain_valid():
    found = blocks(
        '<table><caption><a href="/fees">Fee information</a></caption>'
        "<tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>"
    )
    assert all(b["structure_status"] == "resolved" for b in found)
    assert [a["target"] for b in found for a in b["anchors"]] == ["/fees"]


def test_redefined_header_bands_do_not_label_duration_as_a_fee():
    found = blocks(
        "<table><tr><th>Program</th><th>Fee</th></tr><tr><td>Physics</td><td>900</td></tr>"
        "<tr><th>Program</th><th>Duration</th></tr><tr><td>Engineering</td><td>3 years</td></tr></table>"
    )
    assert found[0]["structure_status"] == "uncertain"
    assert found[0]["structure_reason"] == "ambiguous_header_bands"
    assert "Fee: 3 years" not in found[0]["text"] and "Engineering" in found[0]["text"]
