from pathlib import Path
import sys

import pytest
from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask_app.routes.pages import pages_bp


@pytest.fixture
def client():
    template_root = Path(__file__).resolve().parents[1] / 'templates'
    static_root = Path(__file__).resolve().parents[1] / 'static'

    app = Flask(
        __name__,
        template_folder=str(template_root),
        static_folder=str(static_root),
    )
    app.config['TESTING'] = True
    app.secret_key = 'workspace-nav-test'
    app.register_blueprint(pages_bp)

    with app.test_client() as test_client:
        yield test_client


def test_root_redirects_to_analysis_workspace(client):
    response = client.get('/', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/analysis')


def test_management_workspace_uses_management_navigation_only(client):
    response = client.get('/management')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-workspace="management"' in html
    assert 'data-target-workspace="analysis"' in html
    assert 'data-nav-scope="management"' in html
    assert 'data-nav-key="upload"' in html
    assert 'data-nav-key="analysis-home"' not in html


def test_analysis_workspace_uses_analysis_navigation_only(client):
    response = client.get('/analysis')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-workspace="analysis"' in html
    assert 'data-target-workspace="management"' in html
    assert 'data-nav-scope="analysis"' in html
    assert 'data-nav-key="combined-report"' not in html
    assert 'data-nav-key="pipeline-comparison"' in html
    assert 'data-nav-key="script-hub"' in html
    assert 'data-nav-key="script-hub-jobs"' in html
    assert 'data-nav-key="upload"' not in html


def test_script_hub_jobs_page_uses_analysis_workspace(client):
    response = client.get('/analysis/script-hub/jobs')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-workspace="analysis"' in html
    assert '后台任务' in html
    assert 'data-nav-key="script-hub-jobs"' in html


def test_settings_page_preserves_management_workspace_shell(client):
    response = client.get('/settings?workspace=management')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-workspace="management"' in html
    assert 'data-nav-scope="management"' in html
    assert 'data-nav-key="analysis-home"' not in html


def test_management_pages_include_unified_management_ui(client):
    for path, marker in [
        ('/management', 'management-shell'),
        ('/projects', 'project-shell'),
        ('/samples', 'sample-shell'),
        ('/projects/project-ui-test', 'project-detail-shell'),
    ]:
        response = client.get(path)
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'data-workspace="management"' in html
        assert 'management_common.css' in html
        assert marker in html
