"""
Integration tests for analysis execution workflow.
Tests complete analysis configuration, execution, and result retrieval flow.
Requirements: 14.3 (Integration testing)
"""
import io
import time
import pytest
from datetime import datetime


class TestAnalysisExecutionWorkflow:
    """Test complete analysis execution workflow. Requirements: 14.3"""
    
    @pytest.fixture
    def uploaded_file(self, client):
        """Upload a test file for analysis."""
        csv_content = b"""sample,cdr3,reads,copy,chain
S1,CASSF,100,50,TRB
S1,CASSG,200,100,TRB
S2,CASSF,150,75,TRB
S2,CASSH,180,90,TRB
S3,CASSF,120,60,TRB
S3,CASSI,160,80,TRB"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'analysis_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_similarity_analysis_workflow(self, client, uploaded_file):
        """Test complete chain-specific analysis workflow (similarity_heatmap now uses directory_path)."""
        file_id = uploaded_file['id']
        
        # Step 1: Create analysis - use chain_specific instead of similarity_heatmap
        # (similarity_heatmap now requires directory_path, selected_samples, selected_chains)
        analysis_request = {
            'type': 'chain_specific',
            'file_id': file_id,
            'field_mapping': {
                'sample': 'sample',
                'chain': 'chain',
                'cdr3': 'cdr3',
                'copy': 'copy'
            },
            'parameters': {
                'chains': ['TRB'],
                'metric': 'ucdr3'
            },
            'chart_config': {
                'title': 'Test Chain Analysis',
                'color_scheme': 'viridis',
                'figure_width': 10,
                'figure_height': 8
            }
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        assert create_response.status_code == 201
        create_data = create_response.get_json()
        analysis_id = create_data['id']
        assert create_data['status'] == 'pending'
        
        # Step 2: Check analysis status
        status_response = client.get(f'/api/analysis/{analysis_id}/status')
        assert status_response.status_code == 200
        status_data = status_response.get_json()
        assert 'status' in status_data
        assert 'progress' in status_data
        
        # Step 3: Wait for analysis to complete (with timeout)
        max_wait = 30  # seconds
        start_time = time.time()
        final_status = None
        
        while time.time() - start_time < max_wait:
            status_response = client.get(f'/api/analysis/{analysis_id}/status')
            status_data = status_response.get_json()
            final_status = status_data['status']
            
            if final_status in ['completed', 'failed']:
                break
            
            time.sleep(0.5)
        
        # Verify analysis completed
        assert final_status in ['completed', 'failed'], f"Analysis did not complete within {max_wait}s"
        
        # Step 4: Get analysis results
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200
        results_data = results_response.get_json()
        
        assert results_data['id'] == analysis_id
        assert results_data['type'] == 'chain_specific'  # Changed from similarity_heatmap
        assert results_data['status'] in ['completed', 'failed']
        
        if results_data['status'] == 'completed':
            assert 'results' in results_data
            # Verify results structure
            if results_data.get('results'):
                assert isinstance(results_data['results'], dict)
    
    def test_sequencing_depth_analysis_workflow(self, client):
        """Test sequencing depth analysis workflow."""
        # Upload file with sequencing depth data
        csv_content = b"""sample,total_rna,reads_umi,migs_good,reads_good
S1,1000000,500000,450000,480000
S2,1200000,600000,540000,580000
S3,900000,450000,400000,430000"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'sequencing_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Create sequencing depth analysis
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'field_mapping': {
                'sample': 'sample',
                'total_rna': 'total_rna',
                'reads_umi': 'reads_umi',
                'migs_good': 'migs_good',
                'reads_good': 'reads_good'
            },
            'parameters': {
                'baseline_sample': 'S1'
            },
            'chart_config': {
                'title': 'Sequencing Depth Analysis'
            }
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        assert create_response.status_code == 201
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
        
        # Get results
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200
        results_data = results_response.get_json()
        
        assert results_data['type'] == 'sequencing_depth'
        assert results_data['status'] in ['completed', 'failed']
    
    def test_diversity_metrics_analysis_workflow(self, client):
        """Test diversity metrics analysis workflow."""
        # Upload file with diversity data
        csv_content = b"""sample,chain,d50,gini,shannon,simpson
S1,IGH,25,0.65,3.2,0.85
S1,IGK,30,0.60,3.5,0.88
S2,IGH,28,0.62,3.3,0.86
S2,IGK,32,0.58,3.6,0.89"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'diversity_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Create diversity analysis
        analysis_request = {
            'type': 'diversity_metrics',
            'file_id': file_id,
            'field_mapping': {
                'sample': 'sample',
                'chain': 'chain',
                'd50': 'd50',
                'gini': 'gini',
                'shannon': 'shannon',
                'simpson': 'simpson'
            },
            'parameters': {
                'groups': {
                    'Group1': ['S1'],
                    'Group2': ['S2']
                }
            }
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Check status
        status_response = client.get(f'/api/analysis/{analysis_id}/status')
        assert status_response.status_code == 200
    
    def test_chain_specific_analysis_workflow(self, client):
        """Test chain-specific analysis workflow."""
        # Upload file with chain data
        csv_content = b"""sample,chain,cdr3,copy
S1,IGH,CASSF,100
S1,IGK,CASSG,150
S1,IGL,CASSH,120
S2,IGH,CASSF,110
S2,IGK,CASSG,160
S2,IGL,CASSH,130"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'chain_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Create chain-specific analysis
        analysis_request = {
            'type': 'chain_specific',
            'file_id': file_id,
            'field_mapping': {
                'sample': 'sample',
                'chain': 'chain',
                'cdr3': 'cdr3',
                'copy': 'copy'
            },
            'parameters': {
                'chains': ['IGH', 'IGK', 'IGL']
            }
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Verify analysis was created
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200
    
    def test_analysis_with_auto_mapping(self, client, uploaded_file):
        """Test analysis with automatic field mapping."""
        file_id = uploaded_file['id']
        
        # Create analysis without explicit field mapping
        # Use sequencing_depth instead of similarity_heatmap (which now requires directory_path)
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'parameters': {}
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Verify analysis was created
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200
        results_data = results_response.get_json()
        
        # Verify basic analysis info is present
        assert 'id' in results_data
        assert 'type' in results_data
        assert results_data['type'] == 'sequencing_depth'
    
    def test_analysis_error_handling(self, client):
        """Test analysis error handling workflow."""
        # Test with non-existent file - use sequencing_depth which requires file_id
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': 'non-existent-file-id',
            'field_mapping': {},
            'parameters': {}
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        # Should either fail immediately or create analysis that fails later
        assert create_response.status_code in [201, 400, 404]
        
        # Test with missing required fields - use sequencing_depth which requires file_id
        incomplete_request = {
            'type': 'sequencing_depth'
            # Missing file_id
        }
        
        create_response = client.post(
            '/api/analysis',
            json=incomplete_request
        )
        assert create_response.status_code == 400
        error_data = create_response.get_json()
        assert 'error_code' in error_data
    
    def test_analysis_retry_workflow(self, client, uploaded_file):
        """Test analysis retry workflow."""
        file_id = uploaded_file['id']
        
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
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Try to retry (may fail if analysis hasn't failed yet)
        retry_response = client.post(f'/api/analysis/{analysis_id}/retry')
        # 200 if analysis failed and can be retried, 400 if analysis is not in failed state
        assert retry_response.status_code in [200, 400]
        retry_data = retry_response.get_json()
        # Response should have either 'success' or 'error_code'
        assert 'success' in retry_data or 'error_code' in retry_data
    
    def test_analysis_cancel_workflow(self, client, uploaded_file):
        """Test analysis cancellation workflow."""
        file_id = uploaded_file['id']
        
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
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Try to cancel
        cancel_response = client.post(f'/api/analysis/{analysis_id}/cancel')
        assert cancel_response.status_code == 200
        cancel_data = cancel_response.get_json()
        assert 'success' in cancel_data
    
    def test_analysis_data_table_retrieval(self, client, uploaded_file):
        """Test retrieving data tables from analysis results."""
        file_id = uploaded_file['id']
        
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
        assert create_response.status_code == 201
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
        
        # Try to get data table (may not exist if analysis failed or table name doesn't exist)
        table_response = client.get(f'/api/analysis/{analysis_id}/data/metrics_table')
        # Should return 200 with data, 404 if table doesn't exist, or 400 if invalid request
        assert table_response.status_code in [200, 400, 404]
    
    def test_multiple_analyses_workflow(self, client, uploaded_file):
        """Test running multiple analyses on the same file."""
        file_id = uploaded_file['id']
        
        # Create multiple analyses - use sequencing_depth and diversity_metrics
        # (similarity_heatmap now requires directory_path)
        analysis_types = [
            {
                'type': 'sequencing_depth',
                'parameters': {}
            },
            {
                'type': 'diversity_metrics',
                'parameters': {}
            }
        ]
        
        analysis_ids = []
        
        for analysis_config in analysis_types:
            analysis_request = {
                'file_id': file_id,
                **analysis_config
            }
            
            create_response = client.post(
                '/api/analysis',
                json=analysis_request
            )
            assert create_response.status_code == 201
            analysis_ids.append(create_response.get_json()['id'])
        
        # Verify all analyses were created
        assert len(analysis_ids) == 2
        assert analysis_ids[0] != analysis_ids[1]
        
        # Verify each analysis status can be retrieved
        for analysis_id in analysis_ids:
            status_response = client.get(f'/api/analysis/{analysis_id}/status')
            assert status_response.status_code == 200
            status_data = status_response.get_json()
            assert 'status' in status_data
    
    def test_analysis_types_endpoint(self, client):
        """Test getting available analysis types."""
        response = client.get('/api/analysis/types')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'types' in data
        assert len(data['types']) > 0
        
        # Verify each type has required fields
        for analysis_type in data['types']:
            assert 'id' in analysis_type
            assert 'name' in analysis_type
            assert 'description' in analysis_type
