"""Tests for the S3 storage adapter (unit tests — no real S3 needed)."""

import os
from flask_app.services.storage_adapter import S3Adapter


def test_s3_adapter_scheme():
    adapter = S3Adapter(bucket="test-bucket", access_key="x", secret_key="y")
    assert adapter.scheme == "s3"


def test_uri_for_path():
    adapter = S3Adapter(bucket="test-bucket")
    uri = adapter.uri_for_path("projects/p1/data.csv")
    assert uri == "s3://test-bucket/projects/p1/data.csv"


def test_uri_for_path_strips_leading_slash():
    adapter = S3Adapter(bucket="test-bucket")
    uri = adapter.uri_for_path("/projects/p1/data.csv")
    assert uri == "s3://test-bucket/projects/p1/data.csv"


def test_resolve_uri():
    adapter = S3Adapter(bucket="test-bucket")
    assert adapter.resolve("s3://test-bucket/projects/p1/data.csv") == "projects/p1/data.csv"


def test_resolve_none():
    adapter = S3Adapter(bucket="test-bucket")
    assert adapter.resolve(None) is None
    assert adapter.resolve("") is None


def test_resolve_foreign_scheme():
    adapter = S3Adapter(bucket="test-bucket")
    assert adapter.resolve("local:///data/file.csv") is None


def test_exists_false_for_none():
    adapter = S3Adapter(bucket="test-bucket")
    assert adapter.exists(None) is False


def test_get_storage_adapter_factory_local_default(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    from flask_app.services.storage_adapter import get_storage_adapter, LocalStorageAdapter
    adapter = get_storage_adapter()
    assert isinstance(adapter, LocalStorageAdapter)


def test_get_storage_adapter_factory_s3(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "test")
    from flask_app.services.storage_adapter import get_storage_adapter, S3Adapter
    adapter = get_storage_adapter()
    assert isinstance(adapter, S3Adapter)
