"""Real UMAP regressions; run separately from API tests replacing the umap module."""
import numpy as np
import pandas as pd
import pytest
from flask_app.services.umapin_service import UmapinService

def test_three_sample_umap_runs_and_reports_calculation_stage(tmp_path):
    source = tmp_path / "usage.csv"
    pd.DataFrame({"Sample":["S1","S2","S3"], "Category":["A","A","B"], "V1":[1,2,3], "V2":[3,1,2]}).to_csv(source,index=False)
    events = []
    result = UmapinService(output_parent=tmp_path / "results").generate_report(data_path=str(source), param_begin="V1", param_over="V2", n_epochs=30, progress_callback=lambda *event: events.append(event))
    table = pd.read_csv(result.csv_paths[0])
    assert len(table) == 3
    assert np.isfinite(table[["UMAP1","UMAP2"]]).all().all()
    assert any("正在计算" in event[2] for event in events)
    assert result.png_paths

@pytest.mark.parametrize("values,message", [([1,2],"至少需要"), ([1,2,float("inf")],"无穷值")])
def test_invalid_inputs_fail_with_actionable_message(tmp_path, values, message):
    source = tmp_path / "usage.csv"
    pd.DataFrame({"Category":["A"]*len(values), "V1":values}).to_csv(source,index=False)
    with pytest.raises(ValueError, match=message):
        UmapinService(output_parent=tmp_path / "results").generate_report(data_path=str(source),param_begin="V1",param_over="V1")


def test_profile_umap_multiple_group_fields_has_monotonic_progress(tmp_path):
    from flask_app.services.umap_service import UmapService
    source = tmp_path / "profile.csv"
    pd.DataFrame({"Sample":[f"S{i}" for i in range(8)], "group":["A"]*4+["B"]*4, "other":["A"]*4+["B"]*4, "V1":[1,2,3,4,20,21,22,23], "V2":[2,4,3,1,24,23,21,22]}).to_csv(source,index=False)
    events = []
    report = UmapService(output_parent=tmp_path / "results").generate_report(datapoint_path=str(source), classification_begin="group", classification_over="other", param_begin="V1",param_over="V2", progress_callback=lambda *event: events.append(event))
    assert len(report.png_paths) >= 2
    assert [e[0] for e in events] == sorted(e[0] for e in events)
    assert any(len(e) > 3 and e[3].get("phase") == "fit_umap" for e in events)
