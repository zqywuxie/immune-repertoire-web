import pandas as pd
from flask_app.services.statistical_analysis_service import StatisticalAnalysisService


def test_selected_group_column_does_not_require_category():
    data = pd.DataFrame({'arm': ['A'] * 3 + ['B'] * 3, 'value': [1, 4, 6, 2, 3, 5]})
    service = StatisticalAnalysisService()
    result = service.analyze_groups(data, 'value', 'arm')
    reference = service.analyze_groups(data.rename(columns={'arm': 'category'}), 'value', 'category')
    assert result['success'] is True
    assert result['kruskal_wallis'] == reference['kruskal_wallis']
    assert result['descriptive_stats'] == reference['descriptive_stats']


def test_missing_selected_column_is_an_explicit_error():
    result = StatisticalAnalysisService().analyze_groups(pd.DataFrame({'category': ['A', 'B']}), 'missing', 'arm')
    assert result['success'] is False
    assert 'missing' in result['error'] and 'arm' in result['error']


def test_real_upload_runs_through_worker_endpoint_contract(tmp_path):
    import io
    from flask import Flask
    from flask_app.models.database import db, File
    from flask_app.routes.api.files import bp
    from flask_app.routes.api_statistical import statistical_bp
    from flask_app.services.api_job_runner import call_json_endpoint
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SECRET_KEY='test',
                      SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, UPLOAD_FOLDER=tmp_path)
    db.init_app(app)
    app.register_blueprint(bp, url_prefix='/api')
    app.register_blueprint(statistical_bp)
    with app.app_context():
        db.create_all()
        try:
            client = app.test_client()
            content = b'arm,value\nA,1\nA,4\nA,6\nB,2\nB,3\nB,5\n'
            uploaded = client.post('/api/files/upload', data={'file': (io.BytesIO(content), 'values.csv'), 'project': 'test-project'})
            assert uploaded.status_code == 201
            metadata = uploaded.get_json()
            assert metadata['row_count'] == 6
            assert db.session.get(File, metadata['id']).project == 'test-project'
            payload = {'file_id': metadata['id'], 'value_column': 'value', 'group_column': 'arm'}
            result = call_json_endpoint('statistical.analyze', payload, None)
            assert result['results']['success'] is True
            assert len(result['results']['descriptive_stats']) == 2
            multiple = call_json_endpoint('statistical.analyze-multiple', {
                'files': [{'file_id': metadata['id'], 'name': 'values.csv'}],
                'value_column': 'value', 'group_column': 'arm'}, None)
            assert multiple['results']['results']['values.csv']['success'] is True
            chart = call_json_endpoint('statistical.boxplot', payload, None)
            import base64
            assert base64.b64decode(chart['image']).startswith(b'\x89PNG')
        finally:
            db.session.remove()
            db.drop_all()
