"""
Directory Service for the Immune Repertoire Analysis Web Application.
Handles directory browsing and validation with security checks.
Requirements: 12.2, 12.3, 12.4, 12.5
"""
import os
from pathlib import Path
from typing import List, Dict, Optional

from exceptions import ValidationError


class DirectoryService:
    """
    Service for browsing and validating directories.
    Implements security checks to prevent unauthorized access.
    Requirements: 12.2, 12.3, 12.4, 12.5
    """
    
    @classmethod
    def list_directories(
        cls,
        parent_path: Optional[str] = None,
        allowed_base_paths: Optional[List[str]] = None,
        hidden_directories: Optional[List[str]] = None
    ) -> Dict:
        """
        List directories in the specified parent path.
        
        Requirements: 12.2, 12.3
        
        Args:
            parent_path: Path to list directories from. If None, lists allowed base paths.
            allowed_base_paths: List of allowed base paths for security
            hidden_directories: List of directory names to hide
            
        Returns:
            Dictionary with:
                - current_path: Current directory path
                - directories: List of directory info dicts
                - parent_path: Parent directory path (or None)
                
        Raises:
            ValidationError: If path is not allowed or doesn't exist
        """
        if hidden_directories is None:
            hidden_directories = ['.git', '__pycache__', 'node_modules', '.hypothesis']
        
        # If no parent path, return root directories (drives on Windows, / on Unix)
        if parent_path is None:
            directories = []
            
            # Check if we have allowed base paths configured
            if allowed_base_paths:
                for base_path in allowed_base_paths:
                    if os.path.exists(base_path) and os.path.isdir(base_path):
                        directories.append({
                            'name': os.path.basename(base_path) or base_path,
                            'path': base_path,
                            'has_children': cls._has_subdirectories(base_path, hidden_directories)
                        })
            else:
                # No restrictions - show system root directories
                if os.name == 'nt':  # Windows
                    import string
                    for drive in string.ascii_uppercase:
                        drive_path = f"{drive}:\\"
                        if os.path.exists(drive_path):
                            directories.append({
                                'name': f"{drive}:",
                                'path': drive_path,
                                'has_children': True
                            })
                else:  # Unix/Linux/Mac
                    directories.append({
                        'name': '/',
                        'path': '/',
                        'has_children': True
                    })
            
            return {
                'current_path': None,
                'directories': directories,
                'parent_path': None
            }
        
        # Validate path is allowed (skip if no restrictions)
        if allowed_base_paths:
            if not cls._is_path_allowed(parent_path, allowed_base_paths):
                raise ValidationError(
                    message=f"Access to path not allowed: {parent_path}",
                    details={
                        'path': parent_path,
                        'allowed_base_paths': allowed_base_paths
                    }
                )
        
        # Validate path exists
        if not os.path.exists(parent_path):
            raise ValidationError(
                message=f"Path does not exist: {parent_path}",
                details={'path': parent_path}
            )
        
        if not os.path.isdir(parent_path):
            raise ValidationError(
                message=f"Path is not a directory: {parent_path}",
                details={'path': parent_path}
            )
        
        # Check read permissions
        if not os.access(parent_path, os.R_OK):
            raise ValidationError(
                message=f"No read permission for path: {parent_path}",
                details={'path': parent_path}
            )
        
        # List subdirectories
        directories = []
        try:
            for entry in os.listdir(parent_path):
                # Skip hidden directories
                if entry in hidden_directories or entry.startswith('.'):
                    continue
                
                full_path = os.path.join(parent_path, entry)
                
                # Only include directories
                if os.path.isdir(full_path):
                    directories.append({
                        'name': entry,
                        'path': full_path,
                        'has_children': cls._has_subdirectories(full_path, hidden_directories)
                    })
        except PermissionError:
            raise ValidationError(
                message=f"Permission denied accessing: {parent_path}",
                details={'path': parent_path}
            )
        
        # Sort directories by name
        directories.sort(key=lambda x: x['name'].lower())
        
        # Get parent directory
        parent_dir = str(Path(parent_path).parent)
        if parent_dir == parent_path:
            parent_dir = None
        elif allowed_base_paths and not cls._is_path_allowed(parent_dir, allowed_base_paths):
            parent_dir = None
        
        return {
            'current_path': parent_path,
            'directories': directories,
            'parent_path': parent_dir
        }
    
    @classmethod
    def validate_path(
        cls,
        path: str,
        allowed_base_paths: Optional[List[str]] = None
    ) -> Dict:
        """
        Validate that a path exists and is accessible.
        
        Requirements: 12.4, 12.5
        
        Args:
            path: Path to validate
            allowed_base_paths: List of allowed base paths for security
            
        Returns:
            Dictionary with:
                - valid: Boolean indicating if path is valid
                - exists: Boolean indicating if path exists
                - is_directory: Boolean indicating if path is a directory
                - readable: Boolean indicating if path is readable
                - message: Validation message
                
        Raises:
            ValidationError: If path is not allowed
        """
        result = {
            'valid': False,
            'exists': False,
            'is_directory': False,
            'readable': False,
            'message': ''
        }
        
        # Check if path is allowed
        if allowed_base_paths:
            if not cls._is_path_allowed(path, allowed_base_paths):
                result['message'] = f"Access to path not allowed: {path}"
                return result
        
        # Check if path exists
        if not os.path.exists(path):
            result['message'] = f"Path does not exist: {path}"
            return result
        
        result['exists'] = True
        
        # Check if it's a directory
        if not os.path.isdir(path):
            result['message'] = f"Path is not a directory: {path}"
            return result
        
        result['is_directory'] = True
        
        # Check read permissions
        if not os.access(path, os.R_OK):
            result['message'] = f"No read permission for path: {path}"
            return result
        
        result['readable'] = True
        result['valid'] = True
        result['message'] = "Path is valid"
        
        return result
    
    @classmethod
    def _is_path_allowed(cls, path: str, allowed_base_paths: List[str]) -> bool:
        """
        Check if a path is within allowed base paths.
        
        Args:
            path: Path to check
            allowed_base_paths: List of allowed base paths
            
        Returns:
            True if path is allowed, False otherwise
        """
        path_obj = Path(path).resolve()
        
        for base_path in allowed_base_paths:
            base_path_obj = Path(base_path).resolve()
            try:
                # Check if path is relative to base_path
                path_obj.relative_to(base_path_obj)
                return True
            except ValueError:
                # path is not relative to this base_path
                continue
        
        return False
    
    @classmethod
    def _has_subdirectories(cls, path: str, hidden_directories: List[str]) -> bool:
        """
        Check if a directory has subdirectories.
        
        Args:
            path: Directory path to check
            hidden_directories: List of directory names to ignore
            
        Returns:
            True if directory has subdirectories, False otherwise
        """
        try:
            for entry in os.listdir(path):
                if entry in hidden_directories or entry.startswith('.'):
                    continue
                
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    return True
            return False
        except (PermissionError, OSError):
            return False
    
    @classmethod
    def create_directory(
        cls,
        path: str,
        allowed_base_paths: Optional[List[str]] = None
    ) -> Dict:
        """
        Create a new directory.
        
        Args:
            path: Path of directory to create
            allowed_base_paths: List of allowed base paths for security
            
        Returns:
            Dictionary with:
                - success: Boolean indicating if creation was successful
                - path: Created directory path
                - message: Result message
                
        Raises:
            ValidationError: If path is not allowed or creation fails
        """
        # Check if path is allowed
        if allowed_base_paths:
            parent_path = str(Path(path).parent)
            if not cls._is_path_allowed(parent_path, allowed_base_paths):
                raise ValidationError(
                    message=f"Cannot create directory in disallowed location: {path}",
                    details={'path': path}
                )
        
        # Check if directory already exists
        if os.path.exists(path):
            raise ValidationError(
                message=f"Directory already exists: {path}",
                details={'path': path}
            )
        
        # Create directory
        try:
            os.makedirs(path, exist_ok=False)
            return {
                'success': True,
                'path': path,
                'message': f"Directory created successfully: {path}"
            }
        except PermissionError:
            raise ValidationError(
                message=f"Permission denied creating directory: {path}",
                details={'path': path}
            )
        except OSError as e:
            raise ValidationError(
                message=f"Failed to create directory: {str(e)}",
                details={'path': path, 'error': str(e)}
            )
