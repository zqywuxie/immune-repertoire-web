from datetime import datetime, timedelta
import pytest

from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, ProjectGroupSpec, User, db
from flask_app.services.project_asset_lineage import asset_lineage
from flask_app.exceptions import AnalysisInProgressError


def asset(project, identifier, meta=None):
    value = ProjectAsset(id=identifier, project_id=project.id, asset_type='profile', original_name='same.csv',
                         storage_path='/synthetic/' + identifier + '/same.csv', size=10,
                         metadata_json=meta or {'asset_set': '甲'}, uploaded_at=datetime(2026, 1, 1))
    db.session.add(value)
    db.session.flush()
    return value


def job(project, identifier, payload, **kwargs):
    value = AnalysisJob(id=identifier, project_id=project.id, job_type='script_hub', module='profile',
                        status='completed', payload=payload, created_at=datetime(2026, 1, 1), **kwargs)
    db.session.add(value)
    db.session.flush()
    return value


def test_versions_follow_explicit_edges_not_names_and_paginate(context):
    app, service, project = context
    old = asset(project, 'old', {'superseded': True, 'superseded_by': ['middle'], 'content_version': 'v1', 'dataset': '甲'})
    middle = asset(project, 'middle', {'superseded': True, 'superseded_by': ['latest', 'missing'], 'content_version': 'v2', 'group': '甲'})
    latest = asset(project, 'latest', {'asset_set': '甲', 'content_version': 'v3'})
    unrelated = asset(project, 'same-name')
    latest.uploaded_at += timedelta(days=2)
    middle.uploaded_at += timedelta(days=1)
    other = Project(name='Other');db.session.add(other);db.session.flush()
    foreign = asset(other, 'foreign', {'superseded_by': ['old']})
    db.session.commit()
    first = asset_lineage(old, page_size=2)
    assert [row['id'] for row in first['items']] == ['latest', 'middle']
    assert first['pagination']['total'] == 3
    assert first['unavailable_links'] == 1
    last = asset_lineage(latest, page=2, page_size=2)
    assert last['items'][0]['id'] == old.id
    assert last['items'][0]['asset_set'] == '甲'
    assert last['items'][0]['content_version'] == 'v1'
    assert not any('storage_path' in row for row in first['items'])
    assert asset_lineage(unrelated)['pagination']['total'] == 1
    client=app.test_client()
    response=client.get(f'/api/projects/{project.id}/assets/{old.id}/lineage?page_size=2')
    assert response.status_code == 200 and response.json['pagination']['total'] == 3
    assert client.get(f'/api/projects/{project.id}/assets/{foreign.id}/lineage').status_code == 400
    assert client.get(f'/api/projects/{project.id}/assets/{old.id}/lineage?section=wrong').status_code == 400


def test_reference_view_and_delete_share_exact_id_and_legacy_path_rules(context):
    app, service, project = context
    old=asset(project,'old');new=asset(project,'new')
    job(project,'id-ref',{'input_assets':[{'asset_id':old.id,'path':old.storage_path}], '_task_name':'历史任务'})
    job(project,'path-ref',{'config_json':{'profile_path':old.storage_path}})
    job(project,'parent-ref',{'directory':'/synthetic/old'})
    job(project,'other-version',{'input_assets':[{'asset_id':new.id,'path':new.storage_path}]})
    done=job(project,'validation',{'asset_id':old.id});done.job_type='input_validation'
    active=job(project,'validation-active',{'asset_id':old.id});active.job_type='input_validation';active.status='queued'
    other=Project(name='Other');db.session.add(other);db.session.flush()
    job(other,'foreign-job',{'input_assets':[{'asset_id':old.id}]})
    db.session.commit()
    first=asset_lineage(old,'jobs',page=1,page_size=2)
    second=asset_lineage(old,'jobs',page=2,page_size=2)
    entries=first['items']+second['items']
    assert first['pagination']['total']==4
    assert {row['id'] for row in entries}=={'id-ref','path-ref','parent-ref','validation-active'}
    assert next(row for row in entries if row['id']=='id-ref')['match']=='asset_id'
    assert next(row for row in entries if row['id']=='path-ref')['match']=='path'
    with pytest.raises(AnalysisInProgressError) as exc: service.assert_asset_unreferenced(old)
    assert exc.value.details['job_id'] in {row['id'] for row in entries}


def test_group_references_point_to_exact_version_and_guard_matches(context):
    app, service, project=context
    old=asset(project,'old');new=asset(project,'new')
    spec=ProjectGroupSpec(project_id=project.id,name='固定旧版本',spec_json={'source_asset_id':old.id,'groups':['A','B']})
    db.session.add(spec);db.session.commit()
    assert asset_lineage(old,'groups')['items'][0]['id']==spec.id
    assert asset_lineage(new,'groups')['pagination']['total']==0
    with pytest.raises(AnalysisInProgressError) as exc: service.assert_asset_unreferenced(old)
    assert exc.value.details['group_spec_ids']==[spec.id]


def test_lineage_requires_current_account_project_ownership(context):
    app, service, project=context
    from werkzeug.security import generate_password_hash
    owner=User(username='owner',email='owner@example.test',password_hash=generate_password_hash('synthetic'))
    other=User(username='other',email='other@example.test',password_hash=generate_password_hash('synthetic'))
    db.session.add_all([owner,other]);db.session.flush();project.user_id=owner.id
    value=asset(project,'private');db.session.commit();app.config['REQUIRE_LOGIN']=True
    client=app.test_client()
    with client.session_transaction() as session: session['_user_id']=str(other.id);session['_fresh']=True
    response=client.get(f'/api/projects/{project.id}/assets/{value.id}/lineage')
    assert response.status_code == 400
    assert response.json["message"] == "Project not found"
    assert 'same.csv' not in response.get_data(as_text=True)
