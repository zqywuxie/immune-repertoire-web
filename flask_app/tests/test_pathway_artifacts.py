import pandas as pd
import pytest

from flask_app.models.database import db
from flask_app.exceptions import ValidationError
from flask_app.services.analysis_artifacts import revalidate_job_upstream
from flask_app.services.pathway_artifacts import resolve_pathway_input
from flask_app.tests.pathway_test_support import source_fixture


@pytest.fixture
def application(tmp_path):
    from flask import Flask
    from flask_app.routes.api_script_hub import script_hub_bp

    app = Flask(__name__, root_path=str(tmp_path))
    app.config.update(
        TESTING=True,
        REQUIRE_LOGIN=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RESULTS_FOLDER=str(tmp_path / "results"),
    )
    db.init_app(app)
    app.register_blueprint(script_hub_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_sources_are_dataset_scoped_and_direction_explicit(application,tmp_path):
    data,job,table,frame,expression=source_fixture(application,tmp_path)
    client=application.test_client()
    response=client.get('/api/script-hub/immune-infiltration-pathway/sources',query_string={
        'project_id':data['project_id'],'asset_set':'Set1'})
    assert response.status_code==200,response.json
    assert response.json['candidates'][0]['status']=='available'
    source=resolve_pathway_input({**data,'path':'/untrusted/override.csv'})
    assert source['path']==str(table)
    with pytest.raises(ValidationError,match='比较方向'):
        resolve_pathway_input({**data,'comparison':['B','A']})
    with pytest.raises(ValidationError,match='当前项目和数据集'):
        resolve_pathway_input({**data,'asset_set':'other'})
    resolve_pathway_input(data)
    queued={'payload':{'upstream_input':data['upstream_input']}}
    revalidate_job_upstream(queued)
    frame.loc[0,'NES']=2.3;frame.to_csv(table,index=False)
    with pytest.raises(ValidationError,match='通路结果已改变'):
        revalidate_job_upstream(queued)
    expression.write_text(expression.read_text()+'EGFR,4,3,2,1\n')
    with pytest.raises(ValidationError,match='来源输入已改变'):
        resolve_pathway_input(data)


def test_missing_terms_invalid_probabilities_and_old_results_are_unavailable(application,tmp_path):
    data,job,table,frame,expression=source_fixture(application,tmp_path)
    frame.iloc[:-1].to_csv(table,index=False)
    with pytest.raises(ValidationError,match='缺少预定义通路'):
        resolve_pathway_input(data)
    frame.loc[0,'pvalue']=1.1;frame.to_csv(table,index=False)
    with pytest.raises(ValidationError,match='概率值'):
        resolve_pathway_input(data)
    job.result={**job.result,'metadata':{'comparisons':[{'group1':'A','group2':'B'}]}}
    db.session.commit()
    with pytest.raises(ValidationError,match='没有完整'):
        resolve_pathway_input(data)
