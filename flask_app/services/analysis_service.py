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
        chart_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new analysis task.
        
        Args:
            analysis_type: Type of analysis to perform
            file_id: ID of the uploaded file to analyze
            field_mapping: Mapping from required fields to source columns
            parameters: Analysis-specific parameters
            chart_config: Chart configuration parameters
            
        Returns:
            Analysis task ID
            
        Requirements: 8.1
        """
        from models.database import db, Analysis, File
        from exceptions import ValidationError, FileNotFoundError as AppFileNotFoundError
        
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
        
        # Create analysis record
        analysis_id = str(uuid.uuid4())
        analysis = Analysis(
            id=analysis_id,
            type=analysis_type,
            file_id=file_id,  # Can be None for directory-based analysis
            field_mapping=field_mapping,
            parameters=parameters or {},
            chart_config=chart_config or {},
            status=AnalysisStatus.PENDING.value,
            progress=0.0,
            current_step='Initializing',
            created_at=datetime.utcnow()
        )
        
        db.session.add(analysis)
        db.session.commit()
        
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
        from models.database import Analysis
        from exceptions import AnalysisNotFoundError
        
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
            'created_at': analysis.created_at.isoformat() if analysis.created_at else None,
            'started_at': analysis.started_at.isoformat() if analysis.started_at else None,
            'completed_at': analysis.completed_at.isoformat() if analysis.completed_at else None
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
        from models.database import Analysis, AnalysisResult
        from exceptions import AnalysisNotFoundError
        
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
            'created_at': analysis.created_at.isoformat() if analysis.created_at else None,
            'completed_at': analysis.completed_at.isoformat() if analysis.completed_at else None
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
        from models.database import Analysis, AnalysisResult
        from exceptions import AnalysisNotFoundError, ValidationError
        
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
        from models.database import db, Analysis
        
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
    
    def retry_analysis(self, analysis_id: str) -> bool:
        """
        Retry a failed analysis task.
        
        Args:
            analysis_id: Analysis task ID
            
        Returns:
            True if retry was initiated, False otherwise
            
        Requirements: 8.3
        """
        from models.database import db, Analysis
        from exceptions import AnalysisNotFoundError, ValidationError
        
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
        from models.database import db, Analysis
        from exceptions import AnalysisNotFoundError, ValidationError
        
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
        from models.database import db, Analysis, AnalysisResult, File
        from services.file_parser import FileParserService
        
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
                results_dir = Path(self.results_folder) / analysis_id
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
        from services.integrated_analysis import IntegratedAnalysisEngine
        from services.data_table import DataTableService
        
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
            samples_list = list(chain_samples.keys())
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
                
                for i, s1 in enumerate(samples_list):
                    for j, s2 in enumerate(samples_list):
                        if i == j:
                            matrix[i, j] = 1.0
                        elif s1 in sample_abundance and s2 in sample_abundance:
                            ab1, ab2 = sample_abundance[s1], sample_abundance[s2]
                            
                            if metric == 'r2_inner':
                                # R² Inner - only shared CDR3s (inner join)
                                common = set(ab1.keys()) & set(ab2.keys())
                                if len(common) >= 2:
                                    vals1 = np.array([ab1[k] for k in common])
                                    vals2 = np.array([ab2[k] for k in common])
                                    if np.std(vals1) > 0 and np.std(vals2) > 0:
                                        corr = np.corrcoef(vals1, vals2)[0, 1]
                                        matrix[i, j] = corr ** 2 if not np.isnan(corr) else 0
                                        
                            elif metric == 'r2_outer':
                                # R² Outer - all CDR3s with 0 for missing (outer join)
                                all_keys = set(ab1.keys()) | set(ab2.keys())
                                if len(all_keys) >= 2:
                                    vals1 = np.array([ab1.get(k, 0) for k in all_keys])
                                    vals2 = np.array([ab2.get(k, 0) for k in all_keys])
                                    if np.std(vals1) > 0 and np.std(vals2) > 0:
                                        corr = np.corrcoef(vals1, vals2)[0, 1]
                                        matrix[i, j] = corr ** 2 if not np.isnan(corr) else 0
                                        
                            elif metric == 'cdr3_sharing':
                                # CDR3 Sharing (unique) - normalized by min set size
                                set1 = set(ab1.keys())
                                set2 = set(ab2.keys())
                                intersection = len(set1 & set2)
                                min_size = min(len(set1), len(set2))
                                matrix[i, j] = intersection / min_size if min_size > 0 else 0
                                
                            elif metric == 'expression_sharing':
                                # Expression Sharing (reads) - shared reads proportion
                                all_keys = set(ab1.keys()) | set(ab2.keys())
                                shared_reads = sum(min(ab1.get(k, 0), ab2.get(k, 0)) for k in all_keys)
                                total_reads = sum(ab1.values()) + sum(ab2.values())
                                matrix[i, j] = (2 * shared_reads) / total_reads if total_reads > 0 else 0
                                
                            elif metric == 'morisita_horn':
                                # Morisita-Horn index
                                all_keys = set(ab1.keys()) | set(ab2.keys())
                                n_A = np.array([ab1.get(k, 0) for k in all_keys])
                                n_B = np.array([ab2.get(k, 0) for k in all_keys])
                                N_A, N_B = np.sum(n_A), np.sum(n_B)
                                if N_A > 0 and N_B > 0:
                                    D_A = np.sum((n_A / N_A) ** 2)
                                    D_B = np.sum((n_B / N_B) ** 2)
                                    numerator = 2 * np.sum(n_A * n_B)
                                    denominator = (D_A + D_B) * N_A * N_B
                                    matrix[i, j] = numerator / denominator if denominator > 0 else 0
                                    
                            elif metric == 'sorensen':
                                # Sorensen-Dice coefficient
                                set1 = set(ab1.keys())
                                set2 = set(ab2.keys())
                                intersection = len(set1 & set2)
                                size_sum = len(set1) + len(set2)
                                matrix[i, j] = (2 * intersection) / size_sum if size_sum > 0 else 0
                
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
                
                sns.heatmap(
                    matrix,
                    xticklabels=samples_list,
                    yticklabels=samples_list,
                    annot=chart_config.get('annotation', True),
                    fmt='.3f',
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
                
                results.items.append(AnalysisResultItem(
                    result_type='visualization',
                    name=f'{chain}_{metric}_heatmap',
                    file_path=str(viz_path),
                    mime_type='image/png',
                    metadata={'chain': chain, 'metric': metric}
                ))
                
                # Save matrix as CSV
                matrix_df = pd.DataFrame(matrix, index=samples_list, columns=samples_list)
                csv_path = results_dir / f'{chain}_{metric}_matrix.csv'
                matrix_df.to_csv(csv_path)
                
                results.items.append(AnalysisResultItem(
                    result_type='data_table',
                    name=f'{chain}_{metric}_matrix',
                    file_path=str(csv_path),
                    mime_type='text/csv',
                    table_data={
                        'columns': ['Sample'] + samples_list,
                        'rows': [[s] + list(matrix[i]) for i, s in enumerate(samples_list)]
                    }
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
        from services.integrated_analysis import IntegratedAnalysisEngine
        
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
        from services.integrated_analysis import IntegratedAnalysisEngine
        
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
        from services.integrated_analysis import IntegratedAnalysisEngine
        
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
