"""
Field Mapping Service for the Immune Repertoire Analysis Web Application.
Handles field mapping validation, template management, and mapping suggestions.
Requirements: 11.2, 11.3, 11.4, 11.5
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple, Any


@dataclass
class ValidationResult:
    """Result of field mapping validation."""
    is_valid: bool
    missing_fields: List[str]
    mapped_fields: Dict[str, str]
    message: str


@dataclass
class SuggestedMapping:
    """Suggested field mapping based on column similarity."""
    mapping: Dict[str, str]
    confidence: float
    matched_template_id: Optional[str]
    field_scores: Dict[str, float]


class FieldMappingService:
    """
    Service for field mapping operations.
    Handles validation, suggestions, and template management.
    Requirements: 11.2, 11.3, 11.4, 11.5
    """
    
    # Required fields for each analysis type
    # Maps analysis_type -> {target_field: description}
    REQUIRED_FIELDS: Dict[str, Dict[str, str]] = {
        'similarity_heatmap': {
            'sample': 'Sample identifier column',
            'cdr3': 'CDR3 sequence column',
            'reads': 'Read count column'
        },
        'bcell_isotype': {
            'sample': 'Sample identifier column'
            # Note: Isotype columns are auto-detected, not required in mapping
        },
        'shm_analysis': {
            'sample': 'Sample identifier column'
            # Note: SHM columns are auto-detected, not required in mapping
        },
        'ig_metrics': {
            'sample': 'Sample identifier column'
            # Note: IG metric columns are auto-detected, not required in mapping
        },
        'field_analysis': {
            'sample': 'Sample identifier column'
            # Note: Analysis fields are user-selected, not required in mapping
        },
        'sequencing_depth': {
            'sample': 'Sample identifier column',
            'total_rna': 'Total Receptor RNA column',
            'reads_umi': 'Reads per UMI column',
            'migs_good': 'MigsGoodTotal column',
            'reads_good': 'ReadsGoodTotal column'
        },
        'diversity_metrics': {
            'sample': 'Sample identifier column',
            'chain': 'Chain type column',
            'd50': 'D50 diversity metric column',
            'gini': 'Gini index column',
            'shannon': 'Shannon entropy column',
            'simpson': 'Simpson index column'
        },
        'chain_specific': {
            'sample': 'Sample identifier column',
            'chain': 'Chain type column',
            'cdr3': 'CDR3 sequence column',
            'copy': 'Copy number column'
        },
        'ppt_module': {
            # PPT module has dynamic fields - no required fields
            # Users select which columns to include in the PPT
        }
    }

    # Common column name aliases for auto-suggestion
    FIELD_ALIASES: Dict[str, List[str]] = {
        'sample': ['sample', 'sample_id', 'sample_name', 'sampleid', 'samplename', 'id', 'name', 'sample id', 'sample name'],
        'cdr3': ['cdr3', 'cdr3_aa', 'cdr3_nt', 'cdr3aa', 'cdr3nt', 'cdr3_sequence', 'sequence', 'CDR3(pep)', 'CDR3', 'cdr3(pep)', 'cdr3 aa', 'cdr3 nt', 'cdr3 sequence'],
        'reads': ['reads', 'read_count', 'readcount', 'count', 'read', 'n_reads', 'copy', 'copy_number', 'copynumber', 'copies', 'read count', 'n reads'],
        'copy': ['copy', 'copy_number', 'copynumber', 'copies', 'clone_count', 'clonecount', 'reads', 'read_count', 'copy number', 'clone count'],
        'chain': ['chain', 'chain_type', 'chaintype', 'locus', 'receptor_chain', 'chain type', 'receptor chain'],
        'total_rna': ['total_rna', 'totalrna', 'total_receptor_rna', 'receptor_rna', 'rna_total', 'total rna', 'total receptor rna', 'receptor rna', 'rna total'],
        'reads_umi': ['reads_umi', 'readsumi', 'reads_per_umi', 'umi_reads', 'reads/umi', 'reads umi', 'reads per umi', 'umi reads'],
        'migs_good': ['migs_good', 'migsgood', 'migs_good_total', 'migsgoodtotal', 'good_migs', 'migs good', 'migs good total', 'good migs'],
        'reads_good': ['reads_good', 'readsgood', 'reads_good_total', 'readsgoodtotal', 'good_reads', 'reads good', 'reads good total', 'good reads'],
        'd50': ['d50', 'd_50', 'diversity_50', 'd50_index', 'd 50', 'diversity 50', 'd50 index'],
        'gini': ['gini', 'gini_index', 'giniindex', 'gini_coefficient', 'gini index', 'gini coefficient'],
        'shannon': ['shannon', 'shannon_entropy', 'shannonentropy', 'shannon_index', 'shannon entropy', 'shannon index'],
        'simpson': ['simpson', 'simpson_index', 'simpsonindex', 'simpson_diversity', 'simpson index', 'simpson diversity']
    }
    
    @classmethod
    def get_required_fields(cls, analysis_type: str) -> Dict[str, str]:
        """
        Get required fields for an analysis type.
        
        Args:
            analysis_type: Type of analysis
            
        Returns:
            Dictionary of required field names and descriptions
        """
        return cls.REQUIRED_FIELDS.get(analysis_type, {})
    
    @classmethod
    def get_supported_analysis_types(cls) -> List[str]:
        """Get list of supported analysis types."""
        return list(cls.REQUIRED_FIELDS.keys())
    
    @classmethod
    def validate_mapping(
        cls,
        analysis_type: str,
        mapping: Dict[str, str],
        available_columns: List[str]
    ) -> ValidationResult:
        """
        Validate if a field mapping is complete for an analysis type.
        
        Args:
            analysis_type: Type of analysis
            mapping: Dictionary mapping target_field -> source_column
            available_columns: List of available columns in the data file
            
        Returns:
            ValidationResult with validation status and details
            
        Requirements: 11.5
        """
        required_fields = cls.get_required_fields(analysis_type)
        
        if not required_fields:
            return ValidationResult(
                is_valid=False,
                missing_fields=[],
                mapped_fields={},
                message=f"Unknown analysis type: {analysis_type}"
            )
        
        missing_fields = []
        valid_mappings = {}
        available_columns_set = set(available_columns)
        
        for field in required_fields:
            if field not in mapping:
                missing_fields.append(field)
            elif mapping[field] not in available_columns_set:
                missing_fields.append(field)
            else:
                valid_mappings[field] = mapping[field]
        
        is_valid = len(missing_fields) == 0
        
        if is_valid:
            message = "All required fields are mapped"
        else:
            message = f"Missing required fields: {', '.join(missing_fields)}"
        
        return ValidationResult(
            is_valid=is_valid,
            missing_fields=missing_fields,
            mapped_fields=valid_mappings,
            message=message
        )

    @classmethod
    def _calculate_similarity(cls, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using SequenceMatcher.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity score between 0 and 1
        """
        str1_lower = str1.lower().strip()
        str2_lower = str2.lower().strip()
        
        # Exact match
        if str1_lower == str2_lower:
            return 1.0
        
        # Check if one contains the other
        if str1_lower in str2_lower or str2_lower in str1_lower:
            return 0.8
        
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, str1_lower, str2_lower).ratio()
    
    @classmethod
    def _find_best_match(
        cls,
        target_field: str,
        available_columns: List[str],
        used_columns: Set[str]
    ) -> Tuple[Optional[str], float]:
        """
        Find the best matching column for a target field.
        
        Args:
            target_field: Target field name to match
            available_columns: List of available columns
            used_columns: Set of already used columns
            
        Returns:
            Tuple of (best_match_column, confidence_score)
        """
        best_match = None
        best_score = 0.0
        
        # Get aliases for this field
        aliases = cls.FIELD_ALIASES.get(target_field, [target_field])
        
        for column in available_columns:
            if column in used_columns:
                continue
            
            column_lower = column.lower().strip()
            
            # Check against all aliases
            for alias in aliases:
                # Exact match with alias
                if column_lower == alias.lower():
                    return column, 1.0
                
                # Calculate similarity
                score = cls._calculate_similarity(alias, column)
                if score > best_score:
                    best_score = score
                    best_match = column
        
        return best_match, best_score
    
    @classmethod
    def suggest_mapping(
        cls,
        columns: List[str],
        analysis_type: str,
        saved_templates: Optional[List[Dict[str, Any]]] = None
    ) -> SuggestedMapping:
        """
        Suggest field mappings based on column name similarity.
        
        Args:
            columns: List of column names from the data file
            analysis_type: Type of analysis to suggest mappings for
            saved_templates: Optional list of saved mapping templates
            
        Returns:
            SuggestedMapping with suggested mappings and confidence
            
        Requirements: 11.4
        """
        required_fields = cls.get_required_fields(analysis_type)
        
        if not required_fields:
            return SuggestedMapping(
                mapping={},
                confidence=0.0,
                matched_template_id=None,
                field_scores={}
            )
        
        # First, try to match with saved templates
        if saved_templates:
            best_template_match = cls._match_with_templates(
                columns, analysis_type, saved_templates
            )
            if best_template_match and best_template_match[1] > 0.8:
                template_id, confidence, mapping = best_template_match
                return SuggestedMapping(
                    mapping=mapping,
                    confidence=confidence,
                    matched_template_id=template_id,
                    field_scores={field: confidence for field in mapping}
                )
        
        # Auto-suggest based on column name similarity
        suggested_mapping = {}
        field_scores = {}
        used_columns: Set[str] = set()
        total_score = 0.0
        
        for field in required_fields:
            best_match, score = cls._find_best_match(field, columns, used_columns)
            
            if best_match and score >= 0.5:  # Minimum threshold for suggestion
                suggested_mapping[field] = best_match
                field_scores[field] = score
                used_columns.add(best_match)
                total_score += score
            else:
                field_scores[field] = 0.0
        
        # Calculate overall confidence
        num_fields = len(required_fields)
        confidence = total_score / num_fields if num_fields > 0 else 0.0
        
        return SuggestedMapping(
            mapping=suggested_mapping,
            confidence=confidence,
            matched_template_id=None,
            field_scores=field_scores
        )
    
    @classmethod
    def suggest_mapping_with_confidence(
        cls,
        columns: List[str],
        analysis_type: str
    ) -> Tuple[Dict[str, str], Dict[str, float]]:
        """
        Return suggested mapping and confidence scores for each field.
        
        This method provides a simplified interface that returns just the mapping
        and per-field confidence scores without template matching.
        
        Args:
            columns: List of column names from the data file
            analysis_type: Type of analysis to suggest mappings for
            
        Returns:
            Tuple of (mapping_dict, confidence_scores_dict)
            
        Requirements: 3.1, 3.2
        """
        suggestion = cls.suggest_mapping(columns, analysis_type, saved_templates=None)
        return suggestion.mapping, suggestion.field_scores
    
    @classmethod
    def validate_user_mapping(
        cls,
        mapping: Dict[str, str],
        analysis_type: str,
        available_columns: List[str]
    ) -> ValidationResult:
        """
        Validate user-modified mapping to ensure it's valid.
        
        This is an alias for validate_mapping with a more descriptive name
        for user-initiated validation.
        
        Args:
            mapping: Dictionary mapping target_field -> source_column
            analysis_type: Type of analysis
            available_columns: List of available columns in the data file
            
        Returns:
            ValidationResult with validation status and details
            
        Requirements: 3.4, 3.5
        """
        return cls.validate_mapping(analysis_type, mapping, available_columns)

    @classmethod
    def _match_with_templates(
        cls,
        columns: List[str],
        analysis_type: str,
        templates: List[Dict[str, Any]]
    ) -> Optional[Tuple[str, float, Dict[str, str]]]:
        """
        Try to match columns with saved templates.
        
        Args:
            columns: List of column names
            analysis_type: Type of analysis
            templates: List of saved templates
            
        Returns:
            Tuple of (template_id, confidence, mapping) or None
        """
        columns_set = set(columns)
        best_match = None
        best_score = 0.0
        
        for template in templates:
            if template.get('analysis_type') != analysis_type:
                continue
            
            template_mapping = template.get('mapping', {})
            if not template_mapping:
                continue
            
            # Check how many columns from the template exist in the file
            matched_columns = 0
            valid_mapping = {}
            
            for field, column in template_mapping.items():
                if column in columns_set:
                    matched_columns += 1
                    valid_mapping[field] = column
            
            if len(template_mapping) > 0:
                score = matched_columns / len(template_mapping)
                if score > best_score:
                    best_score = score
                    best_match = (template.get('id'), score, valid_mapping)
        
        return best_match
    
    @classmethod
    def apply_mapping(
        cls,
        data: Dict[str, Any],
        mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Apply field mapping to rename columns in data.
        
        Args:
            data: Dictionary with column data
            mapping: Dictionary mapping target_field -> source_column
            
        Returns:
            Dictionary with renamed columns
        """
        result = {}
        reverse_mapping = {v: k for k, v in mapping.items()}
        
        for column, values in data.items():
            if column in reverse_mapping:
                result[reverse_mapping[column]] = values
            else:
                result[column] = values
        
        return result
    
    @classmethod
    def get_field_info(cls, analysis_type: str) -> List[Dict[str, str]]:
        """
        Get detailed information about required fields for an analysis type.
        
        Args:
            analysis_type: Type of analysis
            
        Returns:
            List of field information dictionaries
        """
        required_fields = cls.get_required_fields(analysis_type)
        
        return [
            {
                'name': field,
                'description': description,
                'aliases': cls.FIELD_ALIASES.get(field, [field])
            }
            for field, description in required_fields.items()
        ]
