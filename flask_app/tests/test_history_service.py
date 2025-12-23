"""
Tests for the History Service.
Requirements: 10.1, 10.2, 10.3, 10.4
"""
import pytest
from datetime import datetime
from models.database import db, Analysis, AnalysisResult, File
from services.history_service import HistoryService, get_history_service, init_history_service


@pytest.fixture
def history_service(app):
    """Create history service for testing."""
    with app.app_context():
        service = init_history_service(app)
        yield service


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


class TestHistoryService:
    """Tests for HistoryService class."""
    
    def test_get_history_empty(self, app, history_service):
        """Test getting history when no analyses exist."""
        with app.app_context():
            result = history_service.get_history()
            assert result.total == 0
            assert len(result.items) == 0
            assert result.page == 1
    
    def test_get_history_with_items(self, app, history_service, sample_analysis):
        """Test getting history with existing analyses."""
        with app.app_context():
            result = history_service.get_history()
            assert result.total == 1
            assert len(result.items) == 1
            assert result.items[0].id == sample_analysis.id
            assert result.items[0].analysis_type == 'similarity_heatmap'
            assert result.items[0].status == 'completed'
    
    def test_get_history_pagination(self, app, history_service, sample_file):
        """Test history pagination."""
        with app.app_context():
            # Create multiple analyses
            for i in range(25):
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
            result = history_service.get_history(page=1, page_size=10)
            assert result.total == 25
            assert len(result.items) == 10
            assert result.page == 1
            assert result.page_size == 10
            
            # Test second page
            result = history_service.get_history(page=2, page_size=10)
            assert len(result.items) == 10
            assert result.page == 2
            
            # Test third page
            result = history_service.get_history(page=3, page_size=10)
            assert len(result.items) == 5
    
    def test_get_history_status_filter(self, app, history_service, sample_file):
        """Test filtering history by status."""
        with app.app_context():
            # Create analyses with different statuses
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
            
            # Filter by completed
            result = history_service.get_history(status_filter='completed')
            assert result.total == 2
            
            # Filter by failed
            result = history_service.get_history(status_filter='failed')
            assert result.total == 1
    
    def test_get_history_type_filter(self, app, history_service, sample_file):
        """Test filtering history by analysis type."""
        with app.app_context():
            # Create analyses with different types
            for analysis_type in ['similarity_heatmap', 'similarity_heatmap', 'sequencing_depth']:
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
            result = history_service.get_history(type_filter='similarity_heatmap')
            assert result.total == 2
            
            # Filter by sequencing_depth
            result = history_service.get_history(type_filter='sequencing_depth')
            assert result.total == 1
    
    def test_get_history_item(self, app, history_service, sample_analysis):
        """Test getting a single history item."""
        with app.app_context():
            item = history_service.get_history_item(sample_analysis.id)
            assert item is not None
            assert item.id == sample_analysis.id
            assert item.analysis_type == 'similarity_heatmap'
            assert item.file_name == 'test_data.csv'
    
    def test_get_history_item_not_found(self, app, history_service):
        """Test getting a non-existent history item."""
        with app.app_context():
            item = history_service.get_history_item('non-existent-id')
            assert item is None
    
    def test_delete_history_item(self, app, history_service, sample_analysis):
        """Test deleting a history item."""
        with app.app_context():
            # Verify item exists
            item = history_service.get_history_item(sample_analysis.id)
            assert item is not None
            
            # Delete item
            result = history_service.delete_history_item(sample_analysis.id)
            assert result is True
            
            # Verify item is deleted
            item = history_service.get_history_item(sample_analysis.id)
            assert item is None
    
    def test_delete_history_item_not_found(self, app, history_service):
        """Test deleting a non-existent history item."""
        from exceptions import AnalysisNotFoundError
        
        with app.app_context():
            with pytest.raises(AnalysisNotFoundError):
                history_service.delete_history_item('non-existent-id')
    
    def test_get_status_counts(self, app, history_service, sample_file):
        """Test getting status counts."""
        with app.app_context():
            # Create analyses with different statuses
            for status in ['completed', 'completed', 'failed', 'running', 'pending']:
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
            
            counts = history_service.get_status_counts()
            assert counts.get('completed') == 2
            assert counts.get('failed') == 1
            assert counts.get('running') == 1
            assert counts.get('pending') == 1
    
    def test_get_type_counts(self, app, history_service, sample_file):
        """Test getting type counts."""
        with app.app_context():
            # Create analyses with different types
            for analysis_type in ['similarity_heatmap', 'similarity_heatmap', 'sequencing_depth']:
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
            
            counts = history_service.get_type_counts()
            assert counts.get('similarity_heatmap') == 2
            assert counts.get('sequencing_depth') == 1
    
    def test_history_item_to_dict(self, app, history_service, sample_analysis):
        """Test HistoryItem to_dict method."""
        with app.app_context():
            item = history_service.get_history_item(sample_analysis.id)
            item_dict = item.to_dict()
            
            assert 'id' in item_dict
            assert 'type' in item_dict  # Verify 'type' field is present
            assert 'analysis_type' in item_dict
            assert 'file_name' in item_dict
            assert 'status' in item_dict
            assert 'created_at' in item_dict
            assert item_dict['id'] == sample_analysis.id
            assert item_dict['type'] == sample_analysis.type  # Verify type matches
            assert item_dict['analysis_type'] == sample_analysis.type  # Verify analysis_type matches
