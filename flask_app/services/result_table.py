"""Paginate and filter complete output tables without coercing their values."""
import csv
import io
from pathlib import PurePosixPath
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


def preview_result_table(job_id, payload):
    if not isinstance(payload, dict):
        raise ArchiveError("请提供需要查看的数据表。")
    offset, limit = payload.get("offset", 0), payload.get("limit", 25)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ArchiveError("分页参数不正确，每页可读取 1 至 100 行。")
    query = payload.get("query", "")
    if not isinstance(query, str):
        raise ArchiveError("筛选条件必须为文本。")
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
                page, total, matched = [], 0, 0
                for row in reader:
                    if not row: continue
                    total += 1
                    if query and not any(query in value.casefold() for value in row): continue
                    if offset <= matched < offset + limit: page.append(row)
                    matched += 1
                return {"success": True, "columns": columns, "rows": page, "total_rows": total, "matched_rows": matched, "offset": offset, "limit": limit}
        except (UnicodeError, csv.Error) as error:
            raise ArchiveError("数据表编码或格式无法解析，请下载原文件检查。", 422) from error
        finally:
            response.close()
