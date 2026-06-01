"""
Configuration Service for the Immune Repertoire Analysis Web Application.
Manages user configuration persistence and loading.
Requirements: 7.3, 7.4
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
import json

from flask_app.models.database import db


# Database model for user configuration
class UserConfig(db.Model):
    """Model for user configuration settings. Requirements: 7.3, 7.4"""
    __tablename__ = 'user_configs'
    
    id = db.Column(db.String(36), primary_key=True, default='default')
    config_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


@dataclass
class ChartConfigDefaults:
    """Default chart configuration settings."""
    color_scheme: str = 'viridis'
    figure_width: int = 10
    figure_height: int = 8
    font_size: int = 12
    dpi: int = 300
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HeatmapConfigDefaults:
    """Default heatmap configuration settings."""
    annotation: bool = True
    cmap: str = 'RdYlBu_r'
    vmin: float = 0.0
    vmax: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BarChartConfigDefaults:
    """Default bar chart configuration settings."""
    bar_width: float = 0.8
    bar_spacing: float = 0.2
    show_values: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserConfiguration:
    """
    Complete user configuration structure.
    Requirements: 7.3, 7.4
    """
    # Chart defaults
    default_color_scheme: str = 'viridis'
    default_figure_size: List[int] = field(default_factory=lambda: [10, 8])
    default_font_size: int = 12
    default_dpi: int = 300
    default_export_format: str = 'png'
    
    # Heatmap defaults
    heatmap_annotation: bool = True
    heatmap_cmap: str = 'RdYlBu_r'
    heatmap_vmin: float = 0.0
    heatmap_vmax: float = 1.0
    
    # Bar chart defaults
    bar_width: float = 0.8
    bar_spacing: float = 0.2
    bar_show_values: bool = True
    
    # UI preferences
    locale: str = 'zh-CN'
    theme: str = 'light'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserConfiguration':
        """Create UserConfiguration from dictionary."""
        # Filter only valid fields
        valid_fields = {
            'default_color_scheme', 'default_figure_size', 'default_font_size',
            'default_dpi', 'default_export_format', 'heatmap_annotation', 'heatmap_cmap', 'heatmap_vmin',
            'heatmap_vmax', 'bar_width', 'bar_spacing', 'bar_show_values',
            'locale', 'theme'
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class ConfigService:
    """
    Service for managing user configuration.
    Requirements: 7.3, 7.4
    """
    
    # Available color schemes
    COLOR_SCHEMES = [
        'viridis', 'plasma', 'inferno', 'magma', 'cividis',
        'RdYlBu_r', 'RdBu_r', 'coolwarm', 'seismic', 'Spectral'
    ]
    
    # Available themes
    THEMES = ['light', 'dark']
    
    # Available locales
    LOCALES = ['zh-CN', 'en-US']
    
    DEFAULT_CONFIG_ID = 'default'
    
    def __init__(self, app=None):
        """
        Initialize the config service.
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app
        # Ensure the UserConfig table exists
        with app.app_context():
            db.create_all()
    
    def get_config(self, config_id: str = None) -> UserConfiguration:
        """
        Get user configuration.
        
        Args:
            config_id: Configuration ID (default: 'default')
            
        Returns:
            UserConfiguration object
            
        Requirements: 7.4
        """
        if config_id is None:
            config_id = self.DEFAULT_CONFIG_ID
        
        config_record = UserConfig.query.get(config_id)
        
        if config_record and config_record.config_data:
            return UserConfiguration.from_dict(config_record.config_data)
        
        # Return default configuration if not found
        return UserConfiguration()
    
    def save_config(
        self, 
        config: UserConfiguration,
        config_id: str = None
    ) -> UserConfiguration:
        """
        Save user configuration.
        
        Args:
            config: UserConfiguration object to save
            config_id: Configuration ID (default: 'default')
            
        Returns:
            Saved UserConfiguration object
            
        Requirements: 7.3
        """
        if config_id is None:
            config_id = self.DEFAULT_CONFIG_ID
        
        config_data = config.to_dict()
        
        # Check if config exists
        config_record = UserConfig.query.get(config_id)
        
        if config_record:
            # Update existing config
            config_record.config_data = config_data
            config_record.updated_at = datetime.utcnow()
        else:
            # Create new config
            config_record = UserConfig(
                id=config_id,
                config_data=config_data
            )
            db.session.add(config_record)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise
        
        return config
    
    def update_config(
        self,
        updates: Dict[str, Any],
        config_id: str = None
    ) -> UserConfiguration:
        """
        Update specific configuration fields.
        
        Args:
            updates: Dictionary of fields to update
            config_id: Configuration ID (default: 'default')
            
        Returns:
            Updated UserConfiguration object
            
        Requirements: 7.3
        """
        # Get current config
        current_config = self.get_config(config_id)
        current_data = current_config.to_dict()
        
        # Apply updates
        current_data.update(updates)
        
        # Create new config object and save
        new_config = UserConfiguration.from_dict(current_data)
        return self.save_config(new_config, config_id)
    
    def reset_config(self, config_id: str = None) -> UserConfiguration:
        """
        Reset configuration to defaults.
        
        Args:
            config_id: Configuration ID (default: 'default')
            
        Returns:
            Default UserConfiguration object
            
        Requirements: 7.3
        """
        default_config = UserConfiguration()
        return self.save_config(default_config, config_id)
    
    def delete_config(self, config_id: str) -> bool:
        """
        Delete a configuration.
        
        Args:
            config_id: Configuration ID to delete
            
        Returns:
            True if deletion was successful
        """
        if config_id == self.DEFAULT_CONFIG_ID:
            # Don't delete default config, just reset it
            self.reset_config(config_id)
            return True
        
        config_record = UserConfig.query.get(config_id)
        
        if not config_record:
            return False
        
        try:
            db.session.delete(config_record)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise
    
    def get_available_color_schemes(self) -> List[str]:
        """Get list of available color schemes."""
        return self.COLOR_SCHEMES.copy()
    
    def get_available_themes(self) -> List[str]:
        """Get list of available themes."""
        return self.THEMES.copy()
    
    def get_available_locales(self) -> List[str]:
        """Get list of available locales."""
        return self.LOCALES.copy()
    
    def validate_config(self, config_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate configuration data.
        
        Args:
            config_data: Configuration data to validate
            
        Returns:
            Dictionary of field names to error messages (empty if valid)
        """
        errors = {}
        
        # Validate color scheme
        if 'default_color_scheme' in config_data:
            if config_data['default_color_scheme'] not in self.COLOR_SCHEMES:
                errors['default_color_scheme'] = [
                    f"Invalid color scheme. Must be one of: {', '.join(self.COLOR_SCHEMES)}"
                ]
        
        # Validate figure size
        if 'default_figure_size' in config_data:
            size = config_data['default_figure_size']
            if not isinstance(size, list) or len(size) != 2:
                errors['default_figure_size'] = ['Figure size must be a list of [width, height]']
            elif not all(isinstance(x, (int, float)) and x > 0 for x in size):
                errors['default_figure_size'] = ['Figure dimensions must be positive numbers']
        
        # Validate font size
        if 'default_font_size' in config_data:
            font_size = config_data['default_font_size']
            if not isinstance(font_size, int) or font_size < 6 or font_size > 72:
                errors['default_font_size'] = ['Font size must be an integer between 6 and 72']
        
        # Validate DPI
        if 'default_dpi' in config_data:
            dpi = config_data['default_dpi']
            if not isinstance(dpi, int) or dpi < 72 or dpi > 600:
                errors['default_dpi'] = ['DPI must be an integer between 72 and 600']

        if 'default_export_format' in config_data:
            if config_data['default_export_format'] not in {'png', 'csv', 'zip'}:
                errors['default_export_format'] = ['Export format must be one of: png, csv, zip']
        
        # Validate theme
        if 'theme' in config_data:
            if config_data['theme'] not in self.THEMES:
                errors['theme'] = [f"Invalid theme. Must be one of: {', '.join(self.THEMES)}"]
        
        # Validate locale
        if 'locale' in config_data:
            if config_data['locale'] not in self.LOCALES:
                errors['locale'] = [f"Invalid locale. Must be one of: {', '.join(self.LOCALES)}"]
        
        # Validate bar width
        if 'bar_width' in config_data:
            bar_width = config_data['bar_width']
            if not isinstance(bar_width, (int, float)) or bar_width <= 0 or bar_width > 1:
                errors['bar_width'] = ['Bar width must be a number between 0 and 1']
        
        # Validate heatmap vmin/vmax
        if 'heatmap_vmin' in config_data and 'heatmap_vmax' in config_data:
            vmin = config_data['heatmap_vmin']
            vmax = config_data['heatmap_vmax']
            if vmin >= vmax:
                errors['heatmap_vmin'] = ['vmin must be less than vmax']

        return errors


# Global service instance
_config_service: Optional[ConfigService] = None


def init_config_service(app) -> ConfigService:
    """Initialize the global config service instance."""
    global _config_service
    _config_service = ConfigService(app)
    return _config_service


def get_config_service() -> ConfigService:
    """Get the global config service instance."""
    if _config_service is None:
        raise RuntimeError("Config service not initialized. Call init_config_service first.")
    return _config_service
