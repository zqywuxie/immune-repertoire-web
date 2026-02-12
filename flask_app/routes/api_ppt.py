"""
API routes for PPT heatmap replacement functionality.
Provides endpoints for uploading PPT templates and replacing heatmaps.

Features:
1. Upload PPT template and analyze slide structure
2. Replace heatmaps with generated images
3. Download modified PPT

Requirements: 10.4, 10.5
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict
from flask import Blueprint, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
import tempfile
import shutil

from flask_app.services.ppt_heatmap_service import (
    PPTHeatmapService,
    scan_heatmap_directory,
    scan_sample_images,
    IMAGE_TYPE_NETWORK_PLOTS,
    IMAGE_TYPE_ISOTYPE_UPSET,
    IMAGE_TYPE_TREE_MAPS,
)
from flask_app.exceptions import (
    PPTError, PPTFileInvalidError, PPTParseError, 
    PPTSlideNotFoundError, PPTImageReplacementError, 
    PPTSessionNotFoundError, PPTNoHeatmapsError
)
from flask_app.routes.api_ppt_comparison import register_ppt_session

logger = logging.getLogger(__name__)

# Create blueprint
ppt_bp = Blueprint('ppt', __name__, url_prefix='/api/ppt')

# Allowed extensions
ALLOWED_EXTENSIONS = {'pptx', 'ppt'}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@ppt_bp.route('/analyze', methods=['POST'])
def analyze_ppt():
    """
    Analyze a PPT file to identify heatmap positions and extract image previews.
    
    Request:
        - Form data with 'file' field containing the PPT file
        - Optional 'include_images' parameter (default: true) to include image previews
        
    Returns:
        {
            "success": true,
            "session_id": "uuid",
            "slide_count": 30,
            "heatmap_slides": [
                {
                    "slide_index": 4,
                    "chain_type": "IGH",
                    "metric_type": "expression_r2",
                    "slide_number_for_chain": 1,
                    "image_count": 3,
                    "image_positions": [
                        {
                            "index": 0,
                            "metric": "expression",
                            "metric_display": "Expression",
                            "data_url": "data:image/png;base64,..."
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'Invalid file type. Only .pptx and .ppt files are allowed'
            }), 400
        
        # Check if images should be included (default: true)
        include_images = request.form.get('include_images', 'true').lower() != 'false'
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Create temp directory for this session
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        ppt_path = temp_dir / filename
        file.save(str(ppt_path))
        
        # Analyze PPT
        service = PPTHeatmapService()
        service.load_presentation(str(ppt_path))
        service.analyze_slides()
        
        # Extract images if requested
        if include_images:
            service.extract_all_heatmap_images(max_size=800)  # Increased to 800 for better preview quality
        
        # Get summary with or without images
        slide_summary = service.get_slide_summary(include_images=include_images)
        
        # Debug logging to verify image data is included
        logger.info(f"Analyze PPT: include_images={include_images}, slide_count={len(slide_summary)}")
        if slide_summary:
            first_slide = slide_summary[0]
            logger.info(f"First slide image_positions count: {len(first_slide.get('image_positions', []))}")
            if first_slide.get('image_positions'):
                first_img = first_slide['image_positions'][0]
                has_data_url = 'data_url' in first_img and first_img['data_url']
                logger.info(f"First image has data_url: {has_data_url}")
        
        # Register session for comparison feature
        register_ppt_session(session_id, str(ppt_path))
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'filename': filename,
            'slide_count': len(service.presentation.slides),
            'heatmap_slides': slide_summary
        })
    
    except PPTFileInvalidError as e:
        logger.warning(f"Invalid PPT file: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code,
            'details': e.details
        }), e.http_status
    
    except PPTParseError as e:
        logger.error(f"PPT parse error: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code,
            'details': e.details
        }), e.http_status
    
    except PPTError as e:
        logger.error(f"PPT error: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
        
    except Exception as e:
        logger.error(f"Error analyzing PPT: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"分析PPT时发生错误: {str(e)}"
        }), 500


@ppt_bp.route('/replace', methods=['POST'])
def replace_heatmaps():
    """
    Replace heatmaps in a PPT file with generated images.
    
    Request JSON:
        {
            "session_id": "uuid",  // From analyze endpoint
            "analysis_id": "uuid", // Analysis that generated the heatmaps
            "heatmap_dir": "/path/to/heatmaps",  // Optional: directory with heatmaps
            "heatmaps": {  // Optional: explicit heatmap mappings
                "IGH": {
                    "r2_inner": "/path/to/heatmap.png",
                    ...
                },
                ...
            }
        }
        
    Returns:
        {
            "success": true,
            "replaced_count": 12,
            "mappings": [...],
            "download_url": "/api/ppt/download/{session_id}"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        session_id = data.get('session_id')
        analysis_id = data.get('analysis_id')
        module = data.get('module')
        layout_config = data.get('layout_config') or {}
        heatmap_dir = data.get('heatmap_dir')
        explicit_heatmaps = data.get('heatmaps')
        sample_images = data.get('sample_images') or {}
        
        # Get border configuration (Requirement 11.8)
        apply_borders = data.get('apply_borders', True)
        border_config_data = data.get('border_config')
        border_config = None
        
        if apply_borders and border_config_data:
            from flask_app.services.ppt_heatmap_service import BorderConfig
            try:
                border_config = BorderConfig(
                    width_pt=border_config_data.get('width_pt', 1.0),
                    color_rgb=tuple(border_config_data.get('color_rgb', [0, 0, 0]))
                )
                if not border_config.validate():
                    logger.warning(f"Invalid border config: {border_config_data}, using defaults")
                    border_config = None
            except Exception as e:
                logger.warning(f"Failed to parse border config: {e}, using defaults")
                border_config = None
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'session_id is required'
            }), 400
        
        # Find session directory
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        if not temp_dir.exists():
            raise PPTSessionNotFoundError(
                message="会话未找到，请重新上传PPT文件",
                details={'session_id': session_id}
            )
        
        # Find the PPT file
        ppt_files = list(temp_dir.glob('*.pptx')) + list(temp_dir.glob('*.ppt'))
        if not ppt_files:
            raise PPTFileInvalidError(
                message="会话中未找到PPT文件",
                details={'session_id': session_id}
            )
        
        ppt_path = ppt_files[0]
        
        sample_modules = {
            IMAGE_TYPE_NETWORK_PLOTS,
            IMAGE_TYPE_ISOTYPE_UPSET,
            IMAGE_TYPE_TREE_MAPS
        }
        if module in sample_modules and not sample_images:
            sample_images = {}
            image_base_dir = data.get('image_dir') or heatmap_dir
            for image_type, dir_key in (
                (IMAGE_TYPE_NETWORK_PLOTS, 'network_plots_dir'),
                (IMAGE_TYPE_ISOTYPE_UPSET, 'isotype_upset_dir'),
                (IMAGE_TYPE_TREE_MAPS, 'tree_maps_dir'),
            ):
                source_dir = data.get(dir_key) or image_base_dir
                if source_dir and os.path.isdir(source_dir):
                    sample_images[image_type] = scan_sample_images(source_dir, image_type)

        available_heatmaps = {}
        if module not in sample_modules:
            if explicit_heatmaps:
                available_heatmaps = explicit_heatmaps
                logger.info(f"Using explicit heatmaps: {len(available_heatmaps)} chains")
            elif heatmap_dir:
                logger.info(f"Scanning heatmap directory: {heatmap_dir}")
                available_heatmaps = scan_heatmap_directory(heatmap_dir)
                logger.info(f"Found heatmaps: {available_heatmaps}")
            elif analysis_id:
                logger.info(f"Getting heatmaps from analysis: {analysis_id}")
                available_heatmaps = _get_heatmaps_from_analysis(analysis_id)

        if module in sample_modules:
            module_images = sample_images.get(module, {}) if isinstance(sample_images, dict) else {}
            if not module_images:
                raise PPTNoHeatmapsError(
                    message=f"模块 {module} 没有可替换图片，请提供 sample_images 或有效目录",
                    details={'module': module}
                )
        elif not available_heatmaps:
            # Provide more detailed error message
            error_details = {'session_id': session_id}
            if heatmap_dir:
                error_details['heatmap_dir'] = heatmap_dir
                error_details['dir_exists'] = os.path.exists(heatmap_dir) if heatmap_dir else False
                if os.path.exists(heatmap_dir):
                    # List what files are in the directory for debugging
                    try:
                        dir_contents = os.listdir(heatmap_dir)
                        error_details['dir_contents'] = dir_contents[:20]  # First 20 items
                    except Exception:
                        pass
            if analysis_id:
                error_details['analysis_id'] = analysis_id
            
            raise PPTNoHeatmapsError(
                message="没有可用的热图文件，请提供 heatmap_dir、heatmaps 或 analysis_id",
                details=error_details
            )
        
        # Load and process PPT
        service = PPTHeatmapService()
        service.load_presentation(str(ppt_path))
        service.analyze_slides()
        if module in sample_modules:
            network_images = sample_images.get(IMAGE_TYPE_NETWORK_PLOTS, {}) if isinstance(sample_images, dict) else {}
            upset_images = sample_images.get(IMAGE_TYPE_ISOTYPE_UPSET, {}) if isinstance(sample_images, dict) else {}
            tree_images = sample_images.get(IMAGE_TYPE_TREE_MAPS, {}) if isinstance(sample_images, dict) else {}
            service.create_image_mappings(
                network_plot_images=network_images,
                isotype_upset_images=upset_images,
                tree_map_images=tree_images,
                module=module,
                layout_config=layout_config,
            )
        else:
            service.create_heatmap_mappings(available_heatmaps)
        
        # Replace heatmaps with border configuration (Requirement 11.8)
        result = service.replace_heatmaps(
            apply_borders=apply_borders,
            border_config=border_config
        )
        
        # Save modified PPT
        output_filename = f"{ppt_path.stem}_updated{ppt_path.suffix}"
        output_path = temp_dir / output_filename
        service.save_presentation(str(output_path))
        
        # Log border application details
        logger.info(
            f"Image replacement complete: {result.replaced_count}/{result.total_count} replaced, "
            f"{result.border_applied_count} borders applied"
        )
        
        return jsonify({
            'success': True,
            'replaced_count': result.replaced_count,
            'total_count': result.total_count,
            'border_applied_count': result.border_applied_count,
            'border_rate': f"{result.border_applied_count}/{result.replaced_count}" if result.replaced_count > 0 else "0/0",
            'mappings': service.get_mapping_summary(),
            'warnings': result.warnings,
            'errors': result.errors,
            'applied_layout_summary': service.layout_summary,
            'output_filename': output_filename,
            'download_url': f'/api/ppt/download/{session_id}/{output_filename}'
        })
    
    except PPTSessionNotFoundError as e:
        logger.warning(f"Session not found: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTNoHeatmapsError as e:
        logger.warning(f"No heatmaps available: {e.message}, details: {e.details}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code,
            'details': e.details
        }), e.http_status
    
    except (PPTFileInvalidError, PPTParseError) as e:
        logger.error(f"PPT error: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTImageReplacementError as e:
        logger.error(f"Image replacement error: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTError as e:
        logger.error(f"PPT error: {e.message}")
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
        
    except Exception as e:
        logger.error(f"Error replacing heatmaps: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"替换热图时发生错误: {str(e)}"
        }), 500


@ppt_bp.route('/download/<session_id>/<filename>', methods=['GET'])
def download_ppt(session_id: str, filename: str):
    """
    Download the modified PPT file.
    
    Args:
        session_id: Session ID from analyze endpoint
        filename: Name of the file to download
        
    Returns:
        PPT file as attachment
    """
    try:
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        
        if not temp_dir.exists():
            raise PPTSessionNotFoundError(
                message="会话未找到",
                details={'session_id': session_id}
            )
        
        file_path = temp_dir / secure_filename(filename)
        
        if not file_path.exists():
            raise PPTFileInvalidError(
                message=f"文件未找到: {filename}",
                details={'session_id': session_id, 'filename': filename}
            )
        
        return send_file(
            str(file_path),
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    
    except PPTSessionNotFoundError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTFileInvalidError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
        
    except Exception as e:
        logger.error(f"Error downloading PPT: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"下载PPT时发生错误: {str(e)}"
        }), 500


@ppt_bp.route('/replace-direct', methods=['POST'])
def replace_heatmaps_direct():
    """
    Upload PPT and heatmaps together, replace and return the modified PPT.
    
    Request:
        - Form data with:
            - 'ppt_file': The PPT template file
            - 'heatmaps': JSON string with heatmap file paths or base64 data
            - Or multiple files named like 'IGH_r2_inner', 'IGH_r2_outer', etc.
        
    Returns:
        Modified PPT file as download
    """
    try:
        # Check for PPT file
        if 'ppt_file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No PPT file provided'
            }), 400
        
        ppt_file = request.files['ppt_file']
        
        if not allowed_file(ppt_file.filename):
            return jsonify({
                'success': False,
                'error': 'Invalid PPT file type'
            }), 400
        
        # Create temp directory
        session_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Save PPT file
        ppt_filename = secure_filename(ppt_file.filename)
        ppt_path = temp_dir / ppt_filename
        ppt_file.save(str(ppt_path))
        
        # Collect heatmap files
        available_heatmaps = {}
        
        # Process uploaded heatmap files
        for key, file in request.files.items():
            if key == 'ppt_file':
                continue
            
            # Parse key to get chain and metric (e.g., "IGH_r2_inner")
            parts = key.split('_', 1)
            if len(parts) == 2:
                chain, metric = parts[0].upper(), parts[1].lower()
                
                # Save heatmap file
                heatmap_path = temp_dir / f"{chain}_{metric}.png"
                file.save(str(heatmap_path))
                
                if chain not in available_heatmaps:
                    available_heatmaps[chain] = {}
                available_heatmaps[chain][metric] = str(heatmap_path)
        
        # Also check for heatmap_dir in form data
        heatmap_dir = request.form.get('heatmap_dir')
        if heatmap_dir and os.path.isdir(heatmap_dir):
            scanned = scan_heatmap_directory(heatmap_dir)
            for chain, metrics in scanned.items():
                if chain not in available_heatmaps:
                    available_heatmaps[chain] = {}
                available_heatmaps[chain].update(metrics)
        
        if not available_heatmaps:
            raise PPTNoHeatmapsError(
                message="未提供热图文件",
                details={'session_id': session_id}
            )
        
        # Process PPT
        service = PPTHeatmapService()
        service.load_presentation(str(ppt_path))
        service.analyze_slides()
        service.create_heatmap_mappings(available_heatmaps)
        result = service.replace_heatmaps()
        
        # Log border application details
        logger.info(
            f"Direct replacement complete: {result.replaced_count}/{result.total_count} replaced, "
            f"{result.border_applied_count} borders applied"
        )
        
        # Save and return
        output_filename = f"{ppt_path.stem}_updated{ppt_path.suffix}"
        output_path = temp_dir / output_filename
        service.save_presentation(str(output_path))
        
        return send_file(
            str(output_path),
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    
    except PPTNoHeatmapsError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except (PPTFileInvalidError, PPTParseError) as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
        
    except Exception as e:
        logger.error(f"Error in direct replace: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"直接替换时发生错误: {str(e)}"
        }), 500


@ppt_bp.route('/cleanup/<session_id>', methods=['DELETE'])
def cleanup_session(session_id: str):
    """
    Clean up temporary files for a session.
    
    Args:
        session_id: Session ID to clean up
        
    Returns:
        Success status
    """
    try:
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            return jsonify({
                'success': True,
                'message': 'Session cleaned up'
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Session not found (already cleaned up)'
            })
        
    except Exception as e:
        logger.error(f"Error cleaning up session: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ppt_bp.route('/scan-images', methods=['POST'])
def scan_images():
    """
    Scan directories for images and return mappings.
    
    Request JSON:
        {
            "session_id": "uuid",
            "image_dir": "/path/to/images",  // Legacy: single directory for all types
            "analysis_id": "uuid",  // Optional
            "image_type": "sharing_analysis",  // Optional: specific type to scan
            "sharing_analysis_dir": "/path/to/heatmaps",  // Optional: specific dir for heatmaps
            "network_plots_dir": "/path/to/network",  // Optional: specific dir for network plots
            "isotype_upset_dir": "/path/to/upset",  // Optional: specific dir for upset plots
            "tree_maps_dir": "/path/to/treemaps"  // Optional: specific dir for tree maps
        }
        
    Returns:
        {
            "success": true,
            "images": {
                "sharing_analysis": {...},
                "network_plots": {...},
                ...
            },
            "mappings": [...],
            "summary": "找到 X 个热图, Y 个网络图..."
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        session_id = data.get('session_id')
        image_dir = data.get('image_dir') or data.get('heatmap_dir')  # Legacy single directory
        analysis_id = data.get('analysis_id')
        image_type = data.get('image_type')  # Optional: specific type to scan
        
        # Get module-specific directories (new feature)
        sharing_analysis_dir = data.get('sharing_analysis_dir') or image_dir
        network_plots_dir = data.get('network_plots_dir') or image_dir
        isotype_upset_dir = data.get('isotype_upset_dir') or image_dir
        tree_maps_dir = data.get('tree_maps_dir') or image_dir
        
        # Debug logging
        logger.info(f"scan-images request data: {data}")
        logger.info(f"image_type: {image_type}, sharing_analysis_dir: {sharing_analysis_dir}")
        logger.info(f"sharing_analysis_dir exists: {os.path.isdir(sharing_analysis_dir) if sharing_analysis_dir else 'N/A'}")
        
        # Collect images from different sources
        all_images = {
            'sharing_analysis': {},
            'network_plots': {},
            'isotype_upset': {},
            'tree_maps': {}
        }
        
        # Scan based on image_type or all types
        if not image_type or image_type == 'sharing_analysis':
            if sharing_analysis_dir and os.path.isdir(sharing_analysis_dir):
                logger.info(f"Scanning sharing_analysis_dir: {sharing_analysis_dir}")
                all_images['sharing_analysis'] = scan_heatmap_directory(sharing_analysis_dir)
                logger.info(f"Found sharing_analysis images: {len(all_images['sharing_analysis'])} chains")
            else:
                logger.warning(f"sharing_analysis_dir not valid: {sharing_analysis_dir}")
        
        if not image_type or image_type == 'network_plots':
            if network_plots_dir and os.path.isdir(network_plots_dir):
                all_images['network_plots'] = scan_sample_images(network_plots_dir, 'network_plots')
        
        if not image_type or image_type == 'isotype_upset':
            if isotype_upset_dir and os.path.isdir(isotype_upset_dir):
                all_images['isotype_upset'] = scan_sample_images(isotype_upset_dir, 'isotype_upset')
        
        if not image_type or image_type == 'tree_maps':
            if tree_maps_dir and os.path.isdir(tree_maps_dir):
                all_images['tree_maps'] = scan_sample_images(tree_maps_dir, 'tree_maps')
        
        # Get from analysis if provided
        if analysis_id:
            analysis_images = _get_heatmaps_from_analysis(analysis_id)
            # Merge with existing
            for chain, metrics in analysis_images.items():
                if chain not in all_images['sharing_analysis']:
                    all_images['sharing_analysis'][chain] = {}
                all_images['sharing_analysis'][chain].update(metrics)
        
        # Build mappings list for preview
        mappings = []
        
        # Sharing Analysis mappings
        for chain, metrics in all_images['sharing_analysis'].items():
            for metric, path in metrics.items():
                mappings.append({
                    'image_type': 'sharing_analysis',
                    'chain': chain,
                    'metric': metric,
                    'image_path': path,
                    'image_file': os.path.basename(path) if path else None,
                    'has_file': path is not None and os.path.exists(path)
                })
        
        # Sample-based image mappings
        for image_type in ['network_plots', 'isotype_upset', 'tree_maps']:
            for sample_name, path in all_images.get(image_type, {}).items():
                mappings.append({
                    'image_type': image_type,
                    'sample_name': sample_name,
                    'image_path': path,
                    'image_file': os.path.basename(path) if path else None,
                    'has_file': path is not None and os.path.exists(path)
                })
        
        # Build summary
        summary_parts = []
        sharing_count = sum(len(m) for m in all_images['sharing_analysis'].values())
        if sharing_count > 0:
            chain_count = len(all_images['sharing_analysis'])
            summary_parts.append(f"热图: {sharing_count} 个 ({chain_count} 条链)")
        
        for image_type, display_name in [
            ('network_plots', '网络图'),
            ('isotype_upset', 'Upset图'),
            ('tree_maps', '树图')
        ]:
            count = len(all_images.get(image_type, {}))
            if count > 0:
                summary_parts.append(f"{display_name}: {count} 个")
        
        summary = ', '.join(summary_parts) if summary_parts else '未找到图片文件'
        
        return jsonify({
            'success': True,
            'images': all_images,
            'mappings': mappings,
            'summary': summary
        })
    
    except Exception as e:
        logger.error(f"Error scanning images: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ppt_bp.route('/load-image', methods=['POST'])
def load_image():
    """
    Load an image from file path and return as data URL.
    
    Request JSON:
        path: File path to the image
        
    Returns:
        JSON with data_url
    """
    try:
        data = request.get_json()
        file_path = data.get('path')
        
        if not file_path or not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'File not found'
            }), 404
        
        # Read image and convert to base64
        import base64
        from PIL import Image
        import io
        
        with Image.open(file_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if too large
            max_size = 1200
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            
            # Save to buffer
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            
            # Encode to base64
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            data_url = f"data:image/jpeg;base64,{img_base64}"
        
        return jsonify({
            'success': True,
            'data_url': data_url,
            'file_name': os.path.basename(file_path)
        })
        
    except Exception as e:
        logger.error(f"Error loading image: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _get_heatmaps_from_analysis(analysis_id: str) -> Dict:
    """
    Get heatmap file paths from an analysis result.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        Dictionary mapping chain -> metric -> file_path
    """
    try:
        from flask_app.models.database import Analysis, AnalysisResult
        
        # Get analysis results
        results = AnalysisResult.query.filter_by(
            analysis_id=analysis_id,
            result_type='visualization'
        ).all()
        
        available_heatmaps = {}
        
        for result in results:
            # Parse result name to get chain and metric
            # Expected format: {chain}_{metric}_heatmap
            name = result.name
            parts = name.replace('_heatmap', '').split('_', 1)
            
            if len(parts) == 2:
                chain, metric = parts[0].upper(), parts[1].lower()
                
                if os.path.exists(result.file_path):
                    if chain not in available_heatmaps:
                        available_heatmaps[chain] = {}
                    available_heatmaps[chain][metric] = result.file_path
        
        return available_heatmaps
        
    except Exception as e:
        logger.error(f"Error getting heatmaps from analysis: {e}")
        return {}


@ppt_bp.route('/render-slides', methods=['POST'])
def render_slides():
    """
    Render PPT slides as images for preview.
    
    Request JSON:
        {
            "session_id": "uuid",
            "slide_indices": [0, 1, 2],  // Optional: specific slides to render
            "max_size": 800  // Optional: max dimension for rendered images
        }
        
    Returns:
        {
            "success": true,
            "slides": [
                {
                    "index": 0,
                    "title": "Slide Title",
                    "data_url": "data:image/png;base64,...",
                    "has_images": true,
                    "image_count": 3
                },
                ...
            ],
            "total_slides": 30
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        session_id = data.get('session_id')
        slide_indices = data.get('slide_indices')  # Optional
        max_size = data.get('max_size', 800)
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'session_id is required'
            }), 400
        
        # Find session directory
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        if not temp_dir.exists():
            raise PPTSessionNotFoundError(
                message="会话未找到，请重新上传PPT文件",
                details={'session_id': session_id}
            )
        
        # Find the PPT file (prefer updated version)
        ppt_files = list(temp_dir.glob('*_updated.pptx')) + list(temp_dir.glob('*.pptx')) + list(temp_dir.glob('*.ppt'))
        if not ppt_files:
            raise PPTFileInvalidError(
                message="会话中未找到PPT文件",
                details={'session_id': session_id}
            )
        
        ppt_path = ppt_files[0]
        
        # Load and render slides
        service = PPTHeatmapService()
        service.load_presentation(str(ppt_path))
        
        total_slides = len(service.presentation.slides)
        
        # Determine which slides to render
        if slide_indices is None:
            slide_indices = list(range(total_slides))
        
        slides_data = []
        for idx in slide_indices:
            if idx >= total_slides:
                continue
            
            try:
                slide_info = service.render_slide_preview(idx, max_size)
                slides_data.append(slide_info)
            except Exception as e:
                logger.error(f"Error rendering slide {idx}: {e}")
                slides_data.append({
                    'index': idx,
                    'title': f'Slide {idx + 1}',
                    'error': str(e),
                    'has_images': False
                })
        
        return jsonify({
            'success': True,
            'slides': slides_data,
            'total_slides': total_slides
        })
    
    except PPTSessionNotFoundError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTFileInvalidError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except Exception as e:
        logger.error(f"Error rendering slides: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"渲染幻灯片时发生错误: {str(e)}"
        }), 500


@ppt_bp.route('/session-status', methods=['POST'])
def get_session_status():
    """
    Get current session status including replacement history.
    
    Request JSON:
        {
            "session_id": "uuid"
        }
        
    Returns:
        {
            "success": true,
            "session_id": "uuid",
            "filename": "template.pptx",
            "total_slides": 30,
            "has_updated_file": true,
            "download_url": "/api/ppt/download/..."
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'session_id is required'
            }), 400
        
        # Find session directory
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        if not temp_dir.exists():
            return jsonify({
                'success': False,
                'error': '会话未找到'
            }), 404
        
        # Check for files
        original_files = list(temp_dir.glob('*.pptx')) + list(temp_dir.glob('*.ppt'))
        updated_files = list(temp_dir.glob('*_updated.pptx'))
        
        original_file = None
        for f in original_files:
            if '_updated' not in f.name:
                original_file = f
                break
        
        has_updated = len(updated_files) > 0
        download_url = None
        
        if has_updated:
            updated_file = updated_files[0]
            download_url = f'/api/ppt/download/{session_id}/{updated_file.name}'
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'filename': original_file.name if original_file else None,
            'has_updated_file': has_updated,
            'download_url': download_url
        })
    
    except Exception as e:
        logger.error(f"Error getting session status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ppt_bp.route('/download-with-summary', methods=['POST'])
def download_with_summary():
    """
    Download PPT with an added summary slide at the end.
    
    Request JSON:
        {
            "session_id": "uuid",
            "filename": "custom_filename.pptx",
            "summary": {
                "total_replaced": 12,
                "modules": [
                    {"name": "Sharing Analysis", "replaced": true, "count": 6, "timestamp": "..."},
                    ...
                ],
                "generated_at": "2026-01-15T10:30:00Z"
            }
        }
    
    Returns:
        PPT file with summary slide as attachment
    
    Requirements: Req 7 - Download Enhancement
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求数据无效'
            }), 400
        
        session_id = data.get('session_id')
        custom_filename = data.get('filename', 'presentation_replaced.pptx')
        summary = data.get('summary', {})
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': '缺少session_id'
            }), 400
        
        # Find the session directory
        temp_dir = Path(tempfile.gettempdir()) / 'ppt_heatmap' / session_id
        
        if not temp_dir.exists():
            raise PPTSessionNotFoundError(
                message="会话未找到",
                details={'session_id': session_id}
            )
        
        # Find the latest modified PPT file
        ppt_files = list(temp_dir.glob('*_replaced*.pptx')) + list(temp_dir.glob('*.pptx'))
        if not ppt_files:
            raise PPTFileInvalidError(
                message="未找到PPT文件",
                details={'session_id': session_id}
            )
        
        # Sort by modification time, get the latest
        ppt_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        source_ppt = ppt_files[0]
        
        # Create service and add summary slide
        service = PPTHeatmapService(str(source_ppt))
        
        # Add summary slide
        service.add_summary_slide(summary)
        
        # Save to a new file with custom filename
        output_path = temp_dir / secure_filename(custom_filename)
        service.save(str(output_path))
        
        logger.info(f"Created PPT with summary slide: {output_path}")
        
        return send_file(
            str(output_path),
            as_attachment=True,
            download_name=custom_filename,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    
    except PPTSessionNotFoundError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except PPTFileInvalidError as e:
        return jsonify({
            'success': False,
            'error': e.message,
            'error_code': e.error_code
        }), e.http_status
    
    except Exception as e:
        logger.error(f"Error creating PPT with summary: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"创建摘要页时发生错误: {str(e)}"
        }), 500
