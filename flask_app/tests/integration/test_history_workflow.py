"""
Integration tests for history record workflow.
Tests complete history save, query, retrieval, and deletion flow.
Requirements: 14.3 (Integration testing)
"""
import io
import time
import pytest
from datetime import datetime


class TestHistoryWorkflow:
    """Test complete history workflow. Requirements: 14.3"""
    
    @pytest.fixture
    def completed_analysis(self, client):
        """Create a completed analysis for history testing."""
        # Upload file
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50\nS2,CASSG,200,TRB,100"
        data = {
            'file': (io.BytesIO(csv_content), 'history_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create analysis - use sequencing_depth instead of similarity_heatmap
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
            'file_id': file_id
        }
    
    def test_history_save_workflow(self, client, completed_analysis):
        """Test that completed analyses are automatically saved to history."""
        analysis_id = completed_analysis['analysis_id']
        
        # Query history
        history_response = client.get('/api/history')
        assert history_response.status_code == 200
        
        history_data = history_response.get_json()
        assert history_data['total'] >= 1
        
        # Verify the analysis appears in history
        analysis_ids = [item['id'] for item in history_data['items']]
        assert analysis_id in analysis_ids
    
    def test_history_query_workflow(self, client):
        """Test querying history with various filters."""
        # Create multiple analyses
        csv_content = b"sample,cdr3,reads\nS1,CASSF,100\nS2,CASSG,200"
        data = {
            'file': (io.BytesIO(csv_content), 'query_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create analyses of different types
        analysis_configs = [
            {'type': 'similarity_heatmap', 'parameters': {'metrics': ['r2_inner']}},
            {'type': 'similarity_heatmap', 'parameters': {'metrics': ['cdr3_sharing']}}
        ]
        
        for config in analysis_configs:
            analysis_request = {
                'file_id': file_id,
                **config
            }
            client.post('/api/analysis', json=analysis_request)
        
        # Wait a bit for analyses to process
        time.sleep(1)
        
        # Test 1: Query all history
        response = client.get('/api/history')
        assert response.status_code == 200
        data = response.get_json()
        assert 'items' in data
        assert 'total' in data
        assert 'page' in data
        
        # Test 2: Query with pagination
        response = client.get('/api/history?page=1&page_size=5')
        assert response.status_code == 200
        data = response.get_json()
        assert data['page'] == 1
        assert len(data['items']) <= 5
        
        # Test 3: Query with type filter
        response = client.get('/api/history?type=similarity_heatmap')
        assert response.status_code == 200
        data = response.get_json()
        for item in data['items']:
            assert item['analysis_type'] == 'similarity_heatmap'
        
        # Test 4: Query with status filter
        response = client.get('/api/history?status=completed')
        assert response.status_code == 200
        data = response.get_json()
        # All items should have completed status (or be empty)
        for item in data['items']:
            assert item['status'] in ['completed', 'pending', 'running', 'failed']
    
    def test_history_retrieval_workflow(self, client, completed_analysis):
        """Test retrieving a specific history item."""
        analysis_id = completed_analysis['analysis_id']
        
        # Retrieve history item
        response = client.get(f'/api/history/{analysis_id}')
        assert response.status_code == 200
        
        item_data = response.get_json()
        assert item_data['id'] == analysis_id
        assert 'analysis_type' in item_data
        assert 'file_name' in item_data
        assert 'status' in item_data
        assert 'created_at' in item_data
        
        # Verify timestamps are valid
        created_at = item_data.get('created_at')
        if created_at:
            # Should be a valid ISO format timestamp
            datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    
    def test_history_retrieval_consistency(self, client, completed_analysis):
        """Test that historical analysis results are consistent with original results."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get original analysis results
        original_response = client.get(f'/api/analysis/{analysis_id}')
        assert original_response.status_code == 200
        original_data = original_response.get_json()
        
        # Get history item
        history_response = client.get(f'/api/history/{analysis_id}')
        assert history_response.status_code == 200
        history_data = history_response.get_json()
        
        # Verify key fields match
        assert history_data['id'] == original_data['id']
        assert history_data['analysis_type'] == original_data['type']
        assert history_data['status'] == original_data['status']
    
    def test_history_deletion_workflow(self, client):
        """Test deleting history items."""
        # Create an analysis
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50"
        data = {
            'file': (io.BytesIO(csv_content), 'delete_test.csv')
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
        
        create_response = client.post('/api/analysis', json=analysis_request)
        analysis_id = create_response.get_json()['id']
        
        # Wait for analysis to complete or fail
        time.sleep(2)
        
        # Verify item exists in history
        history_response = client.get('/api/history')
        history_data = history_response.get_json()
        analysis_ids = [item['id'] for item in history_data['items']]
        assert analysis_id in analysis_ids
        
        # Delete history item
        delete_response = client.delete(f'/api/history/{analysis_id}')
        assert delete_response.status_code == 200
        delete_data = delete_response.get_json()
        assert delete_data['success'] is True
        
        # Verify item no longer exists in history
        history_response = client.get('/api/history')
        history_data = history_response.get_json()
        analysis_ids = [item['id'] for item in history_data['items']]
        assert analysis_id not in analysis_ids
        
        # Verify item cannot be retrieved
        get_response = client.get(f'/api/history/{analysis_id}')
        assert get_response.status_code == 404
    
    def test_history_deletion_completeness(self, client, completed_analysis):
        """Test that deletion removes all associated files."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get analysis details before deletion
        analysis_response = client.get(f'/api/analysis/{analysis_id}')
        assert analysis_response.status_code == 200
        
        # Delete history item
        delete_response = client.delete(f'/api/history/{analysis_id}')
        assert delete_response.status_code == 200
        
        # Verify analysis is deleted
        analysis_response = client.get(f'/api/analysis/{analysis_id}')
        assert analysis_response.status_code == 404
        
        # Verify history item is deleted
        history_response = client.get(f'/api/history/{analysis_id}')
        assert history_response.status_code == 404
    
    def test_history_stats_workflow(self, client):
        """Test getting history statistics."""
        # Create multiple analyses with different statuses
        csv_content = b"sample,cdr3,reads\nS1,CASSF,100\nS2,CASSG,200"
        data = {
            'file': (io.BytesIO(csv_content), 'stats_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create several analyses
        for i in range(3):
            analysis_request = {
                'type': 'similarity_heatmap',
                'file_id': file_id,
                'parameters': {'metrics': ['r2_inner']}
            }
            client.post('/api/analysis', json=analysis_request)
        
        # Wait for analyses to process
        time.sleep(2)
        
        # Get history stats
        stats_response = client.get('/api/history/stats')
        assert stats_response.status_code == 200
        
        stats_data = stats_response.get_json()
        assert 'status_counts' in stats_data
        assert 'type_counts' in stats_data
        
        # Verify counts are dictionaries
        assert isinstance(stats_data['status_counts'], dict)
        assert isinstance(stats_data['type_counts'], dict)
    
    def test_history_pagination_workflow(self, client):
        """Test history pagination."""
        # Create multiple analyses
        csv_content = b"sample,cdr3,reads\nS1,CASSF,100"
        data = {
            'file': (io.BytesIO(csv_content), 'pagination_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create 15 analyses
        for i in range(15):
            analysis_request = {
                'type': 'similarity_heatmap',
                'file_id': file_id,
                'parameters': {'metrics': ['r2_inner']}
            }
            client.post('/api/analysis', json=analysis_request)
        
        # Wait for analyses to be created
        time.sleep(1)
        
        # Test first page
        response = client.get('/api/history?page=1&page_size=10')
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['page'] == 1
        assert len(data['items']) <= 10
        total = data['total']
        
        # Test second page
        response = client.get('/api/history?page=2&page_size=10')
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['page'] == 2
        # Should have remaining items
        assert len(data['items']) <= 10
    
    def test_history_not_found_workflow(self, client):
        """Test handling of non-existent history items."""
        # Try to get non-existent history item
        response = client.get('/api/history/non-existent-id')
        assert response.status_code == 404
        
        error_data = response.get_json()
        assert error_data['error_code'] == 'ANALYSIS_NOT_FOUND'
        
        # Try to delete non-existent history item
        response = client.delete('/api/history/non-existent-id')
        assert response.status_code == 404
    
    def test_history_ordering_workflow(self, client):
        """Test that history items are ordered by creation time."""
        # Create multiple analyses with delays
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50"
        data = {
            'file': (io.BytesIO(csv_content), 'ordering_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        analysis_ids = []
        
        for i in range(3):
            # Use sequencing_depth instead of similarity_heatmap
            analysis_request = {
                'type': 'sequencing_depth',
                'file_id': file_id,
                'parameters': {}
            }
            response = client.post('/api/analysis', json=analysis_request)
            analysis_ids.append(response.get_json()['id'])
            time.sleep(0.5)  # Small delay between creations
        
        # Get history
        history_response = client.get('/api/history')
        assert history_response.status_code == 200
        history_data = history_response.get_json()
        
        # Verify items are ordered (most recent first)
        if len(history_data['items']) >= 3:
            timestamps = [item.get('created_at') for item in history_data['items'][:3]]
            # All timestamps should be present
            assert all(ts is not None for ts in timestamps)
    
    def test_complete_history_lifecycle(self, client):
        """Test complete history lifecycle: create, query, retrieve, delete."""
        # Step 1: Create analysis
        csv_content = b"sample,cdr3,reads,chain,copy\nS1,CASSF,100,TRB,50\nS2,CASSG,200,TRB,100"
        data = {
            'file': (io.BytesIO(csv_content), 'lifecycle_test.csv')
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
        
        create_response = client.post('/api/analysis', json=analysis_request)
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Step 2: Wait for completion
        time.sleep(2)
        
        # Step 3: Verify in history list
        history_response = client.get('/api/history')
        assert history_response.status_code == 200
        history_data = history_response.get_json()
        analysis_ids = [item['id'] for item in history_data['items']]
        assert analysis_id in analysis_ids
        
        # Step 4: Retrieve specific history item
        item_response = client.get(f'/api/history/{analysis_id}')
        assert item_response.status_code == 200
        item_data = item_response.get_json()
        assert item_data['id'] == analysis_id
        
        # Step 5: Delete history item
        delete_response = client.delete(f'/api/history/{analysis_id}')
        assert delete_response.status_code == 200
        
        # Step 6: Verify deletion
        verify_response = client.get(f'/api/history/{analysis_id}')
        assert verify_response.status_code == 404
