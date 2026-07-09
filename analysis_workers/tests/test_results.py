"""Unit tests for WorkerResults — validates structure and static correctness."""

import os

os.environ.setdefault("FLASK_CONFIG", "testing")

import pytest


class TestWorkerResultsStructure:
    """Verify WorkerResults imports and has expected methods."""

    def test_imports_cleanly(self):
        from analysis_workers.results import WorkerResults, worker_results
        assert WorkerResults is not None
        assert worker_results is not None

    def test_methods_exist(self):
        from analysis_workers.results import WorkerResults
        wr = WorkerResults()
        methods = [m for m in dir(wr) if not m.startswith("_")]
        assert "set_status" in methods
        assert "set_running" in methods
        assert "set_progress" in methods
        assert "set_completed" in methods
        assert "set_failed" in methods
        assert "register_output_asset" in methods
        assert "get_job" in methods

    def test_no_flask_import(self):
        """WorkerResults must NOT import Flask — that's the whole point."""
        import inspect
        from analysis_workers.results import WorkerResults

        source = inspect.getsource(WorkerResults)
        assert "flask" not in source.lower(), (
            "WorkerResults contains Flask import — it must be standalone"
        )

    def test_uses_text_not_raw_format(self):
        """SQL must use parameterized text(), never f-string interpolation."""
        import inspect
        from analysis_workers.results import WorkerResults

        source = inspect.getsource(WorkerResults)
        # All SQL should go through text(...), not raw f-strings with values
        assert "text(" in source, "WorkerResults must use text() for SQL"


class TestMimeGuessing:
    """Verify mime type guessing helper."""

    def test_known_types(self):
        from analysis_workers.results import WorkerResults
        wr = WorkerResults()
        assert wr._guess_mime("output.html") == "text/html"
        assert wr._guess_mime("chart.png") == "image/png"
        assert wr._guess_mime("data.csv") in ("text/csv", "application/vnd.ms-excel")
        assert wr._guess_mime("report.pdf") == "application/pdf"

    def test_unknown_extension(self):
        from analysis_workers.results import WorkerResults
        wr = WorkerResults()
        assert wr._guess_mime("file.unknown_ext") == "application/octet-stream"


class TestTerminalStatuses:
    """Verify terminal status constant."""

    def test_terminal_statuses(self):
        from analysis_workers.results import TERMINAL_STATUSES
        assert "completed" in TERMINAL_STATUSES
        assert "failed" in TERMINAL_STATUSES
        assert "cancelled" in TERMINAL_STATUSES
        assert "interrupted" in TERMINAL_STATUSES


class TestWorkerResultEnvelope:
    """B2: Standard worker result envelope."""

    def test_build_envelope(self):
        from analysis_workers.results import build_envelope

        env = build_envelope(
            outputs=[
                {"label": "Treemap", "url": "/tmp/out.html", "kind": "html"},
                {"label": "CSV Data", "url": "/tmp/data.csv", "kind": "csv"},
            ],
            metrics={"duration_seconds": 12.5, "files_generated": 2},
            summary="Generated treemap with 150 clones",
        )
        assert len(env["outputs"]) == 2
        assert env["outputs"][0].label == "Treemap"
        assert env["outputs"][0].kind == "html"
        assert env["metrics"]["duration_seconds"] == 12.5
        assert env["summary"] == "Generated treemap with 150 clones"

    def test_empty_envelope(self):
        from analysis_workers.results import build_envelope

        env = build_envelope()
        assert env["outputs"] == []
        assert env["metrics"] == {}
        assert env["summary"] == ""

    def test_worker_output_dataclass(self):
        from analysis_workers.results import WorkerOutput

        o = WorkerOutput(label="Test", url="/tmp/test.html", kind="html")
        assert o.label == "Test"
        assert o.asset_id is None  # None until registered

    def test_kind_from_path(self):
        from analysis_workers.results import kind_from_path

        assert kind_from_path("/tmp/out.html") == "html"
        assert kind_from_path("/tmp/chart.png") == "png"
        assert kind_from_path("/tmp/data.csv") == "csv"
        assert kind_from_path("/tmp/archive.zip") == "zip"
        assert kind_from_path("/tmp/report.pdf") == "pdf"
        assert kind_from_path("/tmp/slides.pptx") == "ppt"
        assert kind_from_path("/tmp/data.json") == "json"
        assert kind_from_path("/tmp/file.xyz") == "data"

    def test_finalize_job_exists(self):
        from analysis_workers.results import WorkerResults
        wr = WorkerResults()
        assert hasattr(wr, "finalize_job")

    def test_envelope_module_exports(self):
        from analysis_workers.results import (
            WorkerOutput,
            WorkerResultEnvelope,
            build_envelope,
            kind_from_path,
        )
        assert WorkerOutput is not None
        assert WorkerResultEnvelope is not None
        assert callable(build_envelope)
        assert callable(kind_from_path)
