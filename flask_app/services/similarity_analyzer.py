"""
Similarity Analyzer Service for the Immune Repertoire Analysis Web Application.
Implements six similarity metrics for immune repertoire analysis.
Requirements: 2.1, 2.3

Metrics implemented:
1. R² inner - Inner join correlation coefficient
2. R² outer - Outer join correlation coefficient
3. CDR3 sharing (unique) - Unique CDR3 sequence sharing
4. Expression sharing (reads) - Expression-based sharing
5. Morisita-Horn - Ecological similarity index
6. Sorensen - Sorensen-Dice coefficient
"""
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class HeatmapConfig:
    """Configuration for heatmap visualization.
    Requirements: 7.1, 7.5, 7.7
    """
    title: str = ""
    color_scheme: str = "viridis"
    figure_width: int = 10
    figure_height: int = 8
    font_size: int = 12
    dpi: int = 300
    annotation: bool = True
    cmap: str = "RdYlBu_r"
    vmin: Optional[float] = None
    vmax: Optional[float] = None


class SimilarityAnalyzer:
    """
    Similarity analyzer for immune repertoire data.
    Calculates various similarity metrics between samples.
    Requirements: 2.1, 2.3
    """
    
    # Available similarity metrics
    METRICS = [
        'r2_inner',
        'r2_outer', 
        'cdr3_sharing',
        'expression_sharing',
        'morisita_horn',
        'sorensen'
    ]
    
    def __init__(
        self, 
        data: pd.DataFrame, 
        field_mapping: Dict[str, str],
        chart_config: Optional[HeatmapConfig] = None
    ):
        """
        Initialize the similarity analyzer.
        
        Args:
            data: DataFrame containing immune repertoire data
            field_mapping: Mapping from required fields to actual column names
                Required fields: 'sample', 'cdr3', 'copy' (or 'reads')
            chart_config: Optional configuration for heatmap generation
        """
        self.data = data
        self.field_mapping = field_mapping
        self.chart_config = chart_config or HeatmapConfig()
        
        # Extract column names from mapping
        self.sample_col = field_mapping.get('sample', 'sample')
        self.cdr3_col = field_mapping.get('cdr3', 'CDR3(pep)')
        self.copy_col = field_mapping.get('copy', field_mapping.get('reads', 'copy'))
        
        # Build sample data structures
        self._sample_abundance: Dict[str, Dict[str, float]] = {}
        self._sample_cdr3_sets: Dict[str, set] = {}
        self._samples: List[str] = []
        
        self._prepare_data()
    
    def _prepare_data(self) -> None:
        """Prepare data structures for similarity calculations."""
        if self.data.empty:
            return
            
        # Get unique samples
        if self.sample_col in self.data.columns:
            self._samples = sorted(self.data[self.sample_col].dropna().unique().tolist())
        else:
            # If no sample column, treat entire dataset as one sample
            self._samples = ['all_data']
            self.data = self.data.copy()
            self.data[self.sample_col] = 'all_data'
        
        # Build abundance dictionaries and CDR3 sets for each sample
        for sample in self._samples:
            sample_data = self.data[self.data[self.sample_col] == sample]
            
            # Build CDR3 abundance dictionary
            if self.cdr3_col in sample_data.columns and self.copy_col in sample_data.columns:
                abundance = sample_data.groupby(self.cdr3_col)[self.copy_col].sum().to_dict()
                self._sample_abundance[sample] = abundance
            
            # Build CDR3 set
            if self.cdr3_col in sample_data.columns:
                cdr3_set = set(sample_data[self.cdr3_col].dropna().unique())
                self._sample_cdr3_sets[sample] = cdr3_set
    
    @property
    def samples(self) -> List[str]:
        """Get list of sample names."""
        return self._samples
    
    def calculate_r2_inner(self) -> pd.DataFrame:
        """
        Calculate R² inner (inner join correlation coefficient).
        
        Definition: Measures correlation of shared CDR3 sequences between samples.
        Method: Only uses CDR3 sequences present in both samples (inner join).
        
        Formula:
        1. For each pair of samples, keep only shared CDR3 sequences
        2. Calculate Pearson correlation coefficient r for abundances
        3. R² = r²
        
        Returns:
            Symmetric similarity matrix with diagonal = 1.0
            
        Requirements: 2.1, 2.3
        """
        n = len(self._samples)
        if n == 0:
            return pd.DataFrame()
        
        r2_matrix = np.ones((n, n))  # Diagonal is 1
        
        for i in range(n):
            for j in range(i + 1, n):
                sample_i = self._samples[i]
                sample_j = self._samples[j]
                
                if sample_i not in self._sample_abundance or sample_j not in self._sample_abundance:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0.0
                    continue
                
                # Inner join: only keep CDR3 present in both samples
                shared_cdr3 = (
                    set(self._sample_abundance[sample_i].keys()) & 
                    set(self._sample_abundance[sample_j].keys())
                )
                
                if len(shared_cdr3) < 2:
                    # Need at least 2 points for correlation
                    r2_matrix[i, j] = r2_matrix[j, i] = 0.0
                    continue
                
                # Extract abundances for shared CDR3
                abundance_i = np.array([
                    self._sample_abundance[sample_i][cdr3] for cdr3 in shared_cdr3
                ])
                abundance_j = np.array([
                    self._sample_abundance[sample_j][cdr3] for cdr3 in shared_cdr3
                ])
                
                # Calculate Pearson correlation coefficient
                if np.std(abundance_i) > 0 and np.std(abundance_j) > 0:
                    corr = np.corrcoef(abundance_i, abundance_j)[0, 1]
                    r2 = corr ** 2
                    r2_matrix[i, j] = r2_matrix[j, i] = r2
                else:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0.0
        
        return pd.DataFrame(r2_matrix, index=self._samples, columns=self._samples)
    
    def calculate_r2_outer(self) -> pd.DataFrame:
        """
        Calculate R² outer (outer join correlation coefficient).
        
        Definition: Uses outer join, including all CDR3 with 0 for missing values.
        Method: Includes all CDR3 from both samples, missing values set to 0.
        
        Formula:
        1. For each pair of samples, merge all CDR3 (union)
        2. Set abundance to 0 for missing CDR3
        3. Calculate Pearson correlation coefficient r
        4. R² = r²
        
        Returns:
            Symmetric similarity matrix with diagonal = 1.0
            
        Requirements: 2.1, 2.3
        """
        n = len(self._samples)
        if n == 0:
            return pd.DataFrame()
        
        r2_matrix = np.ones((n, n))  # Diagonal is 1
        
        for i in range(n):
            for j in range(i + 1, n):
                sample_i = self._samples[i]
                sample_j = self._samples[j]
                
                if sample_i not in self._sample_abundance or sample_j not in self._sample_abundance:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0.0
                    continue
                
                # Outer join: merge all CDR3
                all_cdr3 = (
                    set(self._sample_abundance[sample_i].keys()) | 
                    set(self._sample_abundance[sample_j].keys())
                )
                
                if len(all_cdr3) < 2:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0.0
                    continue
                
                # Extract abundances, using 0 for missing CDR3
                abundance_i = np.array([
                    self._sample_abundance[sample_i].get(cdr3, 0) for cdr3 in all_cdr3
                ])
                abundance_j = np.array([
                    self._sample_abundance[sample_j].get(cdr3, 0) for cdr3 in all_cdr3
                ])
                
                # Calculate Pearson correlation coefficient
                if np.std(abundance_i) > 0 and np.std(abundance_j) > 0:
                    corr = np.corrcoef(abundance_i, abundance_j)[0, 1]
                    r2 = corr ** 2
                    r2_matrix[i, j] = r2_matrix[j, i] = r2
                else:
                    r2_matrix[i, j] = r2_matrix[j, i] = 0.0
        
        return pd.DataFrame(r2_matrix, index=self._samples, columns=self._samples)

    def calculate_cdr3_sharing(self) -> pd.DataFrame:
        """
        Calculate CDR3 sharing (unique) - unique clone sharing.
        
        Definition: Compares unique CDR3 sharing ratio between samples.
        Method: Only considers presence/absence, not abundance.
        
        Formula:
        CDR3_sharing = |CDR3_A ∩ CDR3_B| / min(|CDR3_A|, |CDR3_B|)
        
        Range: [0, 1], where 1 means all CDR3 from smaller set are in larger set.
        
        Returns:
            Symmetric similarity matrix with diagonal = 1.0
            
        Requirements: 2.1, 2.3
        """
        n = len(self._samples)
        if n == 0:
            return pd.DataFrame()
        
        similarity_matrix = np.ones((n, n))  # Diagonal is 1
        
        for i in range(n):
            for j in range(i + 1, n):
                sample_i = self._samples[i]
                sample_j = self._samples[j]
                
                if sample_i not in self._sample_cdr3_sets or sample_j not in self._sample_cdr3_sets:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
                    continue
                
                set_i = self._sample_cdr3_sets[sample_i]
                set_j = self._sample_cdr3_sets[sample_j]
                
                intersection = len(set_i & set_j)
                min_size = min(len(set_i), len(set_j))
                
                if min_size > 0:
                    sharing = intersection / min_size
                    similarity_matrix[i, j] = similarity_matrix[j, i] = sharing
                else:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
        
        return pd.DataFrame(similarity_matrix, index=self._samples, columns=self._samples)
    
    def calculate_expression_sharing(self) -> pd.DataFrame:
        """
        Calculate Expression sharing (reads) - expression-based sharing.
        
        Definition: Compares shared CDR3 reads abundance similarity.
        Method: Calculates overlap of expression levels for shared clones.
        
        Formula:
        Expression_sharing = 2 * Σ_cdr3 min(reads_A, reads_B) / (Σ reads_A + Σ reads_B)
        
        Range: [0, 1], normalized from original [0, 0.5] range.
        
        Returns:
            Symmetric similarity matrix with diagonal = 1.0
            
        Requirements: 2.1, 2.3
        """
        n = len(self._samples)
        if n == 0:
            return pd.DataFrame()
        
        similarity_matrix = np.ones((n, n))  # Diagonal is 1
        
        for i in range(n):
            for j in range(i + 1, n):
                sample_i = self._samples[i]
                sample_j = self._samples[j]
                
                if sample_i not in self._sample_abundance or sample_j not in self._sample_abundance:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
                    continue
                
                # Get all CDR3 from both samples
                all_cdr3 = (
                    set(self._sample_abundance[sample_i].keys()) | 
                    set(self._sample_abundance[sample_j].keys())
                )
                
                # Calculate shared reads and total reads
                shared_reads = 0.0
                total_reads_a = 0.0
                total_reads_b = 0.0
                
                for cdr3 in all_cdr3:
                    reads_a = self._sample_abundance[sample_i].get(cdr3, 0)
                    reads_b = self._sample_abundance[sample_j].get(cdr3, 0)
                    shared_reads += min(reads_a, reads_b)
                    total_reads_a += reads_a
                    total_reads_b += reads_b
                
                total_reads = total_reads_a + total_reads_b
                
                if total_reads > 0:
                    # Normalize to [0, 1] range (original max is 0.5)
                    sharing = (2 * shared_reads) / total_reads
                    similarity_matrix[i, j] = similarity_matrix[j, i] = sharing
                else:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
        
        return pd.DataFrame(similarity_matrix, index=self._samples, columns=self._samples)
    
    def calculate_morisita_horn(self) -> pd.DataFrame:
        """
        Calculate Morisita-Horn index.
        
        Definition: Ecological similarity index, sensitive to high-abundance clones.
        Method: Considers abundance distribution, high-abundance clones have more impact.
        
        Formula (standard form):
        MH = 2 * Σ(n_Ai * n_Bi) / [(D_A + D_B) * N_A * N_B]
        
        Where:
        - n_Ai = abundance of clone i in sample A
        - N_A = total reads in sample A
        - D_A = Simpson diversity index = Σ(n_Ai² / N_A²)
        
        Range: [0, 1], where 0 = completely different, 1 = identical.
        
        Returns:
            Symmetric similarity matrix with diagonal = 1.0
            
        Requirements: 2.1, 2.3
        """
        n = len(self._samples)
        if n == 0:
            return pd.DataFrame()
        
        similarity_matrix = np.ones((n, n))  # Diagonal is 1
        
        for i in range(n):
            for j in range(i + 1, n):
                sample_i = self._samples[i]
                sample_j = self._samples[j]
                
                if sample_i not in self._sample_abundance or sample_j not in self._sample_abundance:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
                    continue
                
                # Get all CDR3 (union)
                all_cdr3 = (
                    set(self._sample_abundance[sample_i].keys()) | 
                    set(self._sample_abundance[sample_j].keys())
                )
                
                # Extract abundance vectors
                n_A = np.array([
                    self._sample_abundance[sample_i].get(cdr3, 0) for cdr3 in all_cdr3
                ])
                n_B = np.array([
                    self._sample_abundance[sample_j].get(cdr3, 0) for cdr3 in all_cdr3
                ])
                
                N_A = np.sum(n_A)  # Total reads in sample A
                N_B = np.sum(n_B)  # Total reads in sample B
                
                if N_A == 0 or N_B == 0:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
                    continue
                
                # Calculate Simpson diversity index
                D_A = np.sum((n_A / N_A) ** 2)
                D_B = np.sum((n_B / N_B) ** 2)
                
                # Calculate Morisita-Horn index
                numerator = 2 * np.sum(n_A * n_B)
                denominator = (D_A + D_B) * N_A * N_B
                
                if denominator > 0:
                    mh = numerator / denominator
                    similarity_matrix[i, j] = similarity_matrix[j, i] = mh
                else:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
        
        return pd.DataFrame(similarity_matrix, index=self._samples, columns=self._samples)
    
    def calculate_sorensen(self) -> pd.DataFrame:
        """
        Calculate Sorensen coefficient (Sorensen-Dice coefficient).
        
        Definition: Measures unique CDR3 overlap between samples.
        Method: Based on presence/absence only, not abundance.
        
        Formula:
        S = 2 * |A ∩ B| / (|A| + |B|)
        
        Where:
        - |A ∩ B| = number of shared unique CDR3
        - |A| = number of unique CDR3 in sample A
        - |B| = number of unique CDR3 in sample B
        
        Range: [0, 1], where 0 = completely different, 1 = identical.
        
        Returns:
            Symmetric similarity matrix with diagonal = 1.0
            
        Requirements: 2.1, 2.3
        """
        n = len(self._samples)
        if n == 0:
            return pd.DataFrame()
        
        similarity_matrix = np.ones((n, n))  # Diagonal is 1
        
        for i in range(n):
            for j in range(i + 1, n):
                sample_i = self._samples[i]
                sample_j = self._samples[j]
                
                if sample_i not in self._sample_cdr3_sets or sample_j not in self._sample_cdr3_sets:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
                    continue
                
                set_i = self._sample_cdr3_sets[sample_i]
                set_j = self._sample_cdr3_sets[sample_j]
                
                intersection = len(set_i & set_j)
                size_sum = len(set_i) + len(set_j)
                
                if size_sum > 0:
                    sorensen = (2 * intersection) / size_sum
                    similarity_matrix[i, j] = similarity_matrix[j, i] = sorensen
                else:
                    similarity_matrix[i, j] = similarity_matrix[j, i] = 0.0
        
        return pd.DataFrame(similarity_matrix, index=self._samples, columns=self._samples)
    
    def calculate_all_metrics(self) -> Dict[str, pd.DataFrame]:
        """
        Calculate all six similarity metrics.
        
        Returns:
            Dictionary mapping metric names to similarity matrices.
            
        Requirements: 2.1, 2.3
        """
        return {
            'r2_inner': self.calculate_r2_inner(),
            'r2_outer': self.calculate_r2_outer(),
            'cdr3_sharing': self.calculate_cdr3_sharing(),
            'expression_sharing': self.calculate_expression_sharing(),
            'morisita_horn': self.calculate_morisita_horn(),
            'sorensen': self.calculate_sorensen()
        }
    
    def calculate_metric(self, metric_name: str) -> pd.DataFrame:
        """
        Calculate a specific similarity metric.
        
        Args:
            metric_name: Name of the metric to calculate
            
        Returns:
            Similarity matrix as DataFrame
            
        Raises:
            ValueError: If metric name is not recognized
        """
        metric_methods = {
            'r2_inner': self.calculate_r2_inner,
            'r2_outer': self.calculate_r2_outer,
            'cdr3_sharing': self.calculate_cdr3_sharing,
            'expression_sharing': self.calculate_expression_sharing,
            'morisita_horn': self.calculate_morisita_horn,
            'sorensen': self.calculate_sorensen
        }
        
        if metric_name not in metric_methods:
            raise ValueError(
                f"Unknown metric: {metric_name}. "
                f"Available metrics: {list(metric_methods.keys())}"
            )
        
        return metric_methods[metric_name]()
