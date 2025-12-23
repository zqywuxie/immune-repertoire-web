import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os
from matplotlib import rcParams
from typing import Dict, List, Any
import io
import base64

# 设置中文字体
rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
rcParams['axes.unicode_minus'] = False

class PPTService:
    """Service for generating PPT-compatible charts and modules"""
    
    @staticmethod
    def create_sequencing_depth_module(samples: List[str], data: Dict[str, List[float]]):
        """
        创建适合PPT插入的测序深度差异小模块
        返回紧凑的水平条形图，显示相对于最小样本的百分比差异
        """
        
        df = pd.DataFrame(data, index=samples)
        
        # 计算相对于最小值的百分比
        min_values = df.min()
        percentage_diff = df.div(min_values) * 100
        
        # 创建紧凑图表 (4:3比例，适合PPT)
        fig, ax = plt.subplots(1, 1, figsize=(4, 3))
        fig.patch.set_facecolor('none')  # 透明背景
        ax.set_facecolor('none')  # 透明背景
        
        # 设置颜色
        colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c']  # 蓝、绿、橙、红
        
        # 创建水平条形图
        y_pos = np.arange(len(samples))
        height = 0.25
        
        for i, (metric, color) in enumerate(zip(data.keys(), colors[:len(data.keys())])):
            values = percentage_diff[metric]
            bars = ax.barh(y_pos + i*height, values, height, 
                          label=metric, color=color, alpha=0.8)
            
            # 添加百分比标签
            for j, bar in enumerate(bars):
                width = bar.get_width()
                if width > 100:  # 在条形右侧标注
                    ax.text(width + 1, bar.get_y() + bar.get_height()/2,
                           f'+{width-100:.1f}%', ha='left', va='center',
                           fontsize=9, fontweight='bold')
                else:  # 基准样本
                    ax.text(width + 1, bar.get_y() + bar.get_height()/2,
                           '基准', ha='left', va='center',
                           fontsize=9, fontweight='bold', color='red')
        
        # 设置图表样式
        ax.set_yticks(y_pos + height * (len(data.keys()) - 1) / 2)
        ax.set_yticklabels(samples, fontsize=10)
        ax.set_xlabel('Relative Percentage (%)', fontsize=10)
        ax.set_title('Sequencing Depth Differences', fontsize=12, fontweight='bold', pad=5)
        
        # 添加基准线
        ax.axvline(x=100, color='red', linestyle='--', alpha=0.7, linewidth=1)
        
        # 设置x轴范围
        ax.set_xlim(95, percentage_diff.values.max() + 5)
        
        # 简化图例
        ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        
        # 移除顶部和右侧边框
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # 调整布局
        plt.tight_layout()
        
        return fig
    
    @staticmethod
    def create_summary_table(samples: List[str], data: Dict[str, List[float]]):
        """
        创建简化的摘要表格模块
        """
        df = pd.DataFrame(data, index=samples)
        
        # 计算相对于最小值的百分比
        min_values = df.min()
        percentage_diff = df.div(min_values) * 100
        
        # 创建表格图
        fig, ax = plt.subplots(1, 1, figsize=(5, 2.5))
        fig.patch.set_facecolor('none')  # 透明背景
        ax.set_facecolor('none')  # 透明背景
        
        # 准备表格数据
        table_data = []
        for sample in samples:
            row = [sample]
            for metric in data.keys():
                diff = percentage_diff.loc[sample, metric] - 100
                if diff > 0:
                    row.append(f'+{diff:.1f}%')
                else:
                    row.append('基准')
            table_data.append(row)
        
        # 创建表格
        table = ax.table(cellText=table_data,
                        colLabels=['Sample'] + list(data.keys()),
                        cellLoc='center',
                        loc='center',
                        colWidths=[0.2] + [0.8/len(data.keys())] * len(data.keys()))
        
        # 设置表格样式
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        # 设置颜色
        for i in range(len(data.keys()) + 1):
            table[(0, i)].set_facecolor('#34495e')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # 突出显示基准样本
        for j in range(1, len(data.keys()) + 1):
            table[(1, j)].set_text_props(color='red', weight='bold')
        
        # 隐藏坐标轴
        ax.axis('off')
        
        # 添加标题
        ax.set_title('Sequencing Depth Differences', fontsize=12, fontweight='bold', pad=5)
        
        plt.tight_layout()
        
        return fig
    
    @staticmethod
    def fig_to_base64(fig):
        """Convert matplotlib figure to base64 string"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=300, bbox_inches='tight',
                   facecolor='none', edgecolor='none', transparent=True)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig)
        return img_base64
    
    @staticmethod
    def generate_sequencing_depth_ppt(data: Dict[str, Any]):
        """Generate PPT module for sequencing depth analysis"""
        try:
            # Extract samples and metrics from data
            samples = data.get('samples', [])
            metrics = data.get('metrics', {})
            
            if not samples or not metrics:
                raise ValueError("No samples or metrics provided")
            
            # Generate bar chart
            bar_fig = PPTService.create_sequencing_depth_module(samples, metrics)
            bar_base64 = PPTService.fig_to_base64(bar_fig)
            
            # Generate table
            table_fig = PPTService.create_summary_table(samples, metrics)
            table_base64 = PPTService.fig_to_base64(table_fig)
            
            return {
                'bar_chart': f'data:image/png;base64,{bar_base64}',
                'table': f'data:image/png;base64,{table_base64}',
                'success': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
