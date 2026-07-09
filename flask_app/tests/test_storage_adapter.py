"""Tests for the local storage adapter."""

import os
import tempfile
from pathlib import Path

from flask_app.services.storage_adapter import LocalStorageAdapter


def test_uri_for_path_roundtrip():
    adapter = LocalStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"col1,col2\n")
        tmp_path = Path(f.name)

    try:
        uri = adapter.uri_for_path(tmp_path)
        assert uri.startswith("local:///")
        resolved = adapter.resolve(uri)
        assert resolved == tmp_path.resolve()
    finally:
        tmp_path.unlink(missing_ok=True)


def test_resolve_legacy_windows_path():
    adapter = LocalStorageAdapter()
    result = adapter.resolve("C:\\Users\\test\\data\\sample.csv")
    assert result == Path("C:\\Users\\test\\data\\sample.csv")


def test_resolve_legacy_posix_path():
    adapter = LocalStorageAdapter()
    result = adapter.resolve("/data/projects/sample.csv")
    assert result == Path("/data/projects/sample.csv")


def test_resolve_empty_returns_none():
    adapter = LocalStorageAdapter()
    assert adapter.resolve("") is None
    assert adapter.resolve(None) is None


def test_resolve_foreign_scheme_returns_none():
    adapter = LocalStorageAdapter()
    assert adapter.resolve("s3://bucket/key") is None


def test_exists_true_for_existing_file():
    adapter = LocalStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"data\n")
        tmp_path = Path(f.name)

    try:
        assert adapter.exists(tmp_path) is True
        assert adapter.exists(str(tmp_path)) is True
        assert adapter.exists(adapter.uri_for_path(tmp_path)) is True
    finally:
        tmp_path.unlink(missing_ok=True)


def test_exists_false_for_missing_file():
    adapter = LocalStorageAdapter()
    assert adapter.exists("C:\\nonexistent\\file.csv") is False
    assert adapter.exists("/nonexistent/file.csv") is False


def test_exists_false_for_none():
    adapter = LocalStorageAdapter()
    assert adapter.exists(None) is False


def test_put_file_without_root_returns_uri():
    adapter = LocalStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"col1\n")
        tmp_path = Path(f.name)

    try:
        uri = adapter.put_file(tmp_path, "projects/test/assets/test.csv")
        assert uri.startswith("local:///")
        resolved = adapter.resolve(uri)
        assert resolved == tmp_path.resolve()
    finally:
        tmp_path.unlink(missing_ok=True)


def test_put_file_with_root_copies_and_returns_uri():
    with tempfile.TemporaryDirectory() as root_dir:
        adapter = LocalStorageAdapter(root_dir=Path(root_dir))

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"col1\n")
            src = Path(f.name)

        try:
            uri = adapter.put_file(src, "projects/p1/assets/data.csv")
            assert uri.startswith("local:///")
            resolved = adapter.resolve(uri)
            assert resolved is not None
            assert resolved.exists()
            assert resolved.read_text() == "col1\n"
            # Should be under root_dir
            assert str(root_dir) in str(resolved)
        finally:
            src.unlink(missing_ok=True)


def test_put_file_missing_source_raises():
    adapter = LocalStorageAdapter()
    try:
        adapter.put_file(Path("C:\\nonexistent\\file.csv"), "key")
    except FileNotFoundError:
        pass


def test_get_file_returns_path():
    adapter = LocalStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"data\n")
        tmp_path = Path(f.name)

    try:
        uri = adapter.uri_for_path(tmp_path)
        result = adapter.get_file(uri)
        assert result == tmp_path.resolve()
        assert result.read_text() == "data\n"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_get_file_bad_uri_raises():
    adapter = LocalStorageAdapter()
    try:
        adapter.get_file("/nonexistent/file.csv")
    except FileNotFoundError:
        pass


def test_delete_removes_file():
    adapter = LocalStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"data\n")
        tmp_path = Path(f.name)

    uri = adapter.uri_for_path(tmp_path)
    assert tmp_path.exists()

    adapter.delete(uri)
    assert not tmp_path.exists()


def test_delete_missing_file_is_noop():
    adapter = LocalStorageAdapter()
    adapter.delete("/nonexistent/file.csv")


def test_presign_returns_uri():
    adapter = LocalStorageAdapter()
    uri = "local:///data/projects/test.csv"
    assert adapter.presign(uri) == uri
    assert adapter.presign(uri, expires=1800) == uri
