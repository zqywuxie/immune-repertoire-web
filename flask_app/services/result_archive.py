"""Build one archive from authorized job outputs using existing file routes."""
import re
from tempfile import SpooledTemporaryFile
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

from flask import current_app, request
from werkzeug.http import parse_options_header


class ArchiveError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def resolve_result_files(items):
    from flask_app.routes.api_jobs import _can_access_job, _collect_result_outputs, _unwrap_result_payload, _job_result_assets
    from flask_app.services.background_job_service import get_background_job_service
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise ArchiveError("请选择 1 至 200 个结果文件。")
    files, seen, jobs = [], set(), {}
    for item in items:
        if not isinstance(item, dict):
            raise ArchiveError("结果文件选择格式不正确。")
        job_id, url = str(item.get("job_id") or ""), str(item.get("url") or "")
        if job_id not in jobs:
            job = get_background_job_service().get_job(job_id)
            if not job or not _can_access_job(job):
                raise ArchiveError("任务不存在或无权访问。", 404)
            outputs = _collect_result_outputs(_unwrap_result_payload(job.get("result") or {}))
            outputs += _job_result_assets(job)
            jobs[job_id] = {str(output.get(key)) for output in outputs for key in ("url", "download_url", "preview_url") if output.get(key)}
        if not url or url not in jobs[job_id]:
            raise ArchiveError("所选文件不属于该任务，请刷新结果后重试。")
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith(("/api/script-hub/results/", "/api/assets/", "/api/chord/results/", "/api/treemap/results/", "/api/auto-heatmap/pipeline-comparison/results/", "/api/auto-heatmap/similarity-report/results/", "/reports/", "/static/")):
            raise ArchiveError("此结果链接暂不支持打包，请单独下载。")
        if (job_id, url) not in seen:
            files.append((job_id, url)); seen.add((job_id, url))
    return files


def build_archive(items):
    files = resolve_result_files(items)
    archive = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    total = 0
    limit = int(current_app.config.get("RESULT_ARCHIVE_MAX_BYTES", 2 * 1024**3))
    app = current_app._get_current_object()
    cookies = request.headers.get("Cookie", "")
    try:
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, allowZip64=True) as bundle:
            for index, (job_id, url) in enumerate(files):
                # Dispatch locally; do not make network requests or accept filesystem paths.
                with app.test_request_context(url, method="GET", headers={"Cookie": cookies}):
                    response = app.full_dispatch_request()
                    try:
                        if response.status_code != 200:
                            raise ArchiveError("部分文件不存在或无法读取，请刷新结果后重新选择。", 409)
                        filename = parse_options_header(response.headers.get("Content-Disposition", ""))[1].get("filename") or unquote(urlsplit(url).path.rsplit("/", 1)[-1])
                        filename = re.sub(r'[^\w.\-一-鿿]', '_', filename)[:150] or "结果文件"
                        folder = re.sub(r'[^\w-]', '_', job_id)[:80]
                        entry = f"{folder}/{index + 1:03d}_{filename}"
                        info = ZipInfo(entry)
                        info.compress_type = ZIP_STORED if filename.lower().endswith((".zip", ".png", ".jpg", ".pdf")) else ZIP_DEFLATED
                        with bundle.open(info, "w", force_zip64=True) as output:
                            for chunk in response.response:
                                if isinstance(chunk, str): chunk = chunk.encode("utf-8")
                                total += len(chunk)
                                if total > limit:
                                    raise ArchiveError("所选文件过大，请减少文件数量后重试。", 413)
                                output.write(chunk)
                    finally:
                        response.close()
        archive.seek(0)
        return archive
    except BaseException:
        archive.close()
        raise
