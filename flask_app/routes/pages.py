"""
Page routes for rendering HTML templates.
Requirements: 9.1
"""
from urllib.parse import urlencode
from flask import Blueprint, render_template, redirect, url_for, flash, request

pages_bp = Blueprint('pages', __name__)

MANAGEMENT_WORKSPACE = 'management'
ANALYSIS_WORKSPACE = 'analysis'
VALID_WORKSPACES = {MANAGEMENT_WORKSPACE, ANALYSIS_WORKSPACE}


def render_page(template_name, workspace=ANALYSIS_WORKSPACE, **context):
    """Render a page with an explicit workspace marker for shared layout logic."""
    context.setdefault('embedded', request.args.get('embedded') in {'1', 'true', 'yes'})
    return render_template(template_name, workspace=workspace, **context)


def resolve_workspace(default=ANALYSIS_WORKSPACE):
    """Resolve workspace from query args for shared pages such as settings."""
    workspace = request.args.get('workspace', default)
    if workspace not in VALID_WORKSPACES:
        return default
    return workspace


@pages_bp.route('/')
def index():
    """Redirect the root entry to the analysis workspace."""
    return redirect(url_for('pages.analysis_page'))


@pages_bp.route('/management')
def management_page():
    """Data management workspace landing page."""
    return render_page('management.html', workspace=MANAGEMENT_WORKSPACE)


@pages_bp.route('/upload')
def upload_page():
    """Redirect to project management — upload is now integrated into project detail."""
    return redirect(url_for('pages.projects_page'))


@pages_bp.route('/files')
def files_page():
    """Redirect to project management — legacy file management removed."""
    return redirect(url_for('pages.projects_page'))


@pages_bp.route('/projects')
def projects_page():
    """Project management page."""
    return render_page('projects.html', workspace=MANAGEMENT_WORKSPACE)


@pages_bp.route('/projects/<project_id>')
def project_detail_page(project_id):
    """Project detail page."""
    return render_page(
        'project_detail.html',
        workspace=MANAGEMENT_WORKSPACE,
        project_id=project_id,
        project_context={'projectId': project_id},
    )


@pages_bp.route('/samples')
def samples_page():
    """Sample registry page."""
    return render_page('samples.html', workspace=MANAGEMENT_WORKSPACE)


@pages_bp.route('/analysis')
def analysis_page():
    """Analysis page - single page with scheme switching.
    Optimized UI without step-by-step flow.
    """
    return render_page('simple_analysis.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/simple-analysis')
def simple_analysis_page():
    """Simple analysis page - redirect to /analysis."""
    return redirect(url_for('pages.analysis_page'))


@pages_bp.route('/analysis/workflows')
def analysis_workflows_page():
    """Workflow-level entry page for integrated analysis modules."""
    return render_page('analysis_overview.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/analysis/config')
def analysis_config_page():
    """
    Analysis configuration page.

    ⚠️ DEPRECATED: This route is deprecated and redirects to the unified similarity heatmap page.
    Please use /analysis/similarity-heatmap instead.
    """
    from flask import flash, redirect, url_for
    flash('相似度热图功能已整合到统一的相似度热图分析模块中', 'info')
    return redirect(url_for('pages.similarity_heatmap_page'))


@pages_bp.route('/analysis/<analysis_id>/results')
def analysis_results_page(analysis_id):
    """Analysis results page - displays charts and data tables."""
    return render_page(
        'analysis/results.html',
        workspace=ANALYSIS_WORKSPACE,
        analysis_id=analysis_id,
    )


@pages_bp.route('/analysis/field')
def field_analysis_page():
    """Field data analysis page - generic field analysis.
    DEPRECATED: Redirects to unified analysis page.
    Requirements: 5.2, 6.1, 6.2, 6.3, 1.3, 7.1
    """
    # Preserve query parameters
    query_params = request.args.to_dict()
    
    flash('自定义字段分析功能已整合到统一数据分析模块中', 'info')
    
    # Redirect with query parameters if any
    if query_params:
        from urllib.parse import urlencode
        return redirect(url_for('pages.analysis_page') + '?' + urlencode(query_params))
    
    return redirect(url_for('pages.analysis_page'))


@pages_bp.route('/analysis/bcell-isotype')
def bcell_isotype_page():
    """B cell isotype distribution analysis page.
    DEPRECATED: Redirects to unified analysis page.
    Requirements: 1.1, 6.1, 6.2, 6.3, 1.3, 7.1
    """
    # Preserve query parameters
    query_params = request.args.to_dict()
    
    flash('B细胞同型分析功能已整合到统一数据分析模块中，请选择"B细胞同型分析"方案', 'info')
    
    # Add scheme hint to query parameters
    query_params['scheme'] = 'bcell_isotype'
    
    from urllib.parse import urlencode
    return redirect(url_for('pages.analysis_page') + '?' + urlencode(query_params))


@pages_bp.route('/analysis/shm')
def shm_analysis_page():
    """SHM (Somatic Hypermutation) analysis page.
    DEPRECATED: Redirects to unified analysis page.
    Requirements: 2.1, 6.1, 6.2, 6.3, 1.3, 7.2
    """
    # Preserve query parameters
    query_params = request.args.to_dict()
    
    flash('SHM分析功能已整合到统一数据分析模块中，请选择"SHM分析"方案', 'info')
    
    # Add scheme hint to query parameters
    query_params['scheme'] = 'shm_analysis'
    
    from urllib.parse import urlencode
    return redirect(url_for('pages.analysis_page') + '?' + urlencode(query_params))


@pages_bp.route('/analysis/ig-metrics')
def ig_metrics_page():
    """IG Metrics analysis page.
    DEPRECATED: Redirects to unified analysis page.
    Requirements: 3.1, 6.1, 6.2, 6.3, 1.3, 7.3
    """
    # Preserve query parameters
    query_params = request.args.to_dict()
    
    flash('IG指标分析功能已整合到统一数据分析模块中，请选择"IG指标分析"方案', 'info')
    
    # Add scheme hint to query parameters
    query_params['scheme'] = 'ig_metrics'
    
    from urllib.parse import urlencode
    return redirect(url_for('pages.analysis_page') + '?' + urlencode(query_params))


@pages_bp.route('/analysis/pdf-extractor')
def pdf_extractor_page():
    """PDF data and image extractor page.
    Requirements: 9.1-9.6, 12.1-12.6, 6.1, 6.2, 6.3
    """
    return render_page('analysis/pdf_extractor.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/analysis/ppt-report')
def ppt_report_page():
    """PPT report generation page."""
    return render_page('analysis/sequencing_depth.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/settings')
def settings_page():
    """Settings page."""
    return render_page('settings.html', workspace=resolve_workspace())


@pages_bp.route('/analysis/ppt-heatmap')
def ppt_heatmap_page():
    """PPT heatmap replacement page.
    Upload PPT template and replace heatmaps with generated images.
    """
    return render_page('analysis/ppt_heatmap.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/analysis/statistical')
def statistical_comparison_page():
    """Statistical comparison analysis page.
    Performs group comparison with P-value calculation and boxplot visualization.
    """
    return render_page('analysis/statistical_comparison.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/analysis/similarity-heatmap')
def similarity_heatmap_page():
    """Legacy heatmap entry removed with the combined report module."""
    flash('综合图表报告模块已删除，请在 Script Hub 中使用保留的分析模块。', 'info')
    return redirect(url_for('pages.script_hub_page'))


@pages_bp.route('/analysis/treemap')
def treemap_page():
    """Legacy treemap entry removed with the combined report module."""
    flash('综合图表报告模块已删除，请在 Script Hub 中使用保留的分析模块。', 'info')
    return redirect(url_for('pages.script_hub_page'))


@pages_bp.route('/analysis/chord-diagram')
def chord_diagram_page():
    """Legacy chord entry removed with the combined report module."""
    flash('综合图表报告模块已删除，请在 Script Hub 中使用保留的分析模块。', 'info')
    return redirect(url_for('pages.script_hub_page'))


@pages_bp.route('/analysis/advanced-analysis')
def advanced_analysis_page():
    """Legacy advanced-analysis route kept as a compatibility redirect."""
    active_module = str(request.args.get('active_module') or '').strip().lower()
    target_endpoint = 'pages.script_hub_page' if active_module == 'db-alignment' else 'pages.pipeline_comparison_page'
    query_params = request.args.to_dict(flat=True)
    target_url = url_for(target_endpoint)
    return redirect(f"{target_url}?{urlencode(query_params)}" if query_params else target_url)


@pages_bp.route('/analysis/pipeline-comparison')
def pipeline_comparison_page():
    """Pipeline comparison page entry.
    Dedicated workflow for comparing multiple pipelines under one root directory.
    """
    return render_page('analysis/pipeline_comparison.html', workspace=ANALYSIS_WORKSPACE)


@pages_bp.route('/analysis/script-hub')
def script_hub_page():
    """Unified project/data analysis entry for scripts and chart reports."""
    return render_page('analysis/script_hub.html', workspace=ANALYSIS_WORKSPACE)
