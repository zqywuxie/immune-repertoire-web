"""
Annotation Service for the Immune Repertoire Analysis Web Application.
Manages visualization annotations for analysis results.
Requirements: 12.5
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from flask_app.models.database import db, Annotation, Analysis, AnalysisResult


@dataclass
class AnnotationData:
    """Represents an annotation on a visualization."""
    id: str
    analysis_id: str
    result_id: Optional[str]
    annotation_type: str
    content: Optional[str]
    position_x: float
    position_y: float
    style: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'result_id': self.result_id,
            'annotation_type': self.annotation_type,
            'content': self.content,
            'position_x': self.position_x,
            'position_y': self.position_y,
            'style': self.style,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AnnotationService:
    """
    Service for managing visualization annotations.
    Requirements: 12.5
    """
    
    # Supported annotation types
    ANNOTATION_TYPES = ['text', 'arrow', 'highlight', 'label', 'box', 'circle']
    
    # Default styles for each annotation type
    DEFAULT_STYLES = {
        'text': {
            'font_size': 12,
            'font_color': '#000000',
            'font_weight': 'normal',
            'background_color': None,
            'padding': 4
        },
        'arrow': {
            'color': '#FF0000',
            'width': 2,
            'head_size': 10,
            'style': 'solid'
        },
        'highlight': {
            'color': '#FFFF00',
            'opacity': 0.3,
            'border_color': None,
            'border_width': 0
        },
        'label': {
            'font_size': 10,
            'font_color': '#FFFFFF',
            'background_color': '#333333',
            'padding': 4,
            'border_radius': 4
        },
        'box': {
            'border_color': '#FF0000',
            'border_width': 2,
            'fill_color': None,
            'fill_opacity': 0.1
        },
        'circle': {
            'border_color': '#FF0000',
            'border_width': 2,
            'fill_color': None,
            'fill_opacity': 0.1,
            'radius': 20
        }
    }
    
    def __init__(self, app=None):
        """
        Initialize the annotation service.
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app

    def get_annotations(
        self,
        analysis_id: str,
        result_id: Optional[str] = None
    ) -> List[AnnotationData]:
        """
        Get all annotations for an analysis or specific result.
        
        Args:
            analysis_id: Analysis ID
            result_id: Result ID (optional, filters to specific result)
            
        Returns:
            List of AnnotationData objects
            
        Requirements: 12.5
        """
        query = Annotation.query.filter_by(analysis_id=analysis_id)
        
        if result_id:
            query = query.filter_by(result_id=result_id)
        
        annotations = query.order_by(Annotation.created_at).all()
        
        return [
            AnnotationData(
                id=a.id,
                analysis_id=a.analysis_id,
                result_id=a.result_id,
                annotation_type=a.annotation_type,
                content=a.content,
                position_x=a.position_x,
                position_y=a.position_y,
                style=a.style or {},
                created_at=a.created_at,
                updated_at=a.updated_at
            )
            for a in annotations
        ]
    
    def get_annotation(self, annotation_id: str) -> Optional[AnnotationData]:
        """
        Get a single annotation by ID.
        
        Args:
            annotation_id: Annotation ID
            
        Returns:
            AnnotationData or None if not found
            
        Requirements: 12.5
        """
        annotation = Annotation.query.get(annotation_id)
        
        if not annotation:
            return None
        
        return AnnotationData(
            id=annotation.id,
            analysis_id=annotation.analysis_id,
            result_id=annotation.result_id,
            annotation_type=annotation.annotation_type,
            content=annotation.content,
            position_x=annotation.position_x,
            position_y=annotation.position_y,
            style=annotation.style or {},
            created_at=annotation.created_at,
            updated_at=annotation.updated_at
        )
    
    def create_annotation(
        self,
        analysis_id: str,
        annotation_type: str,
        position_x: float,
        position_y: float,
        content: Optional[str] = None,
        result_id: Optional[str] = None,
        style: Optional[Dict[str, Any]] = None
    ) -> AnnotationData:
        """
        Create a new annotation.
        
        Args:
            analysis_id: Analysis ID
            annotation_type: Type of annotation
            position_x: X position
            position_y: Y position
            content: Text content (optional)
            result_id: Result ID (optional)
            style: Style properties (optional)
            
        Returns:
            Created AnnotationData object
            
        Requirements: 12.5
        """
        from exceptions import ValidationError, AnalysisNotFoundError
        
        # Validate analysis exists
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Validate result exists if provided
        if result_id:
            result = AnalysisResult.query.get(result_id)
            if not result or result.analysis_id != analysis_id:
                raise ValidationError(
                    message=f"Result not found or does not belong to analysis: {result_id}",
                    details={'result_id': result_id, 'analysis_id': analysis_id}
                )
        
        # Validate annotation type
        if annotation_type not in self.ANNOTATION_TYPES:
            raise ValidationError(
                message=f"Invalid annotation type: {annotation_type}",
                details={
                    'annotation_type': annotation_type,
                    'supported_types': self.ANNOTATION_TYPES
                }
            )
        
        # Merge with default style
        merged_style = self.DEFAULT_STYLES.get(annotation_type, {}).copy()
        if style:
            merged_style.update(style)
        
        # Create annotation
        annotation = Annotation(
            analysis_id=analysis_id,
            result_id=result_id,
            annotation_type=annotation_type,
            content=content,
            position_x=position_x,
            position_y=position_y,
            style=merged_style
        )
        
        try:
            db.session.add(annotation)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise
        
        return AnnotationData(
            id=annotation.id,
            analysis_id=annotation.analysis_id,
            result_id=annotation.result_id,
            annotation_type=annotation.annotation_type,
            content=annotation.content,
            position_x=annotation.position_x,
            position_y=annotation.position_y,
            style=annotation.style or {},
            created_at=annotation.created_at,
            updated_at=annotation.updated_at
        )
    
    def update_annotation(
        self,
        annotation_id: str,
        content: Optional[str] = None,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
        style: Optional[Dict[str, Any]] = None
    ) -> AnnotationData:
        """
        Update an existing annotation.
        
        Args:
            annotation_id: Annotation ID
            content: New text content (optional)
            position_x: New X position (optional)
            position_y: New Y position (optional)
            style: New style properties (optional)
            
        Returns:
            Updated AnnotationData object
            
        Requirements: 12.5
        """
        from exceptions import ValidationError
        
        annotation = Annotation.query.get(annotation_id)
        
        if not annotation:
            raise ValidationError(
                message=f"Annotation not found: {annotation_id}",
                details={'annotation_id': annotation_id}
            )
        
        # Update fields if provided
        if content is not None:
            annotation.content = content
        
        if position_x is not None:
            annotation.position_x = position_x
        
        if position_y is not None:
            annotation.position_y = position_y
        
        if style is not None:
            # Merge with existing style
            current_style = annotation.style or {}
            current_style.update(style)
            annotation.style = current_style
        
        annotation.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise
        
        return AnnotationData(
            id=annotation.id,
            analysis_id=annotation.analysis_id,
            result_id=annotation.result_id,
            annotation_type=annotation.annotation_type,
            content=annotation.content,
            position_x=annotation.position_x,
            position_y=annotation.position_y,
            style=annotation.style or {},
            created_at=annotation.created_at,
            updated_at=annotation.updated_at
        )
    
    def delete_annotation(self, annotation_id: str) -> bool:
        """
        Delete an annotation.
        
        Args:
            annotation_id: Annotation ID to delete
            
        Returns:
            True if deletion was successful
            
        Requirements: 12.5
        """
        from exceptions import ValidationError
        
        annotation = Annotation.query.get(annotation_id)
        
        if not annotation:
            raise ValidationError(
                message=f"Annotation not found: {annotation_id}",
                details={'annotation_id': annotation_id}
            )
        
        try:
            db.session.delete(annotation)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise
    
    def delete_all_annotations(self, analysis_id: str, result_id: Optional[str] = None) -> int:
        """
        Delete all annotations for an analysis or specific result.
        
        Args:
            analysis_id: Analysis ID
            result_id: Result ID (optional)
            
        Returns:
            Number of annotations deleted
            
        Requirements: 12.5
        """
        query = Annotation.query.filter_by(analysis_id=analysis_id)
        
        if result_id:
            query = query.filter_by(result_id=result_id)
        
        count = query.count()
        
        try:
            query.delete()
            db.session.commit()
            return count
        except Exception as e:
            db.session.rollback()
            raise
    
    def get_supported_types(self) -> List[str]:
        """Get list of supported annotation types."""
        return self.ANNOTATION_TYPES.copy()
    
    def get_default_style(self, annotation_type: str) -> Dict[str, Any]:
        """Get default style for an annotation type."""
        return self.DEFAULT_STYLES.get(annotation_type, {}).copy()


# Global service instance
_annotation_service: Optional[AnnotationService] = None


def init_annotation_service(app) -> AnnotationService:
    """Initialize the global annotation service instance."""
    global _annotation_service
    _annotation_service = AnnotationService(app)
    return _annotation_service


def get_annotation_service() -> AnnotationService:
    """Get the global annotation service instance."""
    if _annotation_service is None:
        raise RuntimeError("Annotation service not initialized. Call init_annotation_service first.")
    return _annotation_service
