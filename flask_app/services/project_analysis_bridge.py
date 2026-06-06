"""
Bridge project-managed data into existing analysis pages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, ProjectAsset


class ProjectAnalysisBridge:
    """Resolve project analysis readiness and target page URLs."""

    PAGE_PATHS = {
        'pipeline-comparison': '/analysis/pipeline-comparison',
        'db-alignment': '/analysis/script-hub',
        'script-hub': '/analysis/script-hub',
    }
    MODULE_HINTS = {
        'pipeline-comparison': 'pipeline-comparison',
        'db-alignment': 'db-alignment',
    }

    def prepare(self, project: Project, analysis_type: str) -> Dict[str, Any]:
        analysis_key = str(analysis_type or '').strip()
        if analysis_key not in self.PAGE_PATHS:
            raise ValidationError(message="Unsupported analysis type", details={'analysis_type': analysis_type})

        source_context = self._resolve_analysis_source(project, analysis_key)
        params = {
            'project_id': project.id,
            'project_name': project.name,
            'auto_scan': '1',
            'analysis_type': analysis_key,
        }
        if source_context.get('base_path'):
            params['base_path'] = source_context['base_path']
        if analysis_key in self.MODULE_HINTS:
            params['active_module'] = self.MODULE_HINTS[analysis_key]
        page_url = f"{self.PAGE_PATHS[analysis_key]}?{urlencode(params)}"
        return {
            'analysis_type': analysis_key,
            'page_url': page_url,
            'project_id': project.id,
            'project_name': project.name,
            **source_context,
        }

    def _resolve_analysis_source(self, project: Project, analysis_type: str) -> Dict[str, Any]:
        if analysis_type in {'db-alignment', 'script-hub'}:
            source = self._asset_source(project, {'pep'})
            if not source['has_any']:
                source = self._asset_source(project, {'raw_archive'})
            if source['has_any']:
                return source
            raise ValidationError(
                message="This project has no pep/raw archive data available for the selected analysis",
                details={'project_id': project.id, 'analysis_type': analysis_type},
            )

        source = self._asset_source(project, {'raw_archive', 'pep'})
        pipeline_root = Path(source.get('base_path') or '') if source.get('base_path') else None
        if pipeline_root is None or not pipeline_root.exists():
            raise ValidationError(
                message="This project has no folder-style data available for pipeline comparison",
                details={'project_id': project.id, 'analysis_type': analysis_type},
            )
        if not self._has_nested_directories(pipeline_root):
            raise ValidationError(
                message="Pipeline comparison requires a root directory containing pipeline subfolders",
                details={'base_path': str(pipeline_root)},
            )
        return source

    def _asset_source(self, project: Project, allowed_types: Iterable[str]) -> Dict[str, Any]:
        allowed = set(allowed_types)
        assets = [
            asset for asset in project.assets
            if asset.asset_type in allowed
        ]
        local_root = self._local_asset_root(assets)
        base_path = str(local_root) if local_root else ''
        return {
            'base_path': base_path,
            'has_any': bool(local_root),
        }

    def _local_asset_root(self, assets: Iterable[ProjectAsset]) -> Optional[Path]:
        roots = []
        for asset in assets:
            asset_path = Path(asset.storage_path)
            if not asset_path.exists():
                continue
            metadata = asset.metadata_json or {}
            relative_path = str(metadata.get('relative_path') or '').strip()
            if relative_path:
                depth = len(Path(relative_path).parts)
                root = asset_path
                for _ in range(depth):
                    root = root.parent
                roots.append(root)
            else:
                roots.append(asset_path.parent)

        roots = [root for root in roots if root.exists()]
        if not roots:
            return None
        return sorted(roots, key=lambda item: len(item.parts))[0]

    @staticmethod
    def _has_nested_directories(base_path: Path) -> bool:
        try:
            return any(path.is_dir() for path in base_path.iterdir())
        except OSError:
            return False


_project_analysis_bridge = ProjectAnalysisBridge()


def get_project_analysis_bridge() -> ProjectAnalysisBridge:
    return _project_analysis_bridge
