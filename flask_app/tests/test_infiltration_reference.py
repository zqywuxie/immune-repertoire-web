import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.skipif(
    not os.environ.get("REFERENCE_PIPELINE") or not shutil.which("Rscript"),
    reason="需要容器内 R 和只读挂载的原始 pipeline",
)
def test_cibersort_composition_and_group_statistics_match_reference(tmp_path):
    reference_dir = (
        Path(os.environ["REFERENCE_PIPELINE"])
        / "07.immuneInfiltration"
    )
    platform_dir = (
        Path(__file__).resolve().parents[2]
        / "scripts/infiltration/07.immuneInfiltration"
    )
    fixture = tmp_path / "deconvolution.csv"
    pd.DataFrame(
        {
            "sample": ["001", "002", "003", "004", "005", "006"],
            "group": ["Control", "Control", "Control", "Treatment", "Treatment", "Treatment"],
            "T_cells": [0.11, 0.17, 0.13, 0.31, 0.29, 0.36],
            "B_cells": [0.08, 0.05, 0.09, 0.16, 0.21, 0.18],
            "NK_cells": [0.04, 0.07, 0.05, 0.10, 0.08, 0.12],
        }
    ).to_csv(fixture, index=False)
    datapoint = tmp_path / "datapoint.csv"
    pd.DataFrame(
        {
            "sample": ["001", "002", "003", "004", "005", "006"],
            "group": ["Control", "Control", "Control", "Treatment", "Treatment", "Treatment"],
        }
    ).to_csv(datapoint, index=False)
    config = tmp_path / "reference-config.json"
    config.write_text('{"paths":{"datapoint_input":"datapoint.csv"}}', encoding="utf-8")

    def run(script_dir, output_dir, script_name):
        completed = subprocess.run(
            [
                "Rscript",
                str(script_dir / script_name),
                f"--input={fixture}",
                f"--output={output_dir}",
                f"--config={config}",
                "--sample-col=sample",
                "--group-col=group",
                "--group-order=Control,Treatment",
                "--cell-cols=T_cells,B_cells,NK_cells",
                "--dpi=72",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr

    for script_name, output_name in (
        ("02.plot_deconv_composition.R", "panel_A_shift_normalized_matrix.csv"),
        ("03.plot_deconv_group_comparison.R", "panel_B_pairwise_stats.csv"),
    ):
        reference_output = tmp_path / f"reference-{script_name}"
        platform_output = tmp_path / f"platform-{script_name}"
        run(reference_dir, reference_output, script_name)
        run(platform_dir, platform_output, script_name)

        reference = pd.read_csv(reference_output / output_name, dtype={"sample": str})
        platform = pd.read_csv(platform_output / output_name, dtype={"sample": str})
        if "sample" in platform.columns:
            assert platform["sample"].tolist() == ["002", "003", "001", "006", "004", "005"]
            reference_ids = reference["sample"].str.lstrip("0")
            platform_ids = platform["sample"].str.lstrip("0")
            assert platform_ids.tolist() == reference_ids.tolist()
            reference = reference.drop(columns="sample")
            platform = platform.drop(columns="sample")
        pd.testing.assert_frame_equal(
            platform,
            reference,
            check_dtype=False,
            check_exact=False,
            rtol=1e-10,
            atol=1e-12,
        )
