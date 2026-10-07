import pandas as pd
import pytest

from flask_app.services.topclone_service import TopCloneService


def _write_pep(path, clone):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "CDR3(pep)": [clone, f"{clone}B"],
        "copy": [9, 1],
    }).to_csv(path, index=False)


def test_trace_topclone_matches_duplicate_sample_ids_by_batch(tmp_path):
    pep_root = tmp_path / "pep"
    for batch, group in (("batch_001", "A"), ("batch_002", "B")):
        for sample in ("S01", "S02"):
            _write_pep(
                pep_root / batch / "TRA" / f"{sample}__TRA.csv",
                f"{batch}_{sample}_{group}",
            )

    profile = tmp_path / "profile.csv"
    pd.DataFrame({
        "sample": ["S01", "S02", "S01", "S02"],
        "batch": ["batch_001", "batch_001", "batch_002", "batch_002"],
        "group": ["A", "A", "B", "B"],
    }).to_csv(profile, index=False)

    report = TopCloneService(output_parent=tmp_path / "results").generate_report(
        pep_data_path=str(pep_root),
        datapoint_path=str(profile),
        group_field="group",
        batch_field="batch",
        selected_chains=["TRA"],
    )

    result = pd.read_csv(report.topclone_csv_path, dtype={"sample": str, "batch": str})
    assert result[["sample", "batch", "group"]].to_dict("records") == [
        {"sample": "S01", "batch": "batch_001", "group": "A"},
        {"sample": "S02", "batch": "batch_001", "group": "A"},
        {"sample": "S01", "batch": "batch_002", "group": "B"},
        {"sample": "S02", "batch": "batch_002", "group": "B"},
    ]
    assert report.metadata["sample_count"] == 4
    assert report.metadata["batch_field"] == "batch"
    assert report.metadata["batch_count"] == 2
    cdr3 = pd.read_csv(report.output_base / "top_cdr3_sequences/TRA/top10_cdr3s.csv")
    assert cdr3[["sample", "batch"]].duplicated().sum() == 0


def test_duplicate_samples_require_a_batch_field(tmp_path):
    pep_root = tmp_path / "pep"
    _write_pep(pep_root / "batch_001" / "TRA" / "S01__TRA.csv", "clone_a")
    _write_pep(pep_root / "batch_002" / "TRA" / "S01__TRA.csv", "clone_b")
    profile = tmp_path / "profile.csv"
    pd.DataFrame({"sample": ["S01", "S01"], "batch": ["batch_001", "batch_002"]}).to_csv(profile, index=False)

    with pytest.raises(ValueError, match="请选择批次字段"):
        TopCloneService(output_parent=tmp_path / "results").generate_report(
            pep_data_path=str(pep_root), datapoint_path=str(profile), selected_chains=["TRA"]
        )


def test_batch_value_must_match_pep_directory(tmp_path):
    pep_root = tmp_path / "pep"
    _write_pep(pep_root / "run_a" / "TRA" / "S01__TRA.csv", "clone_a")
    _write_pep(pep_root / "run_b" / "TRA" / "S01__TRA.csv", "clone_b")
    profile = tmp_path / "profile.csv"
    pd.DataFrame({"sample": ["S01", "S01"], "batch": ["batch_001", "batch_002"]}).to_csv(profile, index=False)

    with pytest.raises(ValueError, match="目录名与所选批次字段值一致"):
        TopCloneService(output_parent=tmp_path / "results").generate_report(
            pep_data_path=str(pep_root), datapoint_path=str(profile), batch_field="batch", selected_chains=["TRA"]
        )
