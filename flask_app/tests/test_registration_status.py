from sqlalchemy import event
from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import ProjectAsset, SampleRecord, db


def test_coverage_registration_state_is_page_scoped_and_preserves_original_identity(context):
    app, _, project = context
    for dataset in ['甲', '乙']:
        db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=dataset+'.csv',
            storage_path='/synthetic/'+dataset+'.csv', metadata_json={'asset_set':dataset,
                'validation':{'status':'valid', 'summary':{'inputs':[{'samples':['001','002','003','RNA-004']}]}}}))
    for original, dataset, attributes in [('001','甲',{}), ('001','乙',{'input_sample_id':None}),
        ('002','甲',{}), ('mapped-two','甲',{'input_sample_id':'002'}),
        ('unified-004','甲',{'input_sample_id':'RNA-004'}), ('RNA-004','甲',{'input_sample_id':None})]:
        db.session.add(SampleRecord(project_id=project.id, sample_id=original, sample_name=original,
            extra_metadata={'asset_set':dataset, **attributes}))
    for index in range(250):
        db.session.add(SampleRecord(project_id=project.id, sample_id=f'other{index}', sample_name='其他',
            extra_metadata={'asset_set':'甲'}))
    db.session.commit()
    project_id=project.id
    db.session.expunge_all()
    loaded=[]
    def on_load(value, _): loaded.append(value.id)
    event.listen(SampleRecord,'load',on_load)
    try:
        response=app.test_client().get(f'/api/projects/{project_id}/input-samples', query_string={'asset_set':'甲','page_size':2})
        assert response.status_code == 200
        assert [row['registration'] for row in response.json['samples']] == [
            {'status':'registered','count':1}, {'status':'multiple','count':2}]
        assert response.json['pagination']['total'] == 4
        assert not loaded, 'Coverage status must not hydrate full registration entities.'
        second=app.test_client().get(f'/api/projects/{project_id}/input-samples', query_string={'asset_set':'甲','page':2,'page_size':2}).json
        assert [row['registration'] for row in second['samples']] == [
            {'status':'unregistered','count':0}, {'status':'registered','count':1}]
        other=app.test_client().get(f'/api/projects/{project_id}/input-samples', query_string={'asset_set':'乙','q':'001'}).json
        assert other['samples'][0]['registration'] == {'status':'unregistered','count':0}
    finally:
        event.remove(SampleRecord,'load',on_load)
