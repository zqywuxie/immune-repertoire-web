"""
SQLAlchemy database models for the Immune Repertoire Analysis Web Application.
Requirements: 1.4, 1.5, 10.1
"""
import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# Database instance - will be initialized by the app
db = SQLAlchemy()


def generate_uuid():
    """Generate a UUID string."""
    return str(uuid.uuid4())


class File(db.Model):
    """Model for uploaded data files. Requirements: 1.4, 1.5"""
    __tablename__ = 'files'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    columns = db.Column(db.JSON, nullable=False)  # List[str]
    row_count = db.Column(db.Integer, nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    project = db.Column(db.String(255), nullable=True, default='default')  # Project/folder name for organization
    
    # Relationships
    analyses = db.relationship("Analysis", back_populates="file", cascade="all, delete-orphan")


class MappingTemplate(db.Model):
    """Model for saved field mapping templates."""
    __tablename__ = 'mapping_templates'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    mapping = db.Column(db.JSON, nullable=False)  # Dict[str, str]
    analysis_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Analysis(db.Model):
    """Model for analysis tasks. Requirements: 7.6, 10.1"""
    __tablename__ = 'analyses'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    type = db.Column(db.String(50), nullable=False)
    file_id = db.Column(db.String(36), db.ForeignKey('files.id'), nullable=True)
    field_mapping = db.Column(db.JSON, nullable=False)
    parameters = db.Column(db.JSON, nullable=False)
    chart_config = db.Column(db.JSON, nullable=True)  # Chart configuration parameters
    status = db.Column(db.String(20), nullable=False, default='pending')
    progress = db.Column(db.Float, default=0.0)
    current_step = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    results_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # New fields for unified analysis - Requirements: 7.6, 10.1
    mode = db.Column(db.String(20), nullable=True)  # 'scheme' or 'custom'
    scheme_id = db.Column(db.String(100), nullable=True)  # Analysis scheme ID
    scheme_name = db.Column(db.String(255), nullable=True)  # Analysis scheme name
    selected_fields = db.Column(db.JSON, nullable=True)  # List of selected fields for custom mode
    
    # Relationships
    file = db.relationship("File", back_populates="analyses")
    results = db.relationship("AnalysisResult", back_populates="analysis", cascade="all, delete-orphan")


class AnalysisResult(db.Model):
    """Model for analysis results (visualizations, data tables)."""
    __tablename__ = 'analysis_results'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    analysis_id = db.Column(db.String(36), db.ForeignKey('analyses.id'), nullable=False)
    result_type = db.Column(db.String(50), nullable=False)  # visualization, data_table, summary
    name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    table_data = db.Column(db.JSON, nullable=True)  # Data table content for frontend display
    result_metadata = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    analysis = db.relationship("Analysis", back_populates="results")


class CustomParameter(db.Model):
    """Model for saved custom parameter templates."""
    __tablename__ = 'custom_parameters'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    analysis_type = db.Column(db.String(50), nullable=False)
    parameters = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Annotation(db.Model):
    """Model for visualization annotations. Requirements: 12.5"""
    __tablename__ = 'annotations'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    analysis_id = db.Column(db.String(36), db.ForeignKey('analyses.id'), nullable=False)
    result_id = db.Column(db.String(36), db.ForeignKey('analysis_results.id'), nullable=True)
    annotation_type = db.Column(db.String(50), nullable=False)  # text, arrow, highlight, label
    content = db.Column(db.Text, nullable=True)  # Text content for text/label annotations
    position_x = db.Column(db.Float, nullable=False)  # X position (percentage or absolute)
    position_y = db.Column(db.Float, nullable=False)  # Y position (percentage or absolute)
    style = db.Column(db.JSON, nullable=True)  # Style properties (color, font_size, etc.)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    analysis = db.relationship("Analysis", backref=db.backref("annotations", cascade="all, delete-orphan"))


class SampleGroup(db.Model):
    """Model for sample groups. Requirements: 16.1, 16.2"""
    __tablename__ = 'sample_groups'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    sample_ids = db.Column(db.JSON, nullable=False)  # List[str] - sample identifiers
    description = db.Column(db.Text, nullable=True)
    file_id = db.Column(db.String(36), db.ForeignKey('files.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    file = db.relationship("File", backref=db.backref("sample_groups", cascade="all, delete-orphan"))
