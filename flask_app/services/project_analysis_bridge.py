"""
Bridge project-managed data into existing analysis pages.
"""

from __future__ import annotations

import json
import posixpath
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, ProjectAsset


class ProjectAnalysisBridge:
    """Resolve project analysis readiness and target page URLs."""

    PAGE_PATHS = {
        'similarity-heatmap': '/analysis/script-hub',
        'treemap': '/analysis/script-hub',
        'chord': '/analysis/script-hub',
        'combined-report': '/analysis/script-hub',
        'pipeline-comparison': '/analysis/pipeline-comparison',
        'db-alignment': '/analysis/script-hub',
        'script-hub': '/analysis/script-hub',
    }
    MODULE_HINTS = {
        'similarity-heatmap': 'charts',
        'treemap': 'charts',
        'chord': 'charts',
        'combined-report': 'charts',
        'pipeline-comparison': 'pipeline-comparison',
        'db-alignment': 'db-alignment',
    }
    CHART_MODULE_HINTS = {
        'similarity-heatmap': 'heatmap',
        'treemap': 'treemap',
        'chord': 'chord',
        'combined-report': 'combined',
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
            'source_mode': source_context['source_mode'],
        }
        if source_context.get('base_path'):
            params['base_path'] = source_context['base_path']
        if source_context.get('local_base_path'):
            params['local_base_path'] = source_context['local_base_path']
        if source_context.get('remote_source_id'):
            params['remote_source_id'] = source_context['remote_source_id']
        if source_context.get('remote_path'):
            params['remote_path'] = source_context['remote_path']
        if source_context.get('needs_remote_sync'):
            params['auto_sync'] = '1'
        if source_context.get('remote_pep_paths'):
            params['remote_pep_paths'] = json.dumps(source_context['remote_pep_paths'], ensure_ascii=False)
        if source_context.get('remote_datapoint_paths'):
            params['remote_datapoint_paths'] = json.dumps(source_context['remote_datapoint_paths'], ensure_ascii=False)
        if analysis_key in self.MODULE_HINTS:
            params['active_module'] = self.MODULE_HINTS[analysis_key]
        if analysis_key in self.CHART_MODULE_HINTS:
            params['chart_module'] = self.CHART_MODULE_HINTS[analysis_key]
        page_url = f"{self.PAGE_PATHS[analysis_key]}?{urlencode(params)}"
        return {
            'analysis_type': analysis_key,
            'page_url': page_url,
            'project_id': project.id,
            'project_name': project.name,
            **source_context,
        }

    def _resolve_analysis_source(self, project: Project, analysis_type: str) -> Dict[str, Any]:
        if analysis_type in {'similarity-heatmap', 'treemap', 'chord', 'combined-report', 'db-alignment', 'script-hub'}:
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
        pipeline_root = Path(source.get('local_base_path') or '') if source.get('local_base_path') else None
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
        local_assets = [asset for asset in assets if not self._remote_source_id(asset)]
        remote_assets = [asset for asset in assets if self._remote_source_id(asset)]

        local_root = self._local_asset_root(local_assets)
        remote_source_id = self._pick_remote_source_id(remote_assets)
        remote_pep_paths = self._remote_paths([asset for asset in remote_assets if asset.asset_type == 'pep'])
        remote_datapoint_paths = self._remote_paths([
            asset for asset in project.assets
            if asset.asset_type == 'datapoint' and self._remote_source_id(asset)
        ])
        remote_archive_paths = self._remote_paths([asset for asset in remote_assets if asset.asset_type == 'raw_archive'])
        remote_path = self._remote_root(remote_pep_paths or remote_archive_paths or remote_datapoint_paths)

        if local_root and remote_path:
            source_mode = 'mixed'
        elif remote_path:
            source_mode = 'remote'
        elif local_root:
            source_mode = 'local'
        else:
            source_mode = 'none'

        base_path = str(local_root) if local_root else ''
        return {
            'source_mode': source_mode,
            'base_path': base_path,
            'local_base_path': base_path,
            'remote_source_id': remote_source_id or '',
            'remote_path': remote_path or '',
            'remote_pep_paths': remote_pep_paths,
            'remote_datapoint_paths': remote_datapoint_paths,
            'needs_remote_sync': source_mode in {'remote', 'mixed'} and bool(remote_source_id and remote_path),
            'has_any': bool(local_root or remote_path),
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
    def _remote_source_id(asset: ProjectAsset) -> str:
        return str((asset.metadata_json or {}).get('remote_source_id') or '').strip()

    @classmethod
    def _pick_remote_source_id(cls, assets: Iterable[ProjectAsset]) -> str:
        for asset in assets:
            source_id = cls._remote_source_id(asset)
            if source_id:
                return source_id
        return ''

    @staticmethod
    def _remote_paths(assets: Iterable[ProjectAsset]) -> List[str]:
        paths: List[str] = []
        for asset in assets:
            path = str(asset.storage_path or '').strip()
            if path:
                paths.append(path.replace('\\', '/'))
        return list(dict.fromkeys(paths))

    @staticmethod
    def _remote_root(paths: List[str]) -> str:
        cleaned = [path.rstrip('/') or '/' for path in paths if path]
        if not cleaned:
            return ''
        if len(cleaned) == 1:
            return cleaned[0]

        split_paths = []
        for path in cleaned:
            normalized = path if path.startswith('/') else f"/{path}"
            split_paths.append([part for part in normalized.split('/') if part])
        common: List[str] = []
        for parts in zip(*split_paths):
            if len(set(parts)) != 1:
                break
            common.append(parts[0])
        return '/' + '/'.join(common) if common else posixpath.dirname(cleaned[0]) or '/'

    @staticmethod
    def _has_nested_directories(base_path: Path) -> bool:
        try:
            return any(path.is_dir() for path in base_path.iterdir())
        except OSError:
            return False


_project_analysis_bridge = ProjectAnalysisBridge()


def get_project_analysis_bridge() -> ProjectAnalysisBridge:
    return _project_analysis_bridge
