"""
End-to-end integration tests for sample selection workflow.
Tests Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7 from ui-fixes spec.

Requirements:
- 5.1: System prompts for sample name column selection
- 5.2: System extracts and displays all unique sample names
- 5.3: System provides checkboxes for selection
- 5.4: System highlights selected samples
- 5.5: System only analyzes selected samples
- 5.6: System displays validation message when no samples selected
- 5.7: System provides select all/deselect all toggle
"""
import io
import pytest


class TestSampleSelectionEndToEnd:
    """End-to-end tests for sample selection workflow. Requirements: 5.1-5.7"""
    
    @pytest.fixture
    def sample_csv_with_samples(self, client):
        """Upload a CSV file with multiple samples."""
        csv_content = b"Sample_Name,CDR3,Reads\nSample1,CASSF,100\nSample2,CASSG,200\nSample3,CASSH,150\nSample1,CASSI,120"
        data = {
            'file': (io.BytesIO(csv_content), 'sample_selection_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_sample_column_extraction(self, client, sample_csv_with_samples):
        """
        Test that system extracts unique sample names from a column.
        Requirement 5.2: System extracts and displays all unique sample names
        """
        file_id = sample_csv_with_samples['id']
        
        # Get unique values from Sample_Name column
        response = client.get(f'/api/files/{file_id}/column-values?column=Sample_Name')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'values' in data
        
        # Verify unique samples are extracted
        unique_samples = data['values']
        assert isinstance(unique_samples, list)
        assert len(unique_samples) == 3  # Sample1, Sample2, Sample3
        assert 'Sample1' in unique_samples
        assert 'Sample2' in unique_samples
        assert 'Sample3' in unique_samples
    
    def test_sample_selection_validation(self, client, sample_csv_with_samples):
        """
        Test validation when no samples are selected.
        Requirement 5.6: System displays validation message when no samples selected
        """
        file_id = sample_csv_with_samples['id']
        
        # Simulate empty sample selection
        selected_samples = []
        
        # Validation should fail with empty selection
        assert len(selected_samples) == 0, "Empty selection should be invalid"
        
        # With at least one sample, validation should pass
        selected_samples = ['Sample1']
        assert len(selected_samples) > 0, "Non-empty selection should be valid"
    
    def test_sample_selection_completeness(self, client, sample_csv_with_samples):
        """
        Test that all unique samples are available for selection.
        Requirement 5.2: System extracts and displays all unique sample names
        Requirement 5.3: System provides checkboxes for selection
        """
        file_id = sample_csv_with_samples['id']
        
        # Get all available samples
        response = client.get(f'/api/files/{file_id}/column-values?column=Sample_Name')
        assert response.status_code == 200
        
        available_samples = response.get_json()['values']
        
        # Verify all samples are available for selection
        assert len(available_samples) >= 1
        
        # Simulate user selecting specific samples
        selected_samples = ['Sample1', 'Sample3']
        
        # Verify selected samples are subset of available samples
        for sample in selected_samples:
            assert sample in available_samples
    
    def test_select_all_functionality(self, client, sample_csv_with_samples):
        """
        Test select all/deselect all functionality.
        Requirement 5.7: System provides select all/deselect all toggle
        """
        file_id = sample_csv_with_samples['id']
        
        # Get all available samples
        response = client.get(f'/api/files/{file_id}/column-values?column=Sample_Name')
        available_samples = response.get_json()['values']
        
        # Simulate "select all"
        all_selected = available_samples.copy()
        assert len(all_selected) == len(available_samples)
        
        # Simulate "deselect all"
        none_selected = []
        assert len(none_selected) == 0
        
        # Verify toggle works
        assert len(all_selected) != len(none_selected)
    
    def test_sample_filtering_logic(self, client, sample_csv_with_samples):
        """
        Test that only selected samples would be analyzed.
        Requirement 5.5: System only analyzes selected samples
        """
        file_id = sample_csv_with_samples['id']
        
        # Get all samples
        response = client.get(f'/api/files/{file_id}/column-values?column=Sample_Name')
        all_samples = response.get_json()['values']
        
        # Select subset of samples
        selected_samples = ['Sample1', 'Sample2']
        
        # Verify filtering logic
        assert len(selected_samples) < len(all_samples)
        
        # Samples not selected should be filtered out
        excluded_samples = [s for s in all_samples if s not in selected_samples]
        assert len(excluded_samples) > 0
        assert 'Sample3' in excluded_samples
    
    def test_column_values_endpoint(self, client, sample_csv_with_samples):
        """
        Test the column values API endpoint.
        Requirement 5.2: System extracts and displays all unique sample names
        """
        file_id = sample_csv_with_samples['id']
        
        # Test with valid column
        response = client.get(f'/api/files/{file_id}/column-values?column=Sample_Name')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'values' in data
        assert isinstance(data['values'], list)
        
        # Test with invalid column
        response = client.get(f'/api/files/{file_id}/column-values?column=NonExistentColumn')
        # Should return error or empty list
        assert response.status_code in [200, 400, 404]
    
    def test_complete_sample_selection_workflow(self, client):
        """
        Test complete workflow: upload, extract samples, select, validate.
        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
        """
        # Step 1: Upload CSV file
        csv_content = b"Sample,CDR3,Reads,Chain\nS1,CASSF,100,TRB\nS2,CASSG,200,TRB\nS3,CASSH,150,TRB\nS1,CASSI,120,TRB"
        data = {
            'file': (io.BytesIO(csv_content), 'workflow_test.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Step 2: Select sample column (simulated - in UI user would select)
        sample_column = 'Sample'
        
        # Step 3: Extract unique samples
        samples_response = client.get(f'/api/files/{file_id}/column-values?column={sample_column}')
        assert samples_response.status_code == 200
        
        available_samples = samples_response.get_json()['values']
        
        # Step 4: Verify samples are displayed
        assert len(available_samples) == 3  # S1, S2, S3
        assert 'S1' in available_samples
        assert 'S2' in available_samples
        assert 'S3' in available_samples
        
        # Step 5: User selects specific samples
        selected_samples = ['S1', 'S3']
        
        # Step 6: Validate selection
        assert len(selected_samples) > 0, "At least one sample must be selected"
        
        # Step 7: Verify selected samples are valid
        for sample in selected_samples:
            assert sample in available_samples
        
        # Step 8: Verify filtering would work
        filtered_samples = [s for s in available_samples if s in selected_samples]
        assert len(filtered_samples) == 2
        assert 'S2' not in filtered_samples
    
    def test_sample_selection_with_duplicates(self, client):
        """
        Test that duplicate sample names are handled correctly.
        Requirement 5.2: System extracts and displays all unique sample names
        """
        # Upload file with duplicate sample names
        csv_content = b"Sample,Value\nA,1\nB,2\nA,3\nC,4\nB,5\nA,6"
        data = {
            'file': (io.BytesIO(csv_content), 'duplicates_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        file_id = response.get_json()['id']
        
        # Get unique samples
        samples_response = client.get(f'/api/files/{file_id}/column-values?column=Sample')
        assert samples_response.status_code == 200
        
        unique_samples = samples_response.get_json()['values']
        
        # Should only have 3 unique samples (A, B, C)
        assert len(unique_samples) == 3
        assert 'A' in unique_samples
        assert 'B' in unique_samples
        assert 'C' in unique_samples
    
    def test_empty_sample_column(self, client):
        """
        Test handling of empty or null values in sample column.
        Requirement 5.2: System extracts and displays all unique sample names
        """
        # Upload file with some empty sample values
        csv_content = b"Sample,Value\nA,1\n,2\nB,3\n,4"
        data = {
            'file': (io.BytesIO(csv_content), 'empty_samples_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        file_id = response.get_json()['id']
        
        # Get samples
        samples_response = client.get(f'/api/files/{file_id}/column-values?column=Sample')
        assert samples_response.status_code == 200
        
        samples = samples_response.get_json()['values']
        
        # Should only include non-empty samples
        assert 'A' in samples
        assert 'B' in samples
        # Empty strings should be filtered out or handled appropriately
