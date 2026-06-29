"""Storage URI helpers for project assets.

The first implementation is local-file backed so existing absolute
``storage_path`` values remain valid while new assets can carry a stable
``local://`` URI in metadata.

Full interface (see architecture doc section 4.4)::

    put_file   Copy a local file into managed storage, return URI
    get_file   Resolve a storage URI to a readable Path
    exists     Check whether a storage ref points to an existing file
    delete     Remove a file from storage
    presign    Generate a time-limited access URL (API-layer pass-through)
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional, Union
from urllib.parse import quote, unquote, urlparse


class LocalStorageAdapter:
    """Resolve local storage URIs and legacy filesystem paths.

    Parameters
    ----------
    root_dir:
        Managed storage root.  When set, ``put_file`` copies files into this
        directory under the given key.  When unset, ``put_file`` falls back to
        returning a ``local://`` URI pointing at the source path unchanged.
    """

    scheme = "local"

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir

    # ── URI ↔ Path resolution ────────────────────────────────────────

    def uri_for_path(self, path: Path) -> str:
        """Convert a filesystem path to a ``local://`` URI."""
        resolved = Path(path).resolve()
        return f"{self.scheme}:///{quote(resolved.as_posix(), safe='/')}"

    def resolve(self, storage_ref: Union[str, Path, None]) -> Optional[Path]:
        """Resolve a storage URI or legacy path to a filesystem Path.

        Handles three forms:
        1. ``local:///…``  – URI produced by ``uri_for_path``
        2. ``C:\\…``      – legacy Windows absolute path
        3. ``/data/…``    – POSIX absolute path
        """
        raw_value = str(storage_ref or "").strip()
        if not raw_value:
            return None

        # Legacy Windows absolute path (e.g. "C:\foo" or "C:/foo")
        if len(raw_value) >= 3 and raw_value[1] == ":" and raw_value[2] in {"\\", "/"}:
            return Path(raw_value)

        parsed = urlparse(raw_value)
        if parsed.scheme:
            if parsed.scheme != self.scheme:
                return None
            if parsed.netloc and parsed.path:
                path_value = unquote(f"/{parsed.netloc}{parsed.path}")
            else:
                path_value = unquote(parsed.path or parsed.netloc)
            # Strip extra leading slash on Windows drive letters
            if len(path_value) >= 4 and path_value[0] == "/" and path_value[2] == ":":
                path_value = path_value[1:]
            return Path(path_value)

        return Path(raw_value)

    # ── CRUD operations ───────────────────────────────────────────────

    def put_file(self, local_path: Union[Path, str], key: str) -> str:
        """Copy a local file into managed storage and return its URI.

        When ``root_dir`` is configured the file is copied to
        ``<root_dir>/<key>`` and a ``local://`` URI is returned.
        Otherwise the source file's location is returned as a URI without
        copying — useful while the adapter is running without a managed
        storage root.
        """
        source = Path(local_path)
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")

        if self.root_dir:
            dest = (self.root_dir / key).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            return self.uri_for_path(dest)

        return self.uri_for_path(source)

    def get_file(self, storage_uri: str) -> Path:
        """Resolve a storage URI to a readable filesystem Path.

        Raises ``FileNotFoundError`` if the URI cannot be resolved or the
        file does not exist.
        """
        path = self.resolve(storage_uri)
        if path is None:
            raise FileNotFoundError(f"Cannot resolve storage URI: {storage_uri!r}")
        if not path.is_file():
            raise FileNotFoundError(f"Resolved path is not a file: {path}")
        return path

    def exists(self, storage_ref: Union[str, Path, None]) -> bool:
        """Return True if the storage reference points to an existing file."""
        path = self.resolve(storage_ref)
        return bool(path and path.is_file())

    def delete(self, storage_uri: str) -> None:
        """Remove a file from local storage.

        This is a no-op if the file does not exist (idempotent).
        Raises ``OSError`` only on permission errors during removal.
        """
        path = self.resolve(storage_uri)
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            if path.exists():
                raise

    def presign(self, storage_uri: str, expires: int = 3600) -> str:
        """Return a reference to the file for API-layer serving.

        For local storage this is the URI itself — the API layer handles
        authentication and file transfer.  For S3/MinIO backends this would
        generate a time-limited pre-signed URL.
        """
        return storage_uri


class S3Adapter:
    """Storage adapter backed by S3-compatible object storage (AWS S3 / MinIO).

    Configuration via environment variables::

        STORAGE_BACKEND=s3
        S3_ENDPOINT_URL=https://s3.amazonaws.com     # or http://127.0.0.1:9000 for MinIO
        S3_BUCKET=immune-repertoire
        S3_ACCESS_KEY=...
        S3_SECRET_KEY=...
        S3_REGION=us-east-1
        S3_PRESIGN_EXPIRES=3600
    """

    scheme = "s3"

    def __init__(
        self,
        endpoint_url: str | None = None,
        bucket: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        presign_expires: int = 3600,
    ) -> None:
        import os

        self.endpoint_url = endpoint_url or os.environ.get("S3_ENDPOINT_URL", "")
        self.bucket = bucket or os.environ.get("S3_BUCKET", "immune-repertoire")
        self.region = region or os.environ.get("S3_REGION", "us-east-1")
        self.presign_expires = int(
            os.environ.get("S3_PRESIGN_EXPIRES", str(presign_expires))
        )
        self._access_key = access_key or os.environ.get("S3_ACCESS_KEY", "")
        self._secret_key = secret_key or os.environ.get("S3_SECRET_KEY", "")
        self._client = None  # Lazy-init on first use

    @property
    def client(self):
        """Lazy-init boto3 S3 client."""
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise ImportError(
                    "S3Adapter requires boto3. Install with: pip install boto3"
                ) from exc

            kwargs: dict = {"service_name": "s3", "region_name": self.region}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            if self._access_key:
                kwargs["aws_access_key_id"] = self._access_key
            if self._secret_key:
                kwargs["aws_secret_access_key"] = self._secret_key

            self._client = boto3.client(**kwargs)
        return self._client

    def uri_for_path(self, key: str) -> str:
        """Build an s3:// URI from an object key."""
        return f"{self.scheme}://{self.bucket}/{key.lstrip('/')}"

    def resolve(self, storage_ref: str | Path | None) -> str | None:
        """Extract the S3 object key from a storage URI."""
        raw = str(storage_ref or "").strip()
        if not raw:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(raw)
        if parsed.scheme != self.scheme:
            return None
        return parsed.path.lstrip("/") or parsed.netloc

    def put_file(self, local_path: str | Path, key: str) -> str:
        """Upload a local file to S3 and return its s3:// URI."""
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"Source file not found: {path}")
        obj_key = key.lstrip("/")
        self.client.upload_file(str(path), self.bucket, obj_key)
        return self.uri_for_path(obj_key)

    def get_file(self, storage_uri: str) -> Path:
        """Download a file from S3 to a local temp path and return it."""
        import tempfile

        obj_key = self.resolve(storage_uri)
        if obj_key is None:
            raise FileNotFoundError(f"Cannot resolve S3 URI: {storage_uri!r}")

        suffix = Path(obj_key).suffix or ".tmp"
        tmp = Path(tempfile.mktemp(suffix=suffix))
        self.client.download_file(self.bucket, obj_key, str(tmp))
        return tmp

    def exists(self, storage_ref: str | Path | None) -> bool:
        """Check whether an object exists in S3."""
        obj_key = self.resolve(storage_ref)
        if obj_key is None:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=obj_key)
            return True
        except Exception:
            return False

    def delete(self, storage_uri: str) -> None:
        """Delete an object from S3."""
        obj_key = self.resolve(storage_uri)
        if obj_key is None:
            return
        try:
            self.client.delete_object(Bucket=self.bucket, Key=obj_key)
        except Exception:
            pass  # best-effort deletion

    def presign(self, storage_uri: str, expires: int | None = None) -> str:
        """Generate a pre-signed download URL."""
        obj_key = self.resolve(storage_uri)
        if obj_key is None:
            return storage_uri
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": obj_key},
            ExpiresIn=expires or self.presign_expires,
        )


_local_storage_adapter = None


def get_storage_adapter():
    """Return the configured storage adapter.

    Backend selection via ``STORAGE_BACKEND`` env var:

        local  (default)  LocalStorageAdapter
        s3                 S3Adapter (requires boto3)
    """
    import os

    backend = os.environ.get("STORAGE_BACKEND", "local").strip().lower()

    if backend == "s3":
        return S3Adapter()

    global _local_storage_adapter
    if _local_storage_adapter is None:
        _local_storage_adapter = LocalStorageAdapter()
    return _local_storage_adapter
