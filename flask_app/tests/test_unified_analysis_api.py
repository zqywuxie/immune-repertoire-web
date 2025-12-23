"""
Tests for Unified Analysis API endpoints.

Requirements: 1.3, 3.1, 3.3, 12.1, 12.2
"""
import json
import pytest
from io import BytesIO


class TestSchemeAPI:
    """Test scheme management API endpoints"""
    
    def test_get_schemes(self, client):
        """Test GET /api/analysis/schemes"""
        response = client.get('/api/analysis/schemes')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'schemes' in data
        assert 'total' in data
        assert isinstance(data['schemes'], list)
        assert data['total'] >= 0
    
    def test_get_scheme_by_id(self, client):
        """Test GET /api/analysis/schemes/<scheme_id>"""
        # First get all schemes to find a valid ID
        response = client.get('/api/analysis/schemes')
        data = json.loads(response.data)
        
        if data['total'] > 0:
            scheme_id = data['schemes'][0]['id']
            
            # Get specific scheme
            response = client.get(f'/api/analysis/schemes/{scheme_id}')
            assert response.status_code == 200
            
            scheme_data = json.loads(response.data)
            assert 'id' in scheme_data
            assert 'name' in scheme_data
            assert 'required_fields' in scheme_data
    
    def test_get_nonexistent_scheme(self, client):
        """Test GET /api/analysis/schemes/<invalid_id>"""
        response = client.get('/api/analysis/schemes/nonexistent_scheme')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_create_custom_scheme(self, client):
        """Test POST /api/analysis/schemes/custom"""
        scheme_data = {
            'name': 'Test Custom Scheme',
            'description': 'A test custom scheme',
            'fields': ['field1', 'field2', 'field3'],
            'parameters': {
                'chart_type': 'bar'
            }
        }
        
        response = client.post(
            '/api/analysis/schemes/custom',
            data=json.dumps(scheme_data),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        
        assert data['success'] is True
        assert 'scheme_id' in data
        assert data['scheme_id'].startswith('custom_')
    
    def test_create_custom_scheme_missing_fields(self, client):
        """Test POST /api/analysis/schemes/custom with missing fields"""
        scheme_data = {
            'name': 'Test Scheme'
            # Missing description and fields
        }
        
        response = client.post(
            '/api/analysis/schemes/custom',
            data=json.dumps(scheme_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_delete_custom_scheme(self, client):
        """Test DELETE /api/analysis/schemes/custom/<scheme_id>"""
        # First create a custom scheme
        scheme_data = {
            'name': 'Test Scheme to Delete',
            'description': 'Will be deleted',
            'fields': ['field1'],
            'parameters': {}
        }
        
        create_response = client.post(
            '/api/analysis/schemes/custom',
            data=json.dumps(scheme_data),
            content_type='application/json'
        )
        
        create_data = json.loads(create_response.data)
        scheme_id = create_data['scheme_id']
        
        # Delete the scheme
        delete_response = client.delete(f'/api/analysis/schemes/custom/{scheme_id}')
        
        assert delete_response.status_code == 200
        delete_data = json.loads(delete_response.data)
        assert delete_data['success'] is True
    
    def test_delete_nonexistent_scheme(self, client):
        """Test DELETE /api/analysis/schemes/custom/<invalid_id>"""
        response = client.delete('/api/analysis/schemes/custom/custom_nonexistent')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data


class TestFieldMappingAPI:
    """Test field mapping API endpoints"""
    
    def test_auto_map_missing_file_id(self, client):
        """Test POST /api/analysis/auto-map without file_id"""
        request_data = {
            'scheme_id': 'bcell_isotype'
        }
        
        response = client.post(
            '/api/analysis/auto-map',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_auto_map_missing_scheme_id(self, client):
        """Test POST /api/analysis/auto-map without scheme_id"""
        request_data = {
            'file_id': 'test-file-id'
        }
        
        response = client.post(
            '/api/analysis/auto-map',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_auto_map_nonexistent_file(self, client):
        """Test POST /api/analysis/auto-map with nonexistent file"""
        request_data = {
            'file_id': 'nonexistent-file-id',
            'scheme_id': 'bcell_isotype'
        }
        
        response = client.post(
            '/api/analysis/auto-map',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_suggest_scheme_missing_file_id(self, client):
        """Test POST /api/analysis/suggest-scheme without file_id"""
        request_data = {}
        
        response = client.post(
            '/api/analysis/suggest-scheme',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_validate_config_missing_fields(self, client):
        """Test POST /api/analysis/validate-config with missing fields"""
        request_data = {
            'mode': 'scheme'
            # Missing file_id
        }
        
        response = client.post(
            '/api/analysis/validate-config',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


class TestAnalysisExecutionAPI:
    """Test analysis execution API endpoints"""
    
    def test_execute_unified_missing_file_id(self, client):
        """Test POST /api/analysis/execute-unified without file_id"""
        request_data = {
            'mode': 'scheme',
            'scheme_id': 'bcell_isotype'
        }
        
        response = client.post(
            '/api/analysis/execute-unified',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_execute_unified_missing_mode(self, client):
        """Test POST /api/analysis/execute-unified without mode"""
        request_data = {
            'file_id': 'test-file-id'
        }
        
        response = client.post(
            '/api/analysis/execute-unified',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_execute_unified_invalid_mode(self, client):
        """Test POST /api/analysis/execute-unified with invalid mode"""
        request_data = {
            'file_id': 'test-file-id',
            'mode': 'invalid_mode'
        }
        
        response = client.post(
            '/api/analysis/execute-unified',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_execute_unified_scheme_mode_missing_scheme_id(self, client):
        """Test POST /api/analysis/execute-unified in scheme mode without scheme_id"""
        # First upload a test file
        csv_content = b"Sample,Isotype,VGene\nS1,IgG,IGHV1-1\nS2,IgM,IGHV2-1"
        
        upload_response = client.post(
            '/api/files/upload',
            data={'file': (BytesIO(csv_content), 'test.csv')},
            content_type='multipart/form-data'
        )
        
        if upload_response.status_code == 201:
            upload_data = json.loads(upload_response.data)
            file_id = upload_data['id']
            
            # Try to execute without scheme_id
            request_data = {
                'file_id': file_id,
                'mode': 'scheme'
                # Missing scheme_id
            }
            
            response = client.post(
                '/api/analysis/execute-unified',
                data=json.dumps(request_data),
                content_type='application/json'
            )
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_execute_unified_custom_mode_missing_fields(self, client):
        """Test POST /api/analysis/execute-unified in custom mode without selected_fields"""
        # First upload a test file
        csv_content = b"field1,field2,field3\nval1,val2,val3\nval4,val5,val6"
        
        upload_response = client.post(
            '/api/files/upload',
            data={'file': (BytesIO(csv_content), 'test.csv')},
            content_type='multipart/form-data'
        )
        
        if upload_response.status_code == 201:
            upload_data = json.loads(upload_response.data)
            file_id = upload_data['id']
            
            # Try to execute without selected_fields
            request_data = {
                'file_id': file_id,
                'mode': 'custom'
                # Missing selected_fields
            }
            
            response = client.post(
                '/api/analysis/execute-unified',
                data=json.dumps(request_data),
                content_type='application/json'
            )
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
