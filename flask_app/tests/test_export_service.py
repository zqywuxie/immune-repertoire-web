"""
Tests for the Export Service.
Requirements: 6.1, 6.2, 6.3, 6.4
"""
import io
import csv
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.export_service import ExportService, ExportMetadata


class TestExportMetadata:
    """Tests for ExportMetadata class."""
    
    def test_metadata_creation(self):
        """Test creating export metadata."""
        metadata = ExportMetadata(
            analysis_id='test-123',
            analysis_type='similarity_heatmap',
            file_name='test_data.csv',
            parameters={'metrics': ['r2_inner']},
            chart_config={'color_scheme': 'viridis'},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 5, 0)
        )
        
        assert metadata.analysis_id == 'test-123'
        assert metadata.analysis_type == 'similarity_heatmap'
        assert metadata.file_name == 'test_data.csv'
        assert metadata.parameters == {'metrics': ['r2_inner']}
        assert metadata.chart_config == {'color_scheme': 'viridis'}
        assert metadata.export_timestamp is not None
    
    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        metadata = ExportMetadata(
            analysis_id='test-123',
            analysis_type='similarity_heatmap',
            file_name='test_data.csv',
            parameters={'metrics': ['r2_inner']},
            chart_config={'color_scheme': 'viridis'},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 5, 0)
        )
        
        result = metadata.to_dict()
        
        assert result['analysis_id'] == 'test-123'
        assert result['analysis_type'] == 'similarity_heatmap'
        assert result['file_name'] == 'test_data.csv'
        assert result['parameters'] == {'metrics': ['r2_inner']}
        assert result['chart_config'] == {'color_scheme': 'viridis'}
        assert 'created_at' in result
        assert 'completed_at' in result
        assert 'export_timestamp' in result
    
    def test_metadata_to_text(self):
        """Test converting metadata to text format."""
        metadata = ExportMetadata(
            analysis_id='test-123',
            analysis_type='similarity_heatmap',
            file_name='test_data.csv',
            parameters={'metrics': ['r2_inner']},
            chart_config={'color_scheme': 'viridis'},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 5, 0)
        )
        
        text = metadata.to_text()
        
        assert 'Analysis ID: test-123' in text
        assert 'Analysis Type: similarity_heatmap' in text
        assert 'Source File: test_data.csv' in text
        assert 'Parameters:' in text
        assert 'Chart Configuration:' in text
    
    def test_metadata_excludes_internal_params(self):
        """Test that internal parameters (starting with _) are excluded from text."""
        metadata = ExportMetadata(
            analysis_id='test-123',
            analysis_type='similarity_heatmap',
            file_name='test_data.csv',
            parameters={'metrics': ['r2_inner'], '_retry_count': 2},
            chart_config={},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=None
        )
        
        text = metadata.to_text()
        
        assert 'metrics' in text
        assert '_retry_count' not in text


class TestExportServiceInit:
    """Tests for ExportService initialization."""
    
    def test_init_without_folder(self):
        """Test initialization without results folder."""
        service = ExportService()
        assert service.results_folder is None
    
    def test_init_with_folder(self):
        """Test initialization with results folder."""
        service = ExportService(results_folder='/path/to/results')
        assert service.results_folder == '/path/to/results'
    
    def test_supported_formats(self):
        """Test that supported formats are defined."""
        assert 'png' in ExportService.SUPPORTED_FORMATS
        assert 'csv' in ExportService.SUPPORTED_FORMATS
        assert 'zip' in ExportService.SUPPORTED_FORMATS
    
    def test_default_dpi(self):
        """Test default DPI is 300."""
        assert ExportService.DEFAULT_DPI == 300


class TestTableDataToCSV:
    """Tests for _table_data_to_csv method."""
    
    def test_basic_conversion(self):
        """Test basic table data to CSV conversion."""
        service = ExportService()
        
        table_data = {
            'columns': ['Sample', 'Value1', 'Value2'],
            'data': [
                {'Sample': 'A', 'Value1': 1.0, 'Value2': 2.0},
                {'Sample': 'B', 'Value1': 3.0, 'Value2': 4.0}
            ]
        }
        
        csv_bytes = service._table_data_to_csv(table_data)
        csv_text = csv_bytes.decode('utf-8')
        
        assert 'Sample,Value1,Value2' in csv_text
        assert 'A,1.0,2.0' in csv_text
        assert 'B,3.0,4.0' in csv_text
    
    def test_empty_data(self):
        """Test conversion with empty data."""
        service = ExportService()
        
        table_data = {
            'columns': ['Sample', 'Value'],
            'data': []
        }
        
        csv_bytes = service._table_data_to_csv(table_data)
        csv_text = csv_bytes.decode('utf-8')
        
        # Should have header but no data rows
        assert 'Sample,Value' in csv_text
        lines = csv_text.strip().split('\n')
        assert len(lines) == 1  # Only header


class TestExportServiceWithApp:
    """Tests for ExportService with Flask app context."""
    
    @pytest.fixture
    def app(self):
        """Create test Flask application."""
        from app import create_app
        app = create_app('testing')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    @pytest.fixture
    def app_context(self, app):
        """Create application context."""
        with app.app_context():
            from models.database import db
            db.create_all()
            yield
            db.session.remove()
            db.drop_all()
    
    def test_get_export_metadata_not_found(self, app_context):
        """Test getting metadata for non-existent analysis."""
        from exceptions import AnalysisNotFoundError
        
        service = ExportService()
        
        with pytest.raises(AnalysisNotFoundError):
            service.get_export_metadata('non-existent-id')
    
    def test_export_png_not_found(self, app_context):
        """Test exporting PNG for non-existent result."""
        from exceptions import AnalysisNotFoundError
        
        service = ExportService()
        
        with pytest.raises(AnalysisNotFoundError):
            service.export_png('non-existent-id', 'test_result')
    
    def test_export_csv_not_found(self, app_context):
        """Test exporting CSV for non-existent result."""
        from exceptions import AnalysisNotFoundError
        
        service = ExportService()
        
        with pytest.raises(AnalysisNotFoundError):
            service.export_csv('non-existent-id', 'test_result')
    
    def test_export_zip_not_found(self, app_context):
        """Test exporting ZIP for non-existent analysis."""
        from exceptions import AnalysisNotFoundError
        
        service = ExportService()
        
        with pytest.raises(AnalysisNotFoundError):
            service.export_zip('non-existent-id')
    
    def test_get_available_exports_not_found(self, app_context):
        """Test getting available exports for non-existent analysis."""
        from exceptions import AnalysisNotFoundError
        
        service = ExportService()
        
        with pytest.raises(AnalysisNotFoundError):
            service.get_available_exports('non-existent-id')
    
    def test_export_single_result_invalid_format(self, app_context):
        """Test exporting with invalid format."""
        from exceptions import ValidationError
        
        service = ExportService()
        
        with pytest.raises(ValidationError) as exc_info:
            service.export_single_result('test-id', 'test_result', format='invalid')
        
        assert 'Unsupported export format' in str(exc_info.value.message)


class TestExportServiceIntegration:
    """Integration tests for ExportService with actual data."""
    
    @pytest.fixture
    def app(self):
        """Create test Flask application."""
        from app import create_app
        app = create_app('testing')
        return app
    
    @pytest.fixture
    def app_context(self, app):
        """Create application context."""
        with app.app_context():
            from models.database import db
            db.create_all()
            yield
            db.session.remove()
            db.drop_all()
    
    @pytest.fixture
    def sample_analysis(self, app_context, tmp_path):
        """Create a sample analysis with results."""
        from models.database import db, File, Analysis, AnalysisResult
        
        # Create a file record
        file_record = File(
            id='test-file-id',
            name='test.csv',
            original_name='test_data.csv',
            size=1000,
            mime_type='text/csv',
            columns=['Sample', 'CDR3', 'reads'],
            row_count=100,
            storage_path=str(tmp_path / 'test.csv')
        )
        db.session.add(file_record)
        
        # Create an analysis record
        analysis = Analysis(
            id='test-analysis-id',
            type='similarity_heatmap',
            file_id='test-file-id',
            field_mapping={'sample': 'Sample', 'cdr3': 'CDR3'},
            parameters={'metrics': ['r2_inner']},
            chart_config={'color_scheme': 'viridis'},
            status='completed',
            progress=100.0,
            results_path=str(tmp_path / 'results')
        )
        db.session.add(analysis)
        
        # Create results directory
        results_dir = tmp_path / 'results'
        results_dir.mkdir(exist_ok=True)
        
        # Create a visualization result
        viz_path = results_dir / 'r2_inner_heatmap.png'
        viz_path.write_bytes(b'PNG_CONTENT')
        
        viz_result = AnalysisResult(
            id='viz-result-id',
            analysis_id='test-analysis-id',
            result_type='visualization',
            name='r2_inner_heatmap',
            file_path=str(viz_path),
            mime_type='image/png'
        )
        db.session.add(viz_result)
        
        # Create a data table result
        table_result = AnalysisResult(
            id='table-result-id',
            analysis_id='test-analysis-id',
            result_type='data_table',
            name='r2_inner_matrix',
            file_path=str(results_dir / 'r2_inner_matrix.csv'),
            mime_type='text/csv',
            table_data={
                'columns': ['Sample', 'A', 'B'],
                'data': [
                    {'Sample': 'A', 'A': 1.0, 'B': 0.8},
                    {'Sample': 'B', 'A': 0.8, 'B': 1.0}
                ],
                'row_count': 2
            }
        )
        db.session.add(table_result)
        
        db.session.commit()
        
        return {
            'analysis_id': 'test-analysis-id',
            'file_id': 'test-file-id',
            'results_dir': results_dir
        }
    
    def test_get_export_metadata(self, sample_analysis):
        """Test getting export metadata for an analysis."""
        service = ExportService()
        
        metadata = service.get_export_metadata(sample_analysis['analysis_id'])
        
        assert metadata.analysis_id == 'test-analysis-id'
        assert metadata.analysis_type == 'similarity_heatmap'
        assert metadata.file_name == 'test_data.csv'
        assert metadata.parameters == {'metrics': ['r2_inner']}
        assert metadata.chart_config == {'color_scheme': 'viridis'}
    
    def test_export_png(self, sample_analysis):
        """Test exporting PNG visualization."""
        service = ExportService()
        
        file_bytes, filename = service.export_png(
            sample_analysis['analysis_id'],
            'r2_inner_heatmap'
        )
        
        assert file_bytes == b'PNG_CONTENT'
        assert filename == 'r2_inner_heatmap.png'
    
    def test_export_csv(self, sample_analysis):
        """Test exporting CSV data table."""
        service = ExportService()
        
        file_bytes, filename = service.export_csv(
            sample_analysis['analysis_id'],
            'r2_inner_matrix',
            include_metadata=False
        )
        
        csv_text = file_bytes.decode('utf-8')
        
        assert 'Sample,A,B' in csv_text
        assert filename == 'r2_inner_matrix.csv'
    
    def test_export_csv_with_metadata(self, sample_analysis):
        """Test exporting CSV with metadata comments."""
        service = ExportService()
        metadata = service.get_export_metadata(sample_analysis['analysis_id'])
        
        file_bytes, filename = service.export_csv(
            sample_analysis['analysis_id'],
            'r2_inner_matrix',
            metadata=metadata,
            include_metadata=True
        )
        
        csv_text = file_bytes.decode('utf-8')
        
        assert '# Analysis ID: test-analysis-id' in csv_text
        assert '# Analysis Type: similarity_heatmap' in csv_text
        assert 'Sample,A,B' in csv_text
    
    def test_export_zip(self, sample_analysis):
        """Test exporting all results as ZIP."""
        service = ExportService()
        
        file_bytes, filename = service.export_zip(
            sample_analysis['analysis_id'],
            include_metadata_file=False
        )
        
        # Verify it's a valid ZIP file
        zip_buffer = io.BytesIO(file_bytes)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            names = zf.namelist()
            assert 'visualizations/r2_inner_heatmap.png' in names
            assert 'data/r2_inner_matrix.csv' in names
        
        assert filename.startswith('analysis_test-ana')
        assert filename.endswith('.zip')
    
    def test_export_zip_with_metadata(self, sample_analysis):
        """Test exporting ZIP with metadata file."""
        service = ExportService()
        metadata = service.get_export_metadata(sample_analysis['analysis_id'])
        
        file_bytes, filename = service.export_zip(
            sample_analysis['analysis_id'],
            metadata=metadata,
            include_metadata_file=True
        )
        
        # Verify metadata.txt is included
        zip_buffer = io.BytesIO(file_bytes)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            names = zf.namelist()
            assert 'metadata.txt' in names
            
            # Read and verify metadata content
            metadata_content = zf.read('metadata.txt').decode('utf-8')
            assert 'Analysis ID: test-analysis-id' in metadata_content
    
    def test_get_available_exports(self, sample_analysis):
        """Test getting available exports for an analysis."""
        service = ExportService()
        
        exports = service.get_available_exports(sample_analysis['analysis_id'])
        
        assert 'visualizations' in exports
        assert 'data_tables' in exports
        assert 'batch' in exports
        
        # Check visualizations
        viz_names = [v['name'] for v in exports['visualizations']]
        assert 'r2_inner_heatmap' in viz_names
        
        # Check data tables
        table_names = [t['name'] for t in exports['data_tables']]
        assert 'r2_inner_matrix' in table_names
        
        # Check batch export option
        assert len(exports['batch']) == 1
        assert exports['batch'][0]['format'] == 'zip'
    
    def test_export_single_result_png(self, sample_analysis):
        """Test exporting single result as PNG."""
        service = ExportService()
        
        file_bytes, filename, mime_type = service.export_single_result(
            sample_analysis['analysis_id'],
            'r2_inner_heatmap',
            format='png'
        )
        
        assert file_bytes == b'PNG_CONTENT'
        assert filename == 'r2_inner_heatmap.png'
        assert mime_type == 'image/png'
    
    def test_export_single_result_csv(self, sample_analysis):
        """Test exporting single result as CSV."""
        service = ExportService()
        
        file_bytes, filename, mime_type = service.export_single_result(
            sample_analysis['analysis_id'],
            'r2_inner_matrix',
            format='csv'
        )
        
        assert filename == 'r2_inner_matrix.csv'
        assert mime_type == 'text/csv'
    
    def test_export_all_results(self, sample_analysis):
        """Test exporting all results as ZIP."""
        service = ExportService()
        
        file_bytes, filename, mime_type = service.export_all_results(
            sample_analysis['analysis_id']
        )
        
        assert mime_type == 'application/zip'
        assert filename.endswith('.zip')
        
        # Verify ZIP contents
        zip_buffer = io.BytesIO(file_bytes)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            names = zf.namelist()
            assert 'metadata.txt' in names
