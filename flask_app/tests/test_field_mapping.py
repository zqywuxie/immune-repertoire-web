"""
Tests for the Field Mapping Service and API.
Requirements: 11.2, 11.3, 11.4, 11.5
"""
import pytest
import json

from services.field_mapping import FieldMappingService, ValidationResult, SuggestedMapping


class TestFieldMappingService:
    """Tests for FieldMappingService class."""
    
    def test_get_supported_analysis_types(self):
        """Test that all expected analysis types are supported."""
        types = FieldMappingService.get_supported_analysis_types()
        
        assert 'similarity_heatmap' in types
        assert 'sequencing_depth' in types
        assert 'diversity_metrics' in types
        assert 'chain_specific' in types
    
    def test_get_required_fields_similarity_heatmap(self):
        """Test required fields for similarity_heatmap analysis."""
        fields = FieldMappingService.get_required_fields('similarity_heatmap')
        
        assert 'sample' in fields
        assert 'cdr3' in fields
        assert 'reads' in fields
    
    def test_get_required_fields_unknown_type(self):
        """Test that unknown analysis type returns empty dict."""
        fields = FieldMappingService.get_required_fields('unknown_type')
        assert fields == {}
    
    def test_validate_mapping_valid(self):
        """Test validation with complete mapping."""
        mapping = {
            'sample': 'Sample_ID',
            'cdr3': 'CDR3_Sequence',
            'reads': 'Read_Count'
        }
        columns = ['Sample_ID', 'CDR3_Sequence', 'Read_Count', 'Other_Col']
        
        result = FieldMappingService.validate_mapping(
            'similarity_heatmap', mapping, columns
        )
        
        assert result.is_valid is True
        assert len(result.missing_fields) == 0
        assert result.mapped_fields == mapping
    
    def test_validate_mapping_missing_fields(self):
        """Test validation with missing required fields."""
        mapping = {
            'sample': 'Sample_ID'
            # Missing cdr3 and reads
        }
        columns = ['Sample_ID', 'CDR3_Sequence', 'Read_Count']
        
        result = FieldMappingService.validate_mapping(
            'similarity_heatmap', mapping, columns
        )
        
        assert result.is_valid is False
        assert 'cdr3' in result.missing_fields
        assert 'reads' in result.missing_fields

    def test_validate_mapping_column_not_in_file(self):
        """Test validation when mapped column doesn't exist in file."""
        mapping = {
            'sample': 'Sample_ID',
            'cdr3': 'NonExistent_Column',
            'reads': 'Read_Count'
        }
        columns = ['Sample_ID', 'CDR3_Sequence', 'Read_Count']
        
        result = FieldMappingService.validate_mapping(
            'similarity_heatmap', mapping, columns
        )
        
        assert result.is_valid is False
        assert 'cdr3' in result.missing_fields
    
    def test_validate_mapping_unknown_analysis_type(self):
        """Test validation with unknown analysis type."""
        result = FieldMappingService.validate_mapping(
            'unknown_type', {}, []
        )
        
        assert result.is_valid is False
        assert 'Unknown analysis type' in result.message
    
    def test_suggest_mapping_exact_match(self):
        """Test suggestion with exact column name matches."""
        columns = ['sample', 'cdr3', 'reads', 'other']
        
        suggestion = FieldMappingService.suggest_mapping(
            columns, 'similarity_heatmap'
        )
        
        assert suggestion.mapping.get('sample') == 'sample'
        assert suggestion.mapping.get('cdr3') == 'cdr3'
        assert suggestion.mapping.get('reads') == 'reads'
        assert suggestion.confidence == 1.0
    
    def test_suggest_mapping_alias_match(self):
        """Test suggestion with alias column names."""
        columns = ['sample_id', 'cdr3_aa', 'read_count']
        
        suggestion = FieldMappingService.suggest_mapping(
            columns, 'similarity_heatmap'
        )
        
        assert suggestion.mapping.get('sample') == 'sample_id'
        assert suggestion.mapping.get('cdr3') == 'cdr3_aa'
        assert suggestion.mapping.get('reads') == 'read_count'
        assert suggestion.confidence > 0.8
    
    def test_suggest_mapping_no_match(self):
        """Test suggestion with no matching columns."""
        columns = ['col_a', 'col_b', 'col_c']
        
        suggestion = FieldMappingService.suggest_mapping(
            columns, 'similarity_heatmap'
        )
        
        assert suggestion.confidence < 0.5
    
    def test_suggest_mapping_unknown_analysis_type(self):
        """Test suggestion with unknown analysis type."""
        suggestion = FieldMappingService.suggest_mapping(
            ['col1', 'col2'], 'unknown_type'
        )
        
        assert suggestion.mapping == {}
        assert suggestion.confidence == 0.0
    
    def test_get_field_info(self):
        """Test getting field information."""
        fields = FieldMappingService.get_field_info('similarity_heatmap')
        
        assert len(fields) == 3
        field_names = [f['name'] for f in fields]
        assert 'sample' in field_names
        assert 'cdr3' in field_names
        assert 'reads' in field_names
        
        # Check that aliases are included
        for field in fields:
            assert 'aliases' in field
            assert len(field['aliases']) > 0


class TestFieldMappingAPI:
    """Tests for Field Mapping API endpoints."""
    
    def test_create_mapping_template(self, client):
        """Test creating a mapping template."""
        response = client.post('/api/mappings', 
            data=json.dumps({
                'name': 'Test Template',
                'mapping': {'sample': 'Sample_ID', 'cdr3': 'CDR3', 'reads': 'Reads'},
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = response.get_json()
        assert data['name'] == 'Test Template'
        assert data['analysis_type'] == 'similarity_heatmap'
        assert 'id' in data

    def test_create_mapping_template_missing_name(self, client):
        """Test creating template without name."""
        response = client.post('/api/mappings',
            data=json.dumps({
                'mapping': {'sample': 'Sample_ID'},
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['error_code'] == 'VALIDATION_ERROR'
    
    def test_create_mapping_template_invalid_analysis_type(self, client):
        """Test creating template with invalid analysis type."""
        response = client.post('/api/mappings',
            data=json.dumps({
                'name': 'Test',
                'mapping': {'sample': 'Sample_ID'},
                'analysis_type': 'invalid_type'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['error_code'] == 'VALIDATION_ERROR'
    
    def test_list_mapping_templates(self, client):
        """Test listing mapping templates."""
        # Create a template first
        client.post('/api/mappings',
            data=json.dumps({
                'name': 'Test Template',
                'mapping': {'sample': 'Sample_ID'},
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        
        response = client.get('/api/mappings')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'templates' in data
        assert 'total' in data
        assert data['total'] >= 1
    
    def test_list_mapping_templates_filter_by_type(self, client):
        """Test listing templates filtered by analysis type."""
        # Create templates of different types
        client.post('/api/mappings',
            data=json.dumps({
                'name': 'Similarity Template',
                'mapping': {'sample': 'S'},
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        client.post('/api/mappings',
            data=json.dumps({
                'name': 'Diversity Template',
                'mapping': {'sample': 'S'},
                'analysis_type': 'diversity_metrics'
            }),
            content_type='application/json'
        )
        
        response = client.get('/api/mappings?analysis_type=similarity_heatmap')
        
        assert response.status_code == 200
        data = response.get_json()
        for template in data['templates']:
            assert template['analysis_type'] == 'similarity_heatmap'
    
    def test_get_mapping_template(self, client):
        """Test getting a specific template."""
        # Create a template
        create_response = client.post('/api/mappings',
            data=json.dumps({
                'name': 'Test Template',
                'mapping': {'sample': 'Sample_ID'},
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        template_id = create_response.get_json()['id']
        
        response = client.get(f'/api/mappings/{template_id}')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == template_id
        assert data['name'] == 'Test Template'
    
    def test_get_mapping_template_not_found(self, client):
        """Test getting non-existent template."""
        response = client.get('/api/mappings/nonexistent-id')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['error_code'] == 'MAPPING_TEMPLATE_NOT_FOUND'
    
    def test_delete_mapping_template(self, client):
        """Test deleting a template."""
        # Create a template
        create_response = client.post('/api/mappings',
            data=json.dumps({
                'name': 'To Delete',
                'mapping': {'sample': 'S'},
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        template_id = create_response.get_json()['id']
        
        response = client.delete(f'/api/mappings/{template_id}')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        
        # Verify it's deleted
        get_response = client.get(f'/api/mappings/{template_id}')
        assert get_response.status_code == 404

    def test_suggest_mapping(self, client):
        """Test mapping suggestion endpoint."""
        response = client.post('/api/mappings/suggest',
            data=json.dumps({
                'columns': ['sample', 'cdr3', 'reads', 'other'],
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'suggested_mapping' in data
        assert 'confidence' in data
        assert 'required_fields' in data
        assert data['suggested_mapping'].get('sample') == 'sample'
    
    def test_suggest_mapping_missing_columns(self, client):
        """Test suggestion with missing columns parameter."""
        response = client.post('/api/mappings/suggest',
            data=json.dumps({
                'analysis_type': 'similarity_heatmap'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_validate_mapping_endpoint(self, client):
        """Test mapping validation endpoint."""
        response = client.post('/api/mappings/validate',
            data=json.dumps({
                'mapping': {'sample': 'Sample_ID', 'cdr3': 'CDR3', 'reads': 'Reads'},
                'analysis_type': 'similarity_heatmap',
                'columns': ['Sample_ID', 'CDR3', 'Reads']
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['is_valid'] is True
        assert len(data['missing_fields']) == 0
    
    def test_validate_mapping_incomplete(self, client):
        """Test validation with incomplete mapping."""
        response = client.post('/api/mappings/validate',
            data=json.dumps({
                'mapping': {'sample': 'Sample_ID'},
                'analysis_type': 'similarity_heatmap',
                'columns': ['Sample_ID', 'CDR3', 'Reads']
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['is_valid'] is False
        assert 'cdr3' in data['missing_fields']
        assert 'reads' in data['missing_fields']
    
    def test_get_required_fields_endpoint(self, client):
        """Test getting required fields for analysis type."""
        response = client.get('/api/mappings/fields/similarity_heatmap')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['analysis_type'] == 'similarity_heatmap'
        assert 'required_fields' in data
        
        field_names = [f['name'] for f in data['required_fields']]
        assert 'sample' in field_names
        assert 'cdr3' in field_names
        assert 'reads' in field_names
    
    def test_get_required_fields_invalid_type(self, client):
        """Test getting fields for invalid analysis type."""
        response = client.get('/api/mappings/fields/invalid_type')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['error_code'] == 'VALIDATION_ERROR'
