from collections import namedtuple
from flask_login import login_user
from flask_app.tests.test_data_management_contracts import context,upload
from flask_app.models.database import ProjectAsset,User,db
from flask_app.services.storage_statistics import storage_statistics


def test_registration_categories_and_shared_filesystem_are_separate(context,tmp_path,monkeypatch):
    app,service,project=context
    first=upload(service,project)
    first.metadata_json={**first.metadata_json,'superseded':True}
    current=upload(service,project,dataset='乙')
    result=ProjectAsset(project_id=project.id,asset_type='processed_result',original_name='结果',storage_path='/unread/synthetic',size=700,metadata_json={})
    db.session.add(result);db.session.commit()
    app.config.update(USER_DATA_ROOT=str(tmp_path),PROJECT_DATA_ROOT=str(tmp_path),RESULTS_DIR=str(tmp_path))
    calls=[]
    def usage(path):
        calls.append(path);return namedtuple('Usage','total used free')(10000,7000,3000)
    monkeypatch.setattr('flask_app.services.storage_statistics.shutil.disk_usage',usage)
    value=storage_statistics()
    assert value['registered_categories']['current_inputs']=={'count':1,'bytes':current.size}
    assert value['registered_categories']['historical_inputs']=={'count':1,'bytes':first.size}
    assert value['registered_categories']['results']=={'count':1,'bytes':700}
    assert value['asset_bytes']==first.size+current.size+700
    assert len(calls)==1 and len(value['filesystem_capacity'])==1
    assert value['filesystem_capacity'][0]['free_bytes']==3000
    assert value['asset_bytes']!=value['filesystem_capacity'][0]['used_bytes']
    assert value['cache_bytes'] is None and 'path' not in value['filesystem_capacity'][0]


def test_normal_account_does_not_read_shared_disk_or_foreign_assets(context,monkeypatch):
    app,service,project=context;upload(service,project)
    user=User(username='storage-user',email='storage@synthetic.test',password_hash='synthetic-no-login')
    db.session.add(user);db.session.commit();app.config['REQUIRE_LOGIN']=True
    def forbidden(path):raise AssertionError('normal account must not read shared capacity')
    monkeypatch.setattr('flask_app.services.storage_statistics.shutil.disk_usage',forbidden)
    with app.test_request_context():
        login_user(user)
        value=storage_statistics()
        assert value['assets']==0 and value['asset_bytes']==0
        assert not value['capacity_visible'] and value['filesystem_capacity']==[]


def test_missing_mount_capacity_is_unknown_not_zero(context):
    app,_,_=context
    app.config.update(USER_DATA_ROOT='/missing/synthetic',PROJECT_DATA_ROOT=None,RESULTS_DIR=None)
    value=storage_statistics()
    assert len(value['filesystem_capacity'])==3
    assert all(row['available'] is False and 'free_bytes' not in row for row in value['filesystem_capacity'])
