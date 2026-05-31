"""
Static integration catalog describing djangoProject and anal_pipeline migration status.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


_CATALOG: Dict[str, Any] = {
    'source_projects': {
        'djangoProject': {
            'description': 'Legacy Django backend with project, sample, search, and analysis workflow logic.',
            'main_content': [
                'project creation and asset upload',
                'sample summary import and editing',
                'sample search and field filtering',
                'download endpoints',
                'analysis scheduler for boxplot / gene usage / UMAP / DB alignment / top clone / ECDF / dominant clone / similar clone / CDR3 length',
            ],
        },
        'anal_pipeline': {
            'description': 'Standalone analysis scripts and notebooks for repertoire post-processing.',
            'main_content': [
                'DB alignment',
                'profile boxplot',
                'top clone',
                'UMAP',
                'pep shared and usage workflows',
                'machine learning',
                'Pgen',
                'MAIT / iNKT analysis',
                'volcano analysis',
            ],
        },
    },
    'flask_integration': {
        'already_integrated': [
            {
                'name': 'project and sample management',
                'status': 'implemented',
                'details': 'Project / ProjectAsset / SampleRecord / ProjectGroupSpec models with project APIs and sample import/update.',
            },
            {
                'name': 'project-driven analysis bridge',
                'status': 'implemented',
                'details': 'Project prepare/register-result flow for similarity heatmap, treemap, chord, and pipeline comparison.',
            },
            {
                'name': 'shared analysis input workspace',
                'status': 'implemented',
                'details': 'Heatmap / treemap / chord now share the same local/remote source panel and workspace logic.',
            },
        ],
        'django_overlap_modules': [
            {
                'name': 'DB alignment',
                'source': ['djangoProject', 'anal_pipeline'],
                'status': 'identified_for_service_migration',
            },
            {
                'name': 'profile boxplot',
                'source': ['djangoProject', 'anal_pipeline'],
                'status': 'identified_for_service_migration',
            },
            {
                'name': 'top clone',
                'source': ['djangoProject', 'anal_pipeline'],
                'status': 'identified_for_service_migration',
            },
            {
                'name': 'UMAP',
                'source': ['djangoProject', 'anal_pipeline'],
                'status': 'identified_for_service_migration',
            },
            {
                'name': 'pep / gene usage / shared-clone family',
                'source': ['djangoProject', 'anal_pipeline'],
                'status': 'identified_for_service_migration',
            },
        ],
        'anal_pipeline_unique_modules': [
            {
                'name': 'ML random forest workflow',
                'status': 'pending',
            },
            {
                'name': 'Pgen / SoNNia workflow',
                'status': 'pending',
            },
            {
                'name': 'MAIT / iNKT restricted clone analysis',
                'status': 'pending',
            },
            {
                'name': 'volcano analysis',
                'status': 'pending',
            },
        ],
        'default_scope_note': 'Authentication and email-code migration from djangoProject remains out of the current phase.',
    },
}


def get_integration_catalog() -> Dict[str, Any]:
    return deepcopy(_CATALOG)
