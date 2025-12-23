"""
Integrated Analysis Engine
Combines analysis logic from standalone scripts for Flask integration.
Based on scripts from parent directory:
- artificial_peps_similarity_heatmaps.py (similarity analysis)
- sequencing_depth_visualization.py (sequencing depth)
- extract_ig_diversity_metrics.py (diversity metrics)
- chain_specific_similarity_analysis.py (chain specific)
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
from typing import Dict, Any, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Set Chinese font support
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class IntegratedAnalysisEngine:
    """
    Integrated analysis engine that combines all analysis functionality.
    """
    
    def __init__(self):
        """Initialize the integrated analysis engine."""
        pass
    
    def _fig_to_base64(self, fig) -> str:
        """Convert matplotlib figure to base64 string."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
        return f"data:image/png;base64,{img_base64}"
    
    # =========================================================================
    # SIMILARITY HEATMAP ANALYSIS
    # Based on: artificial_peps_similarity_heatmaps.py
    # =========================================================================
    
    def run_similarity_analysis(
        self,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run similarity heatmap analysis.
        
        Expected columns (via field_mapping):
        - sample: Sample identifier
        - cdr3: CDR3 sequence (e.g., CDR3(pep))
        - reads: Read count / copy number
        """
        results = {}
        
        print(f"\n=== Similarity Analysis Debug ===")
        print(f"DataFrame shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"Field mapping received: {field_mapping}")
        
        # Get column names from field mapping or auto-detect
        sample_col = field_mapping.get('sample') if field_mapping.get('sample') else None
        cdr3_col = field_mapping.get('cdr3') if field_mapping.get('cdr3') else None
        reads_col = field_mapping.get('reads') if field_mapping.get('reads') else None
        
        # Find actual columns (case-insensitive) with extended alternatives
        sample_col = self._find_column(df, sample_col, ['sample', 'sample_id', 'Sample', 'Barcode', 'sample_name', 'SampleID'])
        cdr3_col = self._find_column(df, cdr3_col, ['CDR3(pep)', 'cdr3', 'CDR3', 'cdr3_aa', 'CDR3.aa', 'aminoAcid', 'aaSeqCDR3'])
        reads_col = self._find_column(df, reads_col, ['copy', 'reads', 'count', 'Copy', 'Reads', 'cloneCount', 'frequency', 'freq'])
        
        print(f"Resolved columns - sample: {sample_col}, cdr3: {cdr3_col}, reads: {reads_col}")
        
        if not all([sample_col, cdr3_col, reads_col]):
            raise ValueError(f"Required columns not found. Need sample, cdr3, reads. Available: {list(df.columns)}")
        
        # Ensure reads column is numeric
        df[reads_col] = pd.to_numeric(df[reads_col], errors='coerce').fillna(0)
        
        # Group data by sample
        samples = df[sample_col].unique().tolist()
        print(f"Found {len(samples)} samples: {samples[:5]}{'...' if len(samples) > 5 else ''}")
        
        # If only 1 sample found, check if data has different structure
        if len(samples) <= 1:
            print(f"WARNING: Only {len(samples)} sample(s) found. Check sample column.")
            print(f"First 5 unique values in sample column: {df[sample_col].unique()[:5].tolist()}")
            print(f"Sample data head:\n{df[[sample_col, cdr3_col, reads_col]].head()}")
        
        sample_data = {s: df[df[sample_col] == s] for s in samples}
        
        # Build CDR3 abundance dictionaries for each sample
        sample_abundance = {}
        for sample, sample_df in sample_data.items():
            if cdr3_col in sample_df.columns and reads_col in sample_df.columns:
                # Drop NA values before grouping
                valid_df = sample_df[[cdr3_col, reads_col]].dropna()
                if len(valid_df) > 0:
                    abundance = valid_df.groupby(cdr3_col)[reads_col].sum().to_dict()
                    sample_abundance[sample] = abundance
                    print(f"Sample '{sample}': {len(abundance)} unique CDR3s, total reads: {sum(abundance.values()):.0f}")
                else:
                    print(f"Sample '{sample}': No valid data after removing NAs")
        
        print(f"=== End Similarity Analysis Debug ===\n")
        
        # Get metrics to calculate
        metrics = parameters.get('metrics', ['r2_inner', 'r2_outer', 'cdr3_sharing', 
                                              'expression_sharing', 'morisita_horn', 'sorensen'])
        
        for metric in metrics:
            try:
                if metric == 'r2_inner':
                    matrix = self._calculate_r2_inner(samples, sample_abundance)
                elif metric == 'r2_outer':
                    matrix = self._calculate_r2_outer(samples, sample_abundance)
                elif metric == 'cdr3_sharing':
                    cdr3_sets = {s: set(sample_data[s][cdr3_col].dropna().unique()) for s in samples}
                    matrix = self._calculate_cdr3_sharing(samples, cdr3_sets)
                elif metric == 'expression_sharing':
                    matrix = self._calculate_expression_sharing(samples, sample_abundance)
                elif metric == 'morisita_horn':
                    matrix = self._calculate_morisita_horn(samples, sample_abundance)
                elif metric == 'sorensen':
                    cdr3_sets = {s: set(sample_data[s][cdr3_col].dropna().unique()) for s in samples}
                    matrix = self._calculate_sorensen(samples, cdr3_sets)
                else:
                    continue
                
                # Generate heatmap
                fig = self._create_heatmap(matrix, metric, chart_config)
                image_base64 = self._fig_to_base64(fig)
                
                results[metric] = {
                    'heatmap': {
                        'image': image_base64,
                        'metadata': {
                            'metric': metric,
                            'samples': samples,
                            'shape': matrix.shape
                        }
                    },
                    'matrix': matrix.to_dict(),
                    'table_data': {
                        'columns': [{'field': 'sample', 'title': 'Sample'}] + 
                                   [{'field': s, 'title': s} for s in samples],
                        'data': [{'sample': s, **{s2: round(matrix.loc[s, s2], 4) for s2 in samples}} 
                                 for s in samples]
                    }
                }
            except Exception as e:
                print(f"Error calculating {metric}: {e}")
                continue
        
        return results
    
    def _find_column(self, df: pd.DataFrame, preferred: str, alternatives: List[str]) -> Optional[str]:
        """Find a column by name, trying alternatives."""
        if preferred in df.columns:
            return preferred
        for alt in alternatives:
            if alt in df.columns:
                return alt
            # Case-insensitive match
            for col in df.columns:
                if col.lower() == alt.lower():
                    return col
        return None
    
    def _calculate_r2_inner(self, samples: List[str], sample_abundance: Dict) -> pd.DataFrame:
        """Calculate R² inner (inner join correlation)."""
        n = len(samples)
        r2_matrix = np.ones((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                sample_i, sample_j = samples[i], samples[j]
                
                if sample_i not in sample_abundance or sample_j not in sample_abundance:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0
                    continue
                
                # Inner join: only shared CDR3s
                shared_cdr3 = set(sample_abundance[sample_i].keys()) & set(sample_abundance[sample_j].keys())
                
                if len(shared_cdr3) < 2:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0
                    continue
                
                abundance_i = np.array([sample_abundance[sample_i][c] for c in shared_cdr3])
                abundance_j = np.array([sample_abundance[sample_j][c] for c in shared_cdr3])
                
                if np.std(abundance_i) > 0 and np.std(abundance_j) > 0:
                    corr = np.corrcoef(abundance_i, abundance_j)[0, 1]
                    r2_matrix[i, j] = r2_matrix[j, i] = corr ** 2
                else:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0
        
        return pd.DataFrame(r2_matrix, index=samples, columns=samples)
    
    def _calculate_r2_outer(self, samples: List[str], sample_abundance: Dict) -> pd.DataFrame:
        """Calculate R² outer (outer join correlation)."""
        n = len(samples)
        r2_matrix = np.ones((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                sample_i, sample_j = samples[i], samples[j]
                
                if sample_i not in sample_abundance or sample_j not in sample_abundance:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0
                    continue
                
                # Outer join: all CDR3s
                all_cdr3 = set(sample_abundance[sample_i].keys()) | set(sample_abundance[sample_j].keys())
                
                if len(all_cdr3) < 2:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0
                    continue
                
                abundance_i = np.array([sample_abundance[sample_i].get(c, 0) for c in all_cdr3])
                abundance_j = np.array([sample_abundance[sample_j].get(c, 0) for c in all_cdr3])
                
                if np.std(abundance_i) > 0 and np.std(abundance_j) > 0:
                    corr = np.corrcoef(abundance_i, abundance_j)[0, 1]
                    r2_matrix[i, j] = r2_matrix[j, i] = corr ** 2
                else:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0
        
        return pd.DataFrame(r2_matrix, index=samples, columns=samples)
    
    def _calculate_cdr3_sharing(self, samples: List[str], cdr3_sets: Dict) -> pd.DataFrame:
        """Calculate CDR3 sharing (unique clone sharing)."""
        n = len(samples)
        matrix = np.ones((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                set_i = cdr3_sets.get(samples[i], set())
                set_j = cdr3_sets.get(samples[j], set())
                
                intersection = len(set_i & set_j)
                min_size = min(len(set_i), len(set_j))
                
                if min_size > 0:
                    matrix[i, j] = matrix[j, i] = intersection / min_size
                else:
                    matrix[i, j] = matrix[j, i] = 0
        
        return pd.DataFrame(matrix, index=samples, columns=samples)
    
    def _calculate_expression_sharing(self, samples: List[str], sample_abundance: Dict) -> pd.DataFrame:
        """Calculate expression sharing (reads overlap)."""
        n = len(samples)
        matrix = np.ones((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                sample_i, sample_j = samples[i], samples[j]
                
                if sample_i not in sample_abundance or sample_j not in sample_abundance:
                    matrix[i, j] = matrix[j, i] = 0
                    continue
                
                all_cdr3 = set(sample_abundance[sample_i].keys()) | set(sample_abundance[sample_j].keys())
                
                shared_reads = sum(
                    min(sample_abundance[sample_i].get(c, 0), sample_abundance[sample_j].get(c, 0))
                    for c in all_cdr3
                )
                total_reads = sum(sample_abundance[sample_i].values()) + sum(sample_abundance[sample_j].values())
                
                if total_reads > 0:
                    matrix[i, j] = matrix[j, i] = (2 * shared_reads) / total_reads
                else:
                    matrix[i, j] = matrix[j, i] = 0
        
        return pd.DataFrame(matrix, index=samples, columns=samples)
    
    def _calculate_morisita_horn(self, samples: List[str], sample_abundance: Dict) -> pd.DataFrame:
        """Calculate Morisita-Horn similarity index."""
        n = len(samples)
        matrix = np.ones((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                sample_i, sample_j = samples[i], samples[j]
                
                if sample_i not in sample_abundance or sample_j not in sample_abundance:
                    matrix[i, j] = matrix[j, i] = 0
                    continue
                
                all_cdr3 = set(sample_abundance[sample_i].keys()) | set(sample_abundance[sample_j].keys())
                
                x = np.array([sample_abundance[sample_i].get(c, 0) for c in all_cdr3])
                y = np.array([sample_abundance[sample_j].get(c, 0) for c in all_cdr3])
                
                xy = np.sum(x * y)
                sum_x2 = np.sum(x ** 2)
                sum_y2 = np.sum(y ** 2)
                sum_x = np.sum(x)
                sum_y = np.sum(y)
                
                if sum_x > 0 and sum_y > 0:
                    denominator = (sum_x2 / sum_x**2 + sum_y2 / sum_y**2) * sum_x * sum_y
                    if denominator > 0:
                        mh = (2 * xy) / denominator
                        matrix[i, j] = matrix[j, i] = min(mh, 1.0)
                    else:
                        matrix[i, j] = matrix[j, i] = 0
                else:
                    matrix[i, j] = matrix[j, i] = 0
        
        return pd.DataFrame(matrix, index=samples, columns=samples)
    
    def _calculate_sorensen(self, samples: List[str], cdr3_sets: Dict) -> pd.DataFrame:
        """Calculate Sorensen-Dice similarity coefficient."""
        n = len(samples)
        matrix = np.ones((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                set_i = cdr3_sets.get(samples[i], set())
                set_j = cdr3_sets.get(samples[j], set())
                
                intersection = len(set_i & set_j)
                total = len(set_i) + len(set_j)
                
                if total > 0:
                    matrix[i, j] = matrix[j, i] = (2 * intersection) / total
                else:
                    matrix[i, j] = matrix[j, i] = 0
        
        return pd.DataFrame(matrix, index=samples, columns=samples)
    
    def _create_heatmap(self, matrix: pd.DataFrame, title: str, chart_config: Dict) -> plt.Figure:
        """Create a heatmap visualization with metric-specific color schemes."""
        fig_width = chart_config.get('figure_width', 10)
        fig_height = chart_config.get('figure_height', 8)
        font_size = chart_config.get('font_size', 12)
        show_annotation = chart_config.get('annotation', True)
        
        # Metric-specific color schemes (matching artificial_peps_similarity_heatmaps.py)
        color_schemes = {
            'expression_sharing': 'Blues',
            'r2_outer': 'Purples',
            'r2_inner': 'Greens',
            'morisita_horn': 'Oranges',
            'cdr3_sharing': 'Reds',
            'sorensen': 'YlGnBu',
            'default': 'YlOrRd'
        }
        
        # Get color scheme based on metric name
        metric_key = title.lower().replace(' ', '_').replace('-', '_')
        color_scheme = color_schemes.get(metric_key, color_schemes['default'])
        
        # Calculate actual data range (excluding diagonal)
        values = matrix.values.copy()
        np.fill_diagonal(values, np.nan)  # Exclude diagonal from min/max calculation
        vmin = np.nanmin(values)  # Start from actual minimum
        vmax = np.nanmax(values)  # End at actual maximum
        
        # Handle edge case where all values are the same
        if np.isnan(vmin) or vmin == vmax:
            vmin = 0
            vmax = 1
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        
        # Create mask for diagonal (hide diagonal values)
        mask = np.eye(len(matrix), dtype=bool)
        
        sns.heatmap(
            matrix,
            annot=show_annotation,
            fmt='.3f',
            cmap=color_scheme,
            mask=mask,
            vmin=vmin,
            vmax=vmax,
            square=True,
            ax=ax,
            linewidths=0.5,
            linecolor='gray',
            annot_kws={'size': font_size - 2},
            cbar_kws={'label': 'Similarity Score', 'shrink': 0.8}
        )
        
        custom_title = chart_config.get('title', '')
        if custom_title:
            ax.set_title(custom_title, fontsize=font_size + 2, fontweight='bold', pad=20)
        else:
            ax.set_title(f'{title.replace("_", " ").title()} Similarity Matrix', 
                        fontsize=font_size + 2, fontweight='bold', pad=20)
        
        ax.set_xlabel('Sample', fontsize=font_size, fontweight='bold')
        ax.set_ylabel('Sample', fontsize=font_size, fontweight='bold')
        ax.tick_params(axis='both', labelsize=font_size)
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()
        
        return fig
    
    # =========================================================================
    # SEQUENCING DEPTH ANALYSIS
    # Based on: sequencing_depth_visualization.py
    # =========================================================================
    
    def run_sequencing_depth_analysis(
        self,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run sequencing depth analysis.
        
        Expected columns:
        - sample: Sample identifier
        - total_rna: Total Receptor RNA
        - reads_umi: Reads/UMI ratio
        - migs_good: MigsGoodTotal
        - reads_good: ReadsGoodTotal
        
        Parameters:
        - baseline_config: Optional dict with baseline_type, baseline_id, baseline_group_sample_ids
        
        Requirements: 3.7
        """
        results = {}
        
        # Get column mappings
        sample_col = self._find_column(df, field_mapping.get('sample', 'sample'), 
                                       ['sample', 'Sample', 'sample_id', 'Barcode'])
        
        metrics_config = {
            'total_rna': {
                'columns': ['Total Receptor RNA', 'total_rna', 'TotalReceptorRNA'],
                'title': 'Total Receptor RNA',
                'color': 'skyblue',
                'show': parameters.get('show_total_rna', True)
            },
            'reads_umi': {
                'columns': ['Reads/UMI', 'reads_umi', 'ReadsUMI'],
                'title': 'Reads/UMI',
                'color': 'lightcoral',
                'show': parameters.get('show_reads_umi', True)
            },
            'migs_good': {
                'columns': ['MigsGoodTotal', 'migs_good', 'MIGsGoodTotal'],
                'title': 'MigsGoodTotal',
                'color': 'lightgreen',
                'show': parameters.get('show_migs_good', True)
            },
            'reads_good': {
                'columns': ['ReadsGoodTotal', 'reads_good', 'ReadsGood'],
                'title': 'ReadsGoodTotal',
                'color': 'gold',
                'show': parameters.get('show_reads_good', True)
            }
        }
        
        # Get sample names
        if sample_col and sample_col in df.columns:
            samples = df[sample_col].tolist()
        else:
            samples = [f'Sample_{i+1}' for i in range(len(df))]
        
        # Collect available metrics
        available_metrics = {}
        for metric_key, config in metrics_config.items():
            if not config['show']:
                continue
            col = None
            for col_name in config['columns']:
                found = self._find_column(df, col_name, config['columns'])
                if found:
                    col = found
                    break
            if col and col in df.columns:
                available_metrics[metric_key] = {
                    'column': col,
                    'values': df[col].tolist(),
                    'title': config['title'],
                    'color': config['color']
                }
        
        if not available_metrics:
            raise ValueError("No sequencing depth metrics found in data")
        
        # Create comparison chart
        fig = self._create_sequencing_depth_chart(samples, available_metrics, chart_config)
        image_base64 = self._fig_to_base64(fig)
        
        results['sequencing_depth'] = {
            'chart': {
                'image': image_base64,
                'metadata': {
                    'samples': samples,
                    'metrics': list(available_metrics.keys())
                }
            },
            'table_data': {
                'columns': [{'field': 'sample', 'title': 'Sample'}] + 
                           [{'field': k, 'title': v['title']} for k, v in available_metrics.items()],
                'data': [
                    {'sample': samples[i], **{k: v['values'][i] for k, v in available_metrics.items()}}
                    for i in range(len(samples))
                ]
            }
        }
        
        # Handle baseline configuration for percentage difference calculation
        baseline_config = parameters.get('baseline_config')
        if baseline_config:
            pct_diff_results = self._calculate_baseline_percentage_diff(
                samples, available_metrics, baseline_config, chart_config
            )
            if pct_diff_results:
                results['percentage_difference'] = pct_diff_results
        
        return results
    
    def _calculate_baseline_percentage_diff(
        self,
        samples: List[str],
        metrics: Dict[str, Any],
        baseline_config: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate percentage differences relative to baseline.
        
        Requirements: 3.7, 17.1, 17.2
        """
        baseline_type = baseline_config.get('baseline_type')
        baseline_id = baseline_config.get('baseline_id')
        baseline_group_sample_ids = baseline_config.get('baseline_group_sample_ids', [])
        
        if not baseline_type or not baseline_id:
            return None
        
        # Calculate baseline values
        baseline_values = {}
        
        if baseline_type == 'sample':
            # Find the baseline sample index
            if baseline_id in samples:
                baseline_idx = samples.index(baseline_id)
                for metric_key, metric_data in metrics.items():
                    baseline_values[metric_key] = metric_data['values'][baseline_idx]
            else:
                return None
        
        elif baseline_type == 'group':
            # Calculate group average for baseline
            if baseline_group_sample_ids:
                for metric_key, metric_data in metrics.items():
                    group_values = []
                    for sample_id in baseline_group_sample_ids:
                        if sample_id in samples:
                            idx = samples.index(sample_id)
                            group_values.append(metric_data['values'][idx])
                    if group_values:
                        baseline_values[metric_key] = sum(group_values) / len(group_values)
                    else:
                        baseline_values[metric_key] = 0
            else:
                return None
        
        if not baseline_values:
            return None
        
        # Calculate percentage differences
        pct_diff_data = {}
        for metric_key, metric_data in metrics.items():
            baseline_val = baseline_values.get(metric_key, 0)
            if baseline_val > 0:
                pct_diff_data[metric_key] = {
                    'values': [(v / baseline_val) * 100 for v in metric_data['values']],
                    'title': f'{metric_data["title"]} (%)',
                    'color': metric_data['color'],
                    'baseline_value': baseline_val
                }
            else:
                pct_diff_data[metric_key] = {
                    'values': [0.0 for _ in metric_data['values']],
                    'title': f'{metric_data["title"]} (%)',
                    'color': metric_data['color'],
                    'baseline_value': 0
                }
        
        # Create percentage difference chart
        fig = self._create_percentage_diff_chart(samples, pct_diff_data, baseline_config, chart_config)
        image_base64 = self._fig_to_base64(fig)
        
        # Build table data
        table_data = []
        for i, sample in enumerate(samples):
            row = {'sample': sample}
            for metric_key, data in pct_diff_data.items():
                row[metric_key] = round(data['values'][i], 2)
            table_data.append(row)
        
        baseline_name = baseline_config.get('baseline_name', baseline_id)
        
        return {
            'chart': {
                'image': image_base64,
                'metadata': {
                    'samples': samples,
                    'metrics': list(pct_diff_data.keys()),
                    'baseline_type': baseline_type,
                    'baseline_id': baseline_id,
                    'baseline_name': baseline_name,
                    'baseline_values': baseline_values
                }
            },
            'table_data': {
                'columns': [{'field': 'sample', 'title': 'Sample'}] + 
                           [{'field': k, 'title': v['title']} for k, v in pct_diff_data.items()],
                'data': table_data
            }
        }
    
    def _create_percentage_diff_chart(
        self,
        samples: List[str],
        metrics: Dict[str, Any],
        baseline_config: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> plt.Figure:
        """Create percentage difference chart with baseline reference line."""
        n_metrics = len(metrics)
        fig_width = chart_config.get('figure_width', 12)
        fig_height = chart_config.get('figure_height', 8)
        font_size = chart_config.get('font_size', 12)
        
        baseline_name = baseline_config.get('baseline_name', baseline_config.get('baseline_id', 'Baseline'))
        
        if n_metrics <= 2:
            fig, axes = plt.subplots(1, n_metrics, figsize=(fig_width, fig_height // 2))
            if n_metrics == 1:
                axes = [axes]
        else:
            rows = (n_metrics + 1) // 2
            fig, axes = plt.subplots(rows, 2, figsize=(fig_width, fig_height))
            axes = axes.flatten()
        
        for idx, (metric_key, metric_data) in enumerate(metrics.items()):
            ax = axes[idx]
            values = metric_data['values']
            color = metric_data['color']
            title = metric_data['title']
            
            bars = ax.bar(samples, values, color=color, alpha=0.8)
            ax.set_title(title, fontsize=font_size, fontweight='bold')
            ax.tick_params(axis='x', rotation=45)
            ax.set_ylabel('Percentage (%)', fontsize=font_size - 2)
            
            # Add baseline reference line at 100%
            ax.axhline(y=100, color='red', linestyle='--', alpha=0.7, linewidth=1.5,
                      label=f'Baseline: {baseline_name} (100%)')
            ax.legend(fontsize=font_size - 3, loc='upper right')
            
            # Add value labels with difference indicator
            if chart_config.get('show_values', True):
                for bar in bars:
                    height = bar.get_height()
                    diff = height - 100
                    if abs(diff) > 0.1:
                        label = f'{height:.1f}%\n({diff:+.1f}%)'
                    else:
                        label = 'Baseline'
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           label, ha='center', va='bottom', fontsize=font_size - 3)
        
        # Hide extra axes
        for idx in range(len(metrics), len(axes)):
            axes[idx].set_visible(False)
        
        plt.suptitle(f'Percentage Difference Relative to {baseline_name}', 
                    fontsize=font_size + 2, fontweight='bold', y=1.02)
        plt.tight_layout()
        return fig
    
    def _create_sequencing_depth_chart(
        self, 
        samples: List[str], 
        metrics: Dict, 
        chart_config: Dict
    ) -> plt.Figure:
        """Create sequencing depth comparison chart."""
        n_metrics = len(metrics)
        fig_width = chart_config.get('figure_width', 12)
        fig_height = chart_config.get('figure_height', 8)
        font_size = chart_config.get('font_size', 12)
        
        if n_metrics <= 2:
            fig, axes = plt.subplots(1, n_metrics, figsize=(fig_width, fig_height // 2))
            if n_metrics == 1:
                axes = [axes]
        else:
            rows = (n_metrics + 1) // 2
            fig, axes = plt.subplots(rows, 2, figsize=(fig_width, fig_height))
            axes = axes.flatten()
        
        for idx, (metric_key, metric_data) in enumerate(metrics.items()):
            ax = axes[idx]
            values = metric_data['values']
            color = metric_data['color']
            title = metric_data['title']
            
            bars = ax.bar(samples, values, color=color, alpha=0.8)
            ax.set_title(title, fontsize=font_size, fontweight='bold')
            ax.tick_params(axis='x', rotation=45)
            
            # Add value labels
            if chart_config.get('show_values', True):
                for bar in bars:
                    height = bar.get_height()
                    if height > 1000:
                        label = f'{height:,.0f}'
                    else:
                        label = f'{height:.2f}'
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           label, ha='center', va='bottom', fontsize=font_size - 2)
        
        # Hide extra axes
        for idx in range(len(metrics), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout()
        return fig
    
    # =========================================================================
    # DIVERSITY METRICS ANALYSIS
    # Based on: extract_ig_diversity_metrics.py
    # =========================================================================
    
    def run_diversity_analysis(
        self,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run diversity metrics analysis.
        
        Expected columns (example):
        - sample: Sample identifier
        - IGH_d50, IGK_d50, IGL_d50
        - IGH_Gini_index, IGK_Gini_index, IGL_Gini_index
        - IGH_Shannon, IGK_Shannon, IGL_Shannon
        - IGH_Simpson, IGK_Simpson, IGL_Simpson
        
        Parameters:
        - baseline_config: Optional dict with baseline_type, baseline_id, baseline_group_sample_ids
        
        Requirements: 4.7
        """
        results = {}
        
        # Get sample column
        sample_col = self._find_column(df, field_mapping.get('sample', 'sample'),
                                       ['sample', 'Sample', 'Barcode', 'sample_id'])
        
        if sample_col and sample_col in df.columns:
            samples = df[sample_col].tolist()
        else:
            samples = [f'Sample_{i+1}' for i in range(len(df))]
        
        # Get metrics and chains to analyze
        requested_metrics = parameters.get('metrics', ['d50', 'gini', 'shannon', 'simpson'])
        requested_chains = parameters.get('chains', ['IGH', 'IGK', 'IGL'])
        
        # Find available metric columns
        available_data = {}
        for metric in requested_metrics:
            metric_data = {}
            for chain in requested_chains:
                # Try different column naming patterns
                patterns = [
                    f'{chain}_{metric}',
                    f'{chain}_{metric.capitalize()}',
                    f'{chain}_{metric}_index',
                    f'{chain}_{metric.capitalize()}_index',
                    f'{chain.lower()}_{metric}',
                ]
                
                col = None
                for pattern in patterns:
                    found = self._find_column(df, pattern, patterns)
                    if found:
                        col = found
                        break
                
                if col and col in df.columns:
                    metric_data[chain] = df[col].tolist()
            
            if metric_data:
                available_data[metric] = metric_data
        
        if not available_data:
            raise ValueError("No diversity metrics found in data")
        
        # Create visualization
        fig = self._create_diversity_chart(samples, available_data, chart_config)
        image_base64 = self._fig_to_base64(fig)
        
        # Build table data
        table_columns = [{'field': 'sample', 'title': 'Sample'}]
        for metric, chains in available_data.items():
            for chain in chains:
                table_columns.append({'field': f'{chain}_{metric}', 'title': f'{chain} {metric.upper()}'})
        
        table_data = []
        for i, sample in enumerate(samples):
            row = {'sample': sample}
            for metric, chains in available_data.items():
                for chain, values in chains.items():
                    if i < len(values):
                        row[f'{chain}_{metric}'] = values[i]
            table_data.append(row)
        
        results['diversity_metrics'] = {
            'chart': {
                'image': image_base64,
                'metadata': {
                    'samples': samples,
                    'metrics': list(available_data.keys())
                }
            },
            'table_data': {
                'columns': table_columns,
                'data': table_data
            }
        }
        
        # Handle baseline configuration for percentage difference calculation
        baseline_config = parameters.get('baseline_config')
        if baseline_config:
            pct_diff_results = self._calculate_diversity_baseline_pct_diff(
                samples, available_data, baseline_config, chart_config
            )
            if pct_diff_results:
                results['percentage_difference'] = pct_diff_results
        
        return results
    
    def _calculate_diversity_baseline_pct_diff(
        self,
        samples: List[str],
        available_data: Dict[str, Dict[str, List]],
        baseline_config: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate percentage differences for diversity metrics relative to baseline.
        
        Requirements: 4.7, 17.1, 17.2
        """
        baseline_type = baseline_config.get('baseline_type')
        baseline_id = baseline_config.get('baseline_id')
        baseline_group_sample_ids = baseline_config.get('baseline_group_sample_ids', [])
        
        if not baseline_type or not baseline_id:
            return None
        
        # Calculate baseline values for each metric/chain combination
        baseline_values = {}
        
        if baseline_type == 'sample':
            if baseline_id in samples:
                baseline_idx = samples.index(baseline_id)
                for metric, chains in available_data.items():
                    for chain, values in chains.items():
                        key = f'{chain}_{metric}'
                        if baseline_idx < len(values):
                            baseline_values[key] = values[baseline_idx]
            else:
                return None
        
        elif baseline_type == 'group':
            if baseline_group_sample_ids:
                for metric, chains in available_data.items():
                    for chain, values in chains.items():
                        key = f'{chain}_{metric}'
                        group_values = []
                        for sample_id in baseline_group_sample_ids:
                            if sample_id in samples:
                                idx = samples.index(sample_id)
                                if idx < len(values):
                                    group_values.append(values[idx])
                        if group_values:
                            baseline_values[key] = sum(group_values) / len(group_values)
            else:
                return None
        
        if not baseline_values:
            return None
        
        # Calculate percentage differences
        pct_diff_data = {}
        for metric, chains in available_data.items():
            for chain, values in chains.items():
                key = f'{chain}_{metric}'
                baseline_val = baseline_values.get(key, 0)
                if baseline_val > 0:
                    pct_diff_data[key] = {
                        'values': [(v / baseline_val) * 100 for v in values],
                        'title': f'{chain} {metric.upper()} (%)',
                        'baseline_value': baseline_val
                    }
                else:
                    pct_diff_data[key] = {
                        'values': [0.0 for _ in values],
                        'title': f'{chain} {metric.upper()} (%)',
                        'baseline_value': 0
                    }
        
        # Create percentage difference chart
        fig = self._create_diversity_pct_diff_chart(samples, pct_diff_data, baseline_config, chart_config)
        image_base64 = self._fig_to_base64(fig)
        
        # Build table data
        table_columns = [{'field': 'sample', 'title': 'Sample'}]
        for key, data in pct_diff_data.items():
            table_columns.append({'field': key, 'title': data['title']})
        
        table_data = []
        for i, sample in enumerate(samples):
            row = {'sample': sample}
            for key, data in pct_diff_data.items():
                if i < len(data['values']):
                    row[key] = round(data['values'][i], 2)
            table_data.append(row)
        
        baseline_name = baseline_config.get('baseline_name', baseline_id)
        
        return {
            'chart': {
                'image': image_base64,
                'metadata': {
                    'samples': samples,
                    'metrics': list(pct_diff_data.keys()),
                    'baseline_type': baseline_type,
                    'baseline_id': baseline_id,
                    'baseline_name': baseline_name,
                    'baseline_values': baseline_values
                }
            },
            'table_data': {
                'columns': table_columns,
                'data': table_data
            }
        }
    
    def _create_diversity_pct_diff_chart(
        self,
        samples: List[str],
        pct_diff_data: Dict[str, Any],
        baseline_config: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> plt.Figure:
        """Create diversity percentage difference chart."""
        n_metrics = len(pct_diff_data)
        fig_width = chart_config.get('figure_width', 14)
        fig_height = chart_config.get('figure_height', 10)
        font_size = chart_config.get('font_size', 10)
        
        baseline_name = baseline_config.get('baseline_name', baseline_config.get('baseline_id', 'Baseline'))
        
        # Calculate grid layout
        if n_metrics <= 2:
            rows, cols = 1, n_metrics
        elif n_metrics <= 4:
            rows, cols = 2, 2
        else:
            cols = 3
            rows = (n_metrics + cols - 1) // cols
        
        fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height))
        if n_metrics == 1:
            axes = [axes]
        else:
            axes = axes.flatten()
        
        colors = plt.cm.Set3(np.linspace(0, 1, len(samples)))
        
        for idx, (key, data) in enumerate(pct_diff_data.items()):
            ax = axes[idx]
            values = data['values']
            title = data['title']
            
            bars = ax.bar(range(len(samples)), values, color=colors, alpha=0.8)
            ax.set_title(title, fontsize=font_size, fontweight='bold')
            ax.set_xticks(range(len(samples)))
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=font_size - 2)
            ax.set_ylabel('Percentage (%)', fontsize=font_size - 2)
            
            # Add baseline reference line
            ax.axhline(y=100, color='red', linestyle='--', alpha=0.7, linewidth=1.5)
            
            # Add value labels
            if chart_config.get('show_values', True) and len(samples) <= 10:
                for bar in bars:
                    height = bar.get_height()
                    diff = height - 100
                    if abs(diff) > 0.1:
                        label = f'{height:.1f}%'
                    else:
                        label = 'Base'
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           label, ha='center', va='bottom', fontsize=font_size - 3)
        
        # Hide extra axes
        for idx in range(len(pct_diff_data), len(axes)):
            axes[idx].set_visible(False)
        
        plt.suptitle(f'Diversity Metrics - Percentage Difference Relative to {baseline_name}',
                    fontsize=font_size + 2, fontweight='bold', y=1.02)
        plt.tight_layout()
        return fig
    
    def _create_diversity_chart(
        self,
        samples: List[str],
        data: Dict[str, Dict[str, List]],
        chart_config: Dict
    ) -> plt.Figure:
        """Create diversity metrics comparison chart."""
        n_metrics = len(data)
        fig_width = chart_config.get('figure_width', 12)
        fig_height = chart_config.get('figure_height', 8)
        font_size = chart_config.get('font_size', 12)
        
        if n_metrics <= 2:
            fig, axes = plt.subplots(1, n_metrics, figsize=(fig_width, fig_height // 2))
            if n_metrics == 1:
                axes = [axes]
        else:
            rows = (n_metrics + 1) // 2
            fig, axes = plt.subplots(rows, 2, figsize=(fig_width, fig_height))
            axes = axes.flatten()
        
        chain_colors = {'IGH': '#3498db', 'IGK': '#e74c3c', 'IGL': '#2ecc71',
                       'TRA': '#9b59b6', 'TRB': '#f39c12', 'TRD': '#1abc9c', 'TRG': '#34495e'}
        
        for idx, (metric, chain_data) in enumerate(data.items()):
            ax = axes[idx]
            x = np.arange(len(samples))
            width = 0.8 / len(chain_data)
            
            for i, (chain, values) in enumerate(chain_data.items()):
                color = chain_colors.get(chain, '#666666')
                offset = (i - len(chain_data) / 2 + 0.5) * width
                bars = ax.bar(x + offset, values, width, label=chain, color=color, alpha=0.8)
            
            ax.set_title(f'{metric.upper()} by Chain', fontsize=font_size, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticklabels(samples, rotation=45, ha='right')
            ax.legend(fontsize=font_size - 2)
        
        # Hide extra axes
        for idx in range(len(data), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout()
        return fig
    
    # =========================================================================
    # CHAIN-SPECIFIC ANALYSIS
    # Based on: chain_specific_similarity_analysis.py
    # =========================================================================
    
    def run_chain_analysis(
        self,
        df: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run chain-specific analysis.
        
        Analyzes metrics for different immune receptor chains (IGH, IGK, IGL, TRA, TRB, etc.)
        
        Parameters:
        - baseline_config: Optional dict with baseline_type, baseline_id, baseline_group_sample_ids
        
        Requirements: 5.7
        """
        results = {}
        
        # Get sample column
        sample_col = self._find_column(df, field_mapping.get('sample', 'sample'),
                                       ['sample', 'Sample', 'Barcode', 'sample_id'])
        
        if sample_col and sample_col in df.columns:
            samples = df[sample_col].tolist()
        else:
            samples = [f'Sample_{i+1}' for i in range(len(df))]
        
        # Get chains to analyze
        requested_chains = parameters.get('chains', ['IGH', 'IGK', 'IGL'])
        metric_type = parameters.get('metric_type', 'ucdr3')
        
        # Find chain-specific columns
        chain_data = {}
        for chain in requested_chains:
            # Try different column patterns
            patterns = [
                f'{chain}_uCDR3', f'{chain}_UCDR3', f'{chain}_ucdr3',
                f'{chain}_count', f'{chain}_reads', f'{chain}',
                f'{chain}_expression', f'{chain}_d50'
            ]
            
            col = None
            for pattern in patterns:
                found = self._find_column(df, pattern, patterns)
                if found:
                    col = found
                    break
            
            if col and col in df.columns:
                chain_data[chain] = df[col].tolist()
        
        if not chain_data:
            raise ValueError("No chain-specific data found")
        
        # Create visualization
        fig = self._create_chain_chart(samples, chain_data, metric_type, chart_config)
        image_base64 = self._fig_to_base64(fig)
        
        # Build table data
        table_columns = [{'field': 'sample', 'title': 'Sample'}]
        for chain in chain_data:
            table_columns.append({'field': chain, 'title': chain})
        
        table_data = []
        for i, sample in enumerate(samples):
            row = {'sample': sample}
            for chain, values in chain_data.items():
                if i < len(values):
                    row[chain] = values[i]
            table_data.append(row)
        
        results['chain_comparison'] = {
            'chart': {
                'image': image_base64,
                'metadata': {
                    'samples': samples,
                    'chains': list(chain_data.keys()),
                    'metric_type': metric_type
                }
            },
            'table_data': {
                'columns': table_columns,
                'data': table_data
            }
        }
        
        # Handle baseline configuration for percentage difference calculation
        baseline_config = parameters.get('baseline_config')
        if baseline_config:
            pct_diff_results = self._calculate_chain_baseline_pct_diff(
                samples, chain_data, metric_type, baseline_config, chart_config
            )
            if pct_diff_results:
                results['percentage_difference'] = pct_diff_results
        
        return results
    
    def _calculate_chain_baseline_pct_diff(
        self,
        samples: List[str],
        chain_data: Dict[str, List],
        metric_type: str,
        baseline_config: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate percentage differences for chain metrics relative to baseline.
        
        Requirements: 5.7, 17.1, 17.2
        """
        baseline_type = baseline_config.get('baseline_type')
        baseline_id = baseline_config.get('baseline_id')
        baseline_group_sample_ids = baseline_config.get('baseline_group_sample_ids', [])
        
        if not baseline_type or not baseline_id:
            return None
        
        # Calculate baseline values for each chain
        baseline_values = {}
        
        if baseline_type == 'sample':
            if baseline_id in samples:
                baseline_idx = samples.index(baseline_id)
                for chain, values in chain_data.items():
                    if baseline_idx < len(values):
                        baseline_values[chain] = values[baseline_idx]
            else:
                return None
        
        elif baseline_type == 'group':
            if baseline_group_sample_ids:
                for chain, values in chain_data.items():
                    group_values = []
                    for sample_id in baseline_group_sample_ids:
                        if sample_id in samples:
                            idx = samples.index(sample_id)
                            if idx < len(values):
                                group_values.append(values[idx])
                    if group_values:
                        baseline_values[chain] = sum(group_values) / len(group_values)
            else:
                return None
        
        if not baseline_values:
            return None
        
        # Calculate percentage differences
        pct_diff_data = {}
        for chain, values in chain_data.items():
            baseline_val = baseline_values.get(chain, 0)
            if baseline_val > 0:
                pct_diff_data[chain] = {
                    'values': [(v / baseline_val) * 100 for v in values],
                    'baseline_value': baseline_val
                }
            else:
                pct_diff_data[chain] = {
                    'values': [0.0 for _ in values],
                    'baseline_value': 0
                }
        
        # Create percentage difference chart
        fig = self._create_chain_pct_diff_chart(samples, pct_diff_data, metric_type, baseline_config, chart_config)
        image_base64 = self._fig_to_base64(fig)
        
        # Build table data
        table_columns = [{'field': 'sample', 'title': 'Sample'}]
        for chain in pct_diff_data:
            table_columns.append({'field': chain, 'title': f'{chain} (%)'})
        
        table_data = []
        for i, sample in enumerate(samples):
            row = {'sample': sample}
            for chain, data in pct_diff_data.items():
                if i < len(data['values']):
                    row[chain] = round(data['values'][i], 2)
            table_data.append(row)
        
        baseline_name = baseline_config.get('baseline_name', baseline_id)
        
        return {
            'chart': {
                'image': image_base64,
                'metadata': {
                    'samples': samples,
                    'chains': list(pct_diff_data.keys()),
                    'metric_type': metric_type,
                    'baseline_type': baseline_type,
                    'baseline_id': baseline_id,
                    'baseline_name': baseline_name,
                    'baseline_values': baseline_values
                }
            },
            'table_data': {
                'columns': table_columns,
                'data': table_data
            }
        }
    
    def _create_chain_pct_diff_chart(
        self,
        samples: List[str],
        pct_diff_data: Dict[str, Any],
        metric_type: str,
        baseline_config: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> plt.Figure:
        """Create chain percentage difference chart."""
        fig_width = chart_config.get('figure_width', 12)
        fig_height = chart_config.get('figure_height', 8)
        font_size = chart_config.get('font_size', 12)
        
        baseline_name = baseline_config.get('baseline_name', baseline_config.get('baseline_id', 'Baseline'))
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        
        chain_colors = {'IGH': '#3498db', 'IGK': '#e74c3c', 'IGL': '#2ecc71',
                       'TRA': '#9b59b6', 'TRB': '#f39c12', 'TRD': '#1abc9c', 'TRG': '#34495e'}
        
        x = np.arange(len(samples))
        n_chains = len(pct_diff_data)
        width = 0.8 / n_chains
        
        for i, (chain, data) in enumerate(pct_diff_data.items()):
            color = chain_colors.get(chain, '#666666')
            offset = (i - n_chains / 2 + 0.5) * width
            values = data['values']
            bars = ax.bar(x + offset, values, width, label=chain, color=color, alpha=0.8)
            
            # Add value labels
            if chart_config.get('show_values', True) and len(samples) <= 8:
                for bar in bars:
                    height = bar.get_height()
                    diff = height - 100
                    if abs(diff) > 0.1:
                        label = f'{height:.1f}%'
                    else:
                        label = 'Base'
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           label, ha='center', va='bottom', fontsize=font_size - 3)
        
        # Add baseline reference line
        ax.axhline(y=100, color='red', linestyle='--', alpha=0.7, linewidth=1.5,
                  label=f'Baseline: {baseline_name} (100%)')
        
        title = chart_config.get('title', '')
        if not title:
            title = f'{metric_type.upper()} by Chain - Percentage Difference Relative to {baseline_name}'
        ax.set_title(title, fontsize=font_size + 2, fontweight='bold')
        ax.set_xlabel('Sample', fontsize=font_size)
        ax.set_ylabel('Percentage (%)', fontsize=font_size)
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right')
        ax.legend(fontsize=font_size - 2, loc='upper right')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        return fig
    
    def _create_chain_chart(
        self,
        samples: List[str],
        chain_data: Dict[str, List],
        metric_type: str,
        chart_config: Dict
    ) -> plt.Figure:
        """Create chain comparison chart."""
        fig_width = chart_config.get('figure_width', 12)
        fig_height = chart_config.get('figure_height', 8)
        font_size = chart_config.get('font_size', 12)
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        
        chain_colors = {'IGH': '#3498db', 'IGK': '#e74c3c', 'IGL': '#2ecc71',
                       'TRA': '#9b59b6', 'TRB': '#f39c12', 'TRD': '#1abc9c', 'TRG': '#34495e'}
        
        x = np.arange(len(samples))
        n_chains = len(chain_data)
        width = 0.8 / n_chains
        
        for i, (chain, values) in enumerate(chain_data.items()):
            color = chain_colors.get(chain, '#666666')
            offset = (i - n_chains / 2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, label=chain, color=color, alpha=0.8)
            
            # Add value labels
            if chart_config.get('show_values', True):
                for bar in bars:
                    height = bar.get_height()
                    if height > 1000:
                        label = f'{height:,.0f}'
                    else:
                        label = f'{height:.1f}'
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           label, ha='center', va='bottom', fontsize=font_size - 3)
        
        title = chart_config.get('title', '')
        if not title:
            title = f'{metric_type.upper()} by Chain'
        ax.set_title(title, fontsize=font_size + 2, fontweight='bold')
        ax.set_xlabel('Sample', fontsize=font_size)
        ax.set_ylabel(metric_type.upper(), fontsize=font_size)
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right')
        ax.legend(fontsize=font_size)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        return fig
