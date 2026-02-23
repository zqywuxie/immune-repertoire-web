"""
Parameter Template Service for the Immune Repertoire Analysis Web Application.
Manages custom parameter templates for analysis configurations.
Requirements: 12.3, 12.4
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from flask_app.models.database import db, CustomParameter


@dataclass
class ParameterTemplate:
    """Represents a custom parameter template."""
    id: str
    name: str
    analysis_type: str
    parameters: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'analysis_type': self.analysis_type,
            'parameters': self.parameters,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ParameterTemplateService:
    """
    Service for managing custom parameter templates.
    Requirements: 12.3, 12.4
    """
    
    # Supported analysis types and their default parameters
    ANALYSIS_TYPE_DEFAULTS = {
        'similarity_heatmap': {
            'metrics': ['r2_inner', 'r2_outer', 'cdr3_sharing', 'expression_sharing', 'morisita_horn', 'sorensen'],
            'chains': ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG'],
            'min_reads': 100,
            'normalize': True
        },
        'sequencing_depth': {
            'baseline_sample': None,
            'metrics': ['total_rna', 'reads_umi', 'migs_good', 'reads_good'],
            'show_percentage_diff': True
        },
        'diversity_metrics': {
            'metrics': ['d50', 'gini', 'shannon', 'simpson'],
            'baseline_sample': None,
            'group_by': None,
            'show_group_averages': True
        },
        'chain_specific': {
            'chains': ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG'],
            'metric': 'ucdr3',
            'show_combined': True,
            'show_statistics': True
        }
    }
    
    def __init__(self, app=None):
        """
        Initialize the parameter template service.
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app

    def get_templates(
        self,
        analysis_type: Optional[str] = None
    ) -> List[ParameterTemplate]:
        """
        Get all parameter templates, optionally filtered by analysis type.
        
        Args:
            analysis_type: Filter by analysis type (optional)
            
        Returns:
            List of ParameterTemplate objects
            
        Requirements: 12.4
        """
        query = CustomParameter.query
        
        if analysis_type:
            query = query.filter_by(analysis_type=analysis_type)
        
        templates = query.order_by(CustomParameter.updated_at.desc()).all()
        
        return [
            ParameterTemplate(
                id=t.id,
                name=t.name,
                analysis_type=t.analysis_type,
                parameters=t.parameters,
                created_at=t.created_at,
                updated_at=t.updated_at
            )
            for t in templates
        ]
    
    def get_template(self, template_id: str) -> Optional[ParameterTemplate]:
        """
        Get a parameter template by ID.
        
        Args:
            template_id: Template ID
            
        Returns:
            ParameterTemplate or None if not found
            
        Requirements: 12.4
        """
        template = CustomParameter.query.get(template_id)
        
        if not template:
            return None
        
        return ParameterTemplate(
            id=template.id,
            name=template.name,
            analysis_type=template.analysis_type,
            parameters=template.parameters,
            created_at=template.created_at,
            updated_at=template.updated_at
        )
    
    def save_template(
        self,
        name: str,
        analysis_type: str,
        parameters: Dict[str, Any],
        template_id: Optional[str] = None
    ) -> ParameterTemplate:
        """
        Save a parameter template.
        
        Args:
            name: Template name
            analysis_type: Analysis type
            parameters: Parameter dictionary
            template_id: Existing template ID to update (optional)
            
        Returns:
            Saved ParameterTemplate object
            
        Requirements: 12.4
        """
        from exceptions import ValidationError
        
        # Validate analysis type
        if analysis_type not in self.ANALYSIS_TYPE_DEFAULTS:
            raise ValidationError(
                message=f"Unsupported analysis type: {analysis_type}",
                details={
                    'analysis_type': analysis_type,
                    'supported_types': list(self.ANALYSIS_TYPE_DEFAULTS.keys())
                }
            )
        
        if template_id:
            # Update existing template
            template = CustomParameter.query.get(template_id)
            if not template:
                raise ValidationError(
                    message=f"Template not found: {template_id}",
                    details={'template_id': template_id}
                )
            
            template.name = name
            template.analysis_type = analysis_type
            template.parameters = parameters
            template.updated_at = datetime.utcnow()
        else:
            # Create new template
            template = CustomParameter(
                name=name,
                analysis_type=analysis_type,
                parameters=parameters
            )
            db.session.add(template)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise
        
        return ParameterTemplate(
            id=template.id,
            name=template.name,
            analysis_type=template.analysis_type,
            parameters=template.parameters,
            created_at=template.created_at,
            updated_at=template.updated_at
        )
    
    def delete_template(self, template_id: str) -> bool:
        """
        Delete a parameter template.
        
        Args:
            template_id: Template ID to delete
            
        Returns:
            True if deletion was successful
            
        Requirements: 12.4
        """
        from exceptions import ValidationError
        
        template = CustomParameter.query.get(template_id)
        
        if not template:
            raise ValidationError(
                message=f"Template not found: {template_id}",
                details={'template_id': template_id}
            )
        
        try:
            db.session.delete(template)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise
    
    def get_default_parameters(self, analysis_type: str) -> Dict[str, Any]:
        """
        Get default parameters for an analysis type.
        
        Args:
            analysis_type: Analysis type
            
        Returns:
            Default parameters dictionary
            
        Requirements: 12.3
        """
        return self.ANALYSIS_TYPE_DEFAULTS.get(analysis_type, {}).copy()
    
    def get_supported_analysis_types(self) -> List[str]:
        """Get list of supported analysis types."""
        return list(self.ANALYSIS_TYPE_DEFAULTS.keys())
    
    def validate_parameters(
        self,
        analysis_type: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Validate parameters for an analysis type.
        
        Args:
            analysis_type: Analysis type
            parameters: Parameters to validate
            
        Returns:
            Dictionary of field names to error messages (empty if valid)
        """
        errors = {}
        
        if analysis_type not in self.ANALYSIS_TYPE_DEFAULTS:
            errors['analysis_type'] = [f"Unsupported analysis type: {analysis_type}"]
            return errors
        
        # Validate based on analysis type
        if analysis_type == 'similarity_heatmap':
            errors.update(self._validate_similarity_params(parameters))
        elif analysis_type == 'sequencing_depth':
            errors.update(self._validate_sequencing_params(parameters))
        elif analysis_type == 'diversity_metrics':
            errors.update(self._validate_diversity_params(parameters))
        elif analysis_type == 'chain_specific':
            errors.update(self._validate_chain_params(parameters))
        
        return errors
    
    def _validate_similarity_params(self, params: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate similarity heatmap parameters."""
        errors = {}
        valid_metrics = ['r2_inner', 'r2_outer', 'cdr3_sharing', 'expression_sharing', 'morisita_horn', 'sorensen']
        valid_chains = ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']
        
        if 'metrics' in params:
            metrics = params['metrics']
            if not isinstance(metrics, list):
                errors['metrics'] = ['Metrics must be a list']
            else:
                invalid = [m for m in metrics if m not in valid_metrics]
                if invalid:
                    errors['metrics'] = [f"Invalid metrics: {', '.join(invalid)}"]
        
        if 'chains' in params:
            chains = params['chains']
            if not isinstance(chains, list):
                errors['chains'] = ['Chains must be a list']
            # Allow custom chains, so no validation on values
        
        if 'min_reads' in params:
            min_reads = params['min_reads']
            if not isinstance(min_reads, int) or min_reads < 0:
                errors['min_reads'] = ['min_reads must be a non-negative integer']
        
        return errors
    
    def _validate_sequencing_params(self, params: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate sequencing depth parameters."""
        errors = {}
        valid_metrics = ['total_rna', 'reads_umi', 'migs_good', 'reads_good']
        
        if 'metrics' in params:
            metrics = params['metrics']
            if not isinstance(metrics, list):
                errors['metrics'] = ['Metrics must be a list']
            else:
                invalid = [m for m in metrics if m not in valid_metrics]
                if invalid:
                    errors['metrics'] = [f"Invalid metrics: {', '.join(invalid)}"]
        
        return errors
    
    def _validate_diversity_params(self, params: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate diversity metrics parameters."""
        errors = {}
        valid_metrics = ['d50', 'gini', 'shannon', 'simpson']
        
        if 'metrics' in params:
            metrics = params['metrics']
            if not isinstance(metrics, list):
                errors['metrics'] = ['Metrics must be a list']
            else:
                invalid = [m for m in metrics if m not in valid_metrics]
                if invalid:
                    errors['metrics'] = [f"Invalid metrics: {', '.join(invalid)}"]
        
        return errors
    
    def _validate_chain_params(self, params: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate chain-specific parameters."""
        errors = {}
        valid_metrics = ['ucdr3', 'total_reads', 'copy']
        
        if 'metric' in params:
            metric = params['metric']
            if metric not in valid_metrics:
                errors['metric'] = [f"Invalid metric. Must be one of: {', '.join(valid_metrics)}"]
        
        if 'chains' in params:
            chains = params['chains']
            if not isinstance(chains, list):
                errors['chains'] = ['Chains must be a list']
        
        return errors


# Global service instance
_parameter_template_service: Optional[ParameterTemplateService] = None


def init_parameter_template_service(app) -> ParameterTemplateService:
    """Initialize the global parameter template service instance."""
    global _parameter_template_service
    _parameter_template_service = ParameterTemplateService(app)
    return _parameter_template_service


def get_parameter_template_service() -> ParameterTemplateService:
    """Get the global parameter template service instance."""
    if _parameter_template_service is None:
        raise RuntimeError("Parameter template service not initialized. Call init_parameter_template_service first.")
    return _parameter_template_service
