"""Exercise report renderers with previously generated synthetic scientific artifacts."""
from pathlib import Path
import copy
import json
import shutil
from flask_app.routes.api_script_hub._common import _build_and_save_viewer, _write_unified_viewer
from flask_app.services.boxplot_service import BoxPlotService
import pandas as pd

out = Path("/evidence")
ml_source = Path("/source-ml")
db_source = Path("/source-db")
saved = json.loads((ml_source / "real-result-before.json").read_text(encoding="utf-8"))
metadata = copy.deepcopy(saved["result"]["metadata"])
ml = out / "ml-report"
ml.mkdir(exist_ok=True)
shutil.copy2(ml_source / "real-cross-validation-accuracy.png", ml / "cross_validation_accuracy.png")
result = {"png_urls": ["cross_validation_accuracy.png"]}
_build_and_save_viewer(ml, result, metadata, title="机器学习分析结果", subtitle="已保存的合成任务模型评估")
assert metadata == saved["result"]["metadata"]
assert json.loads((ml / "metadata.json").read_text(encoding="utf-8")) == metadata

db_context = json.loads((db_source / "artifact-context.json").read_text(encoding="utf-8"))
db_meta_path = db_source / Path(db_context["metadata"]).relative_to("/evidence")
db_meta = json.loads(db_meta_path.read_text(encoding="utf-8"))
significant = next(item for item in db_meta["boxplots"] if item["is_significant"] is True)
non_significant = next(item for item in db_meta["boxplots"] if item["is_significant"] is False and item["chain"] == "TRB")
mixed = out / "recorded-flags"
mixed.mkdir(exist_ok=True)
for name, item in (("recorded-significant.png", significant), ("recorded-non-significant.png", non_significant)):
    shutil.copy2(db_meta_path.parent / item["png"], mixed / name)
shutil.copy2(ml_source / "real-cross-validation-accuracy.png", mixed / "model-evaluation.png")
# This temporary renderer fixture tests separate saved records; it is not a new analysis module.
items = [
    {"src": "recorded-significant.png", "category": "分类甲", "title": significant["param"], "sig": significant["is_significant"]},
    {"src": "recorded-non-significant.png", "category": "分类乙", "title": non_significant["param"], "sig": non_significant["is_significant"]},
    {"src": "model-evaluation.png", "category": "分类甲", "title": "未标注显著性的模型评估"},
    {"src": "model-evaluation.png", "category": "", "title": "未分类的模型评估"},
]
kwargs = {"title": "图表报告筛选验收", "subtitle": "已生成合成结果的独立展示契约",
    "image_groups": [{"items": items}], "download_sections": [], "stats": []}
_write_unified_viewer(viewer_path=mixed / "viewer.html", metadata={}, **kwargs)
_write_unified_viewer(viewer_path=mixed / "disabled.html", metadata={"show_significance_filter": False}, **kwargs)
_write_unified_viewer(viewer_path=mixed / "empty.html", title="无图表报告",
    subtitle="空图表输入的展示契约", image_groups=[], download_sections=[], stats=[], metadata={})

# Generate a real profile report for its shared palette controls, without business input.
context_path = out / "fixture-context.json"
if context_path.exists():
    from types import SimpleNamespace
    previous = json.loads(context_path.read_text(encoding="utf-8"))
    report = SimpleNamespace(viewer_path=Path(previous["profile"]), job_id=previous["profileJob"])
    assert report.viewer_path.is_file()
else:
    profile = out / "合成样本指标.csv"
    pd.DataFrame({"Sample": [f"{n:03d}" for n in range(1, 9)],
        "类别": ["01"] * 4 + ["02"] * 4,
        "TRA_Shannon": [1., 2., 3., 4., 8., 9., 10., 11.],
        "TRB_Shannon": [2., 2., 2., 2., 2., 2., 2., 2.]}).to_csv(profile, index=False)
    report = BoxPlotService(output_parent=out / "profile-generated").generate_report(
        datapoint_path=str(profile), classification_begin="类别", classification_over="类别",
        param_begin="TRA_Shannon", param_over="TRB_Shannon",
    )
(out / "fixture-context.json").write_text(json.dumps({
    "ml": str(ml / "viewer.html"), "flags": str(mixed / "viewer.html"),
    "disabled": str(mixed / "disabled.html"), "empty": str(mixed / "empty.html"),
    "profile": str(report.viewer_path), "mlMetadata": str(ml / "metadata.json"),
    "mlSourceJob": saved["job"].get("job_id") or saved["job"].get("id"),
    "dbSourceJob": db_meta["job_id"],
    "knownTrue": 1, "knownFalse": 1, "unknown": 2, "profileJob": report.job_id,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Generated renderers from existing ML/DB artifacts and one real 8-sample profile report.")
