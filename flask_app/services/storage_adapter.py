"""Storage URI helpers for project assets.

The first implementation is local-file backed so existing absolute
``storage_path`` values remain valid while new assets can carry a stable
``local://`` URI in metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse


class LocalStorageAdapter:
    """Resolve local storage URIs and legacy filesystem paths."""

    scheme = "local"

    def uri_for_path(self, path: Path) -> str:
        resolved = Path(path).resolve()
        return f"{self.scheme}:///{quote(resolved.as_posix(), safe='/')}"

    def resolve(self, storage_ref: str | Path | None) -> Optional[Path]:
        raw_value = str(storage_ref or "").strip()
        if not raw_value:
            return None
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
            if len(path_value) >= 4 and path_value[0] == "/" and path_value[2] == ":":
                path_value = path_value[1:]
            return Path(path_value)
        return Path(raw_value)

    def exists(self, storage_ref: str | Path | None) -> bool:
        path = self.resolve(storage_ref)
        return bool(path and path.exists())


_local_storage_adapter = LocalStorageAdapter()


def get_storage_adapter() -> LocalStorageAdapter:
    return _local_storage_adapter
