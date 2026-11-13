"""Bounded HTML table interpretation, retaining uncertain structure as text."""

import hashlib

from bs4 import NavigableString

MAX_GRID_POSITIONS = 100_000
MAX_COLUMNS = 1_000
MAX_HEADER_ASSOCIATIONS = 100_000
MAX_EVIDENCE_CHARACTERS = 10 * 1024 * 1024


class UncertainTable(ValueError):
    pass


def _own_text(node, table):
    return " ".join(
        str(text).strip()
        for text in node.descendants
        if isinstance(text, NavigableString) and text.find_parent("table") is table and str(text).strip()
    )


def _anchors(node, table):
    return [
        {"anchor_text": _own_text(a, table), "target": a["href"]}
        for a in node.find_all("a", href=True)
        if a.find_parent("table") is table and _own_text(a, table)
    ]


def _span(node, name, remaining):
    try:
        value = int(node.get(name, 1))
    except (ValueError, TypeError):
        raise UncertainTable("invalid_span") from None
    if name == "rowspan" and value == 0:
        return remaining
    if value < 1 or (name == "colspan" and value > MAX_COLUMNS) or (name == "rowspan" and value > remaining):
        raise UncertainTable("invalid_span")
    return value


def _model(table, rows):
    groups = []
    for row in rows:
        parent = row.find_parent(["thead", "tbody", "tfoot", "table"])
        groups.append(parent)
    ends, starts, keys = {}, {}, []
    for index, group in enumerate(groups):
        key = keys[-1] if index and group is groups[index - 1] else index
        keys.append(key)
        ends[key] = index
        starts.setdefault(key, index)
    cells, grid, row_cells = [], {}, []
    header_ids = {}
    column_groups, next_column = {}, 0
    for group in table.find_all("colgroup"):
        if group.find_parent("table") is not table:
            continue
        columns = [c for c in group.find_all("col") if c.find_parent("colgroup") is group]
        width = sum(_span(c, "span", 1) for c in columns) if columns else _span(group, "span", 1)
        if next_column + width > MAX_COLUMNS:
            raise UncertainTable("grid_limit")
        bounds = (next_column, next_column + width)
        for col in range(*bounds):
            column_groups[col] = bounds
        next_column += width
    for r, row in enumerate(rows):
        current, col = [], 0
        for node in row.find_all(["th", "td"]):
            if node.find_parent("tr") is not row or node.find_parent("table") is not table:
                continue
            while (r, col) in grid:
                col += 1
            width = _span(node, "colspan", 1)
            height = _span(node, "rowspan", ends[keys[r]] - r + 1)
            if col + width > MAX_COLUMNS or len(grid) + width * height > MAX_GRID_POSITIONS:
                raise UncertainTable("grid_limit")
            cell = {
                "row": r,
                "column": col,
                "rowspan": height,
                "colspan": width,
                "cell_type": node.name,
                "text": _own_text(node, table),
                "id": node.get("id"),
                "scope": str(node.get("scope", "")).lower(),
                "headers": list(node.get("headers", []))
                if not isinstance(node.get("headers", []), str)
                else node["headers"].split(),
                "headers_explicit": node.has_attr("headers"),
                "group": groups[r].name,
                "group_index": starts[keys[r]],
                "header_cells": [],
            }
            if cell["scope"] not in {"", "row", "col", "rowgroup", "colgroup"}:
                raise UncertainTable("invalid_scope")
            if cell["id"]:
                if cell["id"] in header_ids:
                    raise UncertainTable("duplicate_cell_id")
                header_ids[cell["id"]] = cell
            for rr in range(r, r + height):
                for cc in range(col, col + width):
                    if (rr, cc) in grid:
                        raise UncertainTable("conflicting_spans")
                    grid[rr, cc] = len(cells)
            cells.append(cell)
            current.append(cell)
            col += width
        row_cells.append(current)

    # Index headers so ordinary data tables do not require a quadratic scan.
    column_headers, row_headers, group_headers = {}, {}, {}
    leading = True
    has_implicit_data = any(c["cell_type"] == "td" and not c["headers_explicit"] for c in cells)
    for r, current in enumerate(row_cells):
        all_headers = bool(current) and all(c["cell_type"] == "th" for c in current)
        leading = leading and all_headers
        # A later column-header band can redefine earlier column meanings.
        # Without explicit cell references, retain its text as uncertain rather
        # than combining incompatible bands into invented labels.
        if (
            not leading
            and all_headers
            and column_headers
            and has_implicit_data
            and any(c["scope"] in {"", "col", "colgroup"} for c in current)
        ):
            raise UncertainTable("ambiguous_header_bands")
        for index, cell in enumerate(current):
            if cell["cell_type"] != "th":
                continue
            scope = cell["scope"]
            inferred = not scope and (leading or (index == 0 and not all_headers))
            effective = scope or ("col" if leading else "row" if inferred else "")
            cell["header_inferred"] = inferred
            if effective in {"col", "colgroup"}:
                bounds = (cell["column"], cell["column"] + cell["colspan"])
                if effective == "colgroup" and column_groups:
                    if cell["column"] not in column_groups:
                        raise UncertainTable("invalid_column_group")
                    bounds = column_groups[cell["column"]]
                for col in range(*bounds):
                    column_headers.setdefault(col, []).append(cell)
            elif effective == "row":
                for rr in range(r, r + cell["rowspan"]):
                    row_headers.setdefault(rr, []).append(cell)
            elif effective == "rowgroup":
                group_headers.setdefault(cell["group_index"], []).append(cell)

    associations = header_characters = 0
    for cell in cells:
        if cell["headers_explicit"]:
            try:
                headers = [header_ids[name] for name in cell["headers"]]
            except KeyError:
                raise UncertainTable("unknown_header_reference") from None
            if any(h["cell_type"] != "th" or h is cell for h in headers):
                raise UncertainTable("invalid_header_reference")
            method = "explicit"
        elif cell["cell_type"] == "td":
            headers = [
                h
                for col in range(cell["column"], cell["column"] + cell["colspan"])
                for h in column_headers.get(col, [])
                if h["row"] < cell["row"]
            ]
            headers += [
                h
                for row in range(cell["row"], cell["row"] + cell["rowspan"])
                for h in row_headers.get(row, [])
                if h["column"] < cell["column"]
            ]
            headers += group_headers.get(cell["group_index"], [])
            method = "structural"
        else:
            headers, method = [], "none"
        unique = {(h["row"], h["column"]): h for h in headers}
        associations += len(unique)
        header_characters += sum(len(h["text"]) for h in unique.values())
        if associations > MAX_HEADER_ASSOCIATIONS:
            raise UncertainTable("header_limit")
        if header_characters > MAX_EVIDENCE_CHARACTERS:
            raise UncertainTable("evidence_limit")
        cell["header_cells"] = [
            {"row": h["row"], "column": h["column"], "text": h["text"], "inferred": h.get("header_inferred", False)}
            for h in unique.values()
        ]
        cell["association_method"] = method
    return row_cells


def _render_rows(model, common, rows, table):
    output, evidence_characters = [], 0
    caption = common["caption"]
    caption_anchors = [
        a for node in table.find_all("caption") if node.find_parent("table") is table for a in _anchors(node, table)
    ]
    for r, cells in enumerate(model):
        if not caption and not any(c["text"] for c in cells):
            continue
        # Account for repeated text in evidence and serializable provenance,
        # before rendering. Long captions/headers must not amplify small HTML
        # into unbounded output. The fallback retains the original text once.
        evidence_characters += (
            3 * sum(len(c["text"]) for c in cells)
            + 3 * len(caption)
            + 4 * sum(len(h["text"]) for c in cells for h in c["header_cells"])
        )
        if evidence_characters > MAX_EVIDENCE_CHARACTERS:
            raise UncertainTable("evidence_limit")
        values = []
        for cell in cells:
            names = list(dict.fromkeys(h["text"] for h in cell["header_cells"] if h["text"]))
            values.append((" / ".join(names) + ": " if names else "") + cell["text"])
        prefix = (caption + "\n") if caption else ""
        associated = list(dict.fromkeys(h["text"] for c in cells for h in c["header_cells"] if h["text"]))
        if associated:
            prefix += " | ".join(associated) + "\n"
        text = prefix + f"Row {r + 1}: " + " | ".join(values)
        cursor = len(prefix) + len(f"Row {r + 1}: ")
        for cell, value in zip(cells, values):
            cell["render_start_char"] = cursor
            cell["render_end_char"] = cursor + len(value)
            cursor += len(value) + 3
        output.append(
            {
                **common,
                "row_index": r,
                "structure_status": "resolved",
                "cells": cells,
                "text": text,
                "original_text": " | ".join(c["text"] for c in cells),
                "context_prefix": prefix,
                "anchors": (caption_anchors if not output else []) + _anchors(rows[r], table),
            }
        )
    return output


def table_blocks(table, *, url, table_index, region):
    """One evidence block per source row; nested tables are processed separately."""
    table_id = hashlib.blake2b(f"{url}|table|{table_index}".encode(), digest_size=10).hexdigest()
    caption_node = next((c for c in table.find_all("caption") if c.find_parent("table") is table), None)
    caption = _own_text(caption_node, table) if caption_node else ""
    rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
    common = {"kind": "table", "table_id": table_id, "region": region, "caption": caption}
    try:
        for cell in table.find_all(["td", "th"]):
            if cell.find_parent("table") is not table:
                continue
            enclosing = cell.find_parent(["td", "th"])
            if cell.find_parent("tr") is None or (enclosing is not None and enclosing.find_parent("table") is table):
                raise UncertainTable("misplaced_cell")
        if len([c for c in table.find_all("caption") if c.find_parent("table") is table]) > 1:
            raise UncertainTable("multiple_captions")
        model = _model(table, rows)
        # Text outside cells/captions signals markup we cannot safely interpret.
        if any(
            isinstance(t, NavigableString)
            and str(t).strip()
            and t.find_parent("table") is table
            and t.find_parent(["td", "th", "caption"]) is None
            for t in table.descendants
        ):
            raise UncertainTable("unplaced_text")
        if not rows:
            raise UncertainTable("missing_rows")
        return _render_rows(model, common, rows, table)
    except UncertainTable as exc:
        text = _own_text(table, table)
        return (
            [
                {
                    **common,
                    "structure_status": "uncertain",
                    "structure_reason": str(exc),
                    "text": text,
                    "original_text": text,
                    "context_prefix": "",
                    "anchors": _anchors(table, table),
                    "cells": [],
                }
            ]
            if text
            else []
        )
