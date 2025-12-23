"""
Tests for the File Management API.
Requirements: 1.1, 1.4, 1.5, 1.6
"""
import io
import pytest


class TestFileUploadAPI:
    """Tests for file upload endpoint. Requirements: 1.1, 1.4"""
    
    def test_upload_csv_file(self, client, sample_csv_content):
        """Test uploading a CSV file."""
        data = {
            'file': (io.BytesIO(sample_csv_content), 'test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        json_data = response.get_json()
        assert 'id' in json_data
        assert json_data['name'] == 'test.csv'
        assert json_data['columns'] == ['sample', 'cdr3', 'reads', 'copy']
        assert json_data['row_count'] == 3
    
    def test_upload_no_file(self, client):
        """Test upload without file returns error."""
        response = client.post('/api/files/upload')
        assert response.status_code == 400
    
    def test_upload_invalid_format(self, client):
        """Test upload with invalid format returns error."""
        data = {
            'file': (io.BytesIO(b"test data"), 'test.txt')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        json_data = response.get_json()
        assert json_data['error_code'] == 'FILE_FORMAT_INVALID'
    
    def test_upload_empty_file(self, client):
        """Test upload with empty file returns error."""
        data = {
            'file': (io.BytesIO(b""), 'test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400


class TestFileListAPI:
    """Tests for file list endpoint. Requirements: 1.5"""
    
    def test_list_files_empty(self, client):
        """Test listing files when none uploaded."""
        response = client.get('/api/files')
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['files'] == []
        assert json_data['total'] == 0
    
    def test_list_files_after_upload(self, client, sample_csv_content):
        """Test listing files after upload."""
        # Upload a file first
        data = {
            'file': (io.BytesIO(sample_csv_content), 'test.csv')
        }
        client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        
        # List files
        response = client.get('/api/files')
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['total'] == 1
        assert len(json_data['files']) == 1
        assert json_data['files'][0]['name'] == 'test.csv'


class TestFileDetailAPI:
    """Tests for file detail endpoint. Requirements: 1.5, 1.6"""
    
    def test_get_file_not_found(self, client):
        """Test getting non-existent file returns 404."""
        response = client.get('/api/files/nonexistent-id')
        assert response.status_code == 404
        json_data = response.get_json()
        assert json_data['error_code'] == 'FILE_NOT_FOUND'
    
    def test_get_file_details(self, client, sample_csv_content):
        """Test getting file details after upload."""
        # Upload a file first
        data = {
            'file': (io.BytesIO(sample_csv_content), 'test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Get file details
        response = client.get(f'/api/files/{file_id}')
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['id'] == file_id
        assert json_data['name'] == 'test.csv'
        assert 'sample_data' in json_data


class TestFileDeleteAPI:
    """Tests for file delete endpoint. Requirements: 1.6"""
    
    def test_delete_file_not_found(self, client):
        """Test deleting non-existent file returns 404."""
        response = client.delete('/api/files/nonexistent-id')
        assert response.status_code == 404
    
    def test_delete_file(self, client, sample_csv_content):
        """Test deleting an uploaded file."""
        # Upload a file first
        data = {
            'file': (io.BytesIO(sample_csv_content), 'test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        file_id = upload_response.get_json()['id']
        
        # Delete the file
        response = client.delete(f'/api/files/{file_id}')
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        
        # Verify file is deleted
        response = client.get(f'/api/files/{file_id}')
        assert response.status_code == 404
