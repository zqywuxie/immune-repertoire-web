"""
Comprehensive API endpoint tests.
Tests all REST endpoints for correct status codes, response formats, and error handling.
Requirements: 14.4 (API testing)
"""
import io
import pytest


class TestHealthAndInfoEndpoints:
    """Test health check and info endpoints. Requirements: 14.4"""
    
    def test_health_check(self, client):
        """Test GET /api/health."""
        response = client.get('/api/health')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'status' in data
        assert data['status'] == 'healthy'
    
    def test_app_info(self, client):
        """Test GET /api/info."""
        response = client.get('/api/info')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'name' in data
        assert 'version' in data
        assert 'status' in data


class TestFileEndpoints:
    """Test file management endpoints. Requirements: 14.4"""
    
    def test_upload_file_success(self, client):
        """Test POST /api/files/upload - success case."""
        csv_content = b"sample,cdr3\nS1,CASSF"
        data = {
            'file': (io.BytesIO(csv_content), 'test.csv')
        }
        
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        
        assert response.status_code == 201
        assert response.is_json
        
        data = response.get_json()
        assert 'id' in data
        assert 'name' in data
        assert 'columns' in data
        assert 'row_count' in data
    
    def test_upload_file_no_file(self, client):
        """Test POST /api/files/upload - no file provided."""
        response = client.post('/api/files/upload')
        assert response.status_code == 400
        assert response.is_json
    
    def test_upload_file_invalid_format(self, client):
        """Test POST /api/files/upload - invalid format."""
        data = {
            'file': (io.BytesIO(b"test"), 'test.txt')
        }
        
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        
        assert response.status_code == 400
        assert response.is_json
        
        error_data = response.get_json()
        assert 'error_code' in error_data
    
    def test_list_files(self, client):
        """Test GET /api/files."""
        response = client.get('/api/files')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'files' in data
        assert 'total' in data
        assert isinstance(data['files'], list)
    
    def test_get_file_not_found(self, client):
        """Test GET /api/files/{file_id} - not found."""
        response = client.get('/api/files/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
        
        error_data = response.get_json()
        assert 'error_code' in error_data
    
    def test_delete_file_not_found(self, client):
        """Test DELETE /api/files/{file_id} - not found."""
        response = client.delete('/api/files/non-existent-id')
        assert response.status_code == 404
        assert response.is_json


class TestMappingEndpoints:
    """Test field mapping endpoints. Requirements: 14.4"""
    
    def test_create_mapping_template_success(self, client):
        """Test POST /api/mappings - success case."""
        request_data = {
            'name': 'Test Template',
            'mapping': {'sample': 'sample_col', 'cdr3': 'cdr3_col'},
            'analysis_type': 'similarity_heatmap'
        }
        
        response = client.post('/api/mappings', json=request_data)
        assert response.status_code == 201
        assert response.is_json
        
        data = response.get_json()
        assert 'id' in data
        assert data['name'] == 'Test Template'
    
    def test_create_mapping_template_missing_fields(self, client):
        """Test POST /api/mappings - missing required fields."""
        request_data = {
            'name': 'Test Template'
            # Missing mapping and analysis_type
        }
        
        response = client.post('/api/mappings', json=request_data)
        assert response.status_code == 400
        assert response.is_json
    
    def test_list_mapping_templates(self, client):
        """Test GET /api/mappings."""
        response = client.get('/api/mappings')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'templates' in data
        assert 'total' in data
    
    def test_list_mapping_templates_with_filter(self, client):
        """Test GET /api/mappings with analysis_type filter."""
        response = client.get('/api/mappings?analysis_type=similarity_heatmap')
        assert response.status_code == 200
        assert response.is_json
    
    def test_get_mapping_template_not_found(self, client):
        """Test GET /api/mappings/{template_id} - not found."""
        response = client.get('/api/mappings/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
    
    def test_delete_mapping_template_not_found(self, client):
        """Test DELETE /api/mappings/{template_id} - not found."""
        response = client.delete('/api/mappings/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
    
    def test_suggest_mapping_success(self, client):
        """Test POST /api/mappings/suggest - success case."""
        request_data = {
            'columns': ['sample', 'cdr3', 'reads'],
            'analysis_type': 'similarity_heatmap'
        }
        
        response = client.post('/api/mappings/suggest', json=request_data)
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'suggested_mapping' in data
        assert 'confidence' in data
    
    def test_suggest_mapping_missing_fields(self, client):
        """Test POST /api/mappings/suggest - missing fields."""
        request_data = {
            'columns': ['sample', 'cdr3']
            # Missing analysis_type
        }
        
        response = client.post('/api/mappings/suggest', json=request_data)
        assert response.status_code == 400
        assert response.is_json
    
    def test_validate_mapping_success(self, client):
        """Test POST /api/mappings/validate - success case."""
        request_data = {
            'mapping': {'sample': 'sample_col'},
            'analysis_type': 'similarity_heatmap',
            'columns': ['sample_col', 'cdr3_col']
        }
        
        response = client.post('/api/mappings/validate', json=request_data)
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'is_valid' in data
    
    def test_get_required_fields(self, client):
        """Test GET /api/mappings/fields/{analysis_type}."""
        response = client.get('/api/mappings/fields/similarity_heatmap')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'analysis_type' in data
        assert 'required_fields' in data
    
    def test_get_required_fields_invalid_type(self, client):
        """Test GET /api/mappings/fields/{analysis_type} - invalid type."""
        response = client.get('/api/mappings/fields/invalid_type')
        assert response.status_code == 400
        assert response.is_json


class TestAnalysisEndpoints:
    """Test analysis endpoints. Requirements: 14.4"""
    
    @pytest.fixture
    def uploaded_file(self, client):
        """Upload a test file."""
        csv_content = b"sample,cdr3,reads\nS1,CASSF,100"
        data = {
            'file': (io.BytesIO(csv_content), 'test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        return response.get_json()['id']
    
    def test_create_analysis_success(self, client, uploaded_file):
        """Test POST /api/analysis - success case."""
        # Use sequencing_depth analysis type which uses file_id
        # (similarity_heatmap now uses directory_path instead)
        request_data = {
            'type': 'sequencing_depth',
            'file_id': uploaded_file,
            'parameters': {}
        }
        
        response = client.post('/api/analysis', json=request_data)
        assert response.status_code == 201
        assert response.is_json
        
        data = response.get_json()
        assert 'id' in data
        assert 'status' in data
    
    def test_create_analysis_missing_fields(self, client):
        """Test POST /api/analysis - missing required fields."""
        # Use sequencing_depth which requires file_id
        request_data = {
            'type': 'sequencing_depth'
            # Missing file_id
        }
        
        response = client.post('/api/analysis', json=request_data)
        assert response.status_code == 400
        assert response.is_json
    
    def test_get_analysis_not_found(self, client):
        """Test GET /api/analysis/{analysis_id} - not found."""
        response = client.get('/api/analysis/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
    
    def test_get_analysis_status_not_found(self, client):
        """Test GET /api/analysis/{analysis_id}/status - not found."""
        response = client.get('/api/analysis/non-existent-id/status')
        assert response.status_code == 404
        assert response.is_json
    
    def test_get_analysis_data_table_not_found(self, client):
        """Test GET /api/analysis/{analysis_id}/data/{table_name} - not found."""
        response = client.get('/api/analysis/non-existent-id/data/test_table')
        assert response.status_code == 404
        assert response.is_json
    
    def test_retry_analysis_not_found(self, client):
        """Test POST /api/analysis/{analysis_id}/retry - not found."""
        response = client.post('/api/analysis/non-existent-id/retry')
        assert response.status_code == 404
        assert response.is_json
    
    def test_cancel_analysis_not_found(self, client):
        """Test POST /api/analysis/{analysis_id}/cancel - not found."""
        response = client.post('/api/analysis/non-existent-id/cancel')
        assert response.status_code == 404
        assert response.is_json
    
    def test_download_analysis_result_invalid_format(self, client, uploaded_file):
        """Test GET /api/analysis/{analysis_id}/download - invalid format."""
        # Create analysis first - use sequencing_depth instead of similarity_heatmap
        request_data = {
            'type': 'sequencing_depth',
            'file_id': uploaded_file,
            'parameters': {}
        }
        response = client.post('/api/analysis', json=request_data)
        analysis_id = response.get_json()['id']
        
        # Try to download with invalid format
        response = client.get(
            f'/api/analysis/{analysis_id}/download',
            query_string={'format': 'invalid'}
        )
        assert response.status_code == 400
        assert response.is_json
    
    def test_get_available_exports_not_found(self, client):
        """Test GET /api/analysis/{analysis_id}/exports - not found."""
        response = client.get('/api/analysis/non-existent-id/exports')
        assert response.status_code == 404
        assert response.is_json
    
    def test_get_analysis_types(self, client):
        """Test GET /api/analysis/types."""
        response = client.get('/api/analysis/types')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'types' in data
        assert isinstance(data['types'], list)


class TestHistoryEndpoints:
    """Test history endpoints. Requirements: 14.4"""
    
    def test_get_history(self, client):
        """Test GET /api/history."""
        response = client.get('/api/history')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'items' in data
        assert 'total' in data
        assert 'page' in data
    
    def test_get_history_with_pagination(self, client):
        """Test GET /api/history with pagination."""
        response = client.get('/api/history?page=1&page_size=10')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert data['page'] == 1
    
    def test_get_history_with_filters(self, client):
        """Test GET /api/history with filters."""
        response = client.get('/api/history?status=completed&type=similarity_heatmap')
        assert response.status_code == 200
        assert response.is_json
    
    def test_get_history_item_not_found(self, client):
        """Test GET /api/history/{analysis_id} - not found."""
        response = client.get('/api/history/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
    
    def test_delete_history_item_not_found(self, client):
        """Test DELETE /api/history/{analysis_id} - not found."""
        response = client.delete('/api/history/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
    
    def test_get_history_stats(self, client):
        """Test GET /api/history/stats."""
        response = client.get('/api/history/stats')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'status_counts' in data
        assert 'type_counts' in data


class TestConfigEndpoints:
    """Test configuration endpoints. Requirements: 14.4"""
    
    def test_get_config(self, client):
        """Test GET /api/config."""
        response = client.get('/api/config')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'config_id' in data
        assert 'config' in data
    
    def test_get_config_with_id(self, client):
        """Test GET /api/config with config_id."""
        response = client.get('/api/config?config_id=test')
        assert response.status_code == 200
        assert response.is_json
    
    def test_save_config_success(self, client):
        """Test POST /api/config - success case."""
        request_data = {
            'config': {
                'default_color_scheme': 'viridis',
                'default_figure_size': [10, 8]
            }
        }
        
        response = client.post('/api/config', json=request_data)
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert data['success'] is True
    
    def test_save_config_missing_data(self, client):
        """Test POST /api/config - missing config data."""
        request_data = {}
        
        response = client.post('/api/config', json=request_data)
        assert response.status_code == 400
        assert response.is_json
    
    def test_update_config_success(self, client):
        """Test PATCH /api/config - success case."""
        request_data = {
            'updates': {
                'default_color_scheme': 'plasma'
            }
        }
        
        response = client.patch('/api/config', json=request_data)
        assert response.status_code == 200
        assert response.is_json
    
    def test_reset_config(self, client):
        """Test POST /api/config/reset."""
        response = client.post('/api/config/reset', json={})
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert data['success'] is True
    
    def test_get_config_options(self, client):
        """Test GET /api/config/options."""
        response = client.get('/api/config/options')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'color_schemes' in data


class TestParameterTemplateEndpoints:
    """Test parameter template endpoints. Requirements: 14.4"""
    
    def test_list_parameter_templates(self, client):
        """Test GET /api/parameters/templates."""
        response = client.get('/api/parameters/templates')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'templates' in data
        assert 'total' in data
    
    def test_list_parameter_templates_with_filter(self, client):
        """Test GET /api/parameters/templates with filter."""
        response = client.get('/api/parameters/templates?analysis_type=similarity_heatmap')
        assert response.status_code == 200
        assert response.is_json
    
    def test_get_parameter_template_not_found(self, client):
        """Test GET /api/parameters/templates/{template_id} - not found."""
        response = client.get('/api/parameters/templates/non-existent-id')
        assert response.status_code == 400
        assert response.is_json
    
    def test_create_parameter_template_success(self, client):
        """Test POST /api/parameters/templates - success case."""
        request_data = {
            'name': 'Test Template',
            'analysis_type': 'similarity_heatmap',
            'parameters': {'metrics': ['r2_inner']}
        }
        
        response = client.post('/api/parameters/templates', json=request_data)
        assert response.status_code == 201
        assert response.is_json
    
    def test_create_parameter_template_missing_fields(self, client):
        """Test POST /api/parameters/templates - missing fields."""
        request_data = {
            'name': 'Test Template'
            # Missing analysis_type
        }
        
        response = client.post('/api/parameters/templates', json=request_data)
        assert response.status_code == 400
        assert response.is_json
    
    def test_get_default_parameters(self, client):
        """Test GET /api/parameters/defaults/{analysis_type}."""
        response = client.get('/api/parameters/defaults/similarity_heatmap')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'analysis_type' in data
        assert 'parameters' in data
    
    def test_get_default_parameters_invalid_type(self, client):
        """Test GET /api/parameters/defaults/{analysis_type} - invalid type."""
        response = client.get('/api/parameters/defaults/invalid_type')
        assert response.status_code == 400
        assert response.is_json
    
    def test_validate_parameters(self, client):
        """Test POST /api/parameters/validate."""
        request_data = {
            'analysis_type': 'similarity_heatmap',
            'parameters': {'metrics': ['r2_inner']}
        }
        
        response = client.post('/api/parameters/validate', json=request_data)
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'is_valid' in data


class TestAnnotationEndpoints:
    """Test annotation endpoints. Requirements: 14.4"""
    
    @pytest.fixture
    def test_analysis_id(self, client):
        """Create a test analysis."""
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50"
        data = {
            'file': (io.BytesIO(csv_content), 'test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Use sequencing_depth instead of similarity_heatmap
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'parameters': {}
        }
        response = client.post('/api/analysis', json=analysis_request)
        return response.get_json()['id']
    
    def test_get_annotations(self, client, test_analysis_id):
        """Test GET /api/annotations/{analysis_id}."""
        response = client.get(f'/api/annotations/{test_analysis_id}')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'annotations' in data
        assert 'total' in data
    
    def test_create_annotation_success(self, client, test_analysis_id):
        """Test POST /api/annotations/{analysis_id} - success case."""
        request_data = {
            'annotation_type': 'text',
            'position_x': 100,
            'position_y': 200,
            'content': 'Test annotation'
        }
        
        response = client.post(
            f'/api/annotations/{test_analysis_id}',
            json=request_data
        )
        assert response.status_code == 201
        assert response.is_json
    
    def test_create_annotation_missing_fields(self, client, test_analysis_id):
        """Test POST /api/annotations/{analysis_id} - missing fields."""
        request_data = {
            'annotation_type': 'text'
            # Missing position_x and position_y
        }
        
        response = client.post(
            f'/api/annotations/{test_analysis_id}',
            json=request_data
        )
        assert response.status_code == 400
        assert response.is_json
    
    def test_get_annotation_not_found(self, client):
        """Test GET /api/annotations/item/{annotation_id} - not found."""
        response = client.get('/api/annotations/item/non-existent-id')
        assert response.status_code == 400
        assert response.is_json
    
    def test_get_annotation_types(self, client):
        """Test GET /api/annotations/types."""
        response = client.get('/api/annotations/types')
        assert response.status_code == 200
        assert response.is_json
        
        data = response.get_json()
        assert 'types' in data


class TestErrorHandling:
    """Test error handling across all endpoints. Requirements: 14.4"""
    
    def test_404_not_found(self, client):
        """Test 404 error for non-existent route."""
        response = client.get('/api/non-existent-endpoint')
        assert response.status_code == 404
    
    def test_400_bad_request_no_json(self, client):
        """Test 415 error for endpoints expecting JSON when no content-type is provided."""
        response = client.post('/api/analysis')
        assert response.status_code == 415  # Unsupported Media Type
    
    def test_405_method_not_allowed(self, client):
        """Test 405 error for wrong HTTP method."""
        response = client.put('/api/health')
        assert response.status_code == 405
    
    def test_error_response_format(self, client):
        """Test that error responses have consistent format."""
        response = client.get('/api/files/non-existent-id')
        assert response.status_code == 404
        assert response.is_json
        
        data = response.get_json()
        assert 'error_code' in data
        assert 'message' in data
