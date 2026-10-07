"""Report significance must come from recorded classifications, never a default."""
import copy
import json
from pathlib import Path
from flask_app.routes.api_script_hub._common import _build_and_save_viewer, _write_unified_viewer


def write_report(tmp_path, items, metadata=None):
    path = tmp_path / "viewer.html"
    _write_unified_viewer(viewer_path=path, title="报告", subtitle="原始结果",
        image_groups=[{"items": items}], download_sections=[], stats=[], metadata=metadata or {})
    return path.read_text(encoding="utf-8")


def test_generic_model_report_does_not_invent_non_significant_labels(tmp_path):
    metadata = {"mode": "profile", "samples": 24, "models": [{"roc_auc": 0.9375}],
                "result_items": [{"path": "models/logistic_l2/cross_validation_accuracy.png", "data_mode": "profile"}]}
    saved = copy.deepcopy(metadata)
    result = {"png_urls": ["models/logistic_l2/cross_validation_accuracy.png"]}
    _build_and_save_viewer(tmp_path, result, metadata, title="模型评估", subtitle="保存结果")
    page = (tmp_path / "viewer.html").read_text(encoding="utf-8")
    assert 'id="sigToggle"' not in page
    assert '<em class=' not in page
    assert 'data-sig="unknown"' in page
    assert 'value="profile" selected>样本指标</option>' in page
    assert '<span>样本指标</span>' in page
    assert json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8")) == saved
    assert metadata == saved


def test_known_false_and_missing_classification_are_distinct(tmp_path):
    items = [
        {"src": "true.png", "title": "01", "category": "TRA", "sig": True},
        {"src": "false.png", "title": "02", "category": "TRB", "sig": False},
        {"src": "unknown.png", "title": "001", "category": "TRA"},
        {"src": "unclassified.png", "category": ""},
    ]
    saved = copy.deepcopy(items)
    page = write_report(tmp_path, items)
    assert 'id="sigToggle"' in page
    assert page.count('data-sig="1"') == 1
    assert page.count('data-sig="0"') == 1
    assert page.count('data-sig="unknown"') == 2
    assert '<em class="is-unknown">未标注显著性</em>' in page
    assert '<option value="">全部分类</option>' in page
    assert items == saved


def test_report_can_explicitly_hide_statistical_controls(tmp_path):
    page = write_report(tmp_path, [{"src": "plot.png", "sig": True}],
                        {"show_significance_filter": False})
    assert 'id="sigToggle"' not in page
    assert '<em class=' not in page


def test_empty_or_unannotated_report_is_not_non_significant(tmp_path):
    for items in ([], [{"src": "plot.png"}], [{"src": "plot.png", "sig": None}]):
        page = write_report(tmp_path, items)
        assert 'id="sigToggle"' not in page
        assert '<em class=' not in page
