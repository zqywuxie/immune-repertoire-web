"""Tests for similarity heatmap web report API endpoints."""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

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

