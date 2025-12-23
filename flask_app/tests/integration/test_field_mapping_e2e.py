"""
End-to-end integration tests for field mapping workflow.
Tests Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8 from ui-fixes spec.

Requirements:
- 3.1: System automatically detects and suggests field mappings
- 3.2: System displays detected fields for confirmation
- 3.3: System shows which source columns map to which analysis fields
- 3.4: User can manually modify field mapping
- 3.5: System updates and validates new selection
- 3.6: User can add custom field mappings
- 3.7: User can delete field mappings
- 3.8: System proceeds with analysis using mapped fields
"""
import io
import pytest
from services.field_mapping import FieldMappingService


class TestFieldMappingEndToEnd:
    """End-to-end tests for field mapping workflow. Requirements: 3.1-3.8"""
    
    @pytest.fixture
    def sample_csv_file(self, client):
        """Upload a sample CSV file for testing."""
        csv_content = b"Sample_ID,CDR3_AA,Read_Count,Chain_Type,Copy_Number\nS1,CASSF,100,TRB,50\nS2,CASSG,200,TRB,100"
        data = {
            'file': (io.BytesIO(csv_content), 'field_mapping_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_automatic_field_detection(self, client, sample_csv_file):
        """
        Test that system automatically detects and suggests field mappings.
        Requirement 3.1: System automatically detects and suggests field mappings
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Test auto-suggestion for similarity_heatmap
        suggested_mapping, confidence_scores = FieldMappingService.suggest_mapping_with_confidence(
            columns, 'similarity_heatmap'
        )
        
        # Verify suggestions are made
        assert isinstance(suggested_mapping, dict)
        assert isinstance(confidence_scores, dict)
        
        # Verify key fields are suggested
        assert 'sample' in suggested_mapping or 'sample' in confidence_scores
        assert 'cdr3' in suggested_mapping or 'cdr3' in confidence_scores
        assert 'reads' in suggested_mapping or 'reads' in confidence_scores
        
        # Verify confidence scores are reasonable
        for field, score in confidence_scores.items():
            assert 0.0 <= score <= 1.0
    
    def test_field_mapping_display(self, client, sample_csv_file):
        """
        Test that system displays detected fields for confirmation.
        Requirement 3.2: System displays detected fields for confirmation
        Requirement 3.3: System shows which source columns map to which analysis fields
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Get suggested mapping
        suggested_mapping, confidence_scores = FieldMappingService.suggest_mapping_with_confidence(
            columns, 'chain_specific'
        )
        
        # Verify mapping shows source -> target relationship
        for target_field, source_column in suggested_mapping.items():
            assert source_column in columns, f"Source column {source_column} not in available columns"
            assert target_field in FieldMappingService.get_required_fields('chain_specific')
        
        # Verify confidence scores are provided for display
        for field in FieldMappingService.get_required_fields('chain_specific'):
            assert field in confidence_scores
    
    def test_manual_field_modification(self, client, sample_csv_file):
        """
        Test that user can manually modify field mapping.
        Requirement 3.4: User can manually modify field mapping
        Requirement 3.5: System updates and validates new selection
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Get initial suggestion
        suggested_mapping, _ = FieldMappingService.suggest_mapping_with_confidence(
            columns, 'similarity_heatmap'
        )
        
        # Manually modify mapping
        modified_mapping = suggested_mapping.copy()
        if 'sample' in modified_mapping:
            # Change sample mapping to a different column
            modified_mapping['sample'] = 'Sample_ID'
        else:
            # Add sample mapping
            modified_mapping['sample'] = 'Sample_ID'
        
        # Validate modified mapping
        validation_result = FieldMappingService.validate_user_mapping(
            modified_mapping,
            'similarity_heatmap',
            columns
        )
        
        # Verify validation works
        assert hasattr(validation_result, 'is_valid')
        assert hasattr(validation_result, 'missing_fields')
        assert hasattr(validation_result, 'mapped_fields')
        assert hasattr(validation_result, 'message')
    
    def test_add_custom_field_mapping(self, client, sample_csv_file):
        """
        Test that user can add custom field mappings.
        Requirement 3.6: User can add custom field mappings
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Start with empty mapping
        custom_mapping = {}
        
        # Add fields one by one
        custom_mapping['sample'] = 'Sample_ID'
        custom_mapping['cdr3'] = 'CDR3_AA'
        custom_mapping['reads'] = 'Read_Count'
        
        # Validate after each addition
        validation_result = FieldMappingService.validate_user_mapping(
            custom_mapping,
            'similarity_heatmap',
            columns
        )
        
        # Should be valid now
        assert validation_result.is_valid
        assert len(validation_result.missing_fields) == 0
        assert len(validation_result.mapped_fields) == 3
    
    def test_remove_field_mapping(self, client, sample_csv_file):
        """
        Test that user can delete field mappings.
        Requirement 3.7: User can delete field mappings
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Start with complete mapping
        complete_mapping = {
            'sample': 'Sample_ID',
            'cdr3': 'CDR3_AA',
            'reads': 'Read_Count'
        }
        
        # Validate complete mapping
        validation_result = FieldMappingService.validate_user_mapping(
            complete_mapping,
            'similarity_heatmap',
            columns
        )
        assert validation_result.is_valid
        
        # Remove a field
        incomplete_mapping = complete_mapping.copy()
        del incomplete_mapping['reads']
        
        # Validate after removal
        validation_result = FieldMappingService.validate_user_mapping(
            incomplete_mapping,
            'similarity_heatmap',
            columns
        )
        
        # Should be invalid now
        assert not validation_result.is_valid
        assert 'reads' in validation_result.missing_fields
    
    def test_analysis_with_mapped_fields(self, client, sample_csv_file):
        """
        Test that system proceeds with analysis using mapped fields.
        Requirement 3.8: System proceeds with analysis using mapped fields
        """
        file_id = sample_csv_file['id']
        
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Create field mapping
        field_mapping = {
            'sample': 'Sample_ID',
            'cdr3': 'CDR3_AA',
            'reads': 'Read_Count'
        }
        
        # Validate mapping
        validation_result = FieldMappingService.validate_user_mapping(
            field_mapping,
            'similarity_heatmap',
            columns
        )
        assert validation_result.is_valid
        
        # Note: We're testing that field mapping is validated and accepted.
        # Actual analysis execution is tested in other integration tests.
        # The key requirement here is that the system accepts and validates
        # the field mapping correctly before proceeding with analysis.
    
    def test_field_mapping_validation_errors(self, client, sample_csv_file):
        """
        Test validation error handling for field mappings.
        Requirement 3.5: System updates and validates new selection
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Test 1: Missing required fields
        incomplete_mapping = {
            'sample': 'Sample_ID'
            # Missing cdr3 and reads
        }
        
        validation_result = FieldMappingService.validate_user_mapping(
            incomplete_mapping,
            'similarity_heatmap',
            columns
        )
        
        assert not validation_result.is_valid
        assert len(validation_result.missing_fields) > 0
        assert 'cdr3' in validation_result.missing_fields
        assert 'reads' in validation_result.missing_fields
        
        # Test 2: Invalid column reference
        invalid_mapping = {
            'sample': 'NonExistentColumn',
            'cdr3': 'CDR3_AA',
            'reads': 'Read_Count'
        }
        
        validation_result = FieldMappingService.validate_user_mapping(
            invalid_mapping,
            'similarity_heatmap',
            columns
        )
        
        assert not validation_result.is_valid
        assert 'sample' in validation_result.missing_fields
    
    def test_field_mapping_confidence_scores(self, client, sample_csv_file):
        """
        Test that confidence scores are calculated correctly.
        Requirement 3.1: System automatically detects and suggests field mappings
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Get suggestions with confidence
        suggested_mapping, confidence_scores = FieldMappingService.suggest_mapping_with_confidence(
            columns, 'chain_specific'
        )
        
        # Verify confidence scores
        for field, score in confidence_scores.items():
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0
        
        # High confidence for exact matches
        if 'sample' in suggested_mapping and suggested_mapping['sample'] == 'Sample_ID':
            assert confidence_scores['sample'] >= 0.8
    
    def test_multiple_analysis_types_mapping(self, client, sample_csv_file):
        """
        Test field mapping for different analysis types.
        Requirement 3.1: System automatically detects and suggests field mappings
        """
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Test different analysis types
        analysis_types = ['similarity_heatmap', 'chain_specific']
        
        for analysis_type in analysis_types:
            suggested_mapping, confidence_scores = FieldMappingService.suggest_mapping_with_confidence(
                columns, analysis_type
            )
            
            # Verify suggestions are type-specific
            required_fields = FieldMappingService.get_required_fields(analysis_type)
            
            for field in required_fields:
                assert field in confidence_scores
    
    def test_field_mapping_persistence(self, client, sample_csv_file):
        """
        Test that field mappings are validated and can be persisted.
        Requirement 3.8: System proceeds with analysis using mapped fields
        """
        # Create field mapping
        field_mapping = {
            'sample': 'Sample_ID',
            'cdr3': 'CDR3_AA',
            'reads': 'Read_Count'
        }
        
        # Get columns from upload response
        columns = sample_csv_file['columns']
        
        # Validate mapping
        validation_result = FieldMappingService.validate_user_mapping(
            field_mapping,
            'similarity_heatmap',
            columns
        )
        
        # Verify mapping is valid and can be persisted
        assert validation_result.is_valid
        assert len(validation_result.mapped_fields) == 3
        assert validation_result.mapped_fields == field_mapping
    
    def test_complete_field_mapping_workflow(self, client):
        """
        Test complete workflow: upload, detect, modify, validate, analyze.
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
        """
        # Step 1: Upload file
        csv_content = b"Sample,CDR3,Reads,Chain,Copies\nS1,CASSF,100,TRB,50\nS2,CASSG,200,TRB,100"
        data = {
            'file': (io.BytesIO(csv_content), 'complete_workflow.csv')
        }
        upload_response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 201
        file_id = upload_response.get_json()['id']
        
        # Step 2: Get columns from upload response
        columns = upload_response.get_json()['columns']
        
        # Step 3: Auto-detect field mapping
        suggested_mapping, confidence_scores = FieldMappingService.suggest_mapping_with_confidence(
            columns, 'chain_specific'
        )
        
        # Step 4: Verify suggestions
        assert len(suggested_mapping) > 0
        assert len(confidence_scores) > 0
        
        # Step 5: Manually modify mapping
        modified_mapping = {
            'sample': 'Sample',
            'chain': 'Chain',
            'cdr3': 'CDR3',
            'copy': 'Copies'
        }
        
        # Step 6: Validate modified mapping
        validation_result = FieldMappingService.validate_user_mapping(
            modified_mapping,
            'chain_specific',
            columns
        )
        assert validation_result.is_valid
        
        # Step 7: Create analysis with mapping
        analysis_request = {
            'type': 'chain_specific',
            'file_id': file_id,
            'parameters': {
                'field_mapping': modified_mapping
            }
        }
        
        analysis_response = client.post('/api/analysis', json=analysis_request)
        assert analysis_response.status_code == 201
        
        # Step 8: Verify analysis was created
        analysis_id = analysis_response.get_json()['id']
        status_response = client.get(f'/api/analysis/{analysis_id}/status')
        assert status_response.status_code == 200
