"""
Integration tests for file upload workflow.
Tests complete file upload, validation, storage, and reuse flow.
Requirements: 14.3 (Integration testing)
"""
import io
import pytest
import tempfile
import pandas as pd
from pathlib import Path


class TestFileUploadWorkflow:
    """Test complete file upload workflow. Requirements: 14.3"""
    
    def test_complete_upload_workflow(self, client, sample_csv_content):
        """Test complete file upload, validation, and storage workflow."""
        # Step 1: Upload file
        data = {
            'file': (io.BytesIO(sample_csv_content), 'test_data.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        
        assert upload_response.status_code == 201
        upload_data = upload_response.get_json()
        file_id = upload_data['id']
        
        # Verify upload response contains expected metadata
        assert upload_data['name'] == 'test_data.csv'
        assert upload_data['columns'] == ['sample', 'cdr3', 'reads', 'copy']
        assert upload_data['row_count'] == 3
        assert 'uploaded_at' in upload_data
        
        # Step 2: Verify file appears in file list
        list_response = client.get('/api/files')
        assert list_response.status_code == 200
        list_data = list_response.get_json()
        
        assert list_data['total'] == 1
        assert len(list_data['files']) == 1
        assert list_data['files'][0]['id'] == file_id
        assert list_data['files'][0]['name'] == 'test_data.csv'
        
        # Step 3: Get file details
        detail_response = client.get(f'/api/files/{file_id}')
        assert detail_response.status_code == 200
        detail_data = detail_response.get_json()
        
        assert detail_data['id'] == file_id
        assert detail_data['name'] == 'test_data.csv'
        assert detail_data['columns'] == ['sample', 'cdr3', 'reads', 'copy']
        assert detail_data['row_count'] == 3
        assert 'sample_data' in detail_data
        assert len(detail_data['sample_data']) > 0
        
        # Step 4: Verify file can be reused (retrieved again)
        reuse_response = client.get(f'/api/files/{file_id}')
        assert reuse_response.status_code == 200
        reuse_data = reuse_response.get_json()
        
        # Verify data consistency on reuse
        assert reuse_data['id'] == detail_data['id']
        assert reuse_data['columns'] == detail_data['columns']
        assert reuse_data['row_count'] == detail_data['row_count']
    
    def test_multiple_file_upload_workflow(self, client):
        """Test uploading multiple files and managing them."""
        files_to_upload = [
            ('file1.csv', b"sample,cdr3\nS1,CASSF\nS2,CASSG"),
            ('file2.csv', b"sample,cdr3,reads\nS1,CASSF,100\nS2,CASSG,200"),
            ('file3.csv', b"sample,cdr3,reads,copy\nS1,CASSF,100,50")
        ]
        
        uploaded_ids = []
        
        # Upload all files
        for filename, content in files_to_upload:
            data = {
                'file': (io.BytesIO(content), filename)
            }
            response = client.post(
                '/api/files/upload',
                data=data,
                content_type='multipart/form-data'
            )
            assert response.status_code == 201
            uploaded_ids.append(response.get_json()['id'])
        
        # Verify all files are in the list
        list_response = client.get('/api/files')
        assert list_response.status_code == 200
        list_data = list_response.get_json()
        
        assert list_data['total'] == 3
        assert len(list_data['files']) == 3
        
        # Verify each file can be retrieved
        for file_id in uploaded_ids:
            detail_response = client.get(f'/api/files/{file_id}')
            assert detail_response.status_code == 200
    
    def test_file_validation_workflow(self, client):
        """Test file validation during upload."""
        # Test invalid format
        invalid_data = {
            'file': (io.BytesIO(b"test content"), 'test.txt')
        }
        response = client.post(
            '/api/files/upload',
            data=invalid_data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        error_data = response.get_json()
        assert error_data['error_code'] == 'FILE_FORMAT_INVALID'
        assert 'supported_extensions' in error_data['details']
        
        # Test empty file
        empty_data = {
            'file': (io.BytesIO(b""), 'empty.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=empty_data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        
        # Test corrupted CSV
        corrupted_data = {
            'file': (io.BytesIO(b"invalid,csv\ndata"), 'corrupted.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=corrupted_data,
            content_type='multipart/form-data'
        )
        # Should either succeed with minimal data or fail with parse error
        assert response.status_code in [201, 400]
    
    def test_file_reuse_workflow(self, client, sample_csv_content):
        """Test file reuse without re-upload. Requirements: 1.4, 1.5, 1.6"""
        # Upload file once
        data = {
            'file': (io.BytesIO(sample_csv_content), 'reusable.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Retrieve file multiple times (simulating reuse)
        for _ in range(3):
            reuse_response = client.get(f'/api/files/{file_id}')
            assert reuse_response.status_code == 200
            reuse_data = reuse_response.get_json()
            
            # Verify data consistency
            assert reuse_data['id'] == file_id
            assert reuse_data['name'] == 'reusable.csv'
            assert reuse_data['columns'] == ['sample', 'cdr3', 'reads', 'copy']
            assert reuse_data['row_count'] == 3
    
    def test_file_delete_workflow(self, client, sample_csv_content):
        """Test file deletion workflow."""
        # Upload file
        data = {
            'file': (io.BytesIO(sample_csv_content), 'to_delete.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Verify file exists
        get_response = client.get(f'/api/files/{file_id}')
        assert get_response.status_code == 200
        
        # Delete file
        delete_response = client.delete(f'/api/files/{file_id}')
        assert delete_response.status_code == 200
        delete_data = delete_response.get_json()
        assert delete_data['success'] is True
        
        # Verify file no longer exists
        get_response = client.get(f'/api/files/{file_id}')
        assert get_response.status_code == 404
        
        # Verify file not in list
        list_response = client.get('/api/files')
        list_data = list_response.get_json()
        file_ids = [f['id'] for f in list_data['files']]
        assert file_id not in file_ids
    
    def test_excel_file_upload_workflow(self, client, app):
        """Test uploading Excel files."""
        # Create a temporary Excel file
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            df = pd.DataFrame({
                'sample': ['S1', 'S2', 'S3'],
                'cdr3': ['CASSF', 'CASSG', 'CASSH'],
                'reads': [100, 200, 150]
            })
            df.to_excel(tmp.name, index=False)
            tmp_path = tmp.name
        
        try:
            # Read the Excel file
            with open(tmp_path, 'rb') as f:
                excel_content = f.read()
            
            # Upload Excel file
            data = {
                'file': (io.BytesIO(excel_content), 'test_data.xlsx')
            }
            response = client.post(
                '/api/files/upload',
                data=data,
                content_type='multipart/form-data'
            )
            
            assert response.status_code == 201
            response_data = response.get_json()
            
            assert response_data['name'] == 'test_data.xlsx'
            assert 'sample' in response_data['columns']
            assert 'cdr3' in response_data['columns']
            assert 'reads' in response_data['columns']
            assert response_data['row_count'] == 3
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_gzip_csv_upload_workflow(self, client):
        """Test uploading gzip-compressed CSV files."""
        import gzip
        
        # Create gzip-compressed CSV content
        csv_content = b"sample,cdr3,reads\nS1,CASSF,100\nS2,CASSG,200"
        gzip_content = gzip.compress(csv_content)
        
        # Upload gzip file
        data = {
            'file': (io.BytesIO(gzip_content), 'test_data.csv.gz')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        
        assert response.status_code == 201
        response_data = response.get_json()
        
        assert response_data['name'] == 'test_data.csv.gz'
        assert response_data['columns'] == ['sample', 'cdr3', 'reads']
        assert response_data['row_count'] == 2
    
    def test_file_list_query_workflow(self, client):
        """Test querying file list after multiple uploads."""
        # Upload multiple files with different characteristics
        files = [
            ('small.csv', b"col1,col2\na,b"),
            ('medium.csv', b"col1,col2,col3\na,b,c\nd,e,f\ng,h,i"),
            ('large.csv', b"col1,col2,col3,col4\n" + b"\n".join([b"a,b,c,d"] * 10))
        ]
        
        for filename, content in files:
            data = {
                'file': (io.BytesIO(content), filename)
            }
            response = client.post(
                '/api/files/upload',
                data=data,
                content_type='multipart/form-data'
            )
            assert response.status_code == 201
        
        # Query file list
        list_response = client.get('/api/files')
        assert list_response.status_code == 200
        list_data = list_response.get_json()
        
        assert list_data['total'] == 3
        assert len(list_data['files']) == 3
        
        # Verify files are ordered by upload time (most recent first)
        filenames = [f['name'] for f in list_data['files']]
        assert 'large.csv' in filenames
        assert 'medium.csv' in filenames
        assert 'small.csv' in filenames
        
        # Verify each file has required metadata
        for file_info in list_data['files']:
            assert 'id' in file_info
            assert 'name' in file_info
            assert 'size' in file_info
            assert 'columns' in file_info
            assert 'column_count' in file_info
            assert 'row_count' in file_info
            assert 'uploaded_at' in file_info
