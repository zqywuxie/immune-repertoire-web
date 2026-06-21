from __future__ import annotations

import csv
import gzip
import math
import re
import urllib.request
from pathlib import Path
from typing import Any


HEADER_ALIASES = {
    "cdr3": [
        "cdr3(pep)",
        "cdr3_pep",
        "cdr3pep",
        "cdr3aa",
        "cdr3_aa",
        "cdr3",
        "aa_cdr3",
    ],
    "copy": [
        "copy",
        "copies",
        "count",
        "clonecount",
        "clone_count",
        "readcount",
        "read_count",
        "reads",
        "umis",
        "umi",
    ],
    "v": ["v", "vgene", "v_gene", "bestvgene", "v_call"],
    "d": ["d", "dgene", "d_gene", "bestdgene", "d_call"],
    "j": ["j", "jgene", "j_gene", "bestjgene", "j_call"],
    "c": ["c", "cgene", "c_gene", "constant", "constant_gene", "isotype"],
    "chain": ["chain", "chain_type", "receptor_chain", "locus"],
    "cell_type": ["cell_type", "celltype", "lymphocyte_type", "receptor_type"],
    "joined_seq": ["joinedseq", "joined_seq", "joinedsequence", "joined_sequence"],
}

CHAIN_CELL_MAP = {
    "IGH": "B cell",
    "IGK": "B cell",
    "IGL": "B cell",
    "TRA": "T cell",
    "TRB": "T cell",
    "TRD": "T cell",
    "TRG": "T cell",
}

D3_CDN_URL = "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"


def normalize_header(value: str) -> str:
    value = value.strip().lower()
    return re.sub(r"[\s\-_./]+", "", value)


def open_text_file(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:

        class DefaultDialect(csv.excel):
            delimiter = ","

        return DefaultDialect()


def detect_columns(
    fieldnames: list[str], overrides: dict[str, str | None]
) -> dict[str, str | None]:
    normalized = {normalize_header(name): name for name in fieldnames}
    detected: dict[str, str | None] = {}
    for logical_name, aliases in HEADER_ALIASES.items():
        override = overrides.get(logical_name)
        if override:
            if override not in fieldnames:
                raise ValueError(f"指定列不存在: {logical_name}={override}")
            detected[logical_name] = override
            continue
        detected[logical_name] = None
        for alias in aliases:
            match = normalized.get(normalize_header(alias))
            if match:
                detected[logical_name] = match
                break
    return detected


def parse_copy(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_text(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def infer_chain(*values: str) -> str:
    joined = " ".join(value for value in values if value).upper()
    for prefix in ("IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"):
        if prefix in joined:
            return prefix
    return "Unknown"


def infer_cell_type(raw_value: str | None, chain: str) -> str:
    if raw_value:
        lowered = str(raw_value).strip().lower()
        if lowered in {"b", "bcell", "b-cell", "b cell"}:
            return "B cell"
        if lowered in {"t", "tcell", "t-cell", "t cell"}:
            return "T cell"
    return CHAIN_CELL_MAP.get(chain, "Unknown")


def vj_pair_name(v: str, j: str) -> str:
    if v and j:
        return f"{v} | {j}"
    if v:
        return f"{v} | J?"
    if j:
        return f"V? | {j}"
    return "V? | J?"


def make_title(path: Path, title: str | None) -> str:
    return title or f"{path.stem} clonotype tetris map"


def _normalize_copy_value(copy_value: float) -> int | float:
    return int(copy_value) if math.isclose(copy_value, round(copy_value)) else round(copy_value, 4)


def read_repertoire_rows(
    path: Path, columns: dict[str, str | None]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stats = {
        "input_rows": 0,
        "used_rows": 0,
        "skipped_missing_copy": 0,
        "skipped_missing_cdr3": 0,
    }

    with open_text_file(path) as handle:
        sample = handle.read(4096)
        handle.seek(0)
        reader = csv.DictReader(handle, dialect=detect_dialect(sample))
        if not reader.fieldnames:
            raise ValueError("未检测到表头。")

        for row in reader:
            stats["input_rows"] += 1
            cdr3 = clean_text(
                row.get(columns["cdr3"] or "", "") if columns["cdr3"] else ""
            )
            if not cdr3:
                stats["skipped_missing_cdr3"] += 1
                continue

            copy_value = parse_copy(
                row.get(columns["copy"] or "", "") if columns["copy"] else ""
            )
            if copy_value is None or copy_value <= 0:
                stats["skipped_missing_copy"] += 1
                continue

            v = (
                clean_text(row.get(columns["v"] or "", "") if columns["v"] else "")
                or "V?"
            )
            d = clean_text(row.get(columns["d"] or "", "") if columns.get("d") else "")
            j = (
                clean_text(row.get(columns["j"] or "", "") if columns["j"] else "")
                or "J?"
            )
            c = clean_text(row.get(columns["c"] or "", "") if columns["c"] else "")
            joined_seq = clean_text(
                row.get(columns["joined_seq"] or "", "") if columns.get("joined_seq") else ""
            )
            raw_chain = clean_text(
                row.get(columns["chain"] or "", "") if columns["chain"] else ""
            )
            raw_cell_type = clean_text(
                row.get(columns["cell_type"] or "", "") if columns["cell_type"] else ""
            )

            chain = infer_chain(raw_chain, c, v, j)
            cell_type = infer_cell_type(raw_cell_type, chain)
            rows.append(
                {
                    "cdr3": cdr3,
                    "copy": copy_value,
                    "v": v,
                    "d": d,
                    "j": j,
                    "c": c,
                    "joined_seq": joined_seq,
                    "chain": chain,
                    "cell_type": cell_type,
                    "row_count": 1,
                    "source_order": stats["input_rows"],
                }
            )
            stats["used_rows"] += 1

    aggregated: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("v") or "V?"),
            str(row.get("j") or "J?"),
            str(row.get("cdr3") or ""),
        )
        if key not in aggregated:
            aggregated[key] = {
                **row,
                "copy": 0.0,
                "row_count": 0,
                "source_order": row.get("source_order", 0),
            }
        target = aggregated[key]
        target["copy"] += float(row.get("copy", 0) or 0)
        target["row_count"] += int(row.get("row_count", 0) or 0)
        target["source_order"] = min(
            int(target.get("source_order", 0) or 0),
            int(row.get("source_order", 0) or 0),
        )
        for optional_key in ("d", "c", "joined_seq", "chain", "cell_type"):
            if row.get(optional_key) and not target.get(optional_key):
                target[optional_key] = row[optional_key]

    rows = list(aggregated.values())
    rows.sort(
        key=lambda item: (
            -item["copy"],
            item["v"],
            item["j"],
            item["cdr3"],
            item.get("source_order", 0),
        )
    )
    total_copy = sum(float(item["copy"]) for item in rows)
    for item in rows:
        copy_value = float(item["copy"])
        item["copy"] = _normalize_copy_value(copy_value)
        item["frequency"] = (copy_value / total_copy) if total_copy else 0.0
        item["vj_pair"] = vj_pair_name(item["v"], item["j"])
        item["clone_id"] = f"{item['v']}|{item['j']}|{item['cdr3']}"

    summary = {"total_clones": len(rows), "total_copy": total_copy, **stats}
    return rows, summary


def read_repertoire(
    path: Path, columns: dict[str, str | None]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return read_repertoire_rows(path, columns)


def escape_html_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def load_d3_script_tag() -> str:
    try:
        with urllib.request.urlopen(D3_CDN_URL, timeout=20) as response:
            script_text = response.read().decode("utf-8")
        return f"<script>{script_text}</script>"
    except Exception:
        return f'<script src="{D3_CDN_URL}"></script>'
