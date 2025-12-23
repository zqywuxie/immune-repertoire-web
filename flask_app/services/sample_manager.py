"""
Sample Manager Service for the Immune Repertoire Analysis Web Application.
Handles sample ordering, grouping, and statistics calculation.

Requirements: 11.1, 11.2, 11.3, 11.4
"""
import re
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SampleGroup:
    """Represents a group of samples with computed statistics."""
    name: str
    samples: List[str]
    statistics: Dict[str, Dict[str, float]] = field(default_factory=dict)


class SampleManager:
    """
    Service for managing sample ordering and grouping.
    
    Features:
    - Custom sample ordering
    - Sample grouping by pattern or manual selection
    - Group statistics calculation (mean, std, etc.)
    
    Requirements: 11.1, 11.2, 11.3, 11.4
    """
    
    @staticmethod
    def order_samples(
        samples: List[str],
        custom_order: Optional[List[str]] = None,
        sort_key: Optional[callable] = None,
        reverse: bool = False
    ) -> List[str]:
        """
        Order samples according to custom order or sorting function.
        
        Requirements: 11.1, 11.2
        
        Args:
            samples: List of sample names to order
            custom_order: Optional list defining the desired order.
                         Samples not in this list will be appended at the end.
            sort_key: Optional sorting key function
            reverse: Whether to reverse the sort order
            
        Returns:
            Ordered list of sample names
            
        Examples:
            >>> samples = ['S3', 'S1', 'S2']
            >>> SampleManager.order_samples(samples, custom_order=['S1', 'S2', 'S3'])
            ['S1', 'S2', 'S3']
            
            >>> SampleManager.order_samples(samples, sort_key=lambda x: x)
            ['S1', 'S2', 'S3']
        """
        if custom_order is not None:
            # Create order mapping
            order_map = {name: idx for idx, name in enumerate(custom_order)}
            max_order = len(custom_order)
            
            # Sort samples: those in custom_order first (by their order),
            # then remaining samples in their original order
            def get_order(sample):
                if sample in order_map:
                    return (0, order_map[sample])
                else:
                    return (1, samples.index(sample))
            
            return sorted(samples, key=get_order, reverse=reverse)
        
        elif sort_key is not None:
            return sorted(samples, key=sort_key, reverse=reverse)
        
        else:
            # Return in original order
            return list(samples)
    
    @staticmethod
    def apply_sample_order_to_dataframe(
        df: pd.DataFrame,
        sample_order: List[str],
        sample_column: str = "Sample"
    ) -> pd.DataFrame:
        """
        Reorder DataFrame rows according to sample order.
        
        Requirements: 11.2
        
        Args:
            df: Input DataFrame
            sample_order: Desired order of samples
            sample_column: Name of the column containing sample names
            
        Returns:
            Reordered DataFrame
        """
        if sample_column not in df.columns:
            return df
        
        # Create order mapping
        order_map = {name: idx for idx, name in enumerate(sample_order)}
        max_order = len(sample_order)
        
        # Add temporary sort column
        df = df.copy()
        df['_sort_order'] = df[sample_column].apply(
            lambda x: order_map.get(x, max_order + df[df[sample_column] == x].index[0] 
                                    if x in df[sample_column].values else max_order)
        )
        
        # Sort and remove temporary column
        df = df.sort_values('_sort_order').drop(columns=['_sort_order'])
        
        return df.reset_index(drop=True)
    
    @staticmethod
    def group_samples_by_pattern(
        samples: List[str],
        patterns: Dict[str, str]
    ) -> Dict[str, List[str]]:
        """
        Group samples by matching against regex patterns.
        
        Requirements: 11.3
        
        Args:
            samples: List of sample names
            patterns: Dictionary mapping group names to regex patterns
            
        Returns:
            Dictionary mapping group names to lists of matching samples
            
        Examples:
            >>> samples = ['Control_1', 'Control_2', 'Treatment_1', 'Treatment_2']
            >>> patterns = {'Control': r'Control_.*', 'Treatment': r'Treatment_.*'}
            >>> SampleManager.group_samples_by_pattern(samples, patterns)
            {'Control': ['Control_1', 'Control_2'], 'Treatment': ['Treatment_1', 'Treatment_2']}
        """
        groups = {name: [] for name in patterns}
        
        for sample in samples:
            for group_name, pattern in patterns.items():
                if re.search(pattern, sample):
                    groups[group_name].append(sample)
                    break  # Each sample belongs to at most one group
        
        return groups
    
    @staticmethod
    def group_samples_manually(
        group_assignments: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """
        Create sample groups from manual assignments.
        
        Requirements: 11.3
        
        Args:
            group_assignments: Dictionary mapping group names to lists of sample names
            
        Returns:
            Dictionary mapping group names to lists of samples
        """
        return {name: list(samples) for name, samples in group_assignments.items()}
    
    @staticmethod
    def calculate_group_statistics(
        data: pd.DataFrame,
        groups: Dict[str, List[str]],
        value_columns: List[str],
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Calculate statistics for each group.
        
        Requirements: 11.4
        
        Args:
            data: Input DataFrame with sample data
            groups: Dictionary mapping group names to lists of sample names
            value_columns: List of column names to calculate statistics for
            sample_column: Name of the column containing sample names
            
        Returns:
            Dictionary: {group_name: {column_name: {statistic: value}}}
            Statistics include: mean, std, min, max, median, count
            
        Examples:
            >>> data = pd.DataFrame({
            ...     'Sample': ['S1', 'S2', 'S3', 'S4'],
            ...     'value': [10, 20, 30, 40]
            ... })
            >>> groups = {'Group1': ['S1', 'S2'], 'Group2': ['S3', 'S4']}
            >>> stats = SampleManager.calculate_group_statistics(data, groups, ['value'])
            >>> stats['Group1']['value']['mean']
            15.0
        """
        result = {}
        
        for group_name, sample_list in groups.items():
            result[group_name] = {}
            
            # Filter data for this group
            group_data = data[data[sample_column].isin(sample_list)]
            
            for col in value_columns:
                if col not in data.columns:
                    continue
                
                values = pd.to_numeric(group_data[col], errors='coerce')
                valid_values = values.dropna()
                
                if len(valid_values) == 0:
                    result[group_name][col] = {
                        'mean': None,
                        'std': None,
                        'min': None,
                        'max': None,
                        'median': None,
                        'count': 0
                    }
                else:
                    result[group_name][col] = {
                        'mean': float(valid_values.mean()),
                        'std': float(valid_values.std()) if len(valid_values) > 1 else 0.0,
                        'min': float(valid_values.min()),
                        'max': float(valid_values.max()),
                        'median': float(valid_values.median()),
                        'count': len(valid_values)
                    }
        
        return result
    
    @staticmethod
    def calculate_group_mean(
        data: pd.DataFrame,
        groups: Dict[str, List[str]],
        value_column: str,
        sample_column: str = "Sample"
    ) -> Dict[str, Optional[float]]:
        """
        Calculate mean value for each group.
        
        Requirements: 11.4
        
        This is a convenience method that returns just the mean for each group.
        
        Args:
            data: Input DataFrame with sample data
            groups: Dictionary mapping group names to lists of sample names
            value_column: Column name to calculate mean for
            sample_column: Name of the column containing sample names
            
        Returns:
            Dictionary mapping group names to mean values
        """
        result = {}
        
        for group_name, sample_list in groups.items():
            group_data = data[data[sample_column].isin(sample_list)]
            values = pd.to_numeric(group_data[value_column], errors='coerce')
            valid_values = values.dropna()
            
            if len(valid_values) == 0:
                result[group_name] = None
            else:
                result[group_name] = float(valid_values.mean())
        
        return result
    
    @staticmethod
    def create_group_summary_dataframe(
        group_statistics: Dict[str, Dict[str, Dict[str, float]]],
        statistic: str = 'mean'
    ) -> pd.DataFrame:
        """
        Create a summary DataFrame from group statistics.
        
        Requirements: 11.4
        
        Args:
            group_statistics: Output from calculate_group_statistics
            statistic: Which statistic to include ('mean', 'std', 'min', 'max', 'median')
            
        Returns:
            DataFrame with groups as rows and columns as value columns
        """
        rows = []
        
        for group_name, columns in group_statistics.items():
            row = {'Group': group_name}
            for col_name, stats in columns.items():
                row[col_name] = stats.get(statistic)
            rows.append(row)
        
        return pd.DataFrame(rows)
