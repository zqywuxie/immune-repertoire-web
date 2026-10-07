"""Generate a real synthetic Profile report for raw group identifier browser checks."""
import json
import zipfile
from pathlib import Path
import pandas as pd
from scipy.stats import mannwhitneyu
from flask_app.services.boxplot_service import BoxPlotService

out = Path("/evidence")
source = out / "合成样本指标.csv"
pd.DataFrame({
    "sample": [f"{n:03d}" for n in range(1, 13)],
    "类别": ["01"] * 4 + ["1"] * 4 + ["02"] * 4,
    "TRA_Shannon": [1., 2., 3., 4., 8., 9., 10., 11., 20., 21., 22., 23.],
    "TRB_Shannon": [2.] * 12,
}).to_csv(source, index=False)
source_bytes = source.read_bytes()
report = BoxPlotService(output_parent=out / "generated").generate_report(
    datapoint_path=str(source), classification_begin="类别", classification_over="类别",
    param_begin="TRA_Shannon", param_over="TRB_Shannon",
    group_order="02,01,1",
)
table = pd.read_csv(report.csv_paths[0], dtype={"sample": str, "类别": str})
assert table["类别"].tolist() == ["02"] * 4 + ["01"] * 4 + ["1"] * 4
assert table["sample"].tolist() == ["009", "010", "011", "012", "001", "002", "003", "004", "005", "006", "007", "008"]
stats = pd.read_csv(report.pvalue_paths[0], dtype={"group_a": str, "group_b": str})
assert stats.loc[stats["param"] == "TRB_Shannon", "pvalue"].tolist() == [1., 1., 1.]
stats = stats[stats["param"] == "TRA_Shannon"]
assert list(zip(stats["group_a"], stats["group_b"])) == [("02", "01"), ("02", "1"), ("01", "1")]
expected = mannwhitneyu([1., 2., 3., 4.], [8., 9., 10., 11.], alternative="two-sided").pvalue
assert all(abs(p - expected) < 1e-12 for p in stats["pvalue"])
assert report.metadata["class_type_counts"] == {"类别": 3}
assert source.read_bytes() == source_bytes
with zipfile.ZipFile(report.zip_path) as archive:
    raw_table = next(name for name in archive.namelist() if name.endswith("TRA_Shannon.csv"))
    assert archive.read(raw_table) == Path(report.csv_paths[0]).read_bytes()
(out / "fixture-context.json").write_text(json.dumps({
    "viewer": str(report.viewer_path), "metadata": str(report.output_base / "boxplot_metadata.json"),
    "source": str(source), "job": report.job_id,
    "table": str(report.csv_paths[0]), "stats": str(report.pvalue_paths[0]),
    "expectedGroups": ["02", "01", "1"], "expectedPvalue": expected,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Real 12-sample report keeps 3 distinct raw groups, requested order, metric values and archive bytes.")
