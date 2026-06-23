"""
Analysis Service for the Immune Repertoire Analysis Web Application.
Coordinates analysis task creation, execution, progress updates, and result storage.
Requirements: 8.1, 8.2, 8.3, 8.4

Analysis Types:
1. similarity_heatmap - Similarity analysis with heatmap visualization
2. sequencing_depth - Sequencing depth metrics analysis
3. diversity_metrics - Diversity metrics analysis (D50, Gini, Shannon, Simpson)
4. chain_specific - Chain-specific analysis
"""
import os
import uuid
import traceback
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import threading

import pandas as pd

from flask_app.services.heatmap_generator import format_similarity_value, normalize_sample_order


def _safe_isoformat(value: Any) -> Optional[str]:
    """Best-effort datetime serialization used in API responses."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return value.isoformat()  # type: ignore[attr-defined]
    except Exception:
        return str(value)


class AnalysisStatus(str, Enum):
    """Analysis task status enumeration."""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class AnalysisType(str, Enum):
    """Supported analysis types."""
    SIMILARITY_HEATMAP = 'similarity_heatmap'
    SEQUENCING_DEPTH = 'sequencing_depth'
    DIVERSITY_METRICS = 'diversity_metrics'
    CHAIN_SPECIFIC = 'chain_specific'


@dataclass
class AnalysisProgress:
    """Progress information for an analysis task."""
    progress: float = 0.0
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0


@dataclass
class AnalysisResultItem:
    """Single result item from an analysis."""
    result_type: str  # 'visualization', 'data_table', 'summary'
    name: str
    file_path: str
    mime_type: str
    table_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AnalysisResults:
    """Complete results from an analysis."""
    items: List[AnalysisResultItem] = field(default_factory=list)
    summary: Optional[Dict[str, Any]] = None


class AnalysisService:
    """
    Service for managing analysis tasks.
    Coordinates task creation, execution, progress tracking, and result storage.
    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    
    # Maximum concurrent analysis tasks
    MAX_CONCURRENT_TASKS = 4
    
    # Maximum retry attempts for failed tasks
    MAX_RETRY_ATTEMPTS = 3
    
    def __init__(self, app=None, results_folder: Optional[str] = None):
        """
        Initialize the analysis service.
        
        Args:
            app: Flask application instance (optional)
            results_folder: Path to store analysis results
        """
        self.app = app
        self.results_folder = results_folder
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT_TASKS)
        self._progress_lock = threading.Lock()
        self._progress_cache: Dict[str, AnalysisProgress] = {}
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app
        self.results_folder = app.config.get('RESULTS_FOLDER', 'data/results')
        
        # Ensure results folder exists
        Path(self.results_folder).mkdir(parents=True, exist_ok=True)
    
    def create_analysis(
        self,
        analysis_type: str,
        file_id: str,
        field_mapping: Dict[str, str],
        parameters: Optional[Dict[str, Any]] = None,
        chart_config: Optional[Dict[str, Any]] = None,
        check_duplicate: bool = True
    ) -> str:
        """
        Create a new analysis task.
        
        Args:
            analysis_type: Type of analysis to perform
            file_id: ID of the uploaded file to analyze
            field_mapping: Mapping from required fields to source columns
            parameters: Analysis-specific parameters
            chart_config: Chart configuration parameters
            check_duplicate: Whether to check for duplicate analysis (default: True)
            
        Returns:
            Analysis task ID
            
        Requirements: 8.1
        """
        from flask_app.models.database import db, Analysis, File
        from flask_app.exceptions import ValidationError, FileNotFoundError as AppFileNotFoundError
        from flask_app.services.user_scope import assert_owned, current_user_id
        
        # Validate analysis type
        try:
            AnalysisType(analysis_type)
        except ValueError:
            raise ValidationError(
                message=f"Unsupported analysis type: {analysis_type}",
                details={
                    'analysis_type': analysis_type,
                    'supported_types': [t.value for t in AnalysisType]
                }
            )
        # History module removed: duplicate check disabled.

        # Validate file exists (skip for directory-based similarity analysis)
        if analysis_type == AnalysisType.SIMILARITY_HEATMAP.value:
            # Directory-based analysis - validate directory path exists in parameters
            directory_path = (parameters or {}).get('directory_path')
            if not directory_path or not Path(directory_path).exists():
                raise ValidationError(
                    message=f"Directory not found: {directory_path}",
                    details={'directory_path': directory_path}
                )
            file_record = None
        else:
            file_record = File.query.get(file_id)
            if not file_record:
                raise AppFileNotFoundError(
                    message=f"File not found: {file_id}",
                    details={'file_id': file_id}
                )
            assert_owned(file_record, "File")
        
        # Create analysis record
        analysis_id = str(uuid.uuid4())
        
        # Generate analysis name
        type_names = {
            'similarity_heatmap': 'Similarity Heatmap Analysis',
            'sequencing_depth': 'Sequencing Depth Analysis',
            'diversity_metrics': 'Diversity Metrics Analysis',
            'chain_specific': 'Chain-Specific Analysis',
            'bcell_isotype': 'B Cell Isotype Analysis'
        }
        analysis_name = type_names.get(analysis_type, analysis_type)
        
        analysis = Analysis(
            id=analysis_id,
            name=analysis_name,  # Set the name field
            type=analysis_type,
            file_id=file_id,  # Can be None for directory-based analysis
            field_mapping=field_mapping,
            parameters=parameters or {},
            chart_config=chart_config or {},
            status=AnalysisStatus.PENDING.value,
            progress=0.0,
            current_step='Initializing',
            created_at=datetime.utcnow(),
            user_id=current_user_id(),
        )
        
        db.session.add(analysis)
        db.session.commit()

        try:
            from flask_app.services.background_job_service import get_background_job_service
            get_background_job_service().upsert_job(analysis_id, {
                "job_type": "analysis_service",
                "module": analysis_type,
                "status": AnalysisStatus.PENDING.value,
                "progress": 0.0,
                "stage": "Initializing",
                "detail": "Analysis task created",
                "user_id": current_user_id(),
                "payload": {
                    "analysis_id": analysis_id,
                    "file_id": file_id,
                    "field_mapping": field_mapping,
                    "parameters": parameters or {},
                    "chart_config": chart_config or {},
                },
            })
        except Exception:
            pass
        
        # Initialize progress cache
        with self._progress_lock:
            self._progress_cache[analysis_id] = AnalysisProgress(
                progress=0.0,
                current_step='Initializing'
            )
        
        # Submit task for execution
        self._executor.submit(self._execute_analysis, analysis_id)
        
        return analysis_id
    
    def get_analysis_status(self, analysis_id: str) -> Dict[str, Any]:
        """
        Get the current status of an analysis task.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            Dictionary with status information
            
        Requirements: 8.2
        """
        from flask_app.models.database import Analysis
        from flask_app.exceptions import AnalysisNotFoundError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Get cached progress if available
        with self._progress_lock:
            cached_progress = self._progress_cache.get(analysis_id)
        
        progress = cached_progress.progress if cached_progress else analysis.progress
        current_step = cached_progress.current_step if cached_progress else analysis.current_step
        
        return {
            'id': analysis.id,
            'status': analysis.status,
            'progress': progress,
            'current_step': current_step,
            'error_message': analysis.error_message,
            'created_at': _safe_isoformat(analysis.created_at),
            'started_at': _safe_isoformat(analysis.started_at),
            'completed_at': _safe_isoformat(analysis.completed_at)
        }
    
    def get_analysis_results(self, analysis_id: str) -> Dict[str, Any]:
        """
        Get the results of a completed analysis.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            Dictionary with analysis results
            
        Requirements: 8.4
        """
        from flask_app.models.database import Analysis, AnalysisResult
        from flask_app.exceptions import AnalysisNotFoundError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Get all results for this analysis
        results = AnalysisResult.query.filter_by(analysis_id=analysis_id).all()
        
        # Combine results - pair visualizations with their data tables
        combined_results = []
        viz_dict = {}
        table_dict = {}
        
        for result in results:
            result_info = {
                'id': result.id,
                'name': result.name,
                'result_type': result.result_type,
                'file_path': result.file_path,
                'mime_type': result.mime_type,
                'metadata': result.result_metadata,
                'table_data': result.table_data if result.result_type == 'data_table' else None
            }
            
            if result.result_type == 'visualization':
                viz_dict[result.name] = result_info
            elif result.result_type == 'data_table':
                # Try to find matching visualization
                base_name = result.name.replace('_data', '').replace('_matrix', '')
                table_dict[base_name] = result_info
        
        # Create combined results - visualizations with their tables
        for name, viz in viz_dict.items():
            base_name = name.replace('_heatmap', '')
            combined = {
                **viz,
                'table_data': table_dict.get(base_name, {}).get('table_data') or table_dict.get(name, {}).get('table_data')
            }
            combined_results.append(combined)
        
        # Add any standalone tables
        for name, table in table_dict.items():
            if not any(name in v.get('name', '') for v in viz_dict.values()):
                combined_results.append(table)
        
        return {
            'id': analysis.id,
            'type': analysis.type,
            'status': analysis.status,
            'progress': analysis.progress,
            'file_id': analysis.file_id,
            'parameters': analysis.parameters,
            'chart_config': analysis.chart_config,
            'results': combined_results,
            'error_message': analysis.error_message,
            'created_at': _safe_isoformat(analysis.created_at),
            'completed_at': _safe_isoformat(analysis.completed_at)
        }
    
    def get_data_table(self, analysis_id: str, table_name: str) -> Dict[str, Any]:
        """
        Get a specific data table from analysis results.
        
        Args:
            analysis_id: Analysis task ID
            table_name: Name of the data table
            
        Returns:
            Dictionary with table data
            
        Requirements: 8.4
        """
        from flask_app.models.database import Analysis, AnalysisResult
        from flask_app.exceptions import AnalysisNotFoundError, ValidationError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        # Find the specific data table
        result = AnalysisResult.query.filter_by(
            analysis_id=analysis_id,
            name=table_name,
            result_type='data_table'
        ).first()
        
        if not result:
            raise ValidationError(
                message=f"Data table not found: {table_name}",
                details={'analysis_id': analysis_id, 'table_name': table_name}
            )
        
        return {
            'table_name': result.name,
            'columns': result.table_data.get('columns', []) if result.table_data else [],
            'data': result.table_data.get('data', []) if result.table_data else [],
            'row_count': result.table_data.get('row_count', 0) if result.table_data else 0
        }
    
    def update_progress(
        self,
        analysis_id: str,
        progress: float,
        current_step: str
    ) -> None:
        """
        Update the progress of an analysis task.
        
        Args:
            analysis_id: Analysis task ID
            progress: Progress percentage (0-100)
            current_step: Description of current step
            
        Requirements: 8.2
        """
        from flask_app.models.database import db, Analysis
        
        # Ensure progress is monotonically non-decreasing
        with self._progress_lock:
            cached = self._progress_cache.get(analysis_id)
            if cached and progress < cached.progress:
                progress = cached.progress  # Don't decrease progress
            
            self._progress_cache[analysis_id] = AnalysisProgress(
                progress=progress,
                current_step=current_step
            )
        
        # Update database
        analysis = Analysis.query.get(analysis_id)
        if analysis:
            analysis.progress = progress
            analysis.current_step = current_step
            db.session.commit()
        try:
            from flask_app.services.background_job_service import get_background_job_service
            get_background_job_service().upsert_job(analysis_id, {
                "job_type": "analysis_service",
                "module": analysis.type if analysis else "analysis",
                "status": analysis.status if analysis else "running",
                "progress": progress,
                "stage": current_step,
                "detail": current_step,
            })
        except Exception:
            pass
    
    def retry_analysis(self, analysis_id: str) -> bool:
        """
        Retry a failed analysis task.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            True if retry was initiated, False otherwise
            
        Requirements: 8.3
        """
        from flask_app.models.database import db, Analysis
        from flask_app.exceptions import AnalysisNotFoundError, ValidationError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        if analysis.status != AnalysisStatus.FAILED.value:
            raise ValidationError(
                message="Only failed analyses can be retried",
                details={'current_status': analysis.status}
            )
        
        # Check retry count
        retry_count = analysis.parameters.get('_retry_count', 0)
        if retry_count >= self.MAX_RETRY_ATTEMPTS:
            raise ValidationError(
                message=f"Maximum retry attempts ({self.MAX_RETRY_ATTEMPTS}) exceeded",
                details={'retry_count': retry_count}
            )
        
        # Reset analysis state
        analysis.status = AnalysisStatus.PENDING.value
        analysis.progress = 0.0
        analysis.current_step = 'Retrying'
        analysis.error_message = None
        analysis.parameters['_retry_count'] = retry_count + 1
        db.session.commit()
        
        # Initialize progress cache
        with self._progress_lock:
            self._progress_cache[analysis_id] = AnalysisProgress(
                progress=0.0,
                current_step='Retrying'
            )
        
        # Submit for re-execution
        self._executor.submit(self._execute_analysis, analysis_id)
        
        return True
    
    def cancel_analysis(self, analysis_id: str) -> bool:
        """
        Cancel a running analysis task.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            True if cancellation was successful
        """
        from flask_app.models.database import db, Analysis
        from flask_app.exceptions import AnalysisNotFoundError, ValidationError
        
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(
                message=f"Analysis not found: {analysis_id}",
                details={'analysis_id': analysis_id}
            )
        
        if analysis.status not in [AnalysisStatus.PENDING.value, AnalysisStatus.RUNNING.value]:
            raise ValidationError(
                message="Only pending or running analyses can be cancelled",
                details={'current_status': analysis.status}
            )
        
        analysis.status = AnalysisStatus.CANCELLED.value
        analysis.completed_at = datetime.utcnow()
        db.session.commit()
        try:
            from flask_app.services.background_job_service import get_background_job_service
            get_background_job_service().request_cancel(analysis_id)
        except Exception:
            pass
        
        # Clean up progress cache
        with self._progress_lock:
            self._progress_cache.pop(analysis_id, None)
        
        return True

    
    def _execute_analysis(self, analysis_id: str) -> None:
        """
        Execute an analysis task in a background thread.
        
        Args:
            analysis_id: Analysis task ID
        """
        from flask_app.models.database import db, Analysis, AnalysisResult, File
        from flask_app.services.file_parser import FileParserService
        
        # Need to use app context for database operations in thread
        with self.app.app_context():
            analysis = Analysis.query.get(analysis_id)
            if not analysis:
                return
            
            # Check if cancelled
            if analysis.status == AnalysisStatus.CANCELLED.value:
                return
            
            try:
                # Update status to running
                analysis.status = AnalysisStatus.RUNNING.value
                analysis.started_at = datetime.utcnow()
                db.session.commit()
                
                self.update_progress(analysis_id, 5.0, 'Loading data')
                
                print(f"\n=== Analysis Debug Info ===")
                print(f"Analysis ID: {analysis_id}")
                print(f"Type: {analysis.type}")
                
                # For directory-based similarity analysis, skip file loading
                df = None
                if analysis.type == AnalysisType.SIMILARITY_HEATMAP.value:
                    directory_path = analysis.parameters.get('directory_path')
                    selected_samples = analysis.parameters.get('selected_samples', [])
                    selected_chains = analysis.parameters.get('selected_chains', [])
                    print(f"Directory: {directory_path}")
                    print(f"Selected samples: {selected_samples}")
                    print(f"Selected chains: {selected_chains}")
                else:
                    # Load file data for other analysis types
                    file_record = File.query.get(analysis.file_id)
                    if not file_record:
                        raise ValueError(f"File not found: {analysis.file_id}")
                    
                    storage_path = Path(file_record.storage_path)
                    if not storage_path.exists():
                        raise ValueError(f"File not found on disk: {storage_path}")
                    
                    with open(storage_path, 'rb') as f:
                        file_content = f.read()
                    
                    df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
                    
                    if df.empty:
                        raise ValueError("Parsed data is empty")
                    
                    # Filter by selected samples if specified
                    sample_column = analysis.parameters.get('sample_column')
                    selected_samples = analysis.parameters.get('selected_samples', [])
                    
                    if sample_column and selected_samples and sample_column in df.columns:
                        df = df[df[sample_column].isin(selected_samples)]
                        print(f"Filtered to {len(df)} rows for samples: {selected_samples}")
                        
                        if df.empty:
                            raise ValueError(f"No data found for selected samples: {selected_samples}")
                    
                    print(f"Data shape: {df.shape}")
                    print(f"Columns: {list(df.columns)}")
                    print(f"Field mapping: {analysis.field_mapping}")
                
                print(f"========================\n")
                
                self.update_progress(analysis_id, 15.0, 'Preparing analysis')
                
                # Create results directory for this analysis
                user_segment = str(analysis.user_id) if analysis.user_id else "shared"
                results_dir = Path(self.results_folder) / user_segment / analysis_id
                results_dir.mkdir(parents=True, exist_ok=True)
                
                # Execute analysis based on type
                analysis_type = AnalysisType(analysis.type)
                
                if analysis_type == AnalysisType.SIMILARITY_HEATMAP:
                    # Directory-based similarity analysis
                    results = self._execute_directory_similarity_analysis(
                        analysis_id, analysis.parameters, analysis.chart_config, results_dir
                    )
                elif analysis_type == AnalysisType.SEQUENCING_DEPTH:
                    results = self._execute_sequencing_depth_analysis(
                        analysis_id, df, analysis.field_mapping,
                        analysis.parameters, analysis.chart_config, results_dir
                    )
                elif analysis_type == AnalysisType.DIVERSITY_METRICS:
                    results = self._execute_diversity_analysis(
                        analysis_id, df, analysis.field_mapping,
                        analysis.parameters, analysis.chart_config, results_dir
                    )
                elif analysis_type == AnalysisType.CHAIN_SPECIFIC:
                    results = self._execute_chain_analysis(
                        analysis_id, df, analysis.field_mapping,
                        analysis.parameters, analysis.chart_config, results_dir
                    )
                else:
                    raise ValueError(f"Unsupported analysis type: {analysis.type}")
                
                # Store results in database
                self.update_progress(analysis_id, 95.0, 'Saving results')
                
                for result_item in results.items:
                    result_record = AnalysisResult(
                        analysis_id=analysis_id,
                        result_type=result_item.result_type,
                        name=result_item.name,
                        file_path=result_item.file_path,
                        mime_type=result_item.mime_type,
                        table_data=result_item.table_data,
                        result_metadata=result_item.metadata
                    )
                    db.session.add(result_record)
                
                # Update analysis status
                analysis.status = AnalysisStatus.COMPLETED.value
                analysis.progress = 100.0
                analysis.current_step = 'Completed'
                analysis.results_path = str(results_dir)
                analysis.completed_at = datetime.utcnow()
                db.session.commit()
                
                self.update_progress(analysis_id, 100.0, 'Completed')
                try:
                    from flask_app.services.background_job_service import get_background_job_service
                    get_background_job_service().complete_job(analysis_id, {
                        "module": analysis.type,
                        "analysis_id": analysis_id,
                        "results_path": str(results_dir),
                    })
                except Exception:
                    pass
                
            except Exception as e:
                # Handle failure
                db.session.rollback()
                
                error_message = str(e)
                error_traceback = traceback.format_exc()
                
                analysis = Analysis.query.get(analysis_id)
                if analysis:
                    analysis.status = AnalysisStatus.FAILED.value
                    analysis.error_message = error_message
                    analysis.completed_at = datetime.utcnow()
                    db.session.commit()
                try:
                    from flask_app.services.background_job_service import get_background_job_service
                    get_background_job_service().fail_job(analysis_id, error_message, error_traceback)
                except Exception:
                    pass
                
                # Log error with more details
                if self.app:
                    self.app.logger.error(
                        f"Analysis {analysis_id} failed:\n"
                        f"Type: {analysis.type if analysis else 'unknown'}\n"
                        f"Error: {error_message}\n"
                        f"Traceback: {error_traceback}"
                    )
                    
                    # Also print to console for immediate debugging
                    print(f"\n=== ANALYSIS FAILED ===")
                    print(f"ID: {analysis_id}")
                    print(f"Type: {analysis.type if analysis else 'unknown'}")
                    print(f"Error: {error_message}")
                    print(f"========================\n")
            
            finally:
                # Clean up progress cache
                with self._progress_lock:
                    self._progress_cache.pop(analysis_id, None)
    
    def _execute_similarity_analysis(
        self,
        analysis_id: str,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any],
        results_dir: Path
    ) -> AnalysisResults:
        """Execute similarity heatmap analysis using integrated engine."""
        from flask_app.services.integrated_analysis import IntegratedAnalysisEngine
        from flask_app.services.data_table import DataTableService
        
        results = AnalysisResults()
        
        try:
            # Initialize integrated engine
            engine = IntegratedAnalysisEngine()
            
            self.update_progress(analysis_id, 25.0, 'Running similarity analysis')
            
            # Run analysis
            analysis_results = engine.run_similarity_analysis(
                df, field_mapping, parameters, chart_config
            )
            
            # Process results
            for metric, data in analysis_results.items():
                # Save heatmap
                if 'heatmap' in data and 'image' in data['heatmap']:
                    # Extract base64 image data
                    image_data = data['heatmap']['image'].split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    
                    viz_path = results_dir / f'{metric}_heatmap.png'
                    with open(viz_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    results.items.append(AnalysisResultItem(
                        result_type='visualization',
                        name=f'{metric}_heatmap',
                        file_path=str(viz_path),
                        mime_type='image/png',
                        metadata=data['heatmap'].get('metadata', {})
                    ))
                
                # Save data table
                if 'table_data' in data:
                    table_data = data['table_data']
                    
                    results.items.append(AnalysisResultItem(
                        result_type='data_table',
                        name=f'{metric}_matrix',
                        file_path=str(results_dir / f'{metric}_matrix.csv'),
                        mime_type='text/csv',
                        table_data=table_data
                    ))
                    
                    # Save CSV
                    csv_df = pd.DataFrame(data['matrix'])
                    csv_df.to_csv(results_dir / f'{metric}_matrix.csv')
            
        except Exception as e:
            print(f"Similarity analysis error: {e}")
            raise
        
        return results
    
    def _execute_directory_similarity_analysis(
        self,
        analysis_id: str,
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any],
        results_dir: Path
    ) -> AnalysisResults:
        """Execute directory-based similarity heatmap analysis."""
        import gzip
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        from io import BytesIO
        
        results = AnalysisResults()
        
        directory_path = Path(parameters.get('directory_path'))
        selected_samples = parameters.get('selected_samples', [])
        selected_chains = parameters.get('selected_chains', [])
        metrics = parameters.get('metrics', ['r2_inner', 'cdr3_sharing', 'morisita_horn'])
        
        print(f"\n=== Directory Similarity Analysis ===")
        print(f"Directory: {directory_path}")
        print(f"Samples: {selected_samples}")
        print(f"Chains: {selected_chains}")
        print(f"Metrics: {metrics}")
        
        self.update_progress(analysis_id, 20.0, 'Loading chain data')
        
        # Process each chain
        chain_progress = 20.0
        chain_step = 60.0 / len(selected_chains) if selected_chains else 60.0
        
        for chain in selected_chains:
            self.update_progress(analysis_id, chain_progress, f'Processing {chain} chain')
            
            # Load data for all selected samples for this chain
            chain_samples = {}
            for sample in selected_samples:
                file_path = directory_path / f"{sample}__{chain}.csv.gz"
                if not file_path.exists():
                    file_path = directory_path / f"{sample}__{chain}.csv"
                
                if file_path.exists():
                    try:
                        if str(file_path).endswith('.gz'):
                            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                                df = pd.read_csv(f)
                        else:
                            df = pd.read_csv(file_path)
                        chain_samples[sample] = df
                        print(f"  Loaded {sample}: {len(df)} rows")
                    except Exception as e:
                        print(f"  Error loading {sample}: {e}")
            
            if len(chain_samples) < 2:
                print(f"  Skipping {chain}: not enough samples")
                continue
            
            # Calculate similarity metrics
            # Get available samples from loaded data
            available_samples = list(chain_samples.keys())
            
            # Apply sample ordering if specified - Requirements: 5.1, 5.6, 5.7
            # This ensures heatmap, data table, and CSV export all use the same sample order
            requested_sample_order = parameters.get('sample_order')
            samples_list = normalize_sample_order(available_samples, requested_sample_order)
            n_samples = len(samples_list)
            
            # Build abundance dictionaries
            sample_abundance = {}
            for sample, df in chain_samples.items():
                # Find CDR3 and reads columns
                cdr3_col = None
                reads_col = None
                for col in df.columns:
                    col_lower = col.lower()
                    if 'cdr3' in col_lower and cdr3_col is None:
                        cdr3_col = col
                    if col_lower in ['copy', 'reads', 'count', 'copies'] and reads_col is None:
                        reads_col = col
                
                if cdr3_col and reads_col:
                    abundance = {}
                    for _, row in df.iterrows():
                        cdr3 = str(row[cdr3_col])
                        reads = float(row[reads_col]) if pd.notna(row[reads_col]) else 0
                        if cdr3 and reads > 0:
                            abundance[cdr3] = abundance.get(cdr3, 0) + reads
                    sample_abundance[sample] = abundance
                    print(f"  {sample}: {len(abundance)} unique CDR3s")
            
            if len(sample_abundance) < 2:
                continue
            
            # Calculate metrics and generate heatmaps
            for metric in metrics:
                matrix = np.zeros((n_samples, n_samples))
                boundary_cases = {}  # Collect boundary case details for R虏 metrics
                
                for i, s1 in enumerate(samples_list):
                    for j, s2 in enumerate(samples_list):
                        if i == j:
                            matrix[i, j] = 1.0
                        elif s1 in sample_abundance and s2 in sample_abundance:
                            ab1, ab2 = sample_abundance[s1], sample_abundance[s2]
                            pair_key = f"{s1}_vs_{s2}"
                            
                            if metric == 'r2_inner':
                                # R虏 Inner - only shared CDR3s (inner join)
                                common = set(ab1.keys()) & set(ab2.keys())
                                if len(common) >= 2:
                                    common_sorted = sorted(common)
                                    vals1 = np.array([ab1[k] for k in common_sorted])
                                    vals2 = np.array([ab2[k] for k in common_sorted])
                                    std1, std2 = np.std(vals1), np.std(vals2)
                                    if std1 > 0 and std2 > 0:
                                        corr = np.corrcoef(vals1, vals2)[0, 1]
                                        r2_val = corr ** 2 if not np.isnan(corr) else 0
                                        matrix[i, j] = r2_val
                                        # Record boundary cases (0.0 or 1.0)
                                        if r2_val == 0.0 or r2_val == 1.0:
                                            boundary_cases[pair_key] = {
                                                'value': r2_val,
                                                'reason': 'calculated',
                                                'shared_count': len(common),
                                                'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1[k], 'copy_b': ab2[k]} for k in common_sorted[:20]]
                                            }
                                    elif std1 == 0 and std2 == 0:
                                        matrix[i, j] = 1.0
                                        boundary_cases[pair_key] = {
                                            'value': 1.0,
                                            'reason': 'both_constant',
                                            'message': '涓や釜鏍锋湰鐨勫叡浜獵DR3涓板害閮芥槸甯告暟',
                                            'shared_count': len(common),
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1[k], 'copy_b': ab2[k]} for k in common_sorted[:20]]
                                        }
                                    else:
                                        matrix[i, j] = 0.0
                                        boundary_cases[pair_key] = {
                                            'value': 0.0,
                                            'reason': 'one_constant',
                                            'message': 'One sample has constant shared CDR3 abundance.',
                                            'shared_count': len(common),
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1[k], 'copy_b': ab2[k]} for k in common_sorted[:20]]
                                        }
                                else:
                                    matrix[i, j] = 0.0
                                    boundary_cases[pair_key] = {
                                        'value': 0.0,
                                        'reason': 'insufficient_shared',
                                        'message': f'鍏变韩CDR3鏁伴噺涓嶈冻 ({len(common)} < 2)',
                                        'shared_count': len(common),
                                        'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1[k], 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]] if common else []
                                    }
                                        
                            elif metric == 'r2_outer':
                                # R虏 Outer - all CDR3s with 0 for missing (outer join)
                                all_keys = set(ab1.keys()) | set(ab2.keys())
                                common = set(ab1.keys()) & set(ab2.keys())
                                if len(all_keys) >= 2:
                                    all_sorted = sorted(all_keys)
                                    vals1 = np.array([ab1.get(k, 0) for k in all_sorted])
                                    vals2 = np.array([ab2.get(k, 0) for k in all_sorted])
                                    std1, std2 = np.std(vals1), np.std(vals2)
                                    if std1 > 0 and std2 > 0:
                                        corr = np.corrcoef(vals1, vals2)[0, 1]
                                        r2_val = corr ** 2 if not np.isnan(corr) else 0
                                        matrix[i, j] = r2_val
                                        # Record boundary cases: 0.0, 1.0, or no shared CDR3
                                        if r2_val == 0.0 or r2_val == 1.0:
                                            boundary_cases[pair_key] = {
                                                'value': r2_val,
                                                'reason': 'calculated',
                                                'total_count': len(all_keys),
                                                'shared_count': len(common),
                                                'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                            }
                                        elif len(common) == 0:
                                            # No shared CDR3 - record as special boundary case
                                            boundary_cases[pair_key] = {
                                                'value': r2_val,
                                                'reason': 'no_shared_cdr3',
                                                'message': f'鏃犲叡浜獵DR3锛孯虏鍊煎熀浜庡杩炴帴璁＄畻 (鍊?{r2_val:.4f})',
                                                'total_count': len(all_keys),
                                                'shared_count': 0,
                                                'set_a_count': len(ab1),
                                                'set_b_count': len(ab2)
                                            }
                                    elif std1 == 0 and std2 == 0:
                                        matrix[i, j] = 1.0
                                        boundary_cases[pair_key] = {
                                            'value': 1.0,
                                            'reason': 'both_constant',
                                            'message': '涓や釜鏍锋湰鐨凜DR3涓板害閮芥槸甯告暟',
                                            'total_count': len(all_keys),
                                            'shared_count': len(common),
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                        }
                                    else:
                                        matrix[i, j] = 0.0
                                        boundary_cases[pair_key] = {
                                            'value': 0.0,
                                            'reason': 'one_constant',
                                            'message': 'One sample has constant CDR3 abundance.',
                                            'total_count': len(all_keys),
                                            'shared_count': len(common),
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                        }
                                else:
                                    matrix[i, j] = 0.0
                                    boundary_cases[pair_key] = {
                                        'value': 0.0,
                                        'reason': 'insufficient_total',
                                        'message': f'鎬籆DR3鏁伴噺涓嶈冻 ({len(all_keys)} < 2)',
                                        'total_count': len(all_keys)
                                    }
                                        
                            elif metric == 'cdr3_sharing':
                                # CDR3 Sharing (unique) - directional
                                # When i < j: A鈫払 direction (intersection / |CDR3_A|)
                                # When i > j: B鈫扐 direction (intersection / |CDR3_B|)
                                set1 = set(ab1.keys())
                                set2 = set(ab2.keys())
                                intersection = len(set1 & set2)
                                common = set1 & set2
                                # Directional: divide by row sample's CDR3 count
                                if len(set1) > 0:
                                    val = intersection / len(set1)
                                    matrix[i, j] = val
                                    # Record boundary cases (0.0 or 1.0)
                                    if val == 0.0 or val == 1.0:
                                        boundary_cases[pair_key] = {
                                            'value': val,
                                            'reason': 'no_overlap' if val == 0.0 else 'full_overlap',
                                            'message': 'No shared CDR3' if val == 0.0 else 'All CDR3 from sample A exist in sample B',
                                            'set_a_count': len(set1),
                                            'set_b_count': len(set2),
                                            'intersection': intersection,
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                        }
                                else:
                                    matrix[i, j] = 0.0
                                    boundary_cases[pair_key] = {
                                        'value': 0.0,
                                        'reason': 'empty_sample',
                                        'message': '鏍锋湰A鏃燙DR3鏁版嵁',
                                        'set_a_count': 0,
                                        'set_b_count': len(set2)
                                    }
                                
                            elif metric == 'expression_sharing':
                                # Expression Sharing (reads) - directional shared reads proportion
                                # When i < j: A鈫払 direction (shared_reads / N_A)
                                # When i > j: B鈫扐 direction (shared_reads / N_B)
                                all_keys = set(ab1.keys()) | set(ab2.keys())
                                common = set(ab1.keys()) & set(ab2.keys())
                                shared_reads = sum(min(ab1.get(k, 0), ab2.get(k, 0)) for k in all_keys)
                                total_reads_a = sum(ab1.values())  # N_A (row sample)
                                total_reads_b = sum(ab2.values())  # N_B
                                # Directional: divide by row sample's total reads
                                if total_reads_a > 0:
                                    val = shared_reads / total_reads_a
                                    matrix[i, j] = val
                                    # Record boundary cases (0.0 or 1.0)
                                    if val == 0.0 or val == 1.0:
                                        boundary_cases[pair_key] = {
                                            'value': val,
                                            'reason': 'no_shared_reads' if val == 0.0 else 'full_shared_reads',
                                            'message': '鏃犲叡浜玶eads' if val == 0.0 else '鏍锋湰A鐨勬墍鏈塺eads閮戒笌鏍锋湰B鍏变韩',
                                            'shared_reads': shared_reads,
                                            'total_reads_a': total_reads_a,
                                            'total_reads_b': total_reads_b,
                                            'shared_count': len(common),
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                        }
                                else:
                                    matrix[i, j] = 0.0
                                    boundary_cases[pair_key] = {
                                        'value': 0.0,
                                        'reason': 'zero_reads',
                                        'message': '鏍锋湰A鎬籸eads涓?',
                                        'total_reads_a': 0,
                                        'total_reads_b': total_reads_b
                                    }
                                
                            elif metric == 'morisita_horn':
                                # Morisita-Horn index
                                all_keys = set(ab1.keys()) | set(ab2.keys())
                                common = set(ab1.keys()) & set(ab2.keys())
                                n_A = np.array([ab1.get(k, 0) for k in all_keys])
                                n_B = np.array([ab2.get(k, 0) for k in all_keys])
                                N_A, N_B = np.sum(n_A), np.sum(n_B)
                                if N_A > 0 and N_B > 0:
                                    D_A = np.sum((n_A / N_A) ** 2)
                                    D_B = np.sum((n_B / N_B) ** 2)
                                    numerator = 2 * np.sum(n_A * n_B)
                                    denominator = (D_A + D_B) * N_A * N_B
                                    if denominator > 0:
                                        val = numerator / denominator
                                        matrix[i, j] = val
                                        # Record boundary cases (0.0 or 1.0)
                                        if val == 0.0 or val >= 0.9999:
                                            boundary_cases[pair_key] = {
                                                'value': val,
                                                'reason': 'no_overlap' if val == 0.0 else 'high_similarity',
                                                'message': 'No overlap in shared CDR3 or abundance' if val == 0.0 else 'Highly similar abundance distribution',
                                                'total_reads_a': float(N_A),
                                                'total_reads_b': float(N_B),
                                                'simpson_a': float(D_A),
                                                'simpson_b': float(D_B),
                                                'shared_count': len(common),
                                                'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                            }
                                    else:
                                        matrix[i, j] = 0.0
                                        boundary_cases[pair_key] = {
                                            'value': 0.0,
                                            'reason': 'zero_denominator',
                                            'message': 'Morisita-Horn鍒嗘瘝涓?',
                                            'total_reads_a': float(N_A),
                                            'total_reads_b': float(N_B)
                                        }
                                else:
                                    matrix[i, j] = 0.0
                                    boundary_cases[pair_key] = {
                                        'value': 0.0,
                                        'reason': 'zero_reads',
                                        'message': f'鏍锋湰鎬籸eads涓? (N_A={N_A}, N_B={N_B})',
                                        'total_reads_a': float(N_A),
                                        'total_reads_b': float(N_B)
                                    }
                                    
                            elif metric == 'sorensen':
                                # Sorensen-Dice coefficient
                                set1 = set(ab1.keys())
                                set2 = set(ab2.keys())
                                intersection = len(set1 & set2)
                                common = set1 & set2
                                size_sum = len(set1) + len(set2)
                                if size_sum > 0:
                                    val = (2 * intersection) / size_sum
                                    matrix[i, j] = val
                                    # Record boundary cases (0.0 or 1.0)
                                    if val == 0.0 or val == 1.0:
                                        boundary_cases[pair_key] = {
                                            'value': val,
                                            'reason': 'no_overlap' if val == 0.0 else 'identical_sets',
                                            'message': '鏃犲叡浜獵DR3' if val == 0.0 else '涓や釜鏍锋湰鐨凜DR3闆嗗悎瀹屽叏鐩稿悓',
                                            'set_a_count': len(set1),
                                            'set_b_count': len(set2),
                                            'intersection': intersection,
                                            'shared_cdr3': [{'cdr3': k[:30], 'copy_a': ab1.get(k, 0), 'copy_b': ab2.get(k, 0)} for k in sorted(common)[:20]]
                                        }
                                else:
                                    matrix[i, j] = 0.0
                                    boundary_cases[pair_key] = {
                                        'value': 0.0,
                                        'reason': 'empty_samples',
                                        'message': '涓や釜鏍锋湰閮芥棤CDR3鏁版嵁',
                                        'set_a_count': 0,
                                        'set_b_count': 0
                                    }
                
                # Create heatmap with metric-specific color schemes
                fig, ax = plt.subplots(figsize=(
                    chart_config.get('figure_width', 10),
                    chart_config.get('figure_height', 8)
                ))
                
                # Metric-specific color schemes (matching artificial_peps_similarity_heatmaps.py)
                color_schemes = {
                    'expression_sharing': 'Blues',
                    'r2_outer': 'Purples',
                    'r2_inner': 'Greens',
                    'morisita_horn': 'Oranges',
                    'cdr3_sharing': 'Reds',
                    'sorensen': 'YlGnBu',
                }
                cmap = color_schemes.get(metric, 'YlOrRd')
                
                # Calculate actual data range (excluding diagonal)
                matrix_copy = matrix.copy()
                np.fill_diagonal(matrix_copy, np.nan)
                vmin = np.nanmin(matrix_copy)
                vmax = np.nanmax(matrix_copy)
                if np.isnan(vmin) or vmin == vmax:
                    vmin, vmax = 0, 1
                
                # Create mask for diagonal
                mask = np.eye(n_samples, dtype=bool)
                
                # Create smart-formatted annotation array using format_similarity_value
                # Requirements: 2.5, 2.6 - Use smart formatting for heatmap annotations
                annot_array = np.empty_like(matrix, dtype=object)
                for i in range(n_samples):
                    for j in range(n_samples):
                        annot_array[i, j] = format_similarity_value(matrix[i, j])
                
                sns.heatmap(
                    matrix,
                    xticklabels=samples_list,
                    yticklabels=samples_list,
                    annot=annot_array if chart_config.get('annotation', True) else False,
                    fmt='',  # Empty format since we provide pre-formatted strings
                    cmap=cmap,
                    mask=mask,
                    vmin=vmin,
                    vmax=vmax,
                    square=True,
                    linewidths=0.5,
                    linecolor='gray',
                    ax=ax,
                    cbar_kws={'label': 'Similarity Score', 'shrink': 0.8}
                )
                ax.set_title(f'{chain} - {metric.replace("_", " ").title()}', fontsize=14, fontweight='bold', pad=20)
                ax.set_xlabel('Sample', fontsize=12, fontweight='bold')
                ax.set_ylabel('Sample', fontsize=12, fontweight='bold')
                plt.xticks(rotation=45, ha='right')
                plt.yticks(rotation=0)
                plt.tight_layout()
                
                # Save heatmap
                viz_path = results_dir / f'{chain}_{metric}_heatmap.png'
                fig.savefig(viz_path, dpi=150, bbox_inches='tight')
                plt.close(fig)
                
                # Prepare metadata with boundary cases for all metrics
                viz_metadata = {'chain': chain, 'metric': metric}
                if boundary_cases:
                    viz_metadata['boundary_cases'] = boundary_cases
                
                results.items.append(AnalysisResultItem(
                    result_type='visualization',
                    name=f'{chain}_{metric}_heatmap',
                    file_path=str(viz_path),
                    mime_type='image/png',
                    metadata=viz_metadata
                ))
                
                # Save matrix as CSV
                matrix_df = pd.DataFrame(matrix, index=samples_list, columns=samples_list)
                csv_path = results_dir / f'{chain}_{metric}_matrix.csv'
                matrix_df.to_csv(csv_path)
                
                # Create table_data with both raw values and formatted display values
                # Requirements: 2.5 - Include formatted display values while preserving raw values
                formatted_rows = []
                for i, s in enumerate(samples_list):
                    row = [s]  # Sample name as first column
                    for j in range(n_samples):
                        # Store as dict with raw and formatted values
                        row.append({
                            'raw': float(matrix[i, j]),
                            'formatted': format_similarity_value(matrix[i, j])
                        })
                    formatted_rows.append(row)
                
                # Prepare table_data with boundary cases for all metrics
                table_data_dict = {
                    'columns': ['Sample'] + samples_list,
                    'rows': formatted_rows,
                    'raw_rows': [[s] + list(matrix[i]) for i, s in enumerate(samples_list)]
                }
                if boundary_cases:
                    table_data_dict['boundary_cases'] = boundary_cases
                
                results.items.append(AnalysisResultItem(
                    result_type='data_table',
                    name=f'{chain}_{metric}_matrix',
                    file_path=str(csv_path),
                    mime_type='text/csv',
                    table_data=table_data_dict
                ))
            
            chain_progress += chain_step
        
        print(f"Generated {len(results.items)} result items")
        return results
    
    def _execute_sequencing_depth_analysis(
        self,
        analysis_id: str,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any],
        results_dir: Path
    ) -> AnalysisResults:
        """Execute sequencing depth analysis using integrated engine."""
        from flask_app.services.integrated_analysis import IntegratedAnalysisEngine
        
        results = AnalysisResults()
        
        try:
            # Initialize integrated engine
            engine = IntegratedAnalysisEngine()
            
            self.update_progress(analysis_id, 25.0, 'Running sequencing depth analysis')
            
            # Run analysis
            analysis_results = engine.run_sequencing_depth_analysis(
                df, field_mapping, parameters, chart_config
            )
            
            # Process results
            for chart_type, data in analysis_results.items():
                # Save chart
                if 'chart' in data and 'image' in data['chart']:
                    # Extract base64 image data
                    image_data = data['chart']['image'].split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    
                    viz_path = results_dir / f'{chart_type}.png'
                    with open(viz_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    results.items.append(AnalysisResultItem(
                        result_type='visualization',
                        name=chart_type,
                        file_path=str(viz_path),
                        mime_type='image/png',
                        metadata=data['chart'].get('metadata', {})
                    ))
                
                # Save data table
                if 'table_data' in data:
                    table_data = data['table_data']
                    
                    results.items.append(AnalysisResultItem(
                        result_type='data_table',
                        name=f'{chart_type}_data',
                        file_path=str(results_dir / f'{chart_type}.csv'),
                        mime_type='text/csv',
                        table_data=table_data
                    ))
                    
                    # Save CSV
                    df_data = pd.DataFrame(table_data['data'])
                    df_data.to_csv(results_dir / f'{chart_type}.csv', index=False)
        
        except Exception as e:
            print(f"Sequencing depth analysis error: {e}")
            raise
        
        return results

    
    def _execute_diversity_analysis(
        self,
        analysis_id: str,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any],
        results_dir: Path
    ) -> AnalysisResults:
        """Execute diversity metrics analysis using integrated engine."""
        from flask_app.services.integrated_analysis import IntegratedAnalysisEngine
        
        results = AnalysisResults()
        
        try:
            # Initialize integrated engine
            engine = IntegratedAnalysisEngine()
            
            self.update_progress(analysis_id, 25.0, 'Running diversity analysis')
            
            # Run analysis
            analysis_results = engine.run_diversity_analysis(
                df, field_mapping, parameters, chart_config
            )
            
            # Process results
            for chart_type, data in analysis_results.items():
                # Save chart
                if 'chart' in data and 'image' in data['chart']:
                    # Extract base64 image data
                    image_data = data['chart']['image'].split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    
                    viz_path = results_dir / f'{chart_type}.png'
                    with open(viz_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    results.items.append(AnalysisResultItem(
                        result_type='visualization',
                        name=chart_type,
                        file_path=str(viz_path),
                        mime_type='image/png',
                        metadata=data['chart'].get('metadata', {})
                    ))
                
                # Save data table
                if 'table_data' in data:
                    table_data = data['table_data']
                    
                    results.items.append(AnalysisResultItem(
                        result_type='data_table',
                        name=f'{chart_type}_data',
                        file_path=str(results_dir / f'{chart_type}.csv'),
                        mime_type='text/csv',
                        table_data=table_data
                    ))
                    
                    # Save CSV
                    df_data = pd.DataFrame(table_data['data'])
                    df_data.to_csv(results_dir / f'{chart_type}.csv', index=False)
        
        except Exception as e:
            print(f"Diversity analysis error: {e}")
            raise
        
        return results
    
    def _execute_chain_analysis(
        self,
        analysis_id: str,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any],
        results_dir: Path
    ) -> AnalysisResults:
        """Execute chain-specific analysis using integrated engine."""
        from flask_app.services.integrated_analysis import IntegratedAnalysisEngine
        
        results = AnalysisResults()
        
        try:
            # Initialize integrated engine
            engine = IntegratedAnalysisEngine()
            
            self.update_progress(analysis_id, 25.0, 'Running chain analysis')
            
            # Run analysis
            analysis_results = engine.run_chain_analysis(
                df, field_mapping, parameters, chart_config
            )
            
            # Process results
            for chart_type, data in analysis_results.items():
                # Save chart
                if 'chart' in data and 'image' in data['chart']:
                    # Extract base64 image data
                    image_data = data['chart']['image'].split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    
                    viz_path = results_dir / f'{chart_type}.png'
                    with open(viz_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    results.items.append(AnalysisResultItem(
                        result_type='visualization',
                        name=chart_type,
                        file_path=str(viz_path),
                        mime_type='image/png',
                        metadata=data['chart'].get('metadata', {})
                    ))
                
                # Save data table
                if 'table_data' in data:
                    table_data = data['table_data']
                    
                    results.items.append(AnalysisResultItem(
                        result_type='data_table',
                        name=f'{chart_type}_data',
                        file_path=str(results_dir / f'{chart_type}.csv'),
                        mime_type='text/csv',
                        table_data=table_data
                    ))
                    
                    # Save CSV
                    df_data = pd.DataFrame(table_data['data'])
                    df_data.to_csv(results_dir / f'{chart_type}.csv', index=False)
        
        except Exception as e:
            print(f"Chain analysis error: {e}")
            raise
        
        return results
    
    def _dataframe_to_table(
        self,
        df: pd.DataFrame,
        index_name: str = 'Index'
    ) -> Dict[str, Any]:
        """Convert a DataFrame to table format for frontend display."""
        records = []
        for idx in df.index:
            record = {index_name: str(idx)}
            for col in df.columns:
                value = df.loc[idx, col]
                if pd.isna(value):
                    record[str(col)] = None
                elif isinstance(value, float):
                    record[str(col)] = round(value, 4)
                else:
                    record[str(col)] = value
            records.append(record)
        
        return {
            'columns': [index_name] + [str(c) for c in df.columns],
            'data': records,
            'row_count': len(records)
        }


# Global service instance (will be initialized with app)
analysis_service: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """Get the global analysis service instance."""
    global analysis_service
    if analysis_service is None:
        raise RuntimeError("Analysis service not initialized. Call init_analysis_service first.")
    return analysis_service


def init_analysis_service(app) -> AnalysisService:
    """Initialize the global analysis service with Flask app."""
    global analysis_service
    analysis_service = AnalysisService(app)
    return analysis_service

