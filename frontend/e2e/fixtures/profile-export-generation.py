"""Generate small real reports to verify sample identity and exact exported statistics."""
import csv
import json
import zipfile
from pathlib import Path

import pandas as pd
from flask_app.services.boxplot_service import BoxPlotService

out = Path("/evidence")
source = out / "合成指标与分组.csv"
pd.DataFrame({
    "Sample": [f"{n:03d}" for n in range(1, 13)],
    "类别": ["01"] * 4 + ["1"] * 4 + ["02"] * 4,
    "批次": ["001"] * 4 + ["002"] * 8,
    "TRA_Shannon": [1., 2., 3., 4., 8., 9., 10., 11., 20., 21., 22., 23.],
    "TRB_Shannon": [2.] * 12,
}).to_csv(source, index=False)
before = source.read_bytes()
service = BoxPlotService(output_parent=out / "generated")
common = dict(datapoint_path=str(source), param_begin="TRA_Shannon", param_over="TRB_Shannon",
              selected_samples=[f"{n:03d}" for n in range(1, 13)])
grouped = service.generate_report(**common, grouptype_fields=["类别", "批次"],
    group_order='{"类别":["02","01","1"],"批次":["002","001"]}')
ungrouped = service.generate_report(**common)
files = [str(source)]
def rows(p):
    return list(csv.DictReader(Path(p).read_text(encoding="utf-8").splitlines()))
aggregate = grouped.output_base / "_all_significant.csv"
individual = [p for p in grouped.significant_paths if Path(p).name != aggregate.name]
assert len(individual) == 2
assert rows(aggregate) == [row for p in individual for row in rows(p)]
assert rows(aggregate)[0]["pvalue"] == "0.02857142857142857"
assert any(row["group_a"] == "01" and row["group_b"] == "1" for row in rows(aggregate))
for report in (grouped, ungrouped):
    for p in report.csv_paths:
        data = pd.read_csv(p, dtype={"Sample": str})
        assert set(data["Sample"]) == {f"{n:03d}" for n in range(1, 13)}
    with zipfile.ZipFile(report.zip_path) as archive:
        for p in report.csv_paths:
            assert archive.read("data/" + Path(p).relative_to(report.output_base).as_posix()) == Path(p).read_bytes()
        for p in report.significant_paths:
            assert archive.read("significance/" + Path(p).name) == Path(p).read_bytes()
    files.extend([str(report.output_base / "boxplot_metadata.json"), report.zip_path,
                  *report.csv_paths, *report.significant_paths, *report.pvalue_paths])
assert ungrouped.metadata["non_significant_plot_count"] == 0
assert ungrouped.metadata["significant_plot_count"] == 0
assert source.read_bytes() == before
(out / "fixture-context.json").write_text(json.dumps({
    "grouped": str(grouped.viewer_path), "ungrouped": str(ungrouped.viewer_path),
    "groupedJob": grouped.job_id, "ungroupedJob": ungrouped.job_id,
    "files": files, "aggregate": str(aggregate), "groups": ["02", "01", "1"],
    "individual": individual, "originalPvalue": "0.02857142857142857",
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Generated real grouped and ungrouped reports; original sample headers, aggregate statistics and archive data match.")
