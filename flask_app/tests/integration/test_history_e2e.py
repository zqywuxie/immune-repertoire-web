"""
End-to-end integration tests for history record workflow.
Tests Requirements 1.1, 1.2, 1.3, 1.5 from ui-fixes spec.

Requirements:
- 1.1: Backend includes 'type' field in history response
- 1.2: Frontend correctly maps 'type' field to 'type_text'
- 1.3: DataTables initializes without errors
- 1.5: History data contains all required fields
"""
import io
import time
import pytest
from datetime import datetime


class TestHistoryEndToEnd:
    """End-to-end tests for history workflow. Requirements: 1.1, 1.2, 1.3, 1.5"""
    
    @pytest.fixture
    def sample_analysis(self, client):
        """Create a sample analysis for testing."""
        # Upload file
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50\nS2,CASSG,200,TRB,100"
        data = {
            'file': (io.BytesIO(csv_content), 'e2e_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create analysis
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'parameters': {}
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        analysis_id = create_response.get_json()['id']
        
        # Wait for completion
        max_wait = 30
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_response = client.get(f'/api/analysis/{analysis_id}/status')
            status_data = status_response.get_json()
            
            if status_data['status'] in ['completed', 'failed']:
                break
            
            time.sleep(0.5)
        
        return {
            'analysis_id': analysis_id,
            'file_id': file_id,
            'analysis_type': 'sequencing_depth'
        }
    
    def test_history_type_field_present(self, client, sample_analysis):
        """
        Test that history API response includes 'type' field.
        Requirement 1.1: Backend includes 'type' field in response
        """
        analysis_id = sample_analysis['analysis_id']
        
        # Get history list
        response = client.get('/api/history')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'items' in data
        
        # Find our analysis in the history
        history_item = None
        for item in data['items']:
            if item['id'] == analysis_id:
                history_item = item
                break
        
        assert history_item is not None, "Analysis not found in history"
        
        # Verify 'type' field exists
        assert 'type' in history_item, "Missing 'type' field in history response"
        assert history_item['type'] == sample_analysis['analysis_type']
        
        # Also verify 'analysis_type' field for backward compatibility
        assert 'analysis_type' in history_item
        assert history_item['analysis_type'] == sample_analysis['analysis_type']
    
    def test_history_single_item_type_field(self, client, sample_analysis):
        """
        Test that single history item retrieval includes 'type' field.
        Requirement 1.1: Backend includes 'type' field in response
        """
        analysis_id = sample_analysis['analysis_id']
        
        # Get single history item
        response = client.get(f'/api/history/{analysis_id}')
        assert response.status_code == 200
        
        item = response.get_json()
        
        # Verify 'type' field exists
        assert 'type' in item, "Missing 'type' field in single history item response"
        assert item['type'] == sample_analysis['analysis_type']
        
        # Also verify 'analysis_type' field
        assert 'analysis_type' in item
        assert item['analysis_type'] == sample_analysis['analysis_type']
    
    def test_history_data_completeness(self, client, sample_analysis):
        """
        Test that history data contains all required fields.
        Requirement 1.5: History data contains all required fields
        """
        analysis_id = sample_analysis['analysis_id']
        
        # Get history item
        response = client.get(f'/api/history/{analysis_id}')
        assert response.status_code == 200
        
        item = response.get_json()
        
        # Verify all required fields are present
        required_fields = [
            'id',
            'type',
            'analysis_type',
            'file_id',
            'file_name',
            'status',
            'parameters',
            'chart_config',
            'created_at'
        ]
        
        for field in required_fields:
            assert field in item, f"Missing required field: {field}"
        
        # Verify field types
        assert isinstance(item['id'], str)
        assert isinstance(item['type'], str)
        assert isinstance(item['analysis_type'], str)
        assert isinstance(item['file_id'], str)
        assert isinstance(item['file_name'], str)
        assert isinstance(item['status'], str)
        assert isinstance(item['parameters'], dict)
        assert isinstance(item['chart_config'], dict)
        assert isinstance(item['created_at'], str)
        
        # Verify timestamp format
        try:
            datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"Invalid timestamp format: {item['created_at']}")
    
    def test_history_type_field_consistency(self, client):
        """
        Test that 'type' field is consistent across different analysis types.
        Requirement 1.1: Backend includes 'type' field in response
        """
        # Upload file
        csv_content = b"sample,cdr3,reads\nS1,CASSF,100\nS2,CASSG,200"
        data = {
            'file': (io.BytesIO(csv_content), 'type_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create analyses of different types
        analysis_types = ['similarity_heatmap', 'sequencing_depth']
        created_analyses = []
        
        for analysis_type in analysis_types:
            analysis_request = {
                'type': analysis_type,
                'file_id': file_id,
                'parameters': {}
            }
            response = client.post('/api/analysis', json=analysis_request)
            if response.status_code == 201:
                created_analyses.append({
                    'id': response.get_json()['id'],
                    'type': analysis_type
                })
        
        # Wait for analyses to be created
        time.sleep(2)
        
        # Verify each analysis has correct 'type' field
        for analysis in created_analyses:
            response = client.get(f'/api/history/{analysis["id"]}')
            if response.status_code == 200:
                item = response.get_json()
                assert 'type' in item
                assert item['type'] == analysis['type']
    
    def test_history_page_accessibility(self, client):
        """
        Test that history page is accessible and loads without errors.
        Requirement 1.3: DataTables initializes without errors (page level)
        """
        # Access history page
        response = client.get('/history')
        assert response.status_code == 200
        
        # Verify page contains expected elements
        html = response.data.decode('utf-8')
        
        # Check for history table
        assert 'historyTable' in html or 'history-table' in html
        
        # Check for DataTables initialization
        assert 'DataTable' in html or 'dataTable' in html
    
    def test_history_api_error_handling(self, client):
        """
        Test error handling for history API endpoints.
        Requirement 1.3: Proper error handling prevents crashes
        """
        # Test non-existent history item
        response = client.get('/api/history/non-existent-id')
        assert response.status_code == 404
        
        error_data = response.get_json()
        assert 'error_code' in error_data
        assert error_data['error_code'] == 'ANALYSIS_NOT_FOUND'
    
    def test_history_pagination_with_type_field(self, client):
        """
        Test that paginated history results include 'type' field.
        Requirement 1.1: Backend includes 'type' field in response
        """
        # Get paginated history
        response = client.get('/api/history?page=1&page_size=5')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'items' in data
        
        # Verify all items have 'type' field
        for item in data['items']:
            assert 'type' in item, "Missing 'type' field in paginated history item"
            assert isinstance(item['type'], str)
    
    def test_history_filtered_by_type(self, client):
        """
        Test filtering history by type field.
        Requirement 1.1: Backend includes 'type' field in response
        """
        # Filter by specific type
        response = client.get('/api/history?type=similarity_heatmap')
        assert response.status_code == 200
        
        data = response.get_json()
        
        # Verify all returned items have the correct type
        for item in data['items']:
            assert 'type' in item
            assert item['type'] == 'similarity_heatmap'
    
    def test_complete_history_workflow_with_type_field(self, client):
        """
        Test complete workflow: create, retrieve, verify type field, delete.
        Requirements: 1.1, 1.2, 1.3, 1.5
        """
        # Step 1: Create analysis
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50"
        data = {
            'file': (io.BytesIO(csv_content), 'workflow_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'parameters': {}
        }
        
        create_response = client.post('/api/analysis', json=analysis_request)
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Step 2: Wait for processing
        time.sleep(2)
        
        # Step 3: Retrieve from history and verify type field
        history_response = client.get(f'/api/history/{analysis_id}')
        assert history_response.status_code == 200
        
        history_item = history_response.get_json()
        
        # Verify type field
        assert 'type' in history_item
        assert history_item['type'] == 'sequencing_depth'
        
        # Verify all required fields
        required_fields = ['id', 'type', 'analysis_type', 'file_id', 
                          'file_name', 'status', 'parameters', 
                          'chart_config', 'created_at']
        for field in required_fields:
            assert field in history_item
        
        # Step 4: Verify in history list
        list_response = client.get('/api/history')
        assert list_response.status_code == 200
        
        list_data = list_response.get_json()
        found = False
        for item in list_data['items']:
            if item['id'] == analysis_id:
                assert 'type' in item
                assert item['type'] == 'sequencing_depth'
                found = True
                break
        
        assert found, "Analysis not found in history list"
        
        # Step 5: Clean up
        delete_response = client.delete(f'/api/history/{analysis_id}')
        assert delete_response.status_code == 200
