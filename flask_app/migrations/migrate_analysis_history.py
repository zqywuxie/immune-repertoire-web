"""
Migration script to add mode and scheme_id fields to existing analysis records.

This script migrates old analysis records to the new unified analysis format by:
1. Adding mode field ('scheme' or 'custom')
2. Adding scheme_id field based on analysis type
3. Adding scheme_name field
4. Adding selected_fields field for custom analyses

Requirements: 7.6, 10.1
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from models.database import db, Analysis
from datetime import datetime


# Mapping of old analysis types to new scheme IDs
ANALYSIS_TYPE_TO_SCHEME = {
    'bcell_isotype': 'bcell_isotype',
    'bcell_isotype_analysis': 'bcell_isotype',
    'b_cell_isotype': 'bcell_isotype',
    'shm': 'shm_analysis',
    'shm_analysis': 'shm_analysis',
    'somatic_hypermutation': 'shm_analysis',
    'ig_metrics': 'ig_metrics',
    'ig_metrics_analysis': 'ig_metrics',
    'immunoglobulin_metrics': 'ig_metrics',
    'custom_field': None,  # Custom field analysis
    'field_analysis': None,
    'generic_field': None,
}

# Scheme names for display
SCHEME_NAMES = {
    'bcell_isotype': 'B细胞同型分析',
    'shm_analysis': 'SHM分析',
    'ig_metrics': 'IG指标分析',
}


def migrate_analysis_record(analysis: Analysis, dry_run: bool = False) -> dict:
    """
    Migrate a single analysis record to the new format.
    
    Args:
        analysis: Analysis record to migrate
        dry_run: If True, don't commit changes to database
    
    Returns:
        Dictionary with migration details
    """
    changes = {
        'id': analysis.id,
        'type': analysis.type,
        'original_mode': analysis.mode,
        'original_scheme_id': analysis.scheme_id,
        'changes_made': []
    }
    
    # Skip if already migrated
    if analysis.mode is not None and analysis.scheme_id is not None:
        changes['status'] = 'already_migrated'
        return changes
    
    # Determine mode and scheme_id based on analysis type
    analysis_type_lower = analysis.type.lower() if analysis.type else ''
    
    # Check if it's a scheme-based analysis
    scheme_id = None
    for type_key, scheme_value in ANALYSIS_TYPE_TO_SCHEME.items():
        if type_key in analysis_type_lower:
            scheme_id = scheme_value
            break
    
    if scheme_id:
        # Scheme-based analysis
        analysis.mode = 'scheme'
        analysis.scheme_id = scheme_id
        analysis.scheme_name = SCHEME_NAMES.get(scheme_id, scheme_id)
        changes['changes_made'].append(f"Set mode to 'scheme'")
        changes['changes_made'].append(f"Set scheme_id to '{scheme_id}'")
        changes['changes_made'].append(f"Set scheme_name to '{analysis.scheme_name}'")
    else:
        # Custom field analysis
        analysis.mode = 'custom'
        analysis.scheme_id = None
        analysis.scheme_name = None
        
        # Try to extract selected fields from field_mapping
        if analysis.field_mapping and isinstance(analysis.field_mapping, dict):
            # Get the target fields (keys) from field_mapping
            selected_fields = list(analysis.field_mapping.keys())
            analysis.selected_fields = selected_fields
            changes['changes_made'].append(f"Set mode to 'custom'")
            changes['changes_made'].append(f"Extracted {len(selected_fields)} selected fields")
        else:
            analysis.selected_fields = []
            changes['changes_made'].append(f"Set mode to 'custom' with empty selected_fields")
    
    if not dry_run:
        try:
            db.session.commit()
            changes['status'] = 'migrated'
        except Exception as e:
            db.session.rollback()
            changes['status'] = 'error'
            changes['error'] = str(e)
    else:
        changes['status'] = 'dry_run'
    
    return changes


def migrate_all_analyses(dry_run: bool = False, verbose: bool = True) -> dict:
    """
    Migrate all analysis records in the database.
    
    Args:
        dry_run: If True, don't commit changes to database
        verbose: If True, print progress information
    
    Returns:
        Dictionary with migration statistics
    """
    stats = {
        'total': 0,
        'migrated': 0,
        'already_migrated': 0,
        'errors': 0,
        'dry_run': dry_run,
        'details': []
    }
    
    # Get all analyses
    analyses = Analysis.query.all()
    stats['total'] = len(analyses)
    
    if verbose:
        print(f"\nFound {stats['total']} analysis records to process")
        print(f"Mode: {'DRY RUN (no changes will be saved)' if dry_run else 'LIVE (changes will be saved)'}")
        print("-" * 80)
    
    # Migrate each analysis
    for i, analysis in enumerate(analyses, 1):
        if verbose:
            print(f"\nProcessing {i}/{stats['total']}: Analysis {analysis.id}")
            print(f"  Type: {analysis.type}")
            print(f"  Created: {analysis.created_at}")
        
        result = migrate_analysis_record(analysis, dry_run=dry_run)
        stats['details'].append(result)
        
        if result['status'] == 'migrated':
            stats['migrated'] += 1
            if verbose:
                print(f"  ✓ Migrated:")
                for change in result['changes_made']:
                    print(f"    - {change}")
        elif result['status'] == 'already_migrated':
            stats['already_migrated'] += 1
            if verbose:
                print(f"  ⊘ Already migrated (mode={result['original_mode']}, scheme_id={result['original_scheme_id']})")
        elif result['status'] == 'error':
            stats['errors'] += 1
            if verbose:
                print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        elif result['status'] == 'dry_run':
            stats['migrated'] += 1
            if verbose:
                print(f"  ⚠ Would migrate:")
                for change in result['changes_made']:
                    print(f"    - {change}")
    
    if verbose:
        print("\n" + "=" * 80)
        print("Migration Summary:")
        print(f"  Total records: {stats['total']}")
        print(f"  Migrated: {stats['migrated']}")
        print(f"  Already migrated: {stats['already_migrated']}")
        print(f"  Errors: {stats['errors']}")
        if dry_run:
            print("\n  ⚠ This was a DRY RUN - no changes were saved to the database")
        else:
            print("\n  ✓ Changes have been saved to the database")
        print("=" * 80)
    
    return stats


def verify_migration() -> dict:
    """
    Verify that all analyses have been migrated correctly.
    
    Returns:
        Dictionary with verification results
    """
    results = {
        'total': 0,
        'valid': 0,
        'invalid': 0,
        'issues': []
    }
    
    analyses = Analysis.query.all()
    results['total'] = len(analyses)
    
    for analysis in analyses:
        is_valid = True
        issues = []
        
        # Check mode field
        if analysis.mode is None:
            is_valid = False
            issues.append("Missing mode field")
        elif analysis.mode not in ['scheme', 'custom']:
            is_valid = False
            issues.append(f"Invalid mode value: {analysis.mode}")
        
        # Check scheme-based analysis
        if analysis.mode == 'scheme':
            if not analysis.scheme_id:
                is_valid = False
                issues.append("Scheme mode but missing scheme_id")
            if not analysis.scheme_name:
                is_valid = False
                issues.append("Scheme mode but missing scheme_name")
        
        # Check custom analysis
        if analysis.mode == 'custom':
            if analysis.selected_fields is None:
                is_valid = False
                issues.append("Custom mode but missing selected_fields")
        
        if is_valid:
            results['valid'] += 1
        else:
            results['invalid'] += 1
            results['issues'].append({
                'id': analysis.id,
                'type': analysis.type,
                'mode': analysis.mode,
                'issues': issues
            })
    
    return results


def main():
    """Main migration function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Migrate analysis history records to unified analysis format'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run migration without saving changes to database'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify migration results'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress verbose output'
    )
    
    args = parser.parse_args()
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        if args.verify:
            # Verify migration
            print("\nVerifying migration...")
            results = verify_migration()
            
            print("\nVerification Results:")
            print(f"  Total records: {results['total']}")
            print(f"  Valid: {results['valid']}")
            print(f"  Invalid: {results['invalid']}")
            
            if results['invalid'] > 0:
                print("\nIssues found:")
                for issue in results['issues']:
                    print(f"\n  Analysis {issue['id']} (type={issue['type']}, mode={issue['mode']}):")
                    for problem in issue['issues']:
                        print(f"    - {problem}")
                return 1
            else:
                print("\n✓ All records are valid!")
                return 0
        else:
            # Run migration
            stats = migrate_all_analyses(
                dry_run=args.dry_run,
                verbose=not args.quiet
            )
            
            # Return exit code based on errors
            return 1 if stats['errors'] > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
