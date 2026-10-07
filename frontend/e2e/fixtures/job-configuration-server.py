"""Real read-only job APIs with synthetic saved parameters; no analysis execution."""
import tempfile
from pathlib import Path
from flask_app.config import TestingConfig
from flask_app.app import create_app
from flask_app.models.database import db, Project
from flask_app.services.background_job_service import get_background_job_service
fixture_root = Path(tempfile.mkdtemp(prefix="codex-job-configuration-"))
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(fixture_root/"jobs.sqlite")
app = create_app("testing")
service = get_background_job_service()
with app.app_context():
    db.session.add(Project(id="project-config",name="合成配置项目"))
    db.session.commit()
    def seed(identifier,module,payload,job_type="api_request"):
        service.create_job(job_type=job_type,module=module,job_id=identifier,project_id="project-config",payload=payload)
        service.upsert_job(identifier,{"status":"completed","progress":100,"stage":"已完成"})
    seed("job-source","pep-analysis",{"asset_set":"数据集 二","_task_name":"前置克隆共享"},"script_hub")
    seed("job-legacy","volcano",{
        "_task_name":"病例组差异","asset_set":"数据集 二","project_name":"合成配置项目",
        "input_assets":[{"asset_type":kind,"path":"/storage/输入 数据/"+name,"asset_id":"input-"+kind}
          for kind,name in [("pep","克隆表.csv"),("profile","分组表.tsv"),("transcriptome","表达矩阵.csv"),("cibersort","浸润分数.csv")]],
        "pvalue_threshold":0.05,"_module_config":{"pvalue_threshold":0.02},
        "config_json":{"input_mode":"expression","pvalue_threshold":0,"logfc_cutoff":0,"contained_pathology":False,
          "comparisons":[{"group1":"病例组 / A","group2":"对照组 B"}],
          "selected_samples":["样本-"+str(i).zfill(4) for i in range(2000)]},
        "upstream_input":{"module":"pep-analysis","source_job_id":"job-source","artifact_id":"synthetic-artifact"},
        "future_parameter":"keep-original",
    },"script_hub")
    seed("job-generic","charts.combined",{"asset_set":"数据集 一","_module_config":{"pep_paths":["/storage/克隆 表.csv"],
      "selected_modules":["heatmap"],"field_mapping":{"cdr3_column":"CDR3_AA","copy_column":"counts"}}})
    seed("job-batch","analysis-batch",{"asset_set":"数据集 二","items":[
       {"module":"pep-analysis","job_id":"job-source","status":"completed","payload":{"selected_chains":["TRA","TRB"]}},
       {"module":"volcano","status":"queued","depends_on":[0],"upstream_from":0,"payload":{"input_mode":"usage","pvalue_threshold":0.05}},
    ]})
    seed("job-missing","profile",{"future_parameter":"legacy-keep"})
