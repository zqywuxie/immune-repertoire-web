"""
API routes for Statistical Analysis.
Provides endpoints for group comparison and P-value calculation.
"""

import uuid
import logging
import pandas as pd
import io
from flask import Blueprint, request, jsonify, current_app
from typing import Dict, Any

from services.statistical_analysis_service import get_statistical_analysis_service
from services.file_parser import FileParserService
from models.database import db, File
from exceptions import ValidationError, FileNotFoundError as AppFileNotFoundError

logger = logging.getLogger(__name__)

statistical_bp = Blueprint('statistical', __name__, url_prefix='/api/statistical')


@statistical_bp.route('/analyze', methods=['POST'])
def analyze_groups():
    """
    对分组数据进行统计分析
    
    POST /api/statistical/analyze
    
    Request Body:
    {
        "file_id": "uuid",
        "value_column": "expression",
        "group_column": "category",
        "group_order": ["Baseline", "0-1h", "24h", "48h"],  // optional
        "alpha": 0.05  // optional
    }
    
    Returns:
        统计分析结果，包括Kruskal-Wallis检验和事后比较
    """
    try:
        data = request.get_json()
        
        file_id = data.get('file_id')
        value_column = data.get('value_column', 'expression')
        group_column = data.get('group_column', 'category')
        group_order = data.get('group_order')
        alpha = data.get('alpha', 0.05)
        
        if not file_id:
            raise ValidationError(
                message="file_id is required",
                details={'field': 'file_id'}
            )
        
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(file_record.storage_path, 'rb') as f:
            file_content = f.read()
        
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        service = get_statistical_analysis_service()
        results = service.analyze_groups(
            data=df,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order,
            alpha=alpha
        )
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in statistical analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/boxplot', methods=['POST'])
def create_boxplot():
    """
    创建箱线图
    
    POST /api/statistical/boxplot
    
    Request Body:
    {
        "file_id": "uuid",
        "value_column": "expression",
        "group_column": "category",
        "group_order": ["Baseline", "0-1h", "24h", "48h"],
        "title": "Expression by Time Point",
        "palette": {"Baseline": "#4C72B0", ...}
    }
    
    Returns:
        Base64编码的箱线图图片
    """
    try:
        data = request.get_json()
        
        file_id = data.get('file_id')
        value_column = data.get('value_column', 'expression')
        group_column = data.get('group_column', 'category')
        group_order = data.get('group_order')
        title = data.get('title')
        palette = data.get('palette')
        
        if not file_id:
            raise ValidationError(
                message="file_id is required",
                details={'field': 'file_id'}
            )
        
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(file_record.storage_path, 'rb') as f:
            file_content = f.read()
        
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        service = get_statistical_analysis_service()
        image_base64 = service.create_boxplot(
            data=df,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order,
            title=title,
            palette=palette
        )
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'image': image_base64
        })
        
    except Exception as e:
        logger.error(f"Error creating boxplot: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/analyze-multiple', methods=['POST'])
def analyze_multiple():
    """
    分析多个数据文件
    
    POST /api/statistical/analyze-multiple
    
    Request Body:
    {
        "files": [
            {"file_id": "uuid1", "name": "Blood"},
            {"file_id": "uuid2", "name": "Lung"}
        ],
        "value_column": "expression",
        "group_column": "category",
        "group_order": ["Baseline", "0-1h", "24h", "48h"]
    }
    
    Returns:
        所有文件的统计分析结果和汇总
    """
    try:
        data = request.get_json()
        
        files = data.get('files', [])
        value_column = data.get('value_column', 'expression')
        group_column = data.get('group_column', 'category')
        group_order = data.get('group_order')
        
        if not files:
            raise ValidationError(
                message="files list is required",
                details={'field': 'files'}
            )
        
        datasets = {}
        for file_info in files:
            file_id = file_info.get('file_id')
            name = file_info.get('name', file_id)
            
            file_record = File.query.get(file_id)
            if not file_record:
                logger.warning(f"File not found: {file_id}")
                continue
            
            with open(file_record.storage_path, 'rb') as f:
                file_content = f.read()
            
            df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
            datasets[name] = df
        
        if not datasets:
            raise ValidationError(
                message="No valid files found",
                details={'files': files}
            )
        
        service = get_statistical_analysis_service()
        results = service.analyze_multiple_datasets(
            datasets=datasets,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order
        )
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in multiple file analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/summary-boxplot', methods=['POST'])
def create_summary_boxplot():
    """
    创建汇总箱线图
    
    POST /api/statistical/summary-boxplot
    
    Request Body:
    {
        "files": [
            {"file_id": "uuid1", "name": "Blood"},
            {"file_id": "uuid2", "name": "Lung"}
        ],
        "value_column": "expression",
        "group_column": "category",
        "group_order": ["Baseline", "0-1h", "24h", "48h"],
        "title": "All Tissues - Expression",
        "palette": {...}
    }
    
    Returns:
        Base64编码的汇总箱线图
    """
    try:
        data = request.get_json()
        
        files = data.get('files', [])
        value_column = data.get('value_column', 'expression')
        group_column = data.get('group_column', 'category')
        group_order = data.get('group_order')
        title = data.get('title', 'Summary')
        palette = data.get('palette')
        
        if not files:
            raise ValidationError(
                message="files list is required",
                details={'field': 'files'}
            )
        
        datasets = {}
        for file_info in files:
            file_id = file_info.get('file_id')
            name = file_info.get('name', file_id)
            
            file_record = File.query.get(file_id)
            if not file_record:
                continue
            
            with open(file_record.storage_path, 'rb') as f:
                file_content = f.read()
            
            df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
            datasets[name] = df
        
        if not datasets:
            raise ValidationError(
                message="No valid files found",
                details={'files': files}
            )
        
        service = get_statistical_analysis_service()
        image_base64 = service.create_summary_boxplot(
            datasets=datasets,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order,
            title=title,
            palette=palette
        )
        
        return jsonify({
            'success': True,
            'image': image_base64
        })
        
    except Exception as e:
        logger.error(f"Error creating summary boxplot: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/parse-file/<file_id>', methods=['GET'])
def parse_file_columns(file_id):
    """
    解析已上传文件的列名
    
    GET /api/statistical/parse-file/{file_id}
    
    Returns:
        列名列表和分组值
    """
    try:
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # 读取文件内容
        storage_path = current_app.config['UPLOAD_FOLDER'] / file_record.storage_name
        if not storage_path.exists():
            raise AppFileNotFoundError(
                message=f"File not found on disk: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        
        df, columns, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        # 检测分组
        groups = []
        group_cols = ['category', 'group', 'sample_group', 'condition', 'timepoint']
        
        for col in group_cols:
            if col in df.columns:
                groups = df[col].dropna().unique().tolist()
                break
        
        return jsonify({
            'success': True,
            'columns': columns,
            'groups': groups
        })
        
    except Exception as e:
        logger.error(f"Error parsing file columns: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/parse-columns', methods=['POST'])
def parse_columns():
    """
    解析上传文件的列名
    
    POST /api/statistical/parse-columns
    
    Request Body (multipart/form-data):
    - file: CSV/Excel文件
    
    Returns:
        列名列表和分组值（如果检测到分组列）
    """
    try:
        if 'file' not in request.files:
            raise ValidationError(
                message="No file provided",
                details={'field': 'file'}
            )
        
        file = request.files['file']
        file_content = file.read()
        
        df, columns, _ = FileParserService.parse_file(file_content, file.filename)
        
        # Try to detect groups from common group column names
        groups = []
        group_cols = ['category', 'group', 'sample_group', 'condition', 'timepoint']
        
        for col in group_cols:
            if col in df.columns:
                groups = df[col].dropna().unique().tolist()
                break
        
        return jsonify({
            'success': True,
            'columns': columns,
            'groups': groups
        })
        
    except Exception as e:
        logger.error(f"Error parsing columns: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/analyze-batch', methods=['POST'])
def analyze_batch():
    """
    批量分析多个上传的数据文件，支持全局P值校正
    
    POST /api/statistical/analyze-batch
    
    Request Body (multipart/form-data):
    - files: 多个CSV/Excel文件
    - value_column: 数值列名
    - group_column: 分组列名
    - group_order: 分组顺序（JSON字符串）
    - global_correction: 是否进行全局校正 ('true'/'false')
    
    Returns:
        所有数据集的统计分析结果和箱线图
    """
    try:
        import json
        
        value_column = request.form.get('value_column', 'expression')
        group_column = request.form.get('group_column', 'category')
        group_order_str = request.form.get('group_order')
        global_correction = request.form.get('global_correction', 'false').lower() == 'true'
        file_ids_str = request.form.get('file_ids')
        
        group_order = None
        if group_order_str:
            group_order = json.loads(group_order_str)
        
        # 解析所有文件 - 支持上传文件或使用已上传文件ID
        datasets = {}
        
        if file_ids_str:
            # 使用已上传文件的ID
            file_ids = json.loads(file_ids_str)
            for file_id in file_ids:
                file_record = File.query.get(file_id)
                if not file_record:
                    continue
                storage_path = current_app.config['UPLOAD_FOLDER'] / file_record.storage_name
                if not storage_path.exists():
                    continue
                with open(storage_path, 'rb') as f:
                    file_content = f.read()
                df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
                name = file_record.original_name.rsplit('.', 1)[0]
                datasets[name] = df
        else:
            # 上传新文件
            files = request.files.getlist('files')
            if not files:
                raise ValidationError(
                    message="No files or file_ids provided",
                    details={'field': 'files'}
                )
            for file in files:
                file_content = file.read()
                df, _, _ = FileParserService.parse_file(file_content, file.filename)
                name = file.filename.rsplit('.', 1)[0]
                datasets[name] = df
        
        if not datasets:
            raise ValidationError(
                message="No valid files found",
                details={'field': 'files'}
            )
        
        service = get_statistical_analysis_service()
        
        # 分析所有数据集
        batch_results = service.analyze_multiple_datasets(
            datasets=datasets,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order,
            global_correction=global_correction
        )
        
        # 为每个数据集生成箱线图
        images = {}
        for name, df in datasets.items():
            image_base64 = service.create_boxplot(
                data=df,
                value_column=value_column,
                group_column=group_column,
                group_order=group_order,
                title=name
            )
            images[name] = image_base64
        
        return jsonify({
            'success': True,
            'results': batch_results['results'],
            'summary': batch_results['summary'],
            'correction_mode': batch_results['correction_mode'],
            'images': images
        })
        
    except Exception as e:
        logger.error(f"Error in batch analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statistical_bp.route('/analyze-direct', methods=['POST'])
def analyze_direct():
    """
    直接分析上传的数据（不保存到数据库）
    
    POST /api/statistical/analyze-direct
    
    Request Body (multipart/form-data):
    - file: CSV文件 (或 file_id: 已上传文件的ID)
    - value_column: 数值列名
    - group_column: 分组列名
    - group_order: 分组顺序（JSON字符串）
    
    Returns:
        统计分析结果和箱线图
    """
    try:
        value_column = request.form.get('value_column', 'expression')
        group_column = request.form.get('group_column', 'category')
        group_order_str = request.form.get('group_order')
        title = request.form.get('title')
        file_id = request.form.get('file_id')
        
        group_order = None
        if group_order_str:
            import json
            group_order = json.loads(group_order_str)
        
        # 支持两种方式：上传新文件或使用已上传文件的ID
        if file_id:
            # 使用已上传文件的ID
            file_record = File.query.get(file_id)
            if not file_record:
                raise AppFileNotFoundError(
                    message=f"File not found: {file_id}",
                    details={'file_id': file_id}
                )
            storage_path = current_app.config['UPLOAD_FOLDER'] / file_record.storage_name
            if not storage_path.exists():
                raise AppFileNotFoundError(
                    message=f"File not found on disk: {file_id}",
                    details={'file_id': file_id}
                )
            with open(storage_path, 'rb') as f:
                file_content = f.read()
            df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        elif 'file' in request.files:
            # 上传新文件
            file = request.files['file']
            file_content = file.read()
            df, _, _ = FileParserService.parse_file(file_content, file.filename)
        else:
            raise ValidationError(
                message="No file or file_id provided",
                details={'field': 'file'}
            )
        
        service = get_statistical_analysis_service()
        
        results = service.analyze_groups(
            data=df,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order
        )
        
        image_base64 = service.create_boxplot(
            data=df,
            value_column=value_column,
            group_column=group_column,
            group_order=group_order,
            title=title
        )
        
        return jsonify({
            'success': True,
            'results': results,
            'image': image_base64
        })
        
    except Exception as e:
        logger.error(f"Error in direct analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
