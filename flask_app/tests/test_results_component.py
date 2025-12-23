"""
Tests for the analysis results component integration
Tests that the component is properly integrated into the unified analysis page
"""

import pytest
from flask import url_for


def test_unified_analysis_page_includes_results_component(client):
    """Test that unified analysis page includes the results component"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check that the results component is included
    assert b'analysisResultsComponent' in response.data
    assert b'analysis-results-component' in response.data


def test_results_component_has_required_elements(client):
    """Test that results component has all required UI elements"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for key component elements
    assert b'resultsHeader' in response.data
    assert b'resultsTabsContainer' in response.data
    assert b'noResultsMessage' in response.data
    assert b'downloadOptionsMenu' in response.data


def test_results_component_has_download_functionality(client):
    """Test that results component includes download buttons"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for download functionality
    assert b'downloadAllResults' in response.data
    assert b'downloadChart' in response.data
    assert b'downloadTable' in response.data
    assert b'copyTableToClipboard' in response.data
    assert b'downloadTableAsCSV' in response.data


def test_results_component_has_toast_notifications(client):
    """Test that toast notifications are present for user feedback"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for toast elements
    assert b'copyToast' in response.data
    assert b'downloadToast' in response.data


def test_results_component_javascript_class_defined(client):
    """Test that AnalysisResultsComponent JavaScript class is defined"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check that the JavaScript class is defined
    assert b'class AnalysisResultsComponent' in response.data
    assert b'displayResults' in response.data
    assert b'displayResultsArray' in response.data
    assert b'displayResultsObject' in response.data


def test_results_component_supports_multiple_result_formats(client):
    """Test that component supports different result formats"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for methods that handle different formats
    assert b'createResultPane' in response.data
    assert b'createChartsContent' in response.data
    assert b'createTablesContent' in response.data
    assert b'createStatisticsContent' in response.data


def test_results_component_has_table_actions(client):
    """Test that table actions (copy, download) are available"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for table action methods
    assert b'createTableActions' in response.data
    assert b'copyTableToClipboard' in response.data
    assert b'downloadTableAsCSV' in response.data


def test_results_component_has_datatable_integration(client):
    """Test that DataTables integration is present"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for DataTables initialization
    assert b'initializeDataTables' in response.data
    assert b'result-data-table' in response.data


def test_results_component_has_proper_styling(client):
    """Test that component includes proper CSS styling"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for key CSS classes
    assert b'analysis-results-component' in response.data
    assert b'result-card' in response.data
    assert b'chart-container' in response.data
    assert b'stat-card' in response.data


def test_results_component_handles_no_results(client):
    """Test that component has handling for no results scenario"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for no results handling
    assert b'showNoResults' in response.data
    assert b'noResultsMessage' in response.data
    # Check for Chinese text (encoded)
    assert '暂无分析结果'.encode('utf-8') in response.data


def test_results_component_has_clear_functionality(client):
    """Test that component can clear results"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for clear method
    assert b'clearResults' in response.data


def test_results_component_escapes_html(client):
    """Test that component has HTML escaping for security"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check for escapeHtml method
    assert b'escapeHtml' in response.data


def test_analysis_executor_uses_results_component(client):
    """Test that AnalysisExecutor integrates with results component"""
    response = client.get('/analysis')
    assert response.status_code == 200
    
    # Check that executor checks for component availability
    assert b'analysisResultsComponent' in response.data
    # Check that the executor is loaded
    assert b'analysis_executor.js' in response.data
