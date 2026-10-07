"""Real grouped/ungrouped reports plus an empty-renderer case for report controls."""
import json
import runpy
from pathlib import Path

from flask_app.services.boxplot_service import BoxPlotService

runpy.run_path("/fixtures/profile-export-generation.py", run_name="__main__")
out = Path("/evidence")
metadata = {"job_id": "empty-renderer", "class_columns": [], "param_columns": [],
            "plot_count": 0, "summary_metrics": [], "datapoint_path": ""}
empty = out / "empty-viewer.html"
empty.write_text(BoxPlotService(output_parent=out / "unused")._build_viewer_html(
    metadata=metadata, plot_infos=[], png_urls=[], output_base=out,
), encoding="utf-8")
context = json.loads((out / "fixture-context.json").read_text(encoding="utf-8"))
context["empty"] = str(empty)
(out / "fixture-context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
print("Generated actual reports and a separate empty-renderer contract case.")
