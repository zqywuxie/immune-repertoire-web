"""Tests for similarity heatmap web report API endpoints."""

from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from flask import Flask, Response


def _import_api_module():
    try:
        return import_module('flask_app.routes.api_auto_heatmap')
    except ModuleNotFoundError:
        return import_module('routes.api_auto_heatmap')


def _import_validation_error():
    try:
        from flask_app.exceptions import ValidationError
    except ModuleNotFoundError:
        from exceptions import ValidationError
    return ValidationError


@pytest.fixture
def client():
    """Local test client fixture independent from repository-level fixtures."""
    api_auto_heatmap = _import_api_module()
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['RESULTS_FOLDER'] = str(Path.cwd() / 'data' / 'results')
    app.register_blueprint(api_auto_heatmap.auto_heatmap_bp)

    with app.test_client() as test_client:
        yield test_client


def test_generate_heatmap_report_requires_heatmap_result(client):
    """POST endpoint should validate heatmap_result."""
    response = client.post('/api/auto-heatmap/generate-heatmap-report', json={})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error'] == 'VALIDATION_ERROR'


def test_generate_heatmap_report_success(client, monkeypatch):
    """POST endpoint should return report URLs when generation succeeds."""
    api_auto_heatmap = _import_api_module()

    class FakeService:
        def generate_report(self, **kwargs):
            output_base = Path('E:/virtual/similarity_heatmap_report/job_test/shared_analysis')
            report_path = output_base / 'similarity_heatmap_report.html'
            metadata_path = output_base / 'metadata.json'
            return SimpleNamespace(
                job_id='job_test',
                output_base=output_base,
                metadata_path=metadata_path,
                report_path=report_path,
                metadata={'mode': 'traditional', 'metrics_count': 6},
            )

    monkeypatch.setattr(
        api_auto_heatmap,
        'get_similarity_heatmap_report_service',
        lambda results_root=None: FakeService(),
    )

    response = client.post(
        '/api/auto-heatmap/generate-heatmap-report',
        json={
            'heatmap_result': {
                'mode': 'traditional',
                'metrics': {'expression_sharing': {'matrix_data': {'samples': ['A', 'B'], 'values': [[1, 0.5], [0.5, 1]]}}},
                'images': {'expression_sharing': 'ZmFrZV9pbWFnZQ=='},
            },
            'output_name': 'job_test',
            'embed_images': False,
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['job_id'] == 'job_test'
    assert payload['report_url'].endswith(
        '/api/auto-heatmap/similarity-report/results/job_test/similarity_heatmap_report.html'
    )
    assert payload['metadata_url'].endswith(
        '/api/auto-heatmap/similarity-report/results/job_test/metadata.json'
    )


def test_get_similarity_heatmap_report_result_file_success(client, monkeypatch):
    """GET endpoint should serve generated report files."""
    api_auto_heatmap = _import_api_module()

    class FakeService:
        def resolve_result_file(self, job_id, relative_path):
            assert job_id == 'job1'
            assert relative_path == 'similarity_heatmap_report.html'
            return Path('E:/virtual/report.html')

    monkeypatch.setattr(
        api_auto_heatmap,
        'get_similarity_heatmap_report_service',
        lambda results_root=None: FakeService(),
    )
    monkeypatch.setattr(
        api_auto_heatmap,
        'send_file',
        lambda path: Response('report', mimetype='text/html'),
    )

    response = client.get('/api/auto-heatmap/similarity-report/results/job1/similarity_heatmap_report.html')
    assert response.status_code == 200
    assert b'report' in response.data


def test_get_similarity_heatmap_report_result_file_rejects_invalid_path(client, monkeypatch):
    """GET endpoint should map validation errors to HTTP 400."""
    api_auto_heatmap = _import_api_module()
    ValidationError = _import_validation_error()

    class FakeService:
        def resolve_result_file(self, job_id, relative_path):
            raise ValidationError(message='Invalid path.')

    monkeypatch.setattr(
        api_auto_heatmap,
        'get_similarity_heatmap_report_service',
        lambda results_root=None: FakeService(),
    )

    response = client.get('/api/auto-heatmap/similarity-report/results/job1/similarity_heatmap_report.html')
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error'] == 'VALIDATION_ERROR'


def test_generate_heatmap_converts_nan_to_null(client, monkeypatch):
    """Heatmap API should not emit NaN literals in JSON responses."""
    api_auto_heatmap = _import_api_module()

    class FakeService:
        def load_sample_data(self, samples, file_pattern, field_mapping):
            return {
                'A': pd.DataFrame({'cdr3': ['AAA'], 'copy': [1]}),
                'B': pd.DataFrame({'cdr3': ['BBB'], 'copy': [2]}),
            }

        def calculate_all_metrics(self, sample_data):
            matrix = pd.DataFrame(
                [[1.0, np.nan], [np.nan, 1.0]],
                index=['A', 'B'],
                columns=['A', 'B'],
            )
            return {'r2_inner': matrix}

    class FakeGenerator:
        @staticmethod
        def get_available_plot_types():
            return ['heatmap']

        def generate_heatmap(self, matrix, metric_config, metric_name=None):
            return (b'fake-image', {})

    monkeypatch.setattr(
        api_auto_heatmap,
        'get_auto_heatmap_service',
        lambda: FakeService(),
    )
    monkeypatch.setattr(api_auto_heatmap, 'HeatmapGenerator', FakeGenerator)

    response = client.post(
        '/api/auto-heatmap/generate-heatmap',
        json={
            'samples': [
                {
                    'original_name': 'A',
                    'display_name': 'A',
                    'folder_path': 'E:/virtual/A',
                    'data_files': [{'filename': 'A_pep.csv', 'filepath': 'E:/virtual/A_pep.csv'}],
                },
                {
                    'original_name': 'B',
                    'display_name': 'B',
                    'folder_path': 'E:/virtual/B',
                    'data_files': [{'filename': 'B_pep.csv', 'filepath': 'E:/virtual/B_pep.csv'}],
                },
            ],
            'file_pattern': '_pep.csv',
            'field_mapping': {
                'cdr3_column': 'cdr3',
                'copy_column': 'copy',
            },
            'config': {
                'plot_type': 'heatmap',
                'annotation': True,
            },
        },
    )

    assert response.status_code == 200
    raw_text = response.get_data(as_text=True)
    assert 'NaN' not in raw_text

    payload = response.get_json()
    assert payload['success'] is True
    assert payload['metrics']['r2_inner']['matrix_data']['values'] == [[1.0, None], [None, 1.0]]
    assert payload['metrics']['r2_inner']['table_data']['rows'] == [['A', 1.0, None], ['B', None, 1.0]]


def test_get_file_columns_converts_nan_to_null(client, monkeypatch):
    """Column preview API should not emit NaN literals in JSON responses."""
    api_auto_heatmap = _import_api_module()

    class FakeService:
        def get_file_columns(self, filepath):
            return {
                'columns': ['cdr3', 'd_gene', 'copy'],
                'suggested_cdr3': 'cdr3',
                'suggested_copy': 'copy',
                'sample_data': [
                    ['AAA', np.nan, 10],
                    ['BBB', 'IGHD1-1', 5],
                ],
                'rows': 2,
            }

    monkeypatch.setattr(
        api_auto_heatmap,
        'get_auto_heatmap_service',
        lambda: FakeService(),
    )

    response = client.post(
        '/api/auto-heatmap/get-file-columns',
        json={'filepath': 'E:/virtual/sample.csv'},
    )

    assert response.status_code == 200
    raw_text = response.get_data(as_text=True)
    assert 'NaN' not in raw_text

    payload = response.get_json()
    assert payload['success'] is True
    assert payload['sample_data'] == [['AAA', None, 10], ['BBB', 'IGHD1-1', 5]]


def test_generate_heatmap_report_can_bundle_cdr3_and_archive(client, monkeypatch):
    """Heatmap report API should attach CDR3 exports and archive shared_analysis."""
    api_auto_heatmap = _import_api_module()

    with TemporaryDirectory() as tmp_dir:
        output_base = Path(tmp_dir) / 'similarity_heatmap_report' / 'job_test' / 'shared_analysis'
        output_base.mkdir(parents=True, exist_ok=True)
        metadata_path = output_base / 'metadata.json'
        report_path = output_base / 'similarity_heatmap_report.html'
        metadata_path.write_text('{}', encoding='utf-8')
        report_path.write_text('<html></html>', encoding='utf-8')

        class FakeReportService:
            def generate_report(self, **kwargs):
                return SimpleNamespace(
                    job_id='job_test',
                    output_base=output_base,
                    metadata_path=metadata_path,
                    report_path=report_path,
                    metadata={'mode': 'chain', 'metrics_count': 6},
                )

            def create_archive(self, job_id, archive_name='shared_analysis.zip'):
                archive_path = output_base / archive_name
                archive_path.write_bytes(b'fake-zip')
                return archive_path

        class FakeHeatmapService:
            def load_sample_data_by_chains(self, samples, selected_chains, field_mapping):
                return {
                    'IGH': {
                        'SampleA': pd.DataFrame({'cdr3': ['AAA'], 'copy': [1]}),
                        'SampleB': pd.DataFrame({'cdr3': ['AAA'], 'copy': [2]}),
                    }
                }

        class FakeCDR3ExportService:
            def write_complete_export_directory(self, output_dir, sample_data, include_summary=True, top_n=100):
                target_dir = Path(output_dir) / 'IGH'
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / 'CDR3_Shared_List.xlsx').write_bytes(b'xlsx')
                return [target_dir / 'CDR3_Shared_List.xlsx']

        monkeypatch.setattr(
            api_auto_heatmap,
            'get_similarity_heatmap_report_service',
            lambda results_root=None: FakeReportService(),
        )
        monkeypatch.setattr(
            api_auto_heatmap,
            'get_auto_heatmap_service',
            lambda: FakeHeatmapService(),
        )
        monkeypatch.setattr(
            api_auto_heatmap,
            'get_cdr3_export_service',
            lambda: FakeCDR3ExportService(),
        )

        response = client.post(
            '/api/auto-heatmap/generate-heatmap-report',
            json={
                'heatmap_result': {
                    'mode': 'chain',
                    'chains': {
                        'IGH': {
                            'metrics': {'r2_inner': {'matrix_data': {'samples': ['A', 'B'], 'values': [[1, 0.5], [0.5, 1]]}}},
                            'images': {'r2_inner': 'ZmFrZV9pbWFnZQ=='},
                        }
                    },
                },
                'output_name': 'job_test',
                'create_archive': True,
                'cdr3_export_request': {
                    'samples': [
                        {
                            'original_name': 'SampleA',
                            'display_name': 'SampleA',
                            'folder_path': 'E:/virtual/A',
                            'data_files': [{'filename': 'A_IGH.csv', 'filepath': 'E:/virtual/A_IGH.csv'}],
                        },
                        {
                            'original_name': 'SampleB',
                            'display_name': 'SampleB',
                            'folder_path': 'E:/virtual/B',
                            'data_files': [{'filename': 'B_IGH.csv', 'filepath': 'E:/virtual/B_IGH.csv'}],
                        },
                    ],
                    'selected_chains': ['IGH'],
                    'field_mapping': {
                        'cdr3_column': 'cdr3',
                        'copy_column': 'copy',
                    },
                },
            },
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload['success'] is True
        assert payload['archive_url'].endswith(
            '/api/auto-heatmap/similarity-report/results/job_test/shared_analysis.zip'
        )
        assert payload['metadata']['cdr3_shared_list_path'] == 'CDR3_Shared_List'
        assert (output_base / 'CDR3_Shared_List' / 'IGH' / 'CDR3_Shared_List.xlsx').exists()
