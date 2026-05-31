"""
SQLAlchemy database models for the Immune Repertoire Analysis Web Application.
Requirements: 1.4, 1.5, 10.1
"""
import uuid
from datetime import datetime
from typing import Any, Dict

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'original_name': self.original_name,
            'size': self.size,
            'mime_type': self.mime_type,
            'columns': self.columns or [],
            'row_count': self.row_count,
            'storage_path': self.storage_path,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'project': self.project or 'default',
        }


class MappingTemplate(db.Model):
    """Model for saved field mapping templates."""
    __tablename__ = 'mapping_templates'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    mapping = db.Column(db.JSON, nullable=False)  # Dict[str, str]
    analysis_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'mapping': self.mapping or {},
            'analysis_type': self.analysis_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'file_id': self.file_id,
            'field_mapping': self.field_mapping or {},
            'parameters': self.parameters or {},
            'chart_config': self.chart_config or {},
            'status': self.status,
            'progress': self.progress,
            'current_step': self.current_step,
            'error_message': self.error_message,
            'results_path': self.results_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'mode': self.mode,
            'scheme_id': self.scheme_id,
            'scheme_name': self.scheme_name,
            'selected_fields': self.selected_fields or [],
        }


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'result_type': self.result_type,
            'name': self.name,
            'file_path': self.file_path,
            'mime_type': self.mime_type,
            'table_data': self.table_data,
            'result_metadata': self.result_metadata or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CustomParameter(db.Model):
    """Model for saved custom parameter templates."""
    __tablename__ = 'custom_parameters'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    analysis_type = db.Column(db.String(50), nullable=False)
    parameters = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'analysis_type': self.analysis_type,
            'parameters': self.parameters or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'result_id': self.result_id,
            'annotation_type': self.annotation_type,
            'content': self.content,
            'position_x': self.position_x,
            'position_y': self.position_y,
            'style': self.style or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'sample_ids': self.sample_ids or [],
            'description': self.description,
            'file_id': self.file_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Project(db.Model):
    """Business project entity for project/sample centered workflows."""
    __tablename__ = 'projects'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    institution = db.Column(db.String(255), nullable=True)
    cooperation_level = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='active')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    assets = db.relationship("ProjectAsset", back_populates="project", cascade="all, delete-orphan")
    samples = db.relationship("SampleRecord", back_populates="project", cascade="all, delete-orphan")
    group_specs = db.relationship("ProjectGroupSpec", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        asset_counts: Dict[str, int] = {}
        for asset in self.assets:
            asset_type = str(asset.asset_type or '').strip() or 'unknown'
            asset_counts[asset_type] = asset_counts.get(asset_type, 0) + 1

        return {
            'id': self.id,
            'name': self.name,
            'institution': self.institution,
            'cooperation_level': self.cooperation_level,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'asset_counts': asset_counts,
            'sample_count': len(self.samples),
            'group_spec_count': len(self.group_specs),
            'result_count': asset_counts.get('processed_result', 0),
            'has_datapoint': asset_counts.get('datapoint', 0) > 0,
            'has_pep': asset_counts.get('pep', 0) > 0,
            'has_sample_summary': asset_counts.get('sample_summary', 0) > 0,
            'has_group_spec': asset_counts.get('group_spec', 0) > 0,
        }


class ProjectAsset(db.Model):
    """Stored project file or generated project result."""
    __tablename__ = 'project_assets'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=False, index=True)
    asset_type = db.Column(db.String(50), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    size = db.Column(db.Integer, nullable=False, default=0)
    metadata_json = db.Column(db.JSON, nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    project = db.relationship("Project", back_populates="assets")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'project_id': self.project_id,
            'asset_type': self.asset_type,
            'original_name': self.original_name,
            'storage_path': self.storage_path,
            'mime_type': self.mime_type,
            'size': self.size,
            'metadata': self.metadata_json or {},
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class SampleRecord(db.Model):
    """Sample metadata imported from project sample summary tables."""
    __tablename__ = 'sample_records'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=False, index=True)
    sample_id = db.Column(db.String(255), nullable=True, index=True)
    sample_name = db.Column(db.String(255), nullable=False, index=True)
    sequence_id = db.Column(db.String(255), nullable=True)
    spices = db.Column(db.String(255), nullable=True)
    institution = db.Column(db.String(255), nullable=True)
    chain_flag = db.Column(db.String(255), nullable=True)
    is_healthy = db.Column(db.String(120), nullable=True)
    illness = db.Column(db.String(255), nullable=True)
    is_pe = db.Column(db.String(120), nullable=True)
    contain_method = db.Column(db.String(255), nullable=True)
    iso_tag = db.Column(db.String(255), nullable=True)
    extra_metadata = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", back_populates="samples")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project.name if self.project else None,
            'sample_id': self.sample_id,
            'sample_name': self.sample_name,
            'sequence_id': self.sequence_id,
            'spices': self.spices,
            'institution': self.institution,
            'chain_flag': self.chain_flag,
            'is_healthy': self.is_healthy,
            'illness': self.illness,
            'is_pe': self.is_pe,
            'contain_method': self.contain_method,
            'iso_tag': self.iso_tag,
            'extra_metadata': self.extra_metadata or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ProjectGroupSpec(db.Model):
    """Saved group ordering/specification for a project."""
    __tablename__ = 'project_group_specs'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False, default='default')
    spec_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", back_populates="group_specs")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'spec_json': self.spec_json or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
