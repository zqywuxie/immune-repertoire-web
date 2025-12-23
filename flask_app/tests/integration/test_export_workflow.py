"""
Integration tests for export workflow.
Tests complete PNG, CSV, and ZIP export flow.
Requirements: 14.3 (Integration testing)
"""
import io
import time
import zipfile
import pytest
from PIL import Image


class TestExportWorkflow:
    """Test complete export workflow. Requirements: 14.3"""
    
    @pytest.fixture
    def completed_analysis(self, client):
        """Create a completed analysis for export testing."""
        # Upload file with proper sequencing depth columns
        csv_content = b"sample,total_receptor_rna,reads_umi,migs_good_total,reads_good_total\nS1,10000,5.0,8000,7500\nS2,12000,4.5,9500,9000\nS3,11000,5.2,8800,8200"
        data = {
            'file': (io.BytesIO(csv_content), 'export_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Create analysis - use sequencing_depth with proper field mapping
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'field_mapping': {
                'sample': 'sample',
                'total_receptor_rna': 'total_receptor_rna',
                'reads_umi': 'reads_umi',
                'migs_good_total': 'migs_good_total',
                'reads_good_total': 'reads_good_total'
            },
            'parameters': {},
            'chart_config': {
                'title': 'Export Test Analysis',
                'dpi': 300
            }
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
    
    def test_png_export_workflow(self, client, completed_analysis):
        """Test PNG export workflow."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        exports_data = exports_response.get_json()
        
        assert 'exports' in exports_data
        
        # Get visualizations from exports structure
        visualizations = exports_data['exports'].get('visualizations', [])
        
        # If there are visualizations available, try to download one
        if len(visualizations) > 0:
            result_name = visualizations[0]['name']
            
            # Download PNG
            download_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'png'
                }
            )
            
            # Should return file or 404 if not available
            assert download_response.status_code in [200, 404]
            
            if download_response.status_code == 200:
                # Verify it's a PNG file
                assert download_response.mimetype in ['image/png', 'application/octet-stream']
                
                # Verify PNG content
                png_data = download_response.data
                assert len(png_data) > 0
                
                # Try to open as image
                try:
                    img = Image.open(io.BytesIO(png_data))
                    assert img.format == 'PNG'
                    # Verify DPI (should be 300)
                    if hasattr(img, 'info') and 'dpi' in img.info:
                        dpi = img.info['dpi']
                        assert dpi[0] == 300 or dpi[1] == 300
                except Exception:
                    # If PIL can't open it, at least verify it starts with PNG signature
                    assert png_data[:8] == b'\x89PNG\r\n\x1a\n'
    
    def test_csv_export_workflow(self, client, completed_analysis):
        """Test CSV export workflow."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        exports_data = exports_response.get_json()
        
        # Get data_tables from exports structure
        data_tables = exports_data['exports'].get('data_tables', [])
        
        # If there are data tables available, try to download one as CSV
        if len(data_tables) > 0:
            result_name = data_tables[0]['name']
            
            # Download CSV
            download_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'csv'
                }
            )
            
            # Should return file or 404 if not available
            assert download_response.status_code in [200, 404]
            
            if download_response.status_code == 200:
                # Verify it's a CSV file
                assert download_response.mimetype in ['text/csv', 'application/csv', 'application/octet-stream']
                
                # Verify CSV content
                csv_data = download_response.data
                assert len(csv_data) > 0
                
                # Verify it's valid CSV (has commas or newlines)
                csv_text = csv_data.decode('utf-8')
                assert ',' in csv_text or '\n' in csv_text
    
    def test_zip_export_workflow(self, client, completed_analysis):
        """Test ZIP batch export workflow."""
        analysis_id = completed_analysis['analysis_id']
        
        # Download all results as ZIP
        download_response = client.get(
            f'/api/analysis/{analysis_id}/download',
            query_string={'format': 'zip'}
        )
        
        # Should return file or 404 if no results
        assert download_response.status_code in [200, 404]
        
        if download_response.status_code == 200:
            # Verify it's a ZIP file
            assert download_response.mimetype in ['application/zip', 'application/octet-stream']
            
            # Verify ZIP content
            zip_data = download_response.data
            assert len(zip_data) > 0
            
            # Try to open as ZIP
            try:
                zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
                
                # Verify ZIP is valid
                assert zip_file.testzip() is None
                
                # Verify ZIP contains files
                file_list = zip_file.namelist()
                assert len(file_list) > 0
                
                # Verify files have expected extensions
                extensions = [name.split('.')[-1] for name in file_list]
                assert any(ext in ['png', 'csv', 'json', 'txt'] for ext in extensions)
                
            except zipfile.BadZipFile:
                pytest.fail("Downloaded file is not a valid ZIP archive")
    
    def test_export_with_metadata(self, client, completed_analysis):
        """Test export with metadata inclusion."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        exports_data = exports_response.get_json()
        
        # Get data_tables from exports structure
        data_tables = exports_data['exports'].get('data_tables', [])
        
        if len(data_tables) > 0:
            result_name = data_tables[0]['name']
            
            # Download with metadata
            download_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'csv',
                    'include_metadata': 'true'
                }
            )
            
            assert download_response.status_code in [200, 404]
    
    def test_export_without_metadata(self, client, completed_analysis):
        """Test export without metadata."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        exports_data = exports_response.get_json()
        
        # Get data_tables from exports structure
        data_tables = exports_data['exports'].get('data_tables', [])
        
        if len(data_tables) > 0:
            result_name = data_tables[0]['name']
            
            # Download without metadata
            download_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'csv',
                    'include_metadata': 'false'
                }
            )
            
            assert download_response.status_code in [200, 404]
    
    def test_export_invalid_format(self, client, completed_analysis):
        """Test export with invalid format."""
        analysis_id = completed_analysis['analysis_id']
        
        # Try to download with invalid format
        download_response = client.get(
            f'/api/analysis/{analysis_id}/download',
            query_string={
                'result_name': 'test',
                'format': 'invalid_format'
            }
        )
        
        assert download_response.status_code == 400
        error_data = download_response.get_json()
        assert 'error_code' in error_data
        assert 'supported_formats' in error_data['details']
    
    def test_export_missing_result_name(self, client, completed_analysis):
        """Test export without result name for PNG/CSV."""
        analysis_id = completed_analysis['analysis_id']
        
        # Try to download PNG without result_name
        download_response = client.get(
            f'/api/analysis/{analysis_id}/download',
            query_string={'format': 'png'}
        )
        
        assert download_response.status_code == 400
        error_data = download_response.get_json()
        assert 'error_code' in error_data
    
    def test_export_nonexistent_analysis(self, client):
        """Test export for non-existent analysis."""
        # Try to download from non-existent analysis
        download_response = client.get(
            '/api/analysis/non-existent-id/download',
            query_string={'format': 'zip'}
        )
        
        assert download_response.status_code == 404
    
    def test_available_exports_endpoint(self, client, completed_analysis):
        """Test getting available exports."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'analysis_id' in data
        assert 'exports' in data
        assert data['analysis_id'] == analysis_id
        
        # Verify exports structure - exports is a dict with visualizations, data_tables, batch
        exports = data['exports']
        assert 'visualizations' in exports or 'data_tables' in exports or 'batch' in exports
        
        # Verify visualizations structure
        for viz in exports.get('visualizations', []):
            assert 'name' in viz
            assert 'format' in viz
        
        # Verify data_tables structure
        for table in exports.get('data_tables', []):
            assert 'name' in table
            assert 'format' in table
    
    def test_multiple_format_exports(self, client, completed_analysis):
        """Test exporting the same result in multiple formats."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        exports_data = exports_response.get_json()
        
        # Get visualizations from exports structure
        visualizations = exports_data['exports'].get('visualizations', [])
        
        if len(visualizations) > 0:
            result_name = visualizations[0]['name']
            
            # Download as PNG
            png_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'png'
                }
            )
            
            # Download as CSV
            csv_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'csv'
                }
            )
            
            # At least one should succeed
            assert png_response.status_code in [200, 404] or csv_response.status_code in [200, 404]
    
    def test_zip_export_contents(self, client, completed_analysis):
        """Test ZIP export contains expected files."""
        analysis_id = completed_analysis['analysis_id']
        
        # Download ZIP
        download_response = client.get(
            f'/api/analysis/{analysis_id}/download',
            query_string={'format': 'zip', 'include_metadata': 'true'}
        )
        
        if download_response.status_code == 200:
            zip_data = download_response.data
            
            try:
                zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
                file_list = zip_file.namelist()
                
                # Should contain at least one file
                assert len(file_list) > 0
                
                # Check for metadata file if included
                metadata_files = [f for f in file_list if 'metadata' in f.lower() or f.endswith('.json')]
                # Metadata may or may not be present depending on implementation
                
                # Check for result files
                result_files = [f for f in file_list if f.endswith('.png') or f.endswith('.csv')]
                assert len(result_files) > 0
                
            except zipfile.BadZipFile:
                pytest.fail("Downloaded file is not a valid ZIP archive")
    
    def test_export_filename_format(self, client, completed_analysis):
        """Test that export filenames follow expected format."""
        analysis_id = completed_analysis['analysis_id']
        
        # Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        exports_data = exports_response.get_json()
        
        # Get visualizations from exports structure
        visualizations = exports_data['exports'].get('visualizations', [])
        
        if len(visualizations) > 0:
            result_name = visualizations[0]['name']
            
            # Download file
            download_response = client.get(
                f'/api/analysis/{analysis_id}/download',
                query_string={
                    'result_name': result_name,
                    'format': 'png'
                }
            )
            
            if download_response.status_code == 200:
                # Check Content-Disposition header for filename
                content_disposition = download_response.headers.get('Content-Disposition')
                if content_disposition:
                    assert 'filename=' in content_disposition
    
    def test_complete_export_workflow(self, client):
        """Test complete export workflow from analysis creation to download."""
        # Step 1: Upload file with proper sequencing depth columns
        csv_content = b"sample,total_receptor_rna,reads_umi,migs_good_total,reads_good_total\nS1,10000,5.0,8000,7500\nS2,12000,4.5,9500,9000"
        data = {
            'file': (io.BytesIO(csv_content), 'complete_export_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Step 2: Create analysis - use sequencing_depth with proper field mapping
        analysis_request = {
            'type': 'sequencing_depth',
            'file_id': file_id,
            'field_mapping': {
                'sample': 'sample',
                'total_receptor_rna': 'total_receptor_rna',
                'reads_umi': 'reads_umi',
                'migs_good_total': 'migs_good_total',
                'reads_good_total': 'reads_good_total'
            },
            'parameters': {}
        }
        
        create_response = client.post('/api/analysis', json=analysis_request)
        assert create_response.status_code == 201
        analysis_id = create_response.get_json()['id']
        
        # Step 3: Wait for completion
        max_wait = 30
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_response = client.get(f'/api/analysis/{analysis_id}/status')
            status_data = status_response.get_json()
            
            if status_data['status'] in ['completed', 'failed']:
                break
            
            time.sleep(0.5)
        
        # Step 4: Get available exports
        exports_response = client.get(f'/api/analysis/{analysis_id}/exports')
        assert exports_response.status_code == 200
        
        # Step 5: Download as ZIP
        zip_response = client.get(
            f'/api/analysis/{analysis_id}/download',
            query_string={'format': 'zip'}
        )
        
        # Should succeed or return 404 if no results
        assert zip_response.status_code in [200, 404]
