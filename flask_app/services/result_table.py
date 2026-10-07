"""Paginate, filter and sort output tables without coercing returned values."""
import csv
import io
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from flask import current_app, request
from werkzeug.http import parse_options_header
from flask_app.services.result_archive import ArchiveError, resolve_result_files


class ResponseReader(io.RawIOBase):
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.pending = memoryview(b"")

    def readable(self):
        return True

    def readinto(self, buffer):
        while not self.pending:
            try:
                chunk = next(self.chunks)
            except StopIteration:
                return 0
            self.pending = memoryview(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
        size = min(len(buffer), len(self.pending))
        buffer[:size] = self.pending[:size]
        self.pending = self.pending[size:]
        return size


_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")


def _number(value):
    value = value.strip()
    if not _NUMBER.fullmatch(value):
        return None
    try:
        result = Decimal(value)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _numeric_compare(left, right):
    left, right = _number(left), _number(right)
    if left is None or right is None:
        return 0
    return (left > right) - (left < right)


def _text_compare(left, right):
    left, right = left.casefold(), right.casefold()
    return (left > right) - (left < right)


def _collect_page(reader, query, offset, limit, column, direction, mode):
    total, matched, page = 0, 0, []
    if column is None:
        for row in reader:
            if not row:
                continue
            total += 1
            if query and not any(query in value.casefold() for value in row):
                continue
            if offset <= matched < offset + limit:
                page.append(row)
            matched += 1
        return page, total, matched

    # One request, one ephemeral disk database. No table-sized Python list or persistent cache.
    with tempfile.TemporaryDirectory(prefix="immune-table-sort-") as folder:
        with closing(sqlite3.connect(str(Path(folder) / "page.sqlite"))) as connection:
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("PRAGMA cache_size=-2048")
            connection.execute("PRAGMA mmap_size=0")
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.create_collation("EXACT_NUMBER", _numeric_compare)
            connection.create_collation("FOLDED_TEXT", _text_compare)
            connection.execute("CREATE TABLE records (row_no INTEGER, valid_number INTEGER, sort_value TEXT, original TEXT)")
            for row in reader:
                if not row:
                    continue
                total += 1
                if query and not any(query in value.casefold() for value in row):
                    continue
                value = row[column] if column < len(row) else ""
                valid = int(_number(value) is not None) if mode == "numeric" else 1
                connection.execute("INSERT INTO records VALUES (?, ?, ?, ?)",
                                   (total, valid, value, json.dumps(row, ensure_ascii=False)))
                matched += 1
            connection.commit()
            collation = "EXACT_NUMBER" if mode == "numeric" else "FOLDED_TEXT"
            order = "DESC" if direction == "desc" else "ASC"
            cursor = connection.execute(
                f"SELECT original FROM records ORDER BY valid_number DESC, sort_value COLLATE {collation} {order}, row_no ASC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            page = [json.loads(row[0]) for row in cursor]
    return page, total, matched


def preview_result_table(job_id, payload):
    if not isinstance(payload, dict):
        raise ArchiveError("请提供需要查看的数据表。")
    offset, limit = payload.get("offset", 0), payload.get("limit", 25)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ArchiveError("分页参数不正确，每页可读取 1 至 100 行。")
    query = payload.get("query", "")
    if not isinstance(query, str):
        raise ArchiveError("筛选条件必须为文本。")
    column, direction, mode = payload.get("sort_column"), payload.get("sort_direction", "asc"), payload.get("sort_mode", "text")
    if column is not None and (type(column) is not int or column < 0):
        raise ArchiveError("请选择有效的排序列。")
    if direction not in ("asc", "desc") or mode not in ("text", "numeric"):
        raise ArchiveError("排序方向或方式不正确。")
    query = query.strip().casefold()
    files = resolve_result_files([{"job_id": job_id, "url": payload.get("url")}])
    url = files[0][1]
    app = current_app._get_current_object()
    cookies = request.headers.get("Cookie", "")
    with app.test_request_context(url, method="GET", headers={"Cookie": cookies}):
        response = app.full_dispatch_request()
        try:
            if response.status_code != 200:
                raise ArchiveError("结果文件不存在或无法读取，请刷新结果后重试。", 409)
            filename = parse_options_header(response.headers.get("Content-Disposition", ""))[1].get("filename") or unquote(urlsplit(url).path)
            suffix = PurePosixPath(filename).suffix.lower()
            if suffix not in {".csv", ".tsv"}:
                raise ArchiveError("该文件不是可分页的数据表，请下载原文件。")
            with io.TextIOWrapper(io.BufferedReader(ResponseReader(response.response)), encoding="utf-8-sig", newline="") as source:
                reader = csv.reader(source, delimiter="\t" if suffix == ".tsv" else ",", strict=True)
                columns = next(reader, [])
                if column is not None and column >= len(columns):
                    raise ArchiveError("排序列已不存在，请刷新数据表。")
                page, total, matched = _collect_page(reader, query, offset, limit, column, direction, mode)
                return {"success": True, "columns": columns, "rows": page, "total_rows": total, "matched_rows": matched,
                        "offset": offset, "limit": limit, "sort_column": column, "sort_direction": direction, "sort_mode": mode}
        except (UnicodeError, csv.Error) as error:
            raise ArchiveError("数据表编码或格式无法解析，请下载原文件检查。", 422) from error
        except (sqlite3.Error, OSError) as error:
            raise ArchiveError("临时排序空间不可用或数据表无法读取，请重试或下载原文件。", 503) from error
        finally:
            response.close()
