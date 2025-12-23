"""
Sample Grouping Service for the Immune Repertoire Analysis Web Application.
Provides functionality for managing sample groups, calculating group averages,
and baseline selection for percentage difference calculations.

Requirements: 16.1, 16.2, 16.3, 17.1, 17.2, 17.3, 17.4
"""
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class GroupAverageResult:
    """Result of group average calculation."""
    group_id: str
    group_name: str
    sample_count: int
    averages: Dict[str, float]  # {metric_field: average_value}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'group_id': self.group_id,
            'group_name': self.group_name,
            'sample_count': self.sample_count,
            'averages': self.averages
        }


@dataclass
class MultiGroupAverageResult:
    """Result of multiple group average calculations."""
    averages: Dict[str, Dict[str, float]]  # {group_id: {metric_field: average_value}}
    group_info: Dict[str, Dict[str, Any]]  # {group_id: {name, sample_count, ...}}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'averages': self.averages,
            'group_info': self.group_info
        }


@dataclass
class BaselineResult:
    """Result of baseline value calculation."""
    baseline_type: str  # 'sample' or 'group'
    baseline_id: str
    baseline_name: str
    baseline_values: Dict[str, float]  # {metric_field: baseline_value}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'baseline_type': self.baseline_type,
            'baseline_id': self.baseline_id,
            'baseline_name': self.baseline_name,
            'baseline_values': self.baseline_values
        }


@dataclass
class PercentageDifferenceResult:
    """Result of percentage difference calculation relative to baseline."""
    baseline_type: str  # 'sample' or 'group'
    baseline_id: str
    baseline_name: str
    baseline_values: Dict[str, float]  # {metric_field: baseline_value}
    percentage_differences: Dict[str, Dict[str, float]]  # {target_id: {metric_field: percentage}}
    target_info: Dict[str, Dict[str, Any]]  # {target_id: {name, type, ...}}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'baseline_type': self.baseline_type,
            'baseline_id': self.baseline_id,
            'baseline_name': self.baseline_name,
            'baseline_values': self.baseline_values,
            'percentage_differences': self.percentage_differences,
            'target_info': self.target_info
        }


class GroupingService:
    """
    Service for managing sample groups and calculating group averages.
    
    Requirements: 16.1, 16.2, 16.3
    """
    
    def __init__(self):
        pass
    
    def calculate_group_average(
        self,
        data: pd.DataFrame,
        sample_ids: List[str],
        metric_fields: List[str],
        sample_column: str = 'sample'
    ) -> Dict[str, float]:
        """
        Calculate average values for a single group of samples.
        
        Requirements: 16.2
        
        Args:
            data: DataFrame containing sample data
            sample_ids: List of sample identifiers in the group
            metric_fields: List of metric field names to calculate averages for
            sample_column: Name of the column containing sample identifiers
            
        Returns:
            Dictionary mapping metric field names to their average values
        """
        if data.empty:
            return {field: 0.0 for field in metric_fields}
        
        # Filter data to only include samples in the group
        if sample_column in data.columns:
            group_data = data[data[sample_column].isin(sample_ids)]
        else:
            # If sample column doesn't exist, assume all rows are relevant
            group_data = data
        
        if group_data.empty:
            return {field: 0.0 for field in metric_fields}
        
        # Calculate averages for each metric field
        averages = {}
        for field in metric_fields:
            if field in group_data.columns:
                # Convert to numeric, coercing errors to NaN
                values = pd.to_numeric(group_data[field], errors='coerce')
                # Calculate mean, ignoring NaN values
                avg = values.mean()
                averages[field] = float(avg) if not pd.isna(avg) else 0.0
            else:
                averages[field] = 0.0
        
        return averages
    
    def calculate_multiple_group_averages(
        self,
        data: pd.DataFrame,
        groups: List[Dict[str, Any]],
        metric_fields: List[str],
        sample_column: str = 'sample'
    ) -> MultiGroupAverageResult:
        """
        Calculate average values for multiple groups simultaneously.
        
        Requirements: 16.2, 16.3
        
        Args:
            data: DataFrame containing sample data
            groups: List of group dictionaries with 'id', 'name', 'sample_ids' keys
            metric_fields: List of metric field names to calculate averages for
            sample_column: Name of the column containing sample identifiers
            
        Returns:
            MultiGroupAverageResult containing averages for all groups
        """
        averages = {}
        group_info = {}
        
        for group in groups:
            group_id = group.get('id', '')
            group_name = group.get('name', '')
            sample_ids = group.get('sample_ids', [])
            
            # Calculate averages for this group
            group_averages = self.calculate_group_average(
                data=data,
                sample_ids=sample_ids,
                metric_fields=metric_fields,
                sample_column=sample_column
            )
            
            averages[group_id] = group_averages
            group_info[group_id] = {
                'name': group_name,
                'sample_count': len(sample_ids),
                'sample_ids': sample_ids
            }
        
        return MultiGroupAverageResult(
            averages=averages,
            group_info=group_info
        )
    
    def calculate_group_statistics(
        self,
        data: pd.DataFrame,
        sample_ids: List[str],
        metric_fields: List[str],
        sample_column: str = 'sample'
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate comprehensive statistics for a group of samples.
        
        Args:
            data: DataFrame containing sample data
            sample_ids: List of sample identifiers in the group
            metric_fields: List of metric field names to calculate statistics for
            sample_column: Name of the column containing sample identifiers
            
        Returns:
            Dictionary mapping metric field names to their statistics
            (mean, std, min, max, median)
        """
        if data.empty:
            return {field: {'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0, 'median': 0.0} 
                    for field in metric_fields}
        
        # Filter data to only include samples in the group
        if sample_column in data.columns:
            group_data = data[data[sample_column].isin(sample_ids)]
        else:
            group_data = data
        
        if group_data.empty:
            return {field: {'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0, 'median': 0.0} 
                    for field in metric_fields}
        
        statistics = {}
        for field in metric_fields:
            if field in group_data.columns:
                values = pd.to_numeric(group_data[field], errors='coerce').dropna()
                if len(values) > 0:
                    statistics[field] = {
                        'mean': float(values.mean()),
                        'std': float(values.std()) if len(values) > 1 else 0.0,
                        'min': float(values.min()),
                        'max': float(values.max()),
                        'median': float(values.median())
                    }
                else:
                    statistics[field] = {'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0, 'median': 0.0}
            else:
                statistics[field] = {'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0, 'median': 0.0}
        
        return statistics
    
    def get_baseline_value(
        self,
        data: pd.DataFrame,
        baseline_type: str,
        baseline_id: str,
        metric_fields: List[str],
        sample_column: str = 'sample',
        group_sample_ids: Optional[List[str]] = None
    ) -> BaselineResult:
        """
        Get baseline values for percentage difference calculations.
        
        Requirements: 17.1, 17.2
        
        Args:
            data: DataFrame containing sample data
            baseline_type: 'sample' or 'group'
            baseline_id: Sample identifier or group identifier
            metric_fields: List of metric field names to get baseline values for
            sample_column: Name of the column containing sample identifiers
            group_sample_ids: List of sample IDs if baseline_type is 'group'
            
        Returns:
            BaselineResult containing baseline values for each metric field
        """
        if data.empty:
            return BaselineResult(
                baseline_type=baseline_type,
                baseline_id=baseline_id,
                baseline_name=baseline_id,
                baseline_values={field: 0.0 for field in metric_fields}
            )
        
        baseline_values = {}
        baseline_name = baseline_id
        
        if baseline_type == 'sample':
            # Get values for a single sample
            if sample_column in data.columns:
                sample_data = data[data[sample_column] == baseline_id]
            else:
                sample_data = data
            
            if sample_data.empty:
                baseline_values = {field: 0.0 for field in metric_fields}
            else:
                for field in metric_fields:
                    if field in sample_data.columns:
                        values = pd.to_numeric(sample_data[field], errors='coerce')
                        # For a single sample, take the first value (or mean if multiple rows)
                        avg = values.mean()
                        baseline_values[field] = float(avg) if not pd.isna(avg) else 0.0
                    else:
                        baseline_values[field] = 0.0
        
        elif baseline_type == 'group':
            # Get average values for a group of samples
            if group_sample_ids is None:
                group_sample_ids = []
            
            baseline_values = self.calculate_group_average(
                data=data,
                sample_ids=group_sample_ids,
                metric_fields=metric_fields,
                sample_column=sample_column
            )
        
        else:
            raise ValueError(f"Invalid baseline_type: {baseline_type}. Must be 'sample' or 'group'.")
        
        return BaselineResult(
            baseline_type=baseline_type,
            baseline_id=baseline_id,
            baseline_name=baseline_name,
            baseline_values=baseline_values
        )
    
    def calculate_percentage_differences(
        self,
        data: pd.DataFrame,
        baseline_type: str,
        baseline_id: str,
        target_ids: List[str],
        target_type: str,
        metric_fields: List[str],
        sample_column: str = 'sample',
        baseline_group_sample_ids: Optional[List[str]] = None,
        target_groups: Optional[List[Dict[str, Any]]] = None
    ) -> PercentageDifferenceResult:
        """
        Calculate percentage differences relative to a baseline.
        
        Requirements: 17.1, 17.2, 17.4
        
        Args:
            data: DataFrame containing sample data
            baseline_type: 'sample' or 'group'
            baseline_id: Sample identifier or group identifier for baseline
            target_ids: List of sample or group identifiers to compare
            target_type: 'sample' or 'group'
            metric_fields: List of metric field names to calculate differences for
            sample_column: Name of the column containing sample identifiers
            baseline_group_sample_ids: List of sample IDs if baseline_type is 'group'
            target_groups: List of group dicts with 'id', 'name', 'sample_ids' if target_type is 'group'
            
        Returns:
            PercentageDifferenceResult containing percentage differences for all targets
        """
        # Get baseline values
        baseline_result = self.get_baseline_value(
            data=data,
            baseline_type=baseline_type,
            baseline_id=baseline_id,
            metric_fields=metric_fields,
            sample_column=sample_column,
            group_sample_ids=baseline_group_sample_ids
        )
        
        percentage_differences = {}
        target_info = {}
        
        if target_type == 'sample':
            # Calculate differences for individual samples
            for target_id in target_ids:
                if sample_column in data.columns:
                    sample_data = data[data[sample_column] == target_id]
                else:
                    sample_data = data
                
                target_values = {}
                for field in metric_fields:
                    if field in sample_data.columns and not sample_data.empty:
                        values = pd.to_numeric(sample_data[field], errors='coerce')
                        avg = values.mean()
                        target_values[field] = float(avg) if not pd.isna(avg) else 0.0
                    else:
                        target_values[field] = 0.0
                
                # Calculate percentage differences
                diffs = {}
                for field in metric_fields:
                    baseline_val = baseline_result.baseline_values.get(field, 0.0)
                    target_val = target_values.get(field, 0.0)
                    
                    if baseline_val != 0:
                        diffs[field] = (target_val / baseline_val) * 100
                    else:
                        diffs[field] = 0.0 if target_val == 0 else float('inf')
                
                percentage_differences[target_id] = diffs
                target_info[target_id] = {
                    'name': target_id,
                    'type': 'sample',
                    'values': target_values
                }
        
        elif target_type == 'group':
            # Calculate differences for groups
            if target_groups is None:
                target_groups = []
            
            for group in target_groups:
                group_id = group.get('id', '')
                group_name = group.get('name', group_id)
                sample_ids = group.get('sample_ids', [])
                
                # Calculate group average
                target_values = self.calculate_group_average(
                    data=data,
                    sample_ids=sample_ids,
                    metric_fields=metric_fields,
                    sample_column=sample_column
                )
                
                # Calculate percentage differences
                diffs = {}
                for field in metric_fields:
                    baseline_val = baseline_result.baseline_values.get(field, 0.0)
                    target_val = target_values.get(field, 0.0)
                    
                    if baseline_val != 0:
                        diffs[field] = (target_val / baseline_val) * 100
                    else:
                        diffs[field] = 0.0 if target_val == 0 else float('inf')
                
                percentage_differences[group_id] = diffs
                target_info[group_id] = {
                    'name': group_name,
                    'type': 'group',
                    'sample_count': len(sample_ids),
                    'values': target_values
                }
        
        else:
            raise ValueError(f"Invalid target_type: {target_type}. Must be 'sample' or 'group'.")
        
        return PercentageDifferenceResult(
            baseline_type=baseline_result.baseline_type,
            baseline_id=baseline_result.baseline_id,
            baseline_name=baseline_result.baseline_name,
            baseline_values=baseline_result.baseline_values,
            percentage_differences=percentage_differences,
            target_info=target_info
        )


# Singleton instance
_grouping_service: Optional[GroupingService] = None


def get_grouping_service() -> GroupingService:
    """Get the singleton GroupingService instance."""
    global _grouping_service
    if _grouping_service is None:
        _grouping_service = GroupingService()
    return _grouping_service


def init_grouping_service() -> GroupingService:
    """Initialize and return the GroupingService instance."""
    global _grouping_service
    _grouping_service = GroupingService()
    return _grouping_service
