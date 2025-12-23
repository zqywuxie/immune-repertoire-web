"""
Integration tests for sample grouping and baseline selection workflows.
Tests complete group creation, multi-selection, and baseline percentage difference calculations.
Requirements: 14.3, 16.1, 16.2, 16.3, 17.1, 17.2, 17.3, 17.4
"""
import io
import pytest


class TestGroupCreationAndMultiSelectWorkflow:
    """Test complete group creation and multi-selection workflow. Requirements: 14.3, 16.1, 16.3"""
    
    @pytest.fixture
    def uploaded_file_with_samples(self, client):
        """Upload a test file with multiple samples for grouping."""
        csv_content = b"""sample,metric1,metric2,metric3,chain
Sample_A,100,200,300,TRB
Sample_B,150,250,350,TRB
Sample_C,120,220,320,TRB
Sample_D,180,280,380,TRB
Sample_E,90,190,290,TRB
Sample_F,160,260,360,TRB"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'grouping_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_create_sample_group(self, client, uploaded_file_with_samples):
        """Test creating a new sample group."""
        file_id = uploaded_file_with_samples['id']
        
        # Create a group
        group_data = {
            'name': 'Test Group 1',
            'sample_ids': ['Sample_A', 'Sample_B', 'Sample_C'],
            'description': 'First test group',
            'file_id': file_id
        }
        
        response = client.post(
            '/api/groups',
            json=group_data
        )
        assert response.status_code == 201
        
        data = response.get_json()
        assert 'id' in data
        assert data['name'] == 'Test Group 1'
        assert data['sample_count'] == 3
        assert 'created_at' in data
    
    def test_create_multiple_groups(self, client, uploaded_file_with_samples):
        """Test creating multiple sample groups."""
        file_id = uploaded_file_with_samples['id']
        
        # Create first group
        group1_data = {
            'name': 'Control Group',
            'sample_ids': ['Sample_A', 'Sample_B'],
            'file_id': file_id
        }
        response1 = client.post('/api/groups', json=group1_data)
        assert response1.status_code == 201
        group1_id = response1.get_json()['id']
        
        # Create second group
        group2_data = {
            'name': 'Treatment Group',
            'sample_ids': ['Sample_C', 'Sample_D'],
            'file_id': file_id
        }
        response2 = client.post('/api/groups', json=group2_data)
        assert response2.status_code == 201
        group2_id = response2.get_json()['id']
        
        # Create third group
        group3_data = {
            'name': 'Validation Group',
            'sample_ids': ['Sample_E', 'Sample_F'],
            'file_id': file_id
        }
        response3 = client.post('/api/groups', json=group3_data)
        assert response3.status_code == 201
        group3_id = response3.get_json()['id']
        
        # Verify all groups exist
        list_response = client.get('/api/groups')
        assert list_response.status_code == 200
        groups = list_response.get_json()['groups']
        
        # Should have at least 3 groups (may have more from other tests)
        group_ids = [g['id'] for g in groups]
        assert group1_id in group_ids
        assert group2_id in group_ids
        assert group3_id in group_ids
    
    def test_get_group_details(self, client, uploaded_file_with_samples):
        """Test retrieving group details."""
        file_id = uploaded_file_with_samples['id']
        
        # Create a group
        group_data = {
            'name': 'Detail Test Group',
            'sample_ids': ['Sample_A', 'Sample_B', 'Sample_C'],
            'description': 'Group for detail testing',
            'file_id': file_id
        }
        create_response = client.post('/api/groups', json=group_data)
        assert create_response.status_code == 201
        group_id = create_response.get_json()['id']
        
        # Get group details
        detail_response = client.get(f'/api/groups/{group_id}')
        assert detail_response.status_code == 200
        
        data = detail_response.get_json()
        assert data['id'] == group_id
        assert data['name'] == 'Detail Test Group'
        assert 'sample_ids' in data
        assert len(data['sample_ids']) == 3
    
    def test_update_group(self, client, uploaded_file_with_samples):
        """Test updating a sample group."""
        file_id = uploaded_file_with_samples['id']
        
        # Create a group
        group_data = {
            'name': 'Original Name',
            'sample_ids': ['Sample_A', 'Sample_B'],
            'file_id': file_id
        }
        create_response = client.post('/api/groups', json=group_data)
        assert create_response.status_code == 201
        group_id = create_response.get_json()['id']
        
        # Update the group
        update_data = {
            'name': 'Updated Name',
            'sample_ids': ['Sample_A', 'Sample_B', 'Sample_C'],
            'description': 'Updated description'
        }
        update_response = client.put(f'/api/groups/{group_id}', json=update_data)
        assert update_response.status_code == 200
        
        data = update_response.get_json()
        assert data['name'] == 'Updated Name'
        assert data['sample_count'] == 3
    
    def test_delete_group(self, client, uploaded_file_with_samples):
        """Test deleting a sample group."""
        file_id = uploaded_file_with_samples['id']
        
        # Create a group
        group_data = {
            'name': 'Group to Delete',
            'sample_ids': ['Sample_A'],
            'file_id': file_id
        }
        create_response = client.post('/api/groups', json=group_data)
        assert create_response.status_code == 201
        group_id = create_response.get_json()['id']
        
        # Delete the group
        delete_response = client.delete(f'/api/groups/{group_id}')
        assert delete_response.status_code == 200
        
        data = delete_response.get_json()
        assert data['success'] is True
        
        # Verify group is deleted (API may return 400 or 404 for non-existent groups)
        get_response = client.get(f'/api/groups/{group_id}')
        assert get_response.status_code in [400, 404]
    
    def test_calculate_multiple_group_averages(self, client, uploaded_file_with_samples):
        """Test calculating averages for multiple groups simultaneously."""
        file_id = uploaded_file_with_samples['id']
        
        # Create two groups
        group1_data = {
            'name': 'Avg Group 1',
            'sample_ids': ['Sample_A', 'Sample_B'],
            'file_id': file_id
        }
        response1 = client.post('/api/groups', json=group1_data)
        assert response1.status_code == 201
        group1_id = response1.get_json()['id']
        
        group2_data = {
            'name': 'Avg Group 2',
            'sample_ids': ['Sample_C', 'Sample_D'],
            'file_id': file_id
        }
        response2 = client.post('/api/groups', json=group2_data)
        assert response2.status_code == 201
        group2_id = response2.get_json()['id']
        
        # Calculate averages for both groups
        avg_request = {
            'group_ids': [group1_id, group2_id],
            'metric_fields': ['metric1', 'metric2', 'metric3'],
            'file_id': file_id,
            'sample_column': 'sample'
        }
        
        avg_response = client.post('/api/groups/averages', json=avg_request)
        assert avg_response.status_code == 200
        
        data = avg_response.get_json()
        assert 'averages' in data
        assert group1_id in data['averages']
        assert group2_id in data['averages']
        
        # Verify averages are calculated
        # Group 1: Sample_A (100, 200, 300) + Sample_B (150, 250, 350) = avg (125, 225, 325)
        assert 'metric1' in data['averages'][group1_id]
        assert 'metric2' in data['averages'][group1_id]
        assert 'metric3' in data['averages'][group1_id]


class TestBaselineSelectionWorkflow:
    """Test baseline selection and percentage difference calculation workflow. Requirements: 14.3, 17.1, 17.2, 17.3, 17.4"""
    
    @pytest.fixture
    def uploaded_file_for_baseline(self, client):
        """Upload a test file for baseline testing."""
        csv_content = b"""sample,value1,value2,chain
Baseline_Sample,100,200,TRB
Test_Sample_1,120,240,TRB
Test_Sample_2,80,160,TRB
Test_Sample_3,150,300,TRB"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'baseline_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_get_baseline_value_for_sample(self, client, uploaded_file_for_baseline):
        """Test getting baseline value for an individual sample."""
        file_id = uploaded_file_for_baseline['id']
        
        # Get baseline value for a sample
        baseline_request = {
            'baseline_type': 'sample',
            'baseline_id': 'Baseline_Sample',
            'metric_fields': ['value1', 'value2'],
            'file_id': file_id,
            'sample_column': 'sample'
        }
        
        response = client.post('/api/baseline/value', json=baseline_request)
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'baseline_values' in data
        assert data['baseline_values']['value1'] == 100.0
        assert data['baseline_values']['value2'] == 200.0
    
    def test_get_baseline_value_for_group(self, client, uploaded_file_for_baseline):
        """Test getting baseline value for a sample group (group average)."""
        file_id = uploaded_file_for_baseline['id']
        
        # Create a group to use as baseline
        group_data = {
            'name': 'Baseline Group',
            'sample_ids': ['Baseline_Sample', 'Test_Sample_1'],
            'file_id': file_id
        }
        group_response = client.post('/api/groups', json=group_data)
        assert group_response.status_code == 201
        group_id = group_response.get_json()['id']
        
        # Get baseline value for the group
        baseline_request = {
            'baseline_type': 'group',
            'baseline_id': group_id,
            'metric_fields': ['value1', 'value2'],
            'file_id': file_id,
            'sample_column': 'sample'
        }
        
        response = client.post('/api/baseline/value', json=baseline_request)
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'baseline_values' in data
        # Group average: (100 + 120) / 2 = 110, (200 + 240) / 2 = 220
        assert data['baseline_values']['value1'] == 110.0
        assert data['baseline_values']['value2'] == 220.0
    
    def test_calculate_percentage_difference_sample_baseline(self, client, uploaded_file_for_baseline):
        """Test calculating percentage differences with a sample as baseline."""
        file_id = uploaded_file_for_baseline['id']
        
        # Calculate percentage differences
        calc_request = {
            'baseline_type': 'sample',
            'baseline_id': 'Baseline_Sample',
            'target_ids': ['Test_Sample_1', 'Test_Sample_2', 'Test_Sample_3'],
            'target_type': 'sample',
            'metric_fields': ['value1', 'value2'],
            'file_id': file_id,
            'sample_column': 'sample'
        }
        
        response = client.post('/api/baseline/calculate', json=calc_request)
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'baseline_values' in data
        assert 'percentage_differences' in data
        
        # Verify baseline values
        assert data['baseline_values']['value1'] == 100.0
        assert data['baseline_values']['value2'] == 200.0
        
        # Verify percentage differences
        # Test_Sample_1: 120/100 * 100 = 120%, 240/200 * 100 = 120%
        assert 'Test_Sample_1' in data['percentage_differences']
        assert abs(data['percentage_differences']['Test_Sample_1']['value1'] - 120.0) < 0.01
        
        # Test_Sample_2: 80/100 * 100 = 80%, 160/200 * 100 = 80%
        assert 'Test_Sample_2' in data['percentage_differences']
        assert abs(data['percentage_differences']['Test_Sample_2']['value1'] - 80.0) < 0.01
    
    def test_calculate_percentage_difference_group_baseline(self, client, uploaded_file_for_baseline):
        """Test calculating percentage differences with a group as baseline."""
        file_id = uploaded_file_for_baseline['id']
        
        # Create baseline group
        baseline_group_data = {
            'name': 'Baseline Group',
            'sample_ids': ['Baseline_Sample', 'Test_Sample_1'],
            'file_id': file_id
        }
        baseline_response = client.post('/api/groups', json=baseline_group_data)
        assert baseline_response.status_code == 201
        baseline_group_id = baseline_response.get_json()['id']
        
        # Create target group
        target_group_data = {
            'name': 'Target Group',
            'sample_ids': ['Test_Sample_2', 'Test_Sample_3'],
            'file_id': file_id
        }
        target_response = client.post('/api/groups', json=target_group_data)
        assert target_response.status_code == 201
        target_group_id = target_response.get_json()['id']
        
        # Calculate percentage differences
        calc_request = {
            'baseline_type': 'group',
            'baseline_id': baseline_group_id,
            'target_ids': [target_group_id],
            'target_type': 'group',
            'metric_fields': ['value1', 'value2'],
            'file_id': file_id,
            'sample_column': 'sample'
        }
        
        response = client.post('/api/baseline/calculate', json=calc_request)
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'baseline_values' in data
        assert 'percentage_differences' in data
        
        # Baseline group average: (100 + 120) / 2 = 110
        assert abs(data['baseline_values']['value1'] - 110.0) < 0.01
        
        # Target group average: (80 + 150) / 2 = 115
        # Percentage: 115 / 110 * 100 ≈ 104.55%
        assert target_group_id in data['percentage_differences']


class TestAnalysisWithBaselineSelection:
    """Test analysis types with baseline selection functionality. Requirements: 14.3, 3.7, 4.7, 5.7"""
    
    @pytest.fixture
    def uploaded_analysis_file(self, client):
        """Upload a test file for analysis with baseline."""
        csv_content = b"""sample,total_rna,reads_umi,migs_good,reads_good,d50,gini,shannon,simpson,chain,cdr3,copy
Control_1,1000000,500000,450000,480000,25,0.65,3.2,0.85,TRB,CASSF,100
Control_2,1100000,550000,495000,528000,28,0.62,3.3,0.86,TRB,CASSG,150
Treatment_1,900000,450000,400000,430000,30,0.58,3.5,0.88,TRB,CASSH,120
Treatment_2,950000,475000,420000,450000,32,0.55,3.6,0.89,TRB,CASSI,180"""
        
        data = {
            'file': (io.BytesIO(csv_content), 'analysis_baseline_test.csv')
        }
        response = client.post(
            '/api/files/upload',
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 201
        return response.get_json()
    
    def test_sequencing_depth_with_sample_baseline(self, client, uploaded_analysis_file):
        """Test sequencing depth analysis with sample baseline selection."""
        file_id = uploaded_analysis_file['id']
        
        # Create analysis with baseline sample
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
                'baseline_sample': 'Control_1',
                'baseline_type': 'sample'
            }
        }
        
        response = client.post('/api/analysis', json=analysis_request)
        assert response.status_code == 201
        
        data = response.get_json()
        assert 'id' in data
        assert data['status'] == 'pending'
    
    def test_sequencing_depth_with_group_baseline(self, client, uploaded_analysis_file):
        """Test sequencing depth analysis with group baseline selection."""
        file_id = uploaded_analysis_file['id']
        
        # Create baseline group
        group_data = {
            'name': 'Control Group',
            'sample_ids': ['Control_1', 'Control_2'],
            'file_id': file_id
        }
        group_response = client.post('/api/groups', json=group_data)
        assert group_response.status_code == 201
        group_id = group_response.get_json()['id']
        
        # Create analysis with baseline group
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
                'baseline_group_id': group_id,
                'baseline_type': 'group'
            }
        }
        
        response = client.post('/api/analysis', json=analysis_request)
        assert response.status_code == 201
        
        data = response.get_json()
        assert 'id' in data
    
    def test_diversity_analysis_with_baseline(self, client, uploaded_analysis_file):
        """Test diversity analysis with baseline selection."""
        file_id = uploaded_analysis_file['id']
        
        # Create analysis with baseline
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
                'baseline_sample': 'Control_1',
                'baseline_type': 'sample'
            }
        }
        
        response = client.post('/api/analysis', json=analysis_request)
        assert response.status_code == 201
        
        data = response.get_json()
        assert 'id' in data
    
    def test_chain_analysis_with_baseline(self, client, uploaded_analysis_file):
        """Test chain-specific analysis with baseline selection."""
        file_id = uploaded_analysis_file['id']
        
        # Create analysis with baseline
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
                'baseline_sample': 'Control_1',
                'baseline_type': 'sample'
            }
        }
        
        response = client.post('/api/analysis', json=analysis_request)
        assert response.status_code == 201
        
        data = response.get_json()
        assert 'id' in data


class TestGroupingErrorHandling:
    """Test error handling for grouping and baseline operations. Requirements: 14.3"""
    
    def test_create_group_without_name(self, client):
        """Test creating a group without a name."""
        group_data = {
            'sample_ids': ['Sample_A', 'Sample_B']
        }
        
        response = client.post('/api/groups', json=group_data)
        assert response.status_code == 400
        
        data = response.get_json()
        assert 'error_code' in data
    
    def test_create_group_without_samples(self, client):
        """Test creating a group without samples."""
        group_data = {
            'name': 'Empty Group'
        }
        
        response = client.post('/api/groups', json=group_data)
        assert response.status_code == 400
        
        data = response.get_json()
        assert 'error_code' in data
    
    def test_get_nonexistent_group(self, client):
        """Test getting a non-existent group."""
        response = client.get('/api/groups/nonexistent-group-id')
        # API may return 400 (invalid ID format) or 404 (not found)
        assert response.status_code in [400, 404]
    
    def test_delete_nonexistent_group(self, client):
        """Test deleting a non-existent group."""
        response = client.delete('/api/groups/nonexistent-group-id')
        # API may return 400 (invalid ID format) or 404 (not found)
        assert response.status_code in [400, 404]
    
    def test_baseline_with_invalid_type(self, client):
        """Test baseline calculation with invalid type."""
        calc_request = {
            'baseline_type': 'invalid_type',
            'baseline_id': 'some_id',
            'target_ids': ['target1'],
            'target_type': 'sample',
            'metric_fields': ['value1'],
            'file_id': 'some_file_id'
        }
        
        response = client.post('/api/baseline/calculate', json=calc_request)
        assert response.status_code in [400, 404]
    
    def test_baseline_with_nonexistent_file(self, client):
        """Test baseline calculation with non-existent file."""
        calc_request = {
            'baseline_type': 'sample',
            'baseline_id': 'some_sample',
            'target_ids': ['target1'],
            'target_type': 'sample',
            'metric_fields': ['value1'],
            'file_id': 'nonexistent-file-id'
        }
        
        response = client.post('/api/baseline/calculate', json=calc_request)
        assert response.status_code in [400, 404]
