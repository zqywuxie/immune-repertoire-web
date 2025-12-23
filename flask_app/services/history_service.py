"""
History Service for the Immune Repertoire Analysis Web Application.
Manages analysis history including auto-save, query, and deletion.
Requirements: 10.1, 10.2, 10.3, 10.4
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import shutil

from models.database import db, Analysis, AnalysisResult, File


@dataclass
class HistoryItem:
    """Represents a single history item. Requirements: 7.6, 10.1, 10.2"""
    id: str
    analysis_type: str
    file_id: str
    file_name: str
    status: str
    parameters: Dict[str, Any]
    chart_config: Dict[str, Any]
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    # New fields for unified analysis - Requirements: 7.6, 10.1
    mode: Optional[str] = None  # 'scheme' or 'custom'
    scheme_id: Optional[str] = None
    scheme_name: Optional[str] = None
    selected_fields: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'type': self.analysis_type,  # Add 'type' field for frontend compatibility
            'analysis_type': self.analysis_type,
            'file_id': self.file_id,
            'file_name': self.file_name,
            'status': self.status,
            'parameters': self.parameters,
            'chart_config': self.chart_config,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            # Include new fields
            'mode': self.mode,
            'scheme_id': self.scheme_id,
            'scheme_name': self.scheme_name,
            'selected_fields': self.selected_fields or []
        }


@dataclass
class HistoryListResponse:
    """Response for history list queries."""
    items: List[HistoryItem]
    total: int
    page: int
    page_size: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'items': [item.to_dict() for item in self.items],
            'total': self.total,
            'page': self.page,
            'page_size': self.page_size
        }


class HistoryService:
    """
    Service for managing analysis history.
    Requirements: 10.1, 10.2, 10.3, 10.4
    """
    
    # Analysis type display names
    ANALYSIS_TYPE_NAMES = {
        'similarity_heatmap': '相似度热图',
        'sequencing_depth': '测序深度分析',
        'diversity_metrics': '多样性指标分析',
        'chain_specific': '链特异性分析'
    }
    
    def __init__(self, app=None, results_folder: Optional[str] = None):
        """
        Initialize the history service.
        
        Args:
            app: Flask application instance (optional)
            results_folder: Path to store analysis results
        """
        self.app = app
        self.results_folder = results_folder
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app
        self.results_folder = app.config.get('RESULTS_FOLDER', 'data/results')
    
    def get_history(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
        type_filter: Optional[str] = None
    ) -> HistoryListResponse:
        """
        Get paginated analysis history.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            status_filter: Filter by status (optional)
            type_filter: Filter by analysis type (optional)
            
        Returns:
            HistoryListResponse with paginated history items
            
        Requirements: 10.2
        """
        # Build query
        query = Analysis.query
        
        # Apply filters
        if status_filter:
            query = query.filter(Analysis.status == status_filter)
        
        if type_filter:
            query = query.filter(Analysis.type == type_filter)
        
        # Get total count
        total = query.count()
        
        # Apply pagination and ordering
        offset = (page - 1) * page_size
        analyses = query.order_by(Analysis.created_at.desc()) \
                       .offset(offset) \
                       .limit(page_size) \
                       .all()
        
        # Convert to history items
        items = []
        for analysis in analyses:
            # Get file name
            file_name = 'Unknown'
            if analysis.file:
                file_name = analysis.file.original_name
            
            item = HistoryItem(
                id=analysis.id,
                analysis_type=analysis.type,
                file_id=analysis.file_id,
                file_name=file_name,
                status=analysis.status,
                parameters=analysis.parameters or {},
                chart_config=analysis.chart_config or {},
                created_at=analysis.created_at,
                completed_at=analysis.completed_at,
                error_message=analysis.error_message,
                # New fields for unified analysis
                mode=analysis.mode,
                scheme_id=analysis.scheme_id,
                scheme_name=analysis.scheme_name,
                selected_fields=analysis.selected_fields
            )
            items.append(item)
        
        return HistoryListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size
        )
    
    def get_history_item(self, analysis_id: str) -> Optional[HistoryItem]:
        """
        Get a single history item by analysis ID.
        
        Args:
            analysis_id: Analysis ID
            
        Returns:
            HistoryItem or None if not found
            
        Requirements: 10.3
        """
        analysis = Analysis.query.get(analysis_id)
        
        if not analysis:
            return None
        
        # Get file name
        file_name = 'Unknown'
        if analysis.file:
            file_name = analysis.file.original_name
        
        return HistoryItem(
            id=analysis.id,
            analysis_type=analysis.type,
            file_id=analysis.file_id,
            file_name=file_name,
            status=analysis.status,
            parameters=analysis.parameters or {},
            chart_config=analysis.chart_config or {},
            created_at=analysis.created_at,
            completed_at=analysis.completed_at,
            error_message=analysis.error_message,
            # New fields for unified analysis
            mode=analysis.mode,
            scheme_id=analysis.scheme_id,
            scheme_name=analysis.scheme_name,
            selected_fields=analysis.selected_fields
        )
    
    def delete_history_item(self, analysis_id: str) -> bool:
        """
        Delete a history item and its associated files.
        
        Args:
            analysis_id: Analysis ID to delete
            
        Returns:
            True if deletion was successful
            
        Requirements: 10.4
        """
        from exceptions import AnalysisNotFoundError
        
        analysis = Analysis.query.get(analysis_id)
        
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Delete result files from disk
        if analysis.results_path:
            results_dir = Path(analysis.results_path)
            if results_dir.exists() and results_dir.is_dir():
                try:
                    shutil.rmtree(results_dir)
                except Exception as e:
                    # Log error but continue with database deletion
                    if self.app:
                        self.app.logger.warning(
                            f"Failed to delete results directory {results_dir}: {e}"
                        )
        
        # Delete individual result files
        for result in analysis.results:
            if result.file_path:
                file_path = Path(result.file_path)
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        if self.app:
                            self.app.logger.warning(
                                f"Failed to delete result file {file_path}: {e}"
                            )
        
        # Delete from database (cascade will delete AnalysisResult records)
        try:
            db.session.delete(analysis)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            if self.app:
                self.app.logger.error(f"Failed to delete analysis {analysis_id}: {e}")
            raise
    
    def get_analysis_type_name(self, analysis_type: str) -> str:
        """Get display name for analysis type."""
        return self.ANALYSIS_TYPE_NAMES.get(analysis_type, analysis_type)
    
    def get_status_counts(self) -> Dict[str, int]:
        """
        Get count of analyses by status.
        
        Returns:
            Dictionary mapping status to count
        """
        from sqlalchemy import func
        
        results = db.session.query(
            Analysis.status,
            func.count(Analysis.id)
        ).group_by(Analysis.status).all()
        
        return {status: count for status, count in results}
    
    def get_type_counts(self) -> Dict[str, int]:
        """
        Get count of analyses by type.
        
        Returns:
            Dictionary mapping type to count
        """
        from sqlalchemy import func
        
        results = db.session.query(
            Analysis.type,
            func.count(Analysis.id)
        ).group_by(Analysis.type).all()
        
        return {analysis_type: count for analysis_type, count in results}


# Global service instance
_history_service: Optional[HistoryService] = None


def init_history_service(app) -> HistoryService:
    """Initialize the global history service instance."""
    global _history_service
    _history_service = HistoryService(app)
    return _history_service


def get_history_service() -> HistoryService:
    """Get the global history service instance."""
    if _history_service is None:
        raise RuntimeError("History service not initialized. Call init_history_service first.")
    return _history_service
