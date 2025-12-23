"""
Page routes for rendering HTML templates.
Requirements: 9.1
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """Home page / Dashboard."""
    return render_template('index.html')


@pages_bp.route('/upload')
def upload_page():
    """File upload page."""
    return render_template('upload.html')


@pages_bp.route('/files')
def files_page():
    """File management page - displays all uploaded files."""
    return render_template('files.html')


@pages_bp.route('/analysis')
def analysis_page():
    """Analysis page - single page with scheme switching.
    Optimized UI without step-by-step flow.
    """
    return render_template('simple_analysis.html')


@pages_bp.route('/simple-analysis')
def simple_analysis_page():
    """Simple analysis page - redirect to /analysis.
    """
    return redirect(url_for('pages.analysis_page'))


@pages_bp.route('/analysis/config')
def analysis_config_page():
    """Analysis configuration page."""
    return render_template('analysis/config.html')


@pages_bp.route('/analysis/<analysis_id>/results')
def analysis_results_page(analysis_id):
    """Analysis results page - displays charts and data tables."""
    return render_template('analysis/results.html', analysis_id=analysis_id)


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
        return redirect(url_for('pages.unified_analysis_page') + '?' + urlencode(query_params))
    
    return redirect(url_for('pages.unified_analysis_page'))


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
    return redirect(url_for('pages.unified_analysis_page') + '?' + urlencode(query_params))


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
    return redirect(url_for('pages.unified_analysis_page') + '?' + urlencode(query_params))


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
    return redirect(url_for('pages.unified_analysis_page') + '?' + urlencode(query_params))


@pages_bp.route('/analysis/pdf-extractor')
def pdf_extractor_page():
    """PDF data and image extractor page.
    Requirements: 9.1-9.6, 12.1-12.6, 6.1, 6.2, 6.3
    """
    return render_template('analysis/pdf_extractor.html')


@pages_bp.route('/analysis/ppt-report')
def ppt_report_page():
    """PPT report generation page."""
    return render_template('analysis/sequencing_depth.html')


@pages_bp.route('/history')
def history_page():
    """History page."""
    return render_template('history.html')


@pages_bp.route('/settings')
def settings_page():
    """Settings page."""
    return render_template('settings.html')
