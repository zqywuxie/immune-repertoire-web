from datetime import datetime, timedelta
from flask_app.app import create_app
from flask_app.models.database import AnalysisJob, Project, SampleRecord, db


def test_history_filters_before_paging_and_excludes_children():
    app = create_app("testing")
    with app.app_context():
        now = datetime.utcnow()
        for i in range(121):
            db.session.add(AnalysisJob(id=f"history-{i:03}", job_type="analysis", module="profile", status="completed",
                created_at=now-timedelta(minutes=i), payload={"asset_set":"批次一", "task_name":f"指标比较{i}"}))
        db.session.add(AnalysisJob(id="hidden-child", job_type="analysis", module="profile",status="running",payload={"parent_job_id":"history-000"}))
        db.session.commit()
        client = app.test_client()
        first = client.get('/api/jobs?limit=50').get_json()
        assert first['total'] == 121 and first['has_more']
        assert first['counts'] == {'completed':121}
        last = client.get('/api/jobs?limit=50&offset=100').get_json()
        assert len(last['jobs']) == 21 and not last['has_more']
        found = client.get('/api/jobs?q=history-120&asset_set=批次一').get_json()
        assert found['total'] == 1 and found['jobs'][0]['id'] == 'history-120'
        named = client.get('/api/jobs?q=指标比较120').get_json()
        assert named['total'] == 1 and named['jobs'][0]['id'] == 'history-120'


def test_sample_search_export_and_options_share_scope():
    app = create_app("testing")
    with app.app_context():
        project = Project(id='sample-search',name='样本项目',status='active')
        db.session.add(project)
        db.session.add_all([SampleRecord(id='s1',project_id=project.id,sample_id='001',sample_name='目标样本'),
                            SampleRecord(id='s2',project_id=project.id,sample_id='002',sample_name='其他样本')])
        db.session.commit()
        client = app.test_client()
        listed = client.get('/api/samples?q=目标').get_json()['samples']
        exported = client.get('/api/samples/export?q=目标').data.decode('utf-8-sig')
        assert [row['id'] for row in listed] == ['s1']
        assert '目标样本' in exported and '其他样本' not in exported
        assert client.get('/api/samples/field-options?field=sample_id').get_json()['fields']['sample_id'] == ['001','002']


def test_job_pagination_sorts_without_large_json_and_preserves_tie_order():
    from sqlalchemy import event
    app = create_app("testing")
    with app.app_context():
        created = datetime(2026, 10, 7)
        for i in range(6):
            db.session.add(AnalysisJob(
                id=f"large-json-{i}", job_type="analysis", module="profile", status="completed",
                created_at=created, payload={"task_name": "large-sort-regression", "blob": "x" * 200000},
                result={"csv_urls": [f"/result-{i}.csv"], "large_table": "y" * 200000},
            ))
        db.session.commit()
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            response = app.test_client().get('/api/jobs?q=large-sort-regression&offset=2&limit=2')
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        assert response.status_code == 200
        page = response.get_json()
        assert page['total'] == 6 and page['has_more']
        assert [job['id'] for job in page['jobs']] == ['large-json-3', 'large-json-2']
        assert page['jobs'][0]['result']['large_table'] == 'y' * 200000
        sorted_queries = [sql for sql in statements if 'ORDER BY analysis_jobs.created_at' in sql]
        assert len(sorted_queries) == 1
        projection = sorted_queries[0].split('FROM', 1)[0]
        assert 'analysis_jobs.id' in projection
        assert all(f'analysis_jobs.{field}' not in projection for field in ('payload', 'history', 'result'))
