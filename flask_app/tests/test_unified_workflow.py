import io
from flask import Flask
from flask_app.models.database import db
from flask_app.routes.api.files import bp
from flask_app.routes.api_analysis import analysis_bp
from flask_app.services.api_job_runner import call_json_endpoint


def test_uploaded_file_custom_analysis_returns_selected_metric(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SECRET_KEY='test',
                      SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, UPLOAD_FOLDER=tmp_path)
    db.init_app(app)
    app.register_blueprint(bp, url_prefix='/api')
    app.register_blueprint(analysis_bp)
    with app.app_context():
        db.create_all()
        try:
            client = app.test_client()
            upload = client.post('/api/files/upload', data={'file': (io.BytesIO(b'sample_id,metric,other\nS1,2,100\nS2,4,200\n'), 'profile.csv'), 'project': 'p1'})
            assert upload.status_code == 201
            file_id = upload.get_json()['id']
            result = call_json_endpoint('analysis.execute-unified', {
                'file_id': file_id, 'mode': 'custom', 'selected_fields': ['metric'],
                'parameters': {'sample_column': 'sample_id'}}, None)
            assert result['success'] is True
            table = result['results']['tables'][0]
            assert 'metric' in table['headers']
            assert 'other' not in table['headers']
            assert len(table['data']) == 2
            assert [float(row['metric']) for row in table['data']] == [2,4]
            upload = client.post('/api/files/upload', data={'file': (io.BytesIO(b'sample_id,TRA_reads\nS1,12\nS2,24\n'), 'reads.csv')})
            scheme_result = call_json_endpoint('analysis.execute-unified', {
                'file_id': upload.get_json()['id'], 'mode': 'scheme', 'scheme_id': 'sequencing_reads_chart',
                'field_mapping': {'Sample': 'sample_id'},
                'parameters': {'chains': ['TRA'], 'chart_config': {'figsize': [5,4], 'dpi': 60}}}, None)
            assert scheme_result['success'] is True
            assert scheme_result['results']['charts']
            assert len(scheme_result['results']['tables'][0]['data']) == 2
        finally:
            db.session.remove()
            db.drop_all()


def test_single_field_mapping_is_applied():
    import pandas as pd
    from flask_app.services.analysis_pipeline import AnalysisPipeline
    actual = AnalysisPipeline(save_history=False)._preprocess_data(pd.DataFrame({'sample_id': ['S1'], 'value': [3]}), {'Sample': 'sample_id'})
    assert list(actual.columns) == ['Sample', 'value']
