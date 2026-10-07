"""Isolated project APIs and real ML execution on 24 synthetic samples only."""
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from flask_app.config import TestingConfig
from flask_app.app import create_app
from flask_app.models.database import db, Project, ProjectAsset

root = Path(tempfile.mkdtemp(prefix="codex-ml-overview-"))
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(root / "jobs.sqlite")
TestingConfig.RESULTS_FOLDER = root / "results"
TestingConfig.PROJECT_DATA_ROOT = str(root / "inputs")
TestingConfig.ALLOWED_BASE_PATHS = [str(root)]
TestingConfig.INTERNAL_MODE = True
app = create_app("testing")
app.config["ALLOWED_BASE_PATHS"] = [str(root)]
inputs = root / "inputs"
inputs.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(64)
code = np.repeat([0., 1.], 12)
profile = inputs / "合成样本指标.csv"
pd.DataFrame({
    "sample": [f"{i:03d}" for i in range(1, 25)],
    "类别": ["01"] * 12 + ["02"] * 12,
    "IGHG1": code + rng.normal(0, .7, 24),
    "IGHA1": code * .5 + rng.normal(0, .6, 24),
    "CDR3_ratio": rng.uniform(0, 1, 24),
    "Shannon": rng.normal(1.8, .3, 24),
}).to_csv(profile, index=False)
with app.app_context():
    db.session.add(Project(id="ml-overview-project", name="模型结果合成项目"))
    db.session.add(ProjectAsset(id="ml-profile", project_id="ml-overview-project", asset_type="profile",
        original_name=profile.name, storage_path=str(profile), size=profile.stat().st_size,
        metadata_json={"asset_set":"Set1"}))
    db.session.commit()
