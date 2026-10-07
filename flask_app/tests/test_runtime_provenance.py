from types import SimpleNamespace
import os
import shutil
from pathlib import Path

import pytest

from flask_app.services import runtime_provenance as provenance


def test_runtime_provenance_records_python_and_r_versions(monkeypatch):
    monkeypatch.setattr(provenance, "version", lambda name: f"version-{name}")
    monkeypatch.setattr(provenance.platform, "python_version", lambda: "3.12.test")
    monkeypatch.setattr(provenance.platform, "system", lambda: "Linux")
    monkeypatch.setattr(provenance.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=(
            "R|4.4.1\nBIOC|3.20\nPKG|GSVA|2.0.7\nPKG|org.Hs.eg.db|3.20.0\n"
        )),
    )
    provenance.runtime_provenance.cache_clear()
    try:
        result = provenance.runtime_provenance()
    finally:
        provenance.runtime_provenance.cache_clear()

    assert result["python"] == "3.12.test"
    assert result["system"] == "Linux"
    assert result["architecture"] == "x86_64"
    assert result["packages"]["xgboost"] == "version-xgboost"
    assert result["r"] == {
        "available": True,
        "version": "4.4.1",
        "bioconductor": "3.20",
        "packages": {"GSVA": "2.0.7", "org.Hs.eg.db": "3.20.0"},
    }


def test_runtime_provenance_reports_unavailable_r_without_failing(monkeypatch):
    monkeypatch.setattr(provenance, "version", lambda name: f"version-{name}")
    monkeypatch.setattr(provenance.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    provenance.runtime_provenance.cache_clear()
    try:
        result = provenance.runtime_provenance()
    finally:
        provenance.runtime_provenance.cache_clear()
    assert result["r"] == {"available": False, "reason": "Rscript unavailable"}


def test_reference_file_fingerprint_is_bounded_and_content_specific(tmp_path, monkeypatch):
    path = tmp_path / "reference.csv"
    path.write_bytes(b"reference-version-one")
    provenance._reference_sha256.cache_clear()
    first = provenance.reference_file_provenance(path)
    replacement = tmp_path / "replacement.csv"
    replacement.write_bytes(b"reference-version-two")
    os.replace(replacement, path)
    second = provenance.reference_file_provenance(path)
    assert first["sha256"] != second["sha256"]
    assert first["fingerprint_status"] == second["fingerprint_status"] == "sha256"

    monkeypatch.setattr(provenance, "MAX_REFERENCE_HASH_BYTES", 1)
    skipped = provenance.reference_file_provenance(path)
    assert skipped["fingerprint_status"] == "size_limit_exceeded"
    assert "sha256" not in skipped
    provenance._reference_sha256.cache_clear()


def test_reference_file_fingerprint_does_not_block_on_missing_or_unreadable_path(tmp_path, monkeypatch):
    missing = provenance.reference_file_provenance(tmp_path / "missing.csv")
    assert missing == {
        "available": False,
        "fingerprint_status": "missing_or_not_a_file",
    }

    def deny_stat(_self):
        raise PermissionError("reference path is not readable")

    monkeypatch.setattr(Path, "is_file", deny_stat)
    denied = provenance.reference_file_provenance(tmp_path / "restricted.csv")
    assert denied == {
        "available": False,
        "fingerprint_status": "PermissionError",
    }


def test_full_analysis_container_reports_installed_r_packages():
    if shutil.which("Rscript") is None:
        pytest.skip("该容器未安装 R")
    provenance.runtime_provenance.cache_clear()
    try:
        result = provenance.runtime_provenance()
    finally:
        provenance.runtime_provenance.cache_clear()
    assert result["r"]["available"] is True
    assert result["r"]["version"]
    assert result["r"]["bioconductor"]
    assert result["r"]["packages"]["GSVA"]
    assert result["r"]["packages"]["org.Hs.eg.db"]


def test_installed_r_versions_do_not_load_analysis_namespaces(monkeypatch):
    if shutil.which("Rscript") is None:
        pytest.skip("该容器未安装 R")
    run = provenance.subprocess.run
    def verify_unloaded(arguments, **kwargs):
        arguments = list(arguments)
        arguments[-1] += '\nstopifnot(!any(c("clusterProfiler", "GSVA", "ComplexHeatmap") %in% loadedNamespaces()))\n'
        return run(arguments, **kwargs)
    monkeypatch.setattr(provenance.subprocess, "run", verify_unloaded)
    result = provenance._r_runtime_provenance()
    assert result["available"] is True
    assert result["packages"]["clusterProfiler"]
    assert result["packages"]["GSVA"]
    assert result["packages"]["ComplexHeatmap"]
