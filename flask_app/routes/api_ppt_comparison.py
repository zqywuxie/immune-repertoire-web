"""
PPT热图对比API路由
提供热图扫描和对比PPT生成的API端点
"""

import os
import uuid
import logging
import tempfile
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

from flask_app.services.ppt_comparison_service import PPTComparisonService
from flask_app.exceptions import ValidationError

logger = logging.getLogger(__name__)

# 创建蓝图
ppt_comparison_bp = Blueprint('ppt_comparison', __name__, url_prefix='/api/ppt-comparison')

# 初始化服务
comparison_service = PPTComparisonService()

# 会话存储（用于临时存储PPT模板）
ppt_sessions = {}


@ppt_comparison_bp.route('/scan-heatmaps', methods=['POST'])
def scan_heatmaps():
    """
    扫描指定路径下的热图文件
    
    Request Body:
        {
            "path": "/path/to/heatmaps"
        }
    
    Response:
        {
            "success": true,
            "heatmaps": [
                {
                    "filename": "heatmap_expression.png",
                    "filepath": "/full/path/to/file",
                    "metric": "expression",
                    "metric_display": "Expression Sharing",
                    "image_data": "base64_encoded_image"
                },
                ...
            ]
        }
    """
    try:
        data = request.get_json()
        
        if not data or 'path' not in data:
            return jsonify({
                'success': False,
                'error': '请提供文件夹路径'
            }), 400
        
        folder_path = data['path']
        
        # 扫描热图
        heatmaps = comparison_service.scan_heatmap_folder(folder_path)
        
        return jsonify({
            'success': True,
            'heatmaps': heatmaps,
            'count': len(heatmaps)
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        logger.error(f"扫描热图失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'扫描失败: {str(e)}'
        }), 500


@ppt_comparison_bp.route('/generate', methods=['POST'])
def generate_comparison_ppt():
    """
    生成对比布局的PPT
    
    Request Body:
        {
            "session_id": "uuid",
            "methods": [
                {
                    "name": "方法A",
                    "heatmaps": [...]
                },
                {
                    "name": "方法B",
                    "heatmaps": [...]
                }
            ],
            "layout_mode": "auto"  // 可选: 'auto', 'single_row', 'grid'
        }
    
    Response:
        PPT文件下载
    """
    try:
        data = request.get_json()
        
        if not data or 'session_id' not in data or 'methods' not in data:
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        session_id = data['session_id']
        methods = data['methods']
        layout_mode = data.get('layout_mode', 'auto')  # 默认自动选择
        
        # 验证布局模式
        if layout_mode not in ['auto', 'single_row', 'grid']:
            return jsonify({
                'success': False,
                'error': f'无效的布局模式: {layout_mode}，支持的模式: auto, single_row, grid'
            }), 400
        
        # 检查会话
        if session_id not in ppt_sessions:
            return jsonify({
                'success': False,
                'error': 'PPT会话不存在或已过期'
            }), 404
        
        template_path = ppt_sessions[session_id]['template_path']
        
        # 验证方法数量
        if len(methods) < 2:
            return jsonify({
                'success': False,
                'error': '至少需要2个对比方法'
            }), 400
        
        # 生成输出文件路径
        output_filename = f'comparison_heatmap_{uuid.uuid4().hex[:8]}.pptx'
        output_path = os.path.join(tempfile.gettempdir(), output_filename)
        
        # 生成对比PPT
        result_path = comparison_service.generate_comparison_ppt(
            template_ppt_path=template_path,
            methods=methods,
            output_path=output_path,
            layout_mode=layout_mode
        )
        
        # 返回文件
        return send_file(
            result_path,
            as_attachment=True,
            download_name='comparison_heatmap.pptx',
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
        
    except Exception as e:
        logger.error(f"生成对比PPT失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'生成失败: {str(e)}'
        }), 500


def register_ppt_session(session_id: str, template_path: str):
    """
    注册PPT会话（供其他模块调用）
    
    Args:
        session_id: 会话ID
        template_path: PPT模板路径
    """
    ppt_sessions[session_id] = {
        'template_path': template_path
    }
    logger.info(f"注册PPT会话: {session_id}")


def cleanup_ppt_session(session_id: str):
    """
    清理PPT会话
    
    Args:
        session_id: 会话ID
    """
    if session_id in ppt_sessions:
        del ppt_sessions[session_id]
        logger.info(f"清理PPT会话: {session_id}")
