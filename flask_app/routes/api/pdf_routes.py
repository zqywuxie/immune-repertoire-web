"""PDF extraction and chart generation routes."""

import io
import re
import base64
import zipfile
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from flask import Blueprint, request, jsonify, current_app, send_file

from flask_app.exceptions import ValidationError, FileNotFoundError as AppFileNotFoundError

from ._common import _get_owned_file, logger

bp = Blueprint("api_pdf_routes", __name__)


@bp.route('/pdf/extract-tables', methods=['POST'])
def extract_pdf_tables():
    """
    Extract B cell isotype tables from PDF files.
    POST /api/pdf/extract-tables
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
    
    Request body:
    {
        "file_ids": ["file_id1", "file_id2", ...]
    }
    
    Returns:
    {
        "extracted_data": {filename: {expression: [...], unique_cdr3: [...]}},
        "failed_files": [filenames],
        "error_messages": {filename: error_message},
        "table_data": {headers: [...], rows: [...], tab_separated: "..."}
    }
    """
    from services.analysis.modules.pdf_extractor import (
        PDFExtractor,
        PDFExtractorError,
        PDFFileNotFoundError as PDFNotFound,
        PDFParseError
    )
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    file_ids = data.get('file_ids', [])
    
    if not file_ids:
        raise ValidationError(
            message="At least one file_id is required",
            details={'field': 'file_ids'}
        )
    
    # Get file paths from database
    pdf_paths = []
    file_id_to_name = {}
    
    for file_id in file_ids:
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Validate it's a PDF file
        if not PDFExtractor.is_pdf_file(file_record.original_name):
            raise ValidationError(
                message=f"File is not a PDF: {file_record.original_name}",
                details={'file_id': file_id, 'filename': file_record.original_name}
            )
        
        pdf_paths.append(file_record.storage_path)
        file_id_to_name[file_record.storage_path] = file_record.original_name
    
    # Extract tables from PDFs
    extractor = PDFExtractor()
    
    try:
        result = extractor.batch_extract_tables(pdf_paths)
    except PDFExtractorError as e:
        raise ValidationError(
            message=f"PDF extraction failed: {str(e)}",
            details={'error': str(e)}
        )
    
    # Map storage paths back to original filenames
    extracted_data = {}
    for storage_path, data in result.get('extracted_data', {}).items():
        original_name = file_id_to_name.get(
            str(Path(storage_path).parent / storage_path),
            Path(storage_path).name
        )
        # Use the storage path's filename which matches what batch_extract_tables returns
        for key in result.get('extracted_data', {}).keys():
            if Path(key).name == Path(storage_path).name:
                extracted_data[original_name] = result['extracted_data'][key]
                break
    
    # Re-map the extracted data with original filenames
    final_extracted = {}
    error_messages = {}
    failed_files = []
    
    for storage_path in pdf_paths:
        storage_name = Path(storage_path).name
        original_name = file_id_to_name.get(storage_path, storage_name)
        
        if storage_name in result.get('extracted_data', {}):
            final_extracted[original_name] = result['extracted_data'][storage_name]
        elif storage_name in result.get('failed_files', []):
            failed_files.append(original_name)
            if storage_name in result.get('error_messages', {}):
                error_messages[original_name] = result['error_messages'][storage_name]
    
    # Generate table data if we have extracted data
    table_data = {}
    if final_extracted:
        table_data = extractor.get_data_table(final_extracted)
    
    return jsonify({
        'extracted_data': final_extracted,
        'failed_files': failed_files,
        'error_messages': error_messages,
        'table_data': table_data,
        'success_count': len(final_extracted),
        'fail_count': len(failed_files)
    })


@bp.route('/pdf/generate-chart', methods=['POST'])
def generate_bcell_isotype_chart():
    """
    Generate B cell isotype distribution chart from extracted PDF data.
    POST /api/pdf/generate-chart
    
    Request body:
    {
        "extracted_data": {
            "sample_name": {
                "expression": [values...],
                "unique_cdr3": [values...]
            },
            ...
        }
    }
    """
    import io
    import base64
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    
    data = request.get_json()
    if not data or 'extracted_data' not in data:
        raise ValidationError(
            message="Missing extracted_data in request body",
            details={}
        )
    
    extracted_data = data['extracted_data']
    if not extracted_data:
        raise ValidationError(
            message="No data available for chart generation",
            details={}
        )
    
    try:
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        
        isotypes = ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"]
        samples = list(extracted_data.keys())
        
        charts = []
        
        # 为每个样本生成图表
        for sample_name in samples:
            sample_data = extracted_data.get(sample_name, {})
            if not sample_data:
                continue
            
            fig = _create_bcell_chart_for_sample(sample_name, sample_data, isotypes)
            if fig:
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                charts.append({
                    'title': f'B Cell Isotype Distribution ({sample_name})',
                    'base64': base64.b64encode(buf.read()).decode('utf-8')
                })
                plt.close(fig)
        
        return jsonify({
            'charts': charts,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        raise ValidationError(
            message=f"Chart generation failed: {str(e)}",
            details={'error': str(e)}
        )


def _create_bcell_chart_for_sample(sample_name, sample_data, isotypes):
    """为单个样本创建B细胞同型分布图表 - 参考extract_bcell_isotype_final.py"""
    import matplotlib.pyplot as plt
    
    # 创建1x2布局的图表
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle(
        f"B Cell Isotype Distribution ({sample_name})",
        fontsize=18,
        fontweight="bold",
        y=0.95,
    )
    
    expression_values = sample_data.get("expression", [])
    cdr3_values = sample_data.get("unique_cdr3", [])
    
    # 确保数据长度匹配
    while len(expression_values) < len(isotypes):
        expression_values.append(0)
    while len(cdr3_values) < len(isotypes):
        cdr3_values.append(0)
    
    # 按百分比排序 - Expression
    expr_sorted = sorted(
        zip(isotypes, expression_values), key=lambda x: x[1], reverse=True
    )
    expr_isotypes, expr_values = zip(*expr_sorted) if expr_sorted else ([], [])
    
    # 按百分比排序 - Unique CDR3
    cdr3_sorted = sorted(
        zip(isotypes, cdr3_values), key=lambda x: x[1], reverse=True
    )
    cdr3_isotypes, cdr3_vals = zip(*cdr3_sorted) if cdr3_sorted else ([], [])
    
    # Expression水平条形图
    colors1 = ["#2E86AB", "#457B9D", "#5DADE2", "#85C1E9", "#AED6F1", "#D6EAF8"]
    bars1 = ax1.barh(
        range(len(expr_isotypes)),
        expr_values,
        color=colors1[:len(expr_isotypes)],
        alpha=0.8,
    )
    
    ax1.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
    ax1.set_title("Expression %", fontsize=16, fontweight="bold", pad=20)
    ax1.set_yticks(range(len(expr_isotypes)))
    ax1.set_yticklabels(expr_isotypes, fontsize=12)
    ax1.grid(axis="x", alpha=0.3, linestyle="--")
    ax1.set_facecolor("#f8f9fa")
    
    # 添加数值标签
    max_expr = max(expr_values) if expr_values else 1
    for bar, value in zip(bars1, expr_values):
        ax1.text(
            value + max_expr * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}%",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
        )
    ax1.set_xlim(0, max_expr * 1.15)
    
    # Unique CDR3水平条形图
    colors2 = ["#A23B72", "#C06C84", "#F67280", "#F8B195", "#F6B352", "#FFA07A"]
    bars2 = ax2.barh(
        range(len(cdr3_isotypes)),
        cdr3_vals,
        color=colors2[:len(cdr3_isotypes)],
        alpha=0.8,
    )
    
    ax2.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
    ax2.set_title("Unique CDR3 %", fontsize=16, fontweight="bold", pad=20)
    ax2.set_yticks(range(len(cdr3_isotypes)))
    ax2.set_yticklabels(cdr3_isotypes, fontsize=12)
    ax2.grid(axis="x", alpha=0.3, linestyle="--")
    ax2.set_facecolor("#f8f9fa")
    
    # 添加数值标签
    max_cdr3 = max(cdr3_vals) if cdr3_vals else 1
    for bar, value in zip(bars2, cdr3_vals):
        ax2.text(
            value + max_cdr3 * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}%",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
        )
    ax2.set_xlim(0, max_cdr3 * 1.15)
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.88)
    
    return fig


@bp.route('/pdf/download-charts', methods=['POST'])
def download_charts_as_zip():
    """
    Download all charts as a ZIP file.
    POST /api/pdf/download-charts
    """
    import io
    import base64
    import zipfile
    from flask import send_file
    
    data = request.get_json()
    if not data or 'charts' not in data:
        raise ValidationError(
            message="Missing charts in request body",
            details={}
        )
    
    charts = data['charts']
    if not charts:
        raise ValidationError(
            message="No charts to download",
            details={}
        )
    
    try:
        # 创建内存中的ZIP文件
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for chart in charts:
                # 生成文件名
                title = chart.get('title', 'chart')
                # 清理文件名中的非法字符
                import re
                filename = re.sub(r'[^\w\u4e00-\u9fa5\-_]', '_', title) + '.png'
                
                # 解码base64数据
                image_data = base64.b64decode(chart['base64'])
                
                # 添加到ZIP
                zip_file.writestr(filename, image_data)
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='bcell_isotype_charts.zip'
        )
        
    except Exception as e:
        logger.error(f"Error creating ZIP file: {e}")
        raise ValidationError(
            message=f"Failed to create ZIP file: {str(e)}",
            details={'error': str(e)}
        )


@bp.route('/pdf/download-images', methods=['POST'])
def download_images_as_zip():
    """
    Download all extracted images as a ZIP file.
    POST /api/pdf/download-images
    """
    import io
    import base64
    import zipfile
    from flask import send_file
    
    data = request.get_json()
    if not data or 'images' not in data:
        raise ValidationError(
            message="Missing images in request body",
            details={}
        )
    
    images = data['images']
    if not images:
        raise ValidationError(
            message="No images to download",
            details={}
        )
    
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for pdf_name, img_list in images.items():
                # 清理PDF名称作为文件夹名
                import re
                folder_name = re.sub(r'[^\w\u4e00-\u9fa5\-_]', '_', pdf_name.replace('.pdf', ''))
                
                for img_data in img_list:
                    # 生成文件名
                    filename = f"{folder_name}/image_{img_data['index']}.png"
                    
                    # 解码base64数据
                    image_bytes = base64.b64decode(img_data['image'])
                    
                    # 添加到ZIP
                    zip_file.writestr(filename, image_bytes)
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='extracted_images.zip'
        )
        
    except Exception as e:
        logger.error(f"Error creating images ZIP file: {e}")
        raise ValidationError(
            message=f"Failed to create ZIP file: {str(e)}",
            details={'error': str(e)}
        )


# =============================================================================
# PDF Image Extraction API - Requirements: 12.1-12.6
# =============================================================================

@bp.route('/pdf/images/<file_id>', methods=['GET'])
def list_pdf_images(file_id):
    """
    List all images in a PDF file with thumbnails.
    GET /api/pdf/images/{file_id}
    
    Requirements: 12.1, 12.2
    
    Returns:
    {
        "images": [
            {
                "index": 0,
                "width": 800,
                "height": 600,
                "page_number": 1,
                "thumbnail": "base64_encoded_thumbnail"
            },
            ...
        ],
        "total_count": 10
    }
    """
    from services.analysis.modules.pdf_extractor import (
        PDFExtractor,
        PDFExtractorError,
        PDFImageExtractionError
    )
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Validate it's a PDF file
    if not PDFExtractor.is_pdf_file(file_record.original_name):
        raise ValidationError(
            message=f"File is not a PDF: {file_record.original_name}",
            details={'file_id': file_id, 'filename': file_record.original_name}
        )
    
    # List images
    extractor = PDFExtractor(file_record.storage_path)
    
    try:
        images = extractor.list_images()
    except PDFExtractorError as e:
        raise ValidationError(
            message=f"Failed to list PDF images: {str(e)}",
            details={'error': str(e)}
        )
    
    return jsonify({
        'images': images,
        'total_count': len(images),
        'filename': file_record.original_name
    })


@bp.route('/pdf/extract-images', methods=['POST'])
def extract_pdf_images():
    """
    Extract images from PDF files by index.
    POST /api/pdf/extract-images
    
    Requirements: 12.3, 12.4, 12.5, 12.6
    
    Request body:
    {
        "file_ids": ["file_id1", "file_id2", ...],
        "indices": [16, -1]  // Optional, defaults to [16, -1]
    }
    
    Returns:
    {
        "extracted_images": {
            "filename.pdf": [
                {"index": 16, "image": "base64_encoded_image"},
                {"index": -1, "image": "base64_encoded_image"}
            ]
        },
        "failed_files": ["filename2.pdf"],
        "error_messages": {"filename2.pdf": "error message"}
    }
    """
    from services.analysis.modules.pdf_extractor import (
        PDFExtractor,
        PDFExtractorError,
        PDFImageExtractionError
    )
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    file_ids = data.get('file_ids', [])
    indices = data.get('indices', PDFExtractor.DEFAULT_IMAGE_INDICES)
    
    if not file_ids:
        raise ValidationError(
            message="At least one file_id is required",
            details={'field': 'file_ids'}
        )
    
    if not isinstance(indices, list):
        raise ValidationError(
            message="Indices must be a list of integers",
            details={'field': 'indices'}
        )
    
    # Get file paths from database
    pdf_paths = []
    file_id_to_name = {}
    
    for file_id in file_ids:
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Validate it's a PDF file
        if not PDFExtractor.is_pdf_file(file_record.original_name):
            raise ValidationError(
                message=f"File is not a PDF: {file_record.original_name}",
                details={'file_id': file_id, 'filename': file_record.original_name}
            )
        
        pdf_paths.append(file_record.storage_path)
        file_id_to_name[file_record.storage_path] = file_record.original_name
    
    # Extract images from PDFs
    extractor = PDFExtractor()
    
    try:
        result = extractor.batch_extract_images(pdf_paths, indices)
    except PDFExtractorError as e:
        raise ValidationError(
            message=f"PDF image extraction failed: {str(e)}",
            details={'error': str(e)}
        )
    
    # Map storage paths back to original filenames
    final_extracted = {}
    error_messages = {}
    failed_files = []
    
    for storage_path in pdf_paths:
        storage_name = Path(storage_path).name
        original_name = file_id_to_name.get(storage_path, storage_name)
        
        if storage_name in result.get('extracted_images', {}):
            # Convert tuple format to dict format for JSON response
            images_data = result['extracted_images'][storage_name]
            final_extracted[original_name] = [
                {'index': idx, 'image': img_base64}
                for idx, img_base64 in images_data
            ]
        elif storage_name in result.get('failed_files', []):
            failed_files.append(original_name)
            if storage_name in result.get('error_messages', {}):
                error_messages[original_name] = result['error_messages'][storage_name]
    
    return jsonify({
        'extracted_images': final_extracted,
        'failed_files': failed_files,
        'error_messages': error_messages,
        'indices_used': indices,
        'success_count': len(final_extracted),
        'fail_count': len(failed_files)
    })


# =============================================================================
# PDF Image Extraction API - Requirements: 8.1, 8.2, 8.3, 8.6, 8.7, 8.8, 8.9, 8.10
# =============================================================================

@bp.route('/pdf/upload', methods=['POST'])
def upload_pdf():
    """
    Upload a PDF file for image extraction.
    POST /api/pdf/upload
    
    Requirements: 8.1, 8.2
    
    Returns:
    {
        "file_id": "uuid",
        "filename": "report.pdf",
        "page_count": 10,
        "file_size": 1024000
    }
    """
    from services.pdf_extractor import PDFExtractorService
    
    # Check if file is present
    if 'file' not in request.files:
        raise ValidationError(
            message="No file provided in request",
            details={'field': 'file'}
        )
    
    file = request.files['file']
    
    if file.filename == '':
        raise ValidationError(
            message="No file selected",
            details={'field': 'file'}
        )
    
    filename = file.filename
    
    # Validate PDF extension
    if not filename.lower().endswith('.pdf'):
        raise FileFormatInvalidError(
            message=f"File must be a PDF",
            details={'provided_extension': Path(filename).suffix}
        )
    
    # Read file content
    file_content = file.read()
    
    if len(file_content) == 0:
        raise ValidationError(
            message="Uploaded file is empty",
            details={'field': 'file'}
        )
    
    # Check file size
    pdf_max_size = current_app.config.get('PDF_MAX_SIZE', 50 * 1024 * 1024)
    if len(file_content) > pdf_max_size:
        raise ValidationError(
            message=f"PDF file too large. Maximum size: {pdf_max_size / (1024*1024)}MB",
            details={'file_size': len(file_content), 'max_size': pdf_max_size}
        )
    
    # Generate unique file ID and storage path
    file_id = str(uuid.uuid4())
    storage_filename = f"{file_id}.pdf"
    storage_path = Path(current_app.config['UPLOAD_FOLDER']) / storage_filename
    
    # Save file to disk
    try:
        with open(storage_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        raise StorageError(
            message=f"Failed to save file: {str(e)}",
            details={'filename': filename}
        )
    
    # Get PDF info
    try:
        pdf_info = PDFExtractorService.get_pdf_info(str(storage_path))
    except Exception as e:
        # Clean up file if info extraction fails
        if storage_path.exists():
            storage_path.unlink()
        raise FileParseError(
            message=f"Failed to read PDF: {str(e)}",
            details={'filename': filename}
        )
    
    # Get project name from form data (default to 'default')
    project = request.form.get('project', 'default') or 'default'
    
    # Create file record in database
    file_record = File(
        id=file_id,
        name=storage_filename,
        original_name=filename,
        size=len(file_content),
        storage_path=str(storage_path),
        mime_type='application/pdf',
        columns=[],  # PDFs don't have columns
        row_count=pdf_info['page_count'],
        project=project
    )
    
    db.session.add(file_record)
    db.session.commit()
    
    return jsonify({
        'file_id': file_id,
        'filename': filename,
        'page_count': pdf_info['page_count'],
        'file_size': len(file_content),
        'metadata': pdf_info.get('metadata', {}),
        'project': project
    }), 201


@bp.route('/pdf/extract', methods=['POST'])
def extract_pdf_to_folders():
    """
    Extract images from a PDF file.
    POST /api/pdf/extract
    
    Requirements: 8.6, 8.7, 8.8, 8.9, 8.10
    
    Request body:
    {
        "file_id": "uuid",
        "output_path": "/path/to/output",
        "sample_mapping": {
            "0": "Sample1",
            "1": "Sample2"
        }
    }
    
    Returns:
    {
        "success": true,
        "samples": {
            "Sample1": 5,
            "Sample2": 3
        },
        "total_images": 8,
        "output_path": "/path/to/output",
        "errors": []
    }
    """
    from services.pdf_extractor import PDFExtractorService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={}
        )
    
    file_id = data.get('file_id')
    output_path = data.get('output_path')
    sample_mapping = data.get('sample_mapping', {})
    
    if not file_id:
        raise ValidationError(
            message="file_id is required",
            details={'field': 'file_id'}
        )
    
    if not output_path:
        raise ValidationError(
            message="output_path is required",
            details={'field': 'output_path'}
        )
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Validate it's a PDF
    if not file_record.original_name.lower().endswith('.pdf'):
        raise ValidationError(
            message="File is not a PDF",
            details={'file_id': file_id, 'filename': file_record.original_name}
        )
    
    # Convert sample_mapping keys to integers
    sample_mapping_int = {}
    if sample_mapping:
        try:
            sample_mapping_int = {int(k): v for k, v in sample_mapping.items()}
        except (ValueError, TypeError):
            raise ValidationError(
                message="sample_mapping keys must be page numbers (integers)",
                details={'sample_mapping': sample_mapping}
            )
    
    # Extract images
    try:
        result = PDFExtractorService.extract_images(
            pdf_path=file_record.storage_path,
            output_path=output_path,
            sample_mapping=sample_mapping_int if sample_mapping_int else None
        )
        
        return jsonify({
            'success': result.success,
            'samples': result.samples,
            'total_images': result.total_images,
            'output_path': result.output_path,
            'errors': result.errors
        })
        
    except FileParseError as e:
        raise
    except Exception as e:
        raise FileParseError(
            message=f"Failed to extract images: {str(e)}",
            details={
                'file_id': file_id,
                'error_type': type(e).__name__
            }
        )


@bp.route('/pdf/samples/<file_id>', methods=['GET'])
def detect_pdf_samples(file_id):
    """
    Detect sample names from a PDF file.
    GET /api/pdf/samples/{file_id}
    
    Requirements: 8.8
    
    Returns:
    {
        "samples": ["Sample1", "Sample2", "Sample3"]
    }
    """
    from services.pdf_extractor import PDFExtractorService
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Validate it's a PDF
    if not file_record.original_name.lower().endswith('.pdf'):
        raise ValidationError(
            message="File is not a PDF",
            details={'file_id': file_id, 'filename': file_record.original_name}
        )
    
    # Detect samples
    try:
        samples = PDFExtractorService.detect_samples(file_record.storage_path)
        
        return jsonify({
            'samples': samples
        })
        
    except FileParseError as e:
        raise
    except Exception as e:
        raise FileParseError(
            message=f"Failed to detect samples: {str(e)}",
            details={
                'file_id': file_id,
                'error_type': type(e).__name__
            }
        )

