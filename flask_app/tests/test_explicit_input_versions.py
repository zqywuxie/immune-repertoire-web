from pathlib import Path
import pytest
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.models.database import db, Project, ProjectAsset
from flask_app.routes.api_script_hub._common import _collect_project_script_hub_assets, _profile_path_from_request, _transcriptome_path_from_request
from flask_app.exceptions import ValidationError


def asset(project, tmp_path, name, *, dataset='甲', kind='profile', retired=False):
    path=tmp_path/name
    path.write_text('sample,group,metric\n001,健康,1\n002,疾病,2\n' if kind=='profile' else 'Gene\t001\t002\nG1\t1\t2\n',encoding='utf-8')
    item=ProjectAsset(project_id=project.id,asset_type=kind,original_name='同名.csv',storage_path=str(path),size=path.stat().st_size,metadata_json={'asset_set':dataset,'superseded':retired})
    db.session.add(item);db.session.flush();return item


def project():
    item=Project(name='显式版本回归');db.session.add(item);db.session.flush();return item


def test_current_input_remains_default_and_history_requires_explicit_path(profile_app,tmp_path):
    p=project();old=asset(p,tmp_path,'old.csv',retired=True);current=asset(p,tmp_path,'current.csv');db.session.commit()
    default=_collect_project_script_hub_assets(p.id,'甲',input_types={'profile'})
    assert default['profile_path']==current.storage_path
    explicit=_collect_project_script_hub_assets(p.id,'甲',selections={'profile_path':old.storage_path},input_types={'profile'})
    assert explicit['profile_path']==old.storage_path
    assert old.metadata_json['superseded'] is True
    assert not current.metadata_json['superseded']
    assert _collect_project_script_hub_assets(p.id,'甲',input_types={'profile'})['profile_path']==current.storage_path


def test_history_check_and_run_alias_resolve_same_version(profile_app,tmp_path):
    p=project();old=asset(p,tmp_path,'old.csv',retired=True);asset(p,tmp_path,'current.csv');db.session.commit()
    checked=profile_app.test_client().post('/api/script-hub/data-selection/inspect',json={'project_id':p.id,'asset_set':'甲','input_types':['profile'],'profile_path':old.storage_path})
    assert checked.status_code==200,checked.json
    assert checked.json['profile_path']==old.storage_path
    assert _profile_path_from_request({'project_id':p.id,'asset_set':'甲','datapoint_path':old.storage_path},'datapoint_path','profile_path')==old.storage_path


@pytest.mark.parametrize('other_project',[False,True])
def test_historical_selection_cannot_cross_project_or_dataset(profile_app,tmp_path,other_project):
    p=project();owner=project() if other_project else p
    wrong=asset(owner,tmp_path,'foreign.csv',dataset='乙' if not other_project else '甲',retired=True)
    asset(p,tmp_path,'current.csv');db.session.commit()
    with pytest.raises(ValidationError,match='当前项目的数据集'):
        _collect_project_script_hub_assets(p.id,'甲',selections={'profile_path':wrong.storage_path},input_types={'profile'})


def test_prepared_historical_input_can_be_reselected_after_inspection(profile_app,tmp_path):
    p=project();old=asset(p,tmp_path,'old.csv',retired=True);asset(p,tmp_path,'current.csv')
    prepared_path=tmp_path/'prepared.csv';prepared_path.write_text('sample,group,metric\n001,A,8\n002,B,9\n',encoding='utf-8')
    prepared=ProjectAsset(project_id=p.id,asset_type='prepared_input',original_name='prepared.csv',storage_path=str(prepared_path),size=prepared_path.stat().st_size,metadata_json={})
    db.session.add(prepared);db.session.flush()
    source_stat=Path(old.storage_path).stat();prepared_stat=prepared_path.stat()
    old.metadata_json={**old.metadata_json,'input_preparation':{'prepared_asset_id':prepared.id,'source_size':source_stat.st_size,'source_mtime_ns':source_stat.st_mtime_ns,'prepared_size':prepared_stat.st_size,'prepared_mtime_ns':prepared_stat.st_mtime_ns}}
    db.session.commit()
    first=_collect_project_script_hub_assets(p.id,'甲',selections={'profile_path':old.storage_path},input_types={'profile'})
    assert first['profile_path']==str(prepared_path)
    submitted=_profile_path_from_request({'project_id':p.id,'asset_set':'甲','datapoint_path':str(prepared_path)},'datapoint_path')
    assert submitted==first['profile_path']
    from flask_app.services.analysis_artifacts import capture_input_lineage
    lineage=capture_input_lineage(p.id,[{'asset_type':'profile','path':submitted}],'甲')
    assert [item['asset_id'] for item in lineage['source_assets']]==[old.id]


def test_unavailable_historical_preparation_is_not_replaced_by_current_input(profile_app,tmp_path):
    p=project();old=asset(p,tmp_path,'old.csv',retired=True);asset(p,tmp_path,'current.csv')
    stat=Path(old.storage_path).stat()
    old.metadata_json={**old.metadata_json,'input_preparation':{'prepared_asset_id':'missing','source_size':stat.st_size,'source_mtime_ns':stat.st_mtime_ns}}
    db.session.commit()
    with pytest.raises(ValidationError,match='整理后的输入已删除'):
        _collect_project_script_hub_assets(p.id,'甲',selections={'profile_path':old.storage_path},input_types={'profile'})


def test_transcriptome_execution_alias_does_not_fall_back_to_current_input(profile_app,tmp_path):
    p=project();old=asset(p,tmp_path,'old.tsv',kind='transcriptome',retired=True);asset(p,tmp_path,'current.tsv',kind='transcriptome');db.session.commit()
    result=_transcriptome_path_from_request({'project_id':p.id,'asset_set':'甲','expression_path':old.storage_path},'expression_path')
    assert result==old.storage_path
