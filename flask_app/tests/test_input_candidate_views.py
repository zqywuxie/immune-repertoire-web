"""Lightweight paged inputs and exact source restoration preserve scoped identity."""
import re
from sqlalchemy import event
from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import Project, ProjectAsset, db
from flask_app.services.project_input_summary import input_sample_summary, projected_input_assets
from flask_app.services.project_catalog_service import project_catalog, project_statistics

def asset(project,number,*,kind="profile",dataset="甲",history=False,status="valid"):
    row=ProjectAsset(project_id=project.id,asset_type=kind,original_name=f"指标{number:03d}.csv",storage_path=f"/synthetic/{number}",
        metadata_json={"group_label":dataset,"content_version":f"v{number}","superseded":history,"unused_manifest":"x"*100000,
            "validation":{"status":status,"summary":{"inputs":[{"samples":["001"," 001 ","002","  "]}]}}})
    db.session.add(row);return row

def test_selector_pages_scope_aliases_and_skips_full_metadata(context):
    app,service,project=context
    for number in range(25):asset(project,number,kind="datapoint" if number%2 else "profile")
    asset(project,100,dataset="乙");asset(project,101,history=True);asset(project,102,kind="pep")
    db.session.commit()
    data=app.test_client().get(f"/api/projects/{project.id}/assets",query_string={"view":"selector","inputs_only":"true","asset_set":"甲","asset_type":"profile","page":2,"page_size":20}).json
    assert data["pagination"]=={"page":2,"page_size":20,"total":25,"total_pages":2}
    assert len(data["assets"])==5
    assert all(row["metadata"]["asset_set"]=="甲" for row in data["assets"])
    assert all(set(row["metadata"])=={"asset_set","validation","content_version"} for row in data["assets"])
    assert all(row["metadata"]["validation"]=={"status":"valid"} for row in data["assets"])
    statements=[]
    def capture(_conn,_cursor,sql,_params,_context,_many):
        if sql.lstrip().startswith("SELECT") and "FROM project_assets" in sql:statements.append(sql.split("FROM")[0])
    event.listen(db.engine,"before_cursor_execute",capture)
    try:service.input_candidate_page(project.id,asset_type="profile",asset_set="甲")
    finally:event.remove(db.engine,"before_cursor_execute",capture)
    assert statements and all(not re.search(r",\s*project_assets\.metadata_json\s+(?:AS|,)",sql) for sql in statements)

def test_search_history_and_validation_filters_remain_exact(context):
    app,_,project=context
    asset(project,1);old=asset(project,2,history=True,status="failed");asset(project,3,status="needs_mapping")
    db.session.commit()
    query={"view":"selector","inputs_only":"true","asset_set":"甲","include_superseded":"true","validation_status":"needs_attention"}
    data=app.test_client().get(f"/api/projects/{project.id}/assets",query_string=query).json
    assert {row["id"] for row in data["assets"]}=={old.id,next(row.id for row in ProjectAsset.query.all() if row.original_name=="指标003.csv")}
    query["q"]="指标002";data=app.test_client().get(f"/api/projects/{project.id}/assets",query_string=query).json
    assert data["pagination"]["total"]==1 and data["assets"][0]["metadata"]["superseded"] is True
    query["include_superseded"]="false"
    assert app.test_client().get(f"/api/projects/{project.id}/assets",query_string=query).json["pagination"]["total"]==0

def test_exact_selector_detail_restores_old_source_and_full_default_is_unchanged(context):
    app,_,project=context
    old=asset(project,1,history=True);other=Project(name="另一项目");db.session.add(other);db.session.flush();foreign=asset(other,2);attachment=asset(project,3,kind="project_file");db.session.commit()
    client=app.test_client()
    row=client.get(f"/api/projects/{project.id}/assets/{old.id}?view=selector").json["asset"]
    assert row["id"]==old.id and row["metadata"]["superseded"] is True
    assert "unused_manifest" not in row["metadata"] and "summary" not in row["metadata"]["validation"]
    assert "unused_manifest" in client.get(f"/api/projects/{project.id}/assets/{old.id}").json["asset"]["metadata"]
    assert client.get(f"/api/projects/{project.id}/assets/{foreign.id}?view=selector").status_code==400
    assert client.get(f"/api/projects/{project.id}/assets/{attachment.id}?view=selector").status_code==400
    assert client.get(f"/api/projects/{project.id}/assets/{old.id}?view=invalid").status_code==400
    assert client.get(f"/api/projects/{project.id}/assets?view=selector").status_code==400

def test_catalog_counts_share_coverage_text_identity_and_keep_dataset_separate(context):
    _,service,project=context
    asset(project,1);asset(project,2);asset(project,3,dataset="乙");asset(project,4,history=True)
    db.session.commit()
    results=lambda ids:{}
    rows=project_catalog(result_counts=results,view="summary")["projects"]
    assert rows[0]["input_sample_count"]==4
    assert project_statistics(results)["input_sample_count"]==4
    coverage=input_sample_summary(projected_input_assets(service.asset_query(project.id,inputs_only=True)))
    assert {(row["asset_set"],row["sample_id"]) for row in coverage["samples"]}=={("甲","001"),("甲","002"),("乙","001"),("乙","002")}
