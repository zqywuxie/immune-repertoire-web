"""
Tests for the History API endpoints.
Requirements: 10.1, 10.2, 10.3, 10.4
"""
import pytest
from datetime import datetime
from models.database import db, Analysis, File


@pytest.fixture
def sample_file(app):
    """Create a sample file record for testing."""
    with app.app_context():
        file_record = File(
            id='test-file-id',
            name='test_file.csv',
            original_name='test_data.csv',
            size=1024,
            mime_type='text/csv',
            columns=['sample', 'cdr3', 'reads'],
            row_count=100,
            storage_path='/tmp/test_file.csv',
            uploaded_at=datetime.utcnow()
        )
        db.session.add(file_record)
        db.session.commit()
        yield file_record


@pytest.fixture
def sample_analysis(app, sample_file):
    """Create a sample analysis record for testing."""
    with app.app_context():
        analysis = Analysis(
            id='test-analysis-id',
            type='similarity_heatmap',
            file_id=sample_file.id,
            field_mapping={'sample': 'sample', 'cdr3': 'cdr3'},
            parameters={'metrics': ['r2_inner']},
            chart_config={'title': 'Test'},
            status='completed',
            progress=100.0,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        db.session.add(analysis)
        db.session.commit()
        yield analysis


class TestHistoryAPI:
    """Tests for History API endpoints."""
    
    def test_get_history_empty(self, client):
        """Test GET /api/history with no analyses."""
        response = client.get('/api/history')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['total'] == 0
        assert data['items'] == []
        assert data['page'] == 1
    
    def test_get_history_with_items(self, client, sample_analysis):
        """Test GET /api/history with existing analyses."""
        response = client.get('/api/history')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['total'] == 1
        assert len(data['items']) == 1
        assert data['items'][0]['id'] == sample_analysis.id
        assert data['items'][0]['type'] == 'similarity_heatmap'  # Verify 'type' field
        assert data['items'][0]['analysis_type'] == 'similarity_heatmap'
    
    def test_get_history_pagination(self, client, app, sample_file):
        """Test GET /api/history with pagination."""
        with app.app_context():
            # Create multiple analyses
            for i in range(15):
                analysis = Analysis(
                    id=f'analysis-{i}',
                    type='similarity_heatmap',
                    file_id=sample_file.id,
                    field_mapping={},
                    parameters={},
                    status='completed',
                    created_at=datetime.utcnow()
                )
                db.session.add(analysis)
            db.session.commit()
        
        # Test first page
        response = client.get('/api/history?page=1&page_size=10')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 15
        assert len(data['items']) == 10
        assert data['page'] == 1
        
        # Test second page
        response = client.get('/api/history?page=2&page_size=10')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['items']) == 5
        assert data['page'] == 2
    
    def test_get_history_status_filter(self, client, app, sample_file):
        """Test GET /api/history with status filter."""
        with app.app_context():
            for status in ['completed', 'completed', 'failed']:
                analysis = Analysis(
                    type='similarity_heatmap',
                    file_id=sample_file.id,
                    field_mapping={},
                    parameters={},
                    status=status,
                    created_at=datetime.utcnow()
                )
                db.session.add(analysis)
            db.session.commit()
        
        # Filter by completed
        response = client.get('/api/history?status=completed')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 2
        
        # Filter by failed
        response = client.get('/api/history?status=failed')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 1
    
    def test_get_history_type_filter(self, client, app, sample_file):
        """Test GET /api/history with type filter."""
        with app.app_context():
            for analysis_type in ['similarity_heatmap', 'sequencing_depth']:
                analysis = Analysis(
                    type=analysis_type,
                    file_id=sample_file.id,
                    field_mapping={},
                    parameters={},
                    status='completed',
                    created_at=datetime.utcnow()
                )
                db.session.add(analysis)
            db.session.commit()
        
        # Filter by similarity_heatmap
        response = client.get('/api/history?type=similarity_heatmap')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 1
    
    def test_get_history_item(self, client, sample_analysis):
        """Test GET /api/history/{analysis_id}."""
        response = client.get(f'/api/history/{sample_analysis.id}')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['id'] == sample_analysis.id
        assert data['type'] == 'similarity_heatmap'  # Verify 'type' field
        assert data['analysis_type'] == 'similarity_heatmap'
        assert data['file_name'] == 'test_data.csv'
    
    def test_get_history_item_not_found(self, client):
        """Test GET /api/history/{analysis_id} with non-existent ID."""
        response = client.get('/api/history/non-existent-id')
        assert response.status_code == 404
        
        data = response.get_json()
        assert data['error_code'] == 'ANALYSIS_NOT_FOUND'
    
    def test_delete_history_item(self, client, sample_analysis):
        """Test DELETE /api/history/{analysis_id}."""
        response = client.delete(f'/api/history/{sample_analysis.id}')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['success'] is True
        
        # Verify item is deleted
        response = client.get(f'/api/history/{sample_analysis.id}')
        assert response.status_code == 404
    
    def test_delete_history_item_not_found(self, client):
        """Test DELETE /api/history/{analysis_id} with non-existent ID."""
        response = client.delete('/api/history/non-existent-id')
        assert response.status_code == 404
        
        data = response.get_json()
        assert data['error_code'] == 'ANALYSIS_NOT_FOUND'
    
    def test_get_history_stats(self, client, app, sample_file):
        """Test GET /api/history/stats."""
        with app.app_context():
            for status in ['completed', 'completed', 'failed', 'running']:
                analysis = Analysis(
                    type='similarity_heatmap',
                    file_id=sample_file.id,
                    field_mapping={},
                    parameters={},
                    status=status,
                    created_at=datetime.utcnow()
                )
                db.session.add(analysis)
            db.session.commit()
        
        response = client.get('/api/history/stats')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'status_counts' in data
        assert 'type_counts' in data
        assert data['status_counts'].get('completed') == 2
        assert data['status_counts'].get('failed') == 1
