# Analyzers Package

This package contains the refactored analyzer classes for the unified analysis system.

## Overview

The analyzers have been refactored to use a plugin-style architecture with a common `BaseAnalyzer` interface. This makes it easy to add new analyzers and ensures consistency across all analysis modules.

## Architecture

### BaseAnalyzer

The `BaseAnalyzer` is an abstract base class that all analyzers must inherit from. It provides:

- **Abstract Methods** (must be implemented):
  - `analyze()`: Execute the analysis logic
  - `get_required_fields()`: Return list of required fields
  - `get_default_parameters()`: Return default parameters

- **Concrete Methods** (provided by base class):
  - `validate_data()`: Validate input data (can be overridden)
  - `get_optional_fields()`: Return optional fields (can be overridden)
  - `get_analyzer_info()`: Get analyzer metadata
  - `preprocess_data()`: Apply field mapping
  - `merge_parameters()`: Merge user and default parameters

### ValidationResult

A dataclass that encapsulates validation results with:
- `is_valid`: Boolean indicating if validation passed
- `errors`: List of error messages
- `warnings`: List of warning messages

## Implemented Analyzers

### 1. BCellIsotypeAnalyzer

**Purpose**: Analyze B cell isotype distribution (IgM, IgD, IgA1/2, IgG1/2, IgG3/4, IgE)

**Required Fields**:
- Sample

**Features**:
- Extracts Expression % and Unique CDR3 % for 6 isotypes
- Calculates percentage differences from baseline
- Supports custom sample ordering
- Supports sample grouping with statistics

**Parameters**:
- `sample_column`: Sample column name (default: "Sample")
- `baseline_sample`: Baseline sample for percentage calculations
- `sample_order`: Custom sample ordering
- `sample_groups`: Sample grouping configuration

### 2. SHMAnalyzer

**Purpose**: Analyze somatic hypermutation (SHM) data

**Required Fields**:
- Sample
- IGHA_SHM0, IGHA_SHM1
- IGHG12_SHM0, IGHG12_SHM1
- IGHG34_SHM0, IGHG34_SHM1
- IGHM_IGHD_SHM0, IGHM_IGHD_SHM1
- IGH_SHM0, IGH_SHM1

**Features**:
- Extracts SHM0 and SHM1 values for multiple isotypes
- Calculates percentage changes from baseline
- Supports custom sample ordering
- Supports sample grouping with statistics

**Parameters**:
- `sample_column`: Sample column name (default: "Sample")
- `baseline_sample`: Baseline sample for percentage calculations
- `isotypes`: Specific isotypes to analyze (default: all)
- `sample_order`: Custom sample ordering
- `sample_groups`: Sample grouping configuration

### 3. IGMetricsAnalyzer

**Purpose**: Analyze immunoglobulin metrics for IGH, IGK, IGL chains

**Required Fields**:
- Sample

**Metrics Analyzed**:
- Reads
- UCDR3 (Unique CDR3)
- D50
- Gini_index
- Shannon

**Features**:
- Extracts 5 metrics for 3 chains (IGH, IGK, IGL)
- Calculates percentage changes from baseline
- Supports custom sample ordering
- Supports sample grouping with statistics

**Parameters**:
- `sample_column`: Sample column name (default: "Sample")
- `chains`: Chains to analyze (default: ["IGH", "IGK", "IGL"])
- `metrics`: Metrics to analyze (default: all 5)
- `baseline_sample`: Baseline sample for percentage calculations
- `sample_order`: Custom sample ordering
- `sample_groups`: Sample grouping configuration

### 4. CustomFieldAnalyzer

**Purpose**: Flexible analysis of user-selected fields

**Required Fields**:
- Sample

**Features**:
- Analyzes any numeric fields specified by user
- Identifies available numeric fields automatically
- Calculates percentage differences from baseline
- Supports multiple chart types
- Supports custom sample ordering
- Supports sample grouping with statistics

**Parameters**:
- `sample_column`: Sample column name (default: "Sample")
- `fields`: List of fields to analyze (REQUIRED)
- `baseline_sample`: Baseline sample for percentage calculations
- `sample_order`: Custom sample ordering
- `sample_groups`: Sample grouping configuration
- `chart_type`: Chart type (default: "bar")
- `show_percentage_diff`: Show percentage differences (default: False)
- `aggregation_method`: Aggregation method for groups (default: "mean")

**Supported Chart Types**:
- bar
- line
- grouped_bar
- scatter
- heatmap

## Usage Example

```python
from services.analyzers import BCellIsotypeAnalyzer

# Create analyzer instance
analyzer = BCellIsotypeAnalyzer()

# Validate data
validation_result = analyzer.validate_data(data)
if not validation_result.is_valid:
    print("Validation errors:", validation_result.errors)
    return

# Prepare parameters
parameters = {
    'sample_column': 'Sample',
    'baseline_sample': 'Control',
    'sample_order': ['Control', 'Treatment1', 'Treatment2']
}

# Execute analysis
result = analyzer.analyze(data, parameters)

# Access results
samples = result['samples']
isotype_data = result['isotype_data']
percentage_diffs = result['percentage_diffs']
table_data = result['table_data']
```

## Adding New Analyzers

To add a new analyzer:

1. Create a new file in `services/analyzers/`
2. Import `BaseAnalyzer` and `ValidationResult`
3. Create a class that inherits from `BaseAnalyzer`
4. Implement the required abstract methods:
   - `analyze()`
   - `get_required_fields()`
   - `get_default_parameters()`
5. Optionally override:
   - `validate_data()` for custom validation
   - `get_optional_fields()` for optional fields
6. Add the new analyzer to `__init__.py`

Example:

```python
from .base_analyzer import BaseAnalyzer, ValidationResult

class MyNewAnalyzer(BaseAnalyzer):
    def get_required_fields(self) -> List[str]:
        return ["Sample", "Field1", "Field2"]
    
    def get_default_parameters(self) -> Dict[str, Any]:
        return {
            "sample_column": "Sample",
            "threshold": 0.5
        }
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        # Merge parameters
        params = self.merge_parameters(parameters)
        
        # Perform analysis
        # ...
        
        return {
            "samples": samples,
            "results": results
        }
```

## Testing

All analyzers have basic tests in `tests/test_analyzers_basic.py`. Run tests with:

```bash
pytest tests/test_analyzers_basic.py -v
```

## Requirements Satisfied

This implementation satisfies the following requirements:

- **7.1**: BCellIsotypeAnalyzer produces same results as original module
- **7.2**: SHMAnalyzer produces same results as original module
- **7.3**: IGMetricsAnalyzer produces same results as original module
- **7.4**: CustomFieldAnalyzer supports flexible field combinations
- **11.1**: Unified analysis service handles all analysis types
- **11.2**: New analysis schemes can be added by defining scheme configuration
