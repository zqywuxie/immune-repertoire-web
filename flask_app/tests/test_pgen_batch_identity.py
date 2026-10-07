import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.services.pgen_analysis_service import PgenAnalysisService


class _FakeProcessing:
    def __init__(self, *, pgen_model):
        self.pgen_model = pgen_model

    def filter_dataframe(self, frame):
        return frame


class _FakeSoNNia:
    def __init__(self, *, data_seqs, pgen_model, seed):
        self.data_seqs = data_seqs

    def evaluate_seqs(self, data_seqs):
        size = len(data_seqs)
        return np.ones(size), np.linspace(0.01, 0.1, size), np.ones(size)


def _write_pep(path: Path, cdr3: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "CDR3(pep)": [cdr3, f"{cdr3}-2"],
        "V": ["TRAV1", "TRAV1"],
        "J": ["TRAJ1", "TRAJ1"],
        "copy": [2, 1],
    }).to_csv(path, index=False)


def _install_fake_sonnia(monkeypatch):
    sonnia = types.ModuleType("sonnia")
    processing = types.ModuleType("sonnia.processing")
    processing.Processing = _FakeProcessing
    sonnia_model = types.ModuleType("sonnia.sonnia")
    sonnia_model.SoNNia = _FakeSoNNia
    sonnia.processing = processing
    sonnia.sonnia = sonnia_model
    monkeypatch.setitem(sys.modules, "sonnia", sonnia)
    monkeypatch.setitem(sys.modules, "sonnia.processing", processing)
    monkeypatch.setitem(sys.modules, "sonnia.sonnia", sonnia_model)


def test_pgen_processes_all_selected_files_and_keeps_duplicate_samples_by_batch(tmp_path, monkeypatch):
    _install_fake_sonnia(monkeypatch)
    monkeypatch.setattr(PgenAnalysisService, "dependency_status", staticmethod(lambda: {"available": True}))
    monkeypatch.setattr(PgenAnalysisService, "_sonnia_model_reference", staticmethod(lambda name: name))
    monkeypatch.setattr(PgenAnalysisService, "_repair_sonnia_windows_gene_sets", staticmethod(lambda processor, name: None))

    pep_root = tmp_path / "pep"
    for batch in ("batch-a", "batch-b"):
        _write_pep(pep_root / batch / "TRA" / "S1__TRA.csv", "PUBLIC")
        _write_pep(pep_root / batch / "TRA" / "S2__TRA.csv", "PUBLIC")
    profile = tmp_path / "Profile.csv"
    pd.DataFrame({
        "sample": ["S1", "S2", "S1", "S2"],
        "batch": ["batch-a", "batch-a", "batch-b", "batch-b"],
        "group": ["A", "A", "B", "B"],
    }).to_csv(profile, index=False)
    service = PgenAnalysisService(output_parent=tmp_path / "results")

    report = service.generate_report(
        pep_data_dir=str(pep_root / "batch-a" / "TRA" / "S1__TRA.csv"),
        pep_paths=[
            str(pep_root / "batch-a" / "TRA" / "S1__TRA.csv"),
            str(pep_root / "batch-a" / "TRA" / "S2__TRA.csv"),
            str(pep_root / "batch-b" / "TRA" / "S1__TRA.csv"),
            str(pep_root / "batch-b" / "TRA" / "S2__TRA.csv"),
        ],
        profile_path=str(profile), selected_chains=["TRA"], sample_col="sample", batch_field="batch",
        distribution_category_col="group",
    )

    summary = pd.read_csv(report.output_base / "Pgen_mean.csv", dtype=str)
    assert len(summary) == 4
    assert set(zip(summary["sample"], summary["batch"])) == {
        ("S1", "batch-a"), ("S2", "batch-a"), ("S1", "batch-b"), ("S2", "batch-b")
    }
    detail_index = pd.read_csv(report.output_base / "Pgen_detail_index.csv")
    assert len(detail_index) == 4
    assert set(detail_index["batch"]) == {"batch-a", "batch-b"}
    assert all(Path(path).is_file() for path in report.detail_paths)
    assert report.metadata["sample_count"] == 4
    assert report.metadata["batch_count"] == 2


def test_pgen_file_discovery_deduplicates_overlapping_selected_roots(tmp_path):
    pep_file = tmp_path / "batch" / "TRA" / "S1__TRA.csv"
    _write_pep(pep_file, "PUBLIC")
    files = PgenAnalysisService._collect_pep_files([tmp_path, pep_file], ["TRA"])
    assert files["TRA"] == [pep_file]


def test_pgen_applies_selected_groups_and_samples_before_processing(tmp_path, monkeypatch):
    _install_fake_sonnia(monkeypatch)
    monkeypatch.setattr(PgenAnalysisService, "dependency_status", staticmethod(lambda: {"available": True}))
    monkeypatch.setattr(PgenAnalysisService, "_sonnia_model_reference", staticmethod(lambda name: name))
    monkeypatch.setattr(PgenAnalysisService, "_repair_sonnia_windows_gene_sets", staticmethod(lambda processor, name: None))
    pep_root = tmp_path / "pep"
    file_paths = []
    for batch in ("batch-a", "batch-b"):
        for sample in ("S1", "S2"):
            path = pep_root / batch / "TRA" / f"{sample}__TRA.csv"
            _write_pep(path, "PUBLIC")
            file_paths.append(str(path))
    profile = tmp_path / "Profile.csv"
    pd.DataFrame({
        "sample": ["S1", "S2", "S1", "S2"],
        "batch": ["batch-a", "batch-a", "batch-b", "batch-b"],
        "group": ["A", "A", "B", "B"],
    }).to_csv(profile, index=False)

    report = PgenAnalysisService(output_parent=tmp_path / "filtered-results").generate_report(
        pep_data_dir=file_paths[0], pep_paths=file_paths, profile_path=str(profile),
        selected_chains=["TRA"], batch_field="batch", distribution_category_col="group",
        selected_group_values={"group": ["A"]},
        selected_samples_by_group={"group": {"A": ["S1"]}},
    )

    summary = pd.read_csv(report.output_base / "Pgen_mean.csv", dtype=str)
    assert summary[["sample", "batch", "group"]].to_dict("records") == [
        {"sample": "S1", "batch": "batch-a", "group": "A"}
    ]
    detail_index = pd.read_csv(report.output_base / "Pgen_detail_index.csv", dtype=str)
    assert detail_index[["sample", "batch"]].to_dict("records") == [
        {"sample": "S1", "batch": "batch-a"}
    ]
