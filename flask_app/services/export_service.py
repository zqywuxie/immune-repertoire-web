"""
Export Service for the Immune Repertoire Analysis Web Application.
Provides functionality for exporting analysis results in various formats.
Requirements: 6.1, 6.2, 6.3, 6.4

Export Formats:
1. PNG - Visualization images at 300 DPI
2. CSV - Numerical data and matrices
3. ZIP - Batch download of all results
"""
import io
import csv
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, BinaryIO
from dataclasses import dataclass

import pandas as pd


@dataclass
class ExportMetadata:
    """Metadata to include in exports. Requirements: 6.4"""
    analysis_id: str
    analysis_type: str
    file_name: str
    parameters: Dict[str, Any]
    chart_config: Dict[str, Any]
    created_at: datetime
    completed_at: Optional[datetime]
    export_timestamp: datetime = None
    
    def __post_init__(self):
        if self.export_timestamp is None:
            self.export_timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            'analysis_id': self.analysis_id,
            'analysis_type': self.analysis_type,
            'file_name': self.file_name,
            'parameters': self.parameters,
            'chart_config': self.chart_config,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'export_timestamp': self.export_timestamp.isoformat()
        }
    
    def to_text(self) -> str:
        """Convert metadata to human-readable text format."""
        lines = [
            "=" * 60,
            "Analysis Export Metadata",
            "=" * 60,
            f"Analysis ID: {self.analysis_id}",
            f"Analysis Type: {self.analysis_type}",
            f"Source File: {self.file_name}",
            f"Created At: {self.created_at.isoformat() if self.created_at else 'N/A'}",
            f"Completed At: {self.completed_at.isoformat() if self.completed_at else 'N/A'}",
            f"Export Timestamp: {self.export_timestamp.isoformat()}",
            "",
            "Parameters:",
            "-" * 40,
        ]
        
        for key, value in self.parameters.items():
            if not key.startswith('_'):  # Skip internal parameters
                lines.append(f"  {key}: {value}")
        
        lines.extend([
            "",
            "Chart Configuration:",
            "-" * 40,
        ])
        
        for key, value in self.chart_config.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


class ExportService:
    """
    Service for exporting analysis results.
    Supports PNG, CSV, and ZIP batch exports.
    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    
    # Default DPI for PNG exports
    DEFAULT_DPI = 300
    
    # Supported export formats
    SUPPORTED_FORMATS = ['png', 'csv', 'zip']
    
    def __init__(self, results_folder: Optional[str] = None):
        """
        Initialize the export service.
        
        Args:
            results_folder: Path to the results folder
        """
        self.results_folder = results_folder
    
    def export_png(
        self,
        analysis_id: str,
        result_name: str,
        metadata: Optional[ExportMetadata] = None
    ) -> Tuple[bytes, str]:
        """
        Export a visualization as PNG at 300 DPI.
        
        Args:
            analysis_id: Analysis task ID
            result_name: Name of the result to export
            metadata: Optional metadata to include
            
        Returns:
            Tuple of (file bytes, filename)
            
        Requirements: 6.1
        """
        from models.database import AnalysisResult
        from exceptions import AnalysisNotFoundError, StorageError
        
        # Find the result
        result = AnalysisResult.query.filter_by(
            analysis_id=analysis_id,
            name=result_name,
            result_type='visualization'
        ).first()
        
        if not result:
            raise AnalysisNotFoundError(
                message=f"Visualization result not found: {result_name}",
                details={'analysis_id': analysis_id, 'result_name': result_name}
            )
        
        file_path = Path(result.file_path)
        if not file_path.exists():
            raise StorageError(
                message="Result file not found on disk",
                details={'file_path': str(file_path)}
            )
        
        # Read the PNG file
        with open(file_path, 'rb') as f:
            png_bytes = f.read()
        
        # Generate filename
        filename = f"{result_name}.png"
        
        return png_bytes, filename
    
    def export_csv(
        self,
        analysis_id: str,
        result_name: str,
        metadata: Optional[ExportMetadata] = None,
        include_metadata: bool = True
    ) -> Tuple[bytes, str]:
        """
        Export data as CSV.
        
        Args:
            analysis_id: Analysis task ID
            result_name: Name of the result to export
            metadata: Optional metadata to include
            include_metadata: Whether to include metadata as comments
            
        Returns:
            Tuple of (file bytes, filename)
            
        Requirements: 6.2, 6.4
        """
        from models.database import AnalysisResult
        from exceptions import AnalysisNotFoundError, StorageError
        
        # Find the result
        result = AnalysisResult.query.filter_by(
            analysis_id=analysis_id,
            name=result_name,
            result_type='data_table'
        ).first()
        
        if not result:
            raise AnalysisNotFoundError(
                message=f"Data table result not found: {result_name}",
                details={'analysis_id': analysis_id, 'result_name': result_name}
            )
        
        # Get table data
        table_data = result.table_data
        if not table_data:
            raise StorageError(
                message="Table data is empty",
                details={'result_name': result_name}
            )
        
        # Build CSV content
        output = io.StringIO()
        
        # Add metadata as comments if requested
        if include_metadata and metadata:
            output.write(f"# Analysis ID: {metadata.analysis_id}\n")
            output.write(f"# Analysis Type: {metadata.analysis_type}\n")
            output.write(f"# Source File: {metadata.file_name}\n")
            output.write(f"# Export Timestamp: {metadata.export_timestamp.isoformat()}\n")
            output.write("#\n")
        
        # Write CSV data
        columns = table_data.get('columns', [])
        data = table_data.get('data', [])
        
        # Handle columns that might be dicts with 'name' key
        if columns and isinstance(columns[0], dict):
            fieldnames = [col.get('name', str(col)) for col in columns]
        else:
            fieldnames = columns
        
        # If data is empty, just write headers
        if not data:
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
        else:
            # Use the keys from the first data row as fieldnames if they don't match
            data_keys = list(data[0].keys()) if data else fieldnames
            writer = csv.DictWriter(output, fieldnames=data_keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        
        csv_bytes = output.getvalue().encode('utf-8')
        filename = f"{result_name}.csv"
        
        return csv_bytes, filename
    
    def export_csv_from_file(
        self,
        analysis_id: str,
        result_name: str,
        metadata: Optional[ExportMetadata] = None
    ) -> Tuple[bytes, str]:
        """
        Export CSV from saved file on disk.
        
        Args:
            analysis_id: Analysis task ID
            result_name: Name of the result to export
            metadata: Optional metadata to include
            
        Returns:
            Tuple of (file bytes, filename)
            
        Requirements: 6.2
        """
        from models.database import AnalysisResult
        from exceptions import AnalysisNotFoundError, StorageError
        
        # Find the result
        result = AnalysisResult.query.filter_by(
            analysis_id=analysis_id,
            name=result_name
        ).first()
        
        if not result:
            raise AnalysisNotFoundError(
                message=f"Result not found: {result_name}",
                details={'analysis_id': analysis_id, 'result_name': result_name}
            )
        
        # Check if CSV file exists
        file_path = Path(result.file_path)
        csv_path = file_path.with_suffix('.csv')
        
        if not csv_path.exists():
            # Try to generate from table_data
            if result.table_data:
                return self.export_csv(analysis_id, result_name, metadata)
            raise StorageError(
                message="CSV file not found on disk",
                details={'file_path': str(csv_path)}
            )
        
        # Read the CSV file
        with open(csv_path, 'rb') as f:
            csv_bytes = f.read()
        
        filename = f"{result_name}.csv"
        
        return csv_bytes, filename

    
    def export_zip(
        self,
        analysis_id: str,
        metadata: Optional[ExportMetadata] = None,
        include_metadata_file: bool = True
    ) -> Tuple[bytes, str]:
        """
        Export all analysis results as a ZIP archive.
        
        Args:
            analysis_id: Analysis task ID
            metadata: Optional metadata to include
            include_metadata_file: Whether to include a metadata.txt file
            
        Returns:
            Tuple of (file bytes, filename)
            
        Requirements: 6.3, 6.4
        """
        from models.database import Analysis, AnalysisResult
        from exceptions import AnalysisNotFoundError, StorageError
        
        # Get analysis record
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Get all results for this analysis
        results = AnalysisResult.query.filter_by(analysis_id=analysis_id).all()
        
        if not results:
            raise StorageError(
                message="No results found for this analysis",
                details={'analysis_id': analysis_id}
            )
        
        # Create ZIP archive in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add metadata file if requested
            if include_metadata_file and metadata:
                metadata_content = metadata.to_text()
                zip_file.writestr('metadata.txt', metadata_content)
            
            # Track added files to avoid duplicates
            added_files = set()
            
            # Add all result files
            for result in results:
                file_path = Path(result.file_path)
                
                # Add visualization files (PNG) - organize by chain for heatmap results
                if result.result_type == 'visualization' and file_path.exists():
                    # Check if result name follows chain pattern (e.g., "IGH_r2_inner_heatmap")
                    parts = result.name.split('_')
                    if len(parts) >= 3 and parts[-1] == 'heatmap':
                        # Group by chain: chain/metric_heatmap.png
                        chain = parts[0]
                        metric_name = '_'.join(parts[1:])  # e.g., "r2_inner_heatmap"
                        filename = f"{chain}/{metric_name}.png"
                    else:
                        # Default: use result name directly
                        filename = f"{result.name}.png"
                    
                    if filename not in added_files:
                        with open(file_path, 'rb') as f:
                            zip_file.writestr(filename, f.read())
                        added_files.add(filename)
                
                # Add summary files
                elif result.result_type == 'summary' and file_path.exists():
                    filename = f"{result.name}{file_path.suffix}"
                    if filename not in added_files:
                        with open(file_path, 'rb') as f:
                            zip_file.writestr(filename, f.read())
                        added_files.add(filename)
        
        zip_buffer.seek(0)
        zip_bytes = zip_buffer.read()
        
        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"analysis_{analysis_id[:8]}_{timestamp}.zip"
        
        return zip_bytes, filename
    
    def _table_data_to_csv(self, table_data: Dict[str, Any]) -> bytes:
        """
        Convert table_data dictionary to CSV bytes.
        
        Args:
            table_data: Dictionary with 'columns' and 'data' keys
            
        Returns:
            CSV content as bytes
        """
        output = io.StringIO()
        
        columns = table_data.get('columns', [])
        data = table_data.get('data', [])
        
        # Extract column names - handle both list of strings and list of dicts
        if columns and isinstance(columns[0], dict):
            fieldnames = [col['name'] for col in columns]
        else:
            fieldnames = columns
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        
        return output.getvalue().encode('utf-8')
    
    def get_export_metadata(self, analysis_id: str) -> ExportMetadata:
        """
        Get metadata for an analysis export.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            ExportMetadata object
            
        Requirements: 6.4
        """
        from models.database import Analysis, File
        from exceptions import AnalysisNotFoundError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Get source file name
        file_record = File.query.get(analysis.file_id)
        file_name = file_record.original_name if file_record else 'Unknown'
        
        return ExportMetadata(
            analysis_id=analysis.id,
            analysis_type=analysis.type,
            file_name=file_name,
            parameters=analysis.parameters or {},
            chart_config=analysis.chart_config or {},
            created_at=analysis.created_at,
            completed_at=analysis.completed_at
        )
    
    def export_single_result(
        self,
        analysis_id: str,
        result_name: str,
        format: str = 'png',
        include_metadata: bool = True
    ) -> Tuple[bytes, str, str]:
        """
        Export a single result in the specified format.
        
        Args:
            analysis_id: Analysis task ID
            result_name: Name of the result to export
            format: Export format ('png', 'csv')
            include_metadata: Whether to include metadata
            
        Returns:
            Tuple of (file bytes, filename, mime_type)
            
        Requirements: 6.1, 6.2, 6.4
        """
        from exceptions import ValidationError
        
        if format not in ['png', 'csv']:
            raise ValidationError(
                message=f"Unsupported export format: {format}",
                details={'format': format, 'supported_formats': ['png', 'csv']}
            )
        
        # Get metadata if needed
        metadata = None
        if include_metadata:
            metadata = self.get_export_metadata(analysis_id)
        
        if format == 'png':
            file_bytes, filename = self.export_png(analysis_id, result_name, metadata)
            mime_type = 'image/png'
        else:  # csv
            file_bytes, filename = self.export_csv(analysis_id, result_name, metadata)
            mime_type = 'text/csv'
        
        return file_bytes, filename, mime_type
    
    def export_all_results(
        self,
        analysis_id: str,
        include_metadata: bool = True
    ) -> Tuple[bytes, str, str]:
        """
        Export all results as a ZIP archive.
        
        Args:
            analysis_id: Analysis task ID
            include_metadata: Whether to include metadata file
            
        Returns:
            Tuple of (file bytes, filename, mime_type)
            
        Requirements: 6.3, 6.4
        """
        # Get metadata
        metadata = None
        if include_metadata:
            metadata = self.get_export_metadata(analysis_id)
        
        file_bytes, filename = self.export_zip(analysis_id, metadata, include_metadata)
        mime_type = 'application/zip'
        
        return file_bytes, filename, mime_type
    
    def get_available_exports(self, analysis_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get list of available exports for an analysis.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            Dictionary with available exports by type
        """
        from models.database import Analysis, AnalysisResult
        from exceptions import AnalysisNotFoundError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        results = AnalysisResult.query.filter_by(analysis_id=analysis_id).all()
        
        exports = {
            'visualizations': [],
            'data_tables': [],
            'batch': []
        }
        
        for result in results:
            if result.result_type == 'visualization':
                exports['visualizations'].append({
                    'name': result.name,
                    'format': 'png',
                    'mime_type': 'image/png'
                })
            elif result.result_type == 'data_table':
                exports['data_tables'].append({
                    'name': result.name,
                    'format': 'csv',
                    'mime_type': 'text/csv'
                })
        
        # Add batch export option if there are results
        if results:
            exports['batch'].append({
                'name': 'all_results',
                'format': 'zip',
                'mime_type': 'application/zip',
                'description': 'Download all results as ZIP archive'
            })
        
        return exports


# Global service instance
export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get the global export service instance."""
    global export_service
    if export_service is None:
        export_service = ExportService()
    return export_service


def init_export_service(results_folder: str) -> ExportService:
    """Initialize the global export service."""
    global export_service
    export_service = ExportService(results_folder)
    return export_service
