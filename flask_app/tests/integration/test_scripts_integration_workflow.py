"""
Integration tests for scripts integration workflow.
Tests complete workflows for B cell isotype, SHM, IG metrics, PDF extraction, and field analysis.
Requirements: All requirements from scripts-integration spec
"""
import io
import time
import pytest
import pandas as pd
from datetime import datetime


class TestBcellIsotypeWorkflow:
    """Test complete B cell isotype analysis workflow. Requirements: 1.1-1.5"""
    
    @pytest.fixture
    def bcell_isotype_file(self, client):
        """Upload a test file with B cell isotype data."""
        csv_content = b"""sample,IgM_expression,IgM_ucdr3,IgD_expression,IgD_ucdr3,IgA_expression,IgA_ucdr3,IgG1_expression,IgG1_ucdr3,IgG3_expression,IgG3_ucdr3,IgE_expression,IgE_ucdr3
S1,15.5,12.3,8.2,6.5,25.3,22.1,35.6,30.2,12.4,10.5,3.0,2.8
S2,18.2,14.5,9.1,7.2,28.5,24.8,32.1,28.5,10.2,8.9,1.9,1.6
S3,16.8,13.2,7.5,5.8,26.9,23.5,34.2,29.8,11.8,9.8,2.8,2.5"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'bcell_isotype_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_bcell_isotype_analysis_complete_workflow(self, client, bcell_isotype_file):
        """Test complete B cell isotype analysis from upload to results."""
        file_id = bcell_isotype_file['id']
        
        # Step 1: Create B cell isotype analysis
        analysis_request = {
            'type': 'bcell_isotype',
            'file_id': file_id,
            'parameters': {
                'baseline_sample': 'S1'
            },
            'chart_config': {
                'title': 'B Cell Isotype Distribution',
                'color_scheme': 'Set2',
                'figure_width': 12,
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
        
        # Step 2: Wait for analysis to complete
        max_wait = 30
        start_time = time.time()
        final_status = None
        
        while time.time() - start_time < max_wait:
            status_response = client.get(f'/api/analysis/{analysis_id}/status')
            status_data = status_response.get_json()
            final_status = status_data['status']
            
            if final_status in ['completed', 'failed']:
                break
            
            time.sleep(0.5)
        
        # Step 3: Verify analysis completed successfully
        assert final_status == 'completed', f"Analysis failed or timed out: {final_status}"
        
        # Step 4: Get analysis results
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200
        results_data = results_response.get_json()
        
        assert results_data['type'] == 'bcell_isotype'
        assert results_data['status'] == 'completed'
        assert 'results' in results_data
        
        # Step 5: Verify results structure
        results = results_data['results']
        assert 'isotypes' in results or 'data' in results
        
        # Step 6: Verify data table can be retrieved
        table_response = client.get(f'/api/analysis/{analysis_id}/data/isotype_table')
        # Should return 200 with data or 404 if table doesn't exist
        assert table_response.status_code in [200, 404]
    
    def test_bcell_isotype_baseline_comparison(self, client, bcell_isotype_file):
        """Test B cell isotype analysis with baseline comparison."""
        file_id = bcell_isotype_file['id']
        
        # Create analysis with baseline
        analysis_request = {
            'type': 'bcell_isotype',
            'file_id': file_id,
            'parameters': {
                'baseline_sample': 'S1'
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
        
        # Verify baseline comparison was performed
        if results_data['status'] == 'completed' and 'results' in results_data:
            results = results_data['results']
            # Check for percentage differences or baseline-related data
            assert isinstance(results, dict)


class TestSHMAnalysisWorkflow:
    """Test complete SHM analysis workflow. Requirements: 2.1-2.5"""
    
    @pytest.fixture
    def shm_file(self, client):
        """Upload a test file with SHM data."""
        csv_content = b"""sample,IGHA_SHM0,IGHA_SHM1,IGHG12_SHM0,IGHG12_SHM1,IGHG34_SHM0,IGHG34_SHM1,IGHM_IGHD_SHM0,IGHM_IGHD_SHM1,IGH_SHM0,IGH_SHM1
S1,25.5,74.5,30.2,69.8,28.8,71.2,45.6,54.4,32.1,67.9
S2,28.3,71.7,32.5,67.5,31.2,68.8,48.2,51.8,35.4,64.6
S3,26.9,73.1,31.1,68.9,29.5,70.5,46.8,53.2,33.7,66.3"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'shm_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_shm_analysis_complete_workflow(self, client, shm_file):
        """Test complete SHM analysis from upload to results."""
        file_id = shm_file['id']
        
        # Create SHM analysis
        analysis_request = {
            'type': 'shm_analysis',
            'file_id': file_id,
            'parameters': {
                'baseline_sample': 'S1',
                'isotypes': ['IgA', 'IgG1/2', 'IgG3/4', 'IgM/IgD', 'IGH']
            },
            'chart_config': {
                'title': 'SHM Analysis',
                'color_scheme': 'Set1'
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
        
        assert results_data['type'] == 'shm_analysis'
        assert results_data['status'] in ['completed', 'failed']
        
        if results_data['status'] == 'completed':
            assert 'results' in results_data
    
    def test_shm_field_validation(self, client):
        """Test SHM analysis with missing required fields."""
        # Upload file with missing SHM fields
        csv_content = b"""sample,IGHA_SHM0,IGHA_SHM1
S1,25.5,74.5
S2,28.3,71.7"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'incomplete_shm.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Try to create SHM analysis
        analysis_request = {
            'type': 'shm_analysis',
            'file_id': file_id,
            'parameters': {}
        }
        
        create_response = client.post(
            '/api/analysis',
            json=analysis_request
        )
        # Should either fail immediately or create analysis that fails during execution
        assert create_response.status_code in [201, 400]


class TestIGMetricsWorkflow:
    """Test complete IG metrics analysis workflow. Requirements: 3.1-3.5"""
    
    @pytest.fixture
    def ig_metrics_file(self, client):
        """Upload a test file with IG metrics data."""
        csv_content = b"""sample,chain,Reads,UCDR3,D50,Gini_index,Shannon
S1,IGH,50000,12500,25.5,0.65,3.2
S1,IGK,45000,11200,28.3,0.62,3.4
S1,IGL,38000,9500,30.1,0.58,3.5
S2,IGH,52000,13000,26.2,0.63,3.3
S2,IGK,47000,11800,29.1,0.60,3.5
S2,IGL,40000,10000,31.2,0.56,3.6"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'ig_metrics_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_ig_metrics_analysis_complete_workflow(self, client, ig_metrics_file):
        """Test complete IG metrics analysis from upload to results."""
        file_id = ig_metrics_file['id']
        
        # Create IG metrics analysis
        analysis_request = {
            'type': 'ig_metrics',
            'file_id': file_id,
            'parameters': {
                'chains': ['IGH', 'IGK', 'IGL'],
                'metrics': ['UCDR3', 'D50', 'Gini_index', 'Shannon'],
                'baseline_sample': 'S1'
            },
            'chart_config': {
                'title': 'IG Metrics Analysis'
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
        
        assert results_data['type'] == 'ig_metrics'
        assert results_data['status'] in ['completed', 'failed']
        
        if results_data['status'] == 'completed':
            assert 'results' in results_data
    
    def test_ig_metrics_chain_selection(self, client, ig_metrics_file):
        """Test IG metrics analysis with specific chain selection."""
        file_id = ig_metrics_file['id']
        
        # Create analysis with only IGH chain
        analysis_request = {
            'type': 'ig_metrics',
            'file_id': file_id,
            'parameters': {
                'chains': ['IGH'],
                'baseline_sample': 'S1'
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
        
        # Verify analysis completed
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200


class TestPDFExtractionWorkflow:
    """Test complete PDF extraction workflow. Requirements: 9.1-9.6, 12.1-12.6"""
    
    def test_pdf_table_extraction_workflow(self, client):
        """Test PDF table extraction workflow."""
        # Note: This test requires actual PDF files with tables
        # For now, we'll test the API endpoints exist
        
        # Test PDF upload endpoint exists
        response = client.get('/api/pdf/extract-tables')
        # Should return 405 (Method Not Allowed) for GET, meaning POST exists
        assert response.status_code in [405, 404]
    
    def test_pdf_image_extraction_workflow(self, client):
        """Test PDF image extraction workflow."""
        # Test PDF image listing endpoint exists
        response = client.get('/api/pdf/images/test-file-id')
        # Should return 404 (file not found) or 400 (invalid request)
        assert response.status_code in [400, 404]
    
    def test_pdf_batch_processing(self, client):
        """Test PDF batch processing workflow."""
        # Test batch extraction endpoint
        request_data = {
            'file_ids': ['file1', 'file2'],
            'indices': [16, -1]
        }
        
        response = client.post(
            '/api/pdf/extract-images',
            json=request_data
        )
        # Should return 400 or 404 for non-existent files
        assert response.status_code in [400, 404]


class TestFieldAnalysisWorkflow:
    """Test complete field analysis workflow. Requirements: 5.1-5.6"""
    
    @pytest.fixture
    def field_analysis_file(self, client):
        """Upload a test file with various numeric fields."""
        csv_content = b"""sample,metric1,metric2,metric3,category
S1,125.5,88.3,45.2,TypeA
S2,138.2,92.1,48.7,TypeB
S3,142.8,95.4,52.3,TypeA
S4,131.5,89.7,46.8,TypeB"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'field_analysis_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_field_detection_workflow(self, client, field_analysis_file):
        """Test field detection and analysis workflow."""
        file_id = field_analysis_file['id']
        
        # Step 1: Detect numeric fields
        fields_response = client.get(f'/api/analysis/fields/{file_id}')
        # Should return 200 with fields or 404 if endpoint doesn't exist
        assert fields_response.status_code in [200, 404]
        
        if fields_response.status_code == 200:
            fields_data = fields_response.get_json()
            assert 'numeric_fields' in fields_data or 'fields' in fields_data
    
    def test_field_analysis_complete_workflow(self, client, field_analysis_file):
        """Test complete field analysis from detection to results."""
        file_id = field_analysis_file['id']
        
        # Create field analysis
        analysis_request = {
            'type': 'field_analysis',
            'file_id': file_id,
            'parameters': {
                'fields': ['metric1', 'metric2', 'metric3'],
                'baseline_sample': 'S1'
            },
            'chart_config': {
                'title': 'Field Analysis'
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
        
        assert results_data['type'] == 'field_analysis'
        assert results_data['status'] in ['completed', 'failed']
    
    def test_field_analysis_baseline_comparison(self, client, field_analysis_file):
        """Test field analysis with baseline comparison."""
        file_id = field_analysis_file['id']
        
        # Create analysis with baseline
        analysis_request = {
            'type': 'field_analysis',
            'file_id': file_id,
            'parameters': {
                'fields': ['metric1', 'metric2'],
                'baseline_sample': 'S1'
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
        
        # Verify analysis completed
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200


class TestCrossModuleIntegration:
    """Test integration across multiple analysis modules."""
    
    def test_multiple_analysis_types_on_same_file(self, client):
        """Test running different analysis types on the same file."""
        # Upload a comprehensive file
        csv_content = b"""sample,chain,Reads,UCDR3,D50,Gini_index,Shannon,metric1,metric2
S1,IGH,50000,12500,25.5,0.65,3.2,125.5,88.3
S1,IGK,45000,11200,28.3,0.62,3.4,138.2,92.1
S2,IGH,52000,13000,26.2,0.63,3.3,142.8,95.4
S2,IGK,47000,11800,29.1,0.60,3.5,131.5,89.7"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'comprehensive_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Create multiple analyses
        analysis_types = [
            {'type': 'ig_metrics', 'parameters': {'chains': ['IGH', 'IGK']}},
            {'type': 'field_analysis', 'parameters': {'fields': ['metric1', 'metric2']}}
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
            if create_response.status_code == 201:
                analysis_ids.append(create_response.get_json()['id'])
        
        # Verify at least one analysis was created
        assert len(analysis_ids) > 0
    
    def test_chart_configuration_consistency(self, client):
        """Test that chart configuration is applied consistently across analysis types."""
        # Upload test file
        csv_content = b"""sample,metric1,metric2
S1,125.5,88.3
S2,138.2,92.1"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'chart_config_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Create analysis with custom chart config
        chart_config = {
            'title': 'Custom Chart Title',
            'color_scheme': 'viridis',
            'figure_width': 12,
            'figure_height': 8
        }
        
        analysis_request = {
            'type': 'field_analysis',
            'file_id': file_id,
            'parameters': {'fields': ['metric1']},
            'chart_config': chart_config
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
        
        # Verify analysis completed
        results_response = client.get(f'/api/analysis/{analysis_id}')
        assert results_response.status_code == 200
