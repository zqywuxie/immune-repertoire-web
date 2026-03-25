#!/usr/bin/env python3
"""
鐙珛鐑浘鐢熸垚鍛戒护琛屽伐鍏?- 浜や簰寮忕増鏈?鐢ㄤ簬Linux鐜涓嬫壒閲忕敓鎴愬厤鐤粍搴撶浉浼煎害鐑浘

鍔熻兘鐗圭偣:
    - 鎸夐摼鍒嗙粍鐢熸垚鐑浘锛堟瘡涓摼鍗曠嫭涓€涓儹鍥撅級
    - 鑷姩鎵цCDR3鍒嗘瀽瀵煎嚭
    - 鍙€夌敓鎴愮綉椤电増鍒嗕韩鎶ュ憡锛堥粯璁ゅ叧闂級
    - 涓庣綉椤电増淇濇寔涓€鑷寸殑鍒嗘瀽閫昏緫

浣跨敤鏂规硶:
    # 浜や簰妯″紡锛堟帹鑽愶級
    python standalone_heatmap_cli.py -i /path/to/samples -o /path/to/output --interactive
    
    # 鎵归噺妯″紡
    python standalone_heatmap_cli.py -i /path/to/samples -o /path/to/output
    
鍙傛暟璇存槑:
    --input, -i: 鏍锋湰鏂囦欢澶硅矾寰勶紙鍖呭惈CSV鎴朇SV.GZ鏂囦欢锛?    --output, -o: 杈撳嚭鐩綍璺緞
    --interactive: 鍚敤浜や簰妯″紡锛屽厑璁哥敤鎴烽€夋嫨鏍锋湰鍜屽瓧娈?    --cdr3-col: CDR3搴忓垪鍒楀悕锛堥粯璁よ嚜鍔ㄦ娴嬶級
    --copy-col: 鎷疯礉鏁板垪鍚嶏紙榛樿鑷姩妫€娴嬶級
    --mode: 妯″紡 chain/traditional锛堥粯璁よ嚜鍔ㄦ娴嬶級
    --chains: 閾剧被鍨嬶紝閫楀彿鍒嗛殧锛堝 IGH,IGK,IGL锛?    --title: 鐑浘鏍囬
    --show-values: 鍦ㄧ儹鍥句笂鏄剧ず鏁板€硷紙榛樿寮€鍚級
"""

import os
import sys
import argparse
import logging
import re
import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict
import json
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 鏃燝UI鍚庣
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr
import gzip

# 閰嶇疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_header(text: str):
    """鎵撳嵃鏍囬"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_info(text: str):
    """鎵撳嵃淇℃伅"""
    print(f"[INFO] {text}")


def print_success(text: str):
    """鎵撳嵃鎴愬姛淇℃伅"""
    print(f"[OK] {text}")


def print_warning(text: str):
    """鎵撳嵃璀﹀憡"""
    print(f"[!] {text}")


def print_error(text: str):
    """鎵撳嵃閿欒"""
    print(f"[ERROR] {text}")


def format_similarity_value(value) -> str:
    """
    鏍规嵁鏁板€煎ぇ灏忔櫤鑳芥牸寮忓寲鐩镐技搴﹀€笺€?    
    鏍煎紡鍖栬鍒?
    - value >= 0.01: 3浣嶅皬鏁?(濡?"0.123")
    - 0.001 <= value < 0.01: 4浣嶅皬鏁?(濡?"0.0012")
    - 0.0001 <= value < 0.001: 5浣嶅皬鏁?(濡?"0.00012")
    - value < 0.0001 涓?value > 0: 绉戝璁℃暟娉?(濡?"1.2e-05")
    - value == 1.0: 鏄剧ず "1.000"
    - value == 0: 鏄剧ず "0"
    - NaN/Infinity/None: 鏄剧ず "-"
    """
    import math
    
    # Handle None
    if value is None:
        return "-"
    
    # Handle NaN and Infinity
    if isinstance(value, float):
        if math.isnan(value):
            return "-"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
    
    # Convert to float for consistent handling
    try:
        val = float(value)
    except (ValueError, TypeError):
        return "-"
    
    # Handle exact 0
    if val == 0:
        return "0"
    
    # Handle exact 1 (common for diagonal elements)
    if val == 1.0:
        return "1.000"
    
    # Get absolute value for threshold comparison
    abs_val = abs(val)
    
    # Apply formatting rules based on magnitude
    if abs_val >= 0.01:
        return f"{val:.3f}"
    elif abs_val >= 0.001:
        return f"{val:.4f}"
    elif abs_val >= 0.0001:
        return f"{val:.5f}"
    else:
        return f"{val:.2e}"


class StandaloneHeatmapGenerator:
    """鐙珛鐑浘鐢熸垚鍣?- 鏀寔浜や簰妯″紡"""
    
    # 鏀寔鐨勬枃浠舵墿灞曞悕
    SUPPORTED_EXTENSIONS = ['.csv', '.tsv', '.txt', '.csv.gz']
    
    # 閾剧被鍨?    CHAIN_TYPES = ['TRA', 'TRB', 'TRG', 'TRD', 'IGH', 'IGK', 'IGL', 'TCRA', 'TCRB', 'TCRG', 'TCRD']
    
    # CDR3鍒楀悕妯″紡
    CDR3_PATTERNS = ['cdr3', 'cdr3(pep)', 'cdr3_pep', 'cdr3_aa', 'aminoacid', 'amino_acid', 'aa_sequence', 'sequence']
    
    # 鎷疯礉鏁板垪鍚嶆ā寮?    COPY_PATTERNS = ['copy', 'copies', 'count', 'counts', 'reads', 'freq', 'frequency', 'abundance', 'expression']
    
    # 鐩镐技搴︽寚鏍?    METRICS = ['expression_sharing', 'morisita_horn', 'cdr3_sharing', 'r2_inner', 'r2_outer', 'sorensen']
    
    METRIC_NAMES = {
        'expression_sharing': 'Expression Sharing',
        'morisita_horn': 'Morisita-Horn Index',
        'cdr3_sharing': 'Unique CDR3 Sharing',
        'r2_inner': 'R虏 Inner',
        'r2_outer': 'R虏 Outer',
        'sorensen': 'Sorensen-Dice Index'
    }
    
    # Default fixed color scheme
    DEFAULT_COLOR_SCHEME = 'RdYlBu_r'
    
    def __init__(self, input_dir: str, output_dir: str, interactive: bool = False, **kwargs):
        """
        鍒濆鍖?        
        Args:
            input_dir: 杈撳叆鐩綍
            output_dir: 杈撳嚭鐩綍锛堝鏋滀负None锛屽垯鍦ㄨ緭鍏ョ洰褰曚笅鍒涘缓锛?            interactive: 鏄惁鍚敤浜や簰妯″紡
            **kwargs: 鍏朵粬鍙傛暟锛坈dr3_col, copy_col, mode, chains, title, color, show_values, export_cdr3, web_report, report_scan_path锛?        """
        self.input_dir = Path(input_dir)
        
        # Normalize output root to a single shared_analysis directory.
        if output_dir is None:
            base_output_dir = self.input_dir
        else:
            base_output_dir = Path(output_dir)
        
        # Avoid nesting if user already points to shared_analysis.
        if base_output_dir.name.lower() == 'shared_analysis':
            self.output_dir = base_output_dir
        else:
            self.output_dir = base_output_dir / 'shared_analysis'
        
        # Output structure: heatmap PNGs + metric CSVs.
        self.heatmap_dir = self.output_dir / 'heatmap'
        self.metric_dir = self.output_dir / 'metric'
        self.heatmap_dir.mkdir(parents=True, exist_ok=True)
        self.metric_dir.mkdir(parents=True, exist_ok=True)
        
        self.interactive = interactive
        self.cdr3_col = kwargs.get('cdr3_col')
        self.copy_col = kwargs.get('copy_col')
        self.mode = kwargs.get('mode', 'auto')
        self.chains = kwargs.get('chains', [])
        self.title = kwargs.get('title', 'Similarity Heatmap')
        # 鍥哄畾浣跨敤榛樿棰滆壊鏂规
        self.color_scheme = self.DEFAULT_COLOR_SCHEME
        self.show_values = kwargs.get('show_values', True)
        self.export_cdr3 = kwargs.get('export_cdr3', False)
        self.generate_web_report = kwargs.get('web_report', False)
        self.report_scan_path = kwargs.get('report_scan_path')
        
        # 瀛樺偍鎵弿缁撴灉
        self.scanned_samples: Dict[str, List[Path]] = {}
        self.detected_chains: Set[str] = set()
        self.selected_samples: List[str] = []
        self.sample_display_names: Dict[str, str] = {}  # 鏍锋湰閲嶅懡鍚嶆槧灏?        
        print_info(f"杈撳叆鐩綍: {self.input_dir}")
        print_info(f"杈撳嚭鐩綍: {self.output_dir}")
    
    def scan_samples(self) -> Dict[str, List[Path]]:
        """鎵弿鏍锋湰鏂囦欢"""
        print_info("寮€濮嬫壂鎻忔牱鏈枃浠?..")
        
        samples = {}
        chains_found = set()
        
        for file_path in self.input_dir.rglob('*'):
            if not file_path.is_file():
                continue
            
            # 妫€鏌ユ枃浠舵墿灞曞悕
            if not any(str(file_path).lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS):
                continue
            
            # 鎻愬彇鏍锋湰鍚嶅拰閾剧被鍨?            chain = self._extract_chain_from_filename(file_path.name)
            
            if chain:
                # 閾惧悗缂€妯″紡
                chains_found.add(chain)
                sample_name = self._extract_sample_name_from_chain_file(file_path.name)
                if sample_name:
                    if sample_name not in samples:
                        samples[sample_name] = []
                    samples[sample_name].append(file_path)
            else:
                # Traditional mode: use filename stem as sample name.
                sample_name = file_path.stem
                if sample_name not in samples:
                    samples[sample_name] = []
                samples[sample_name].append(file_path)
        
        self.scanned_samples = samples
        self.detected_chains = chains_found
        
        print_success(f"找到 {len(samples)} 个样本")
        if chains_found:
            print_info(f"检测到链类型: {', '.join(sorted(chains_found))}")
        
        return samples
    
    def group_samples_by_prefix(self) -> Dict[str, List[str]]:
        """
        鎸夋牱鏈墠缂€鍒嗙粍,鑷姩璇嗗埆鍚屼竴鏍锋湰鐨勫鏉￠摼鏁版嵁
        
        渚嬪: CL1-PER_036LH_IGH_pep, CL1-PER_036LH_IGK_pep 
        浼氳璇嗗埆涓哄悓涓€鏍锋湰缁?CL1-PER_036LH
        
        Returns:
            Dict[鏍锋湰缁勫悕, List[鏍锋湰鏂囦欢鍚峕]
        """
        sample_groups = {}
        
        for sample_name in self.scanned_samples.keys():
            # 灏濊瘯鎻愬彇鏍锋湰鍓嶇紑(绉婚櫎閾剧被鍨嬪悗缂€)
            # 鏀寔鐨勯摼绫诲瀷
            chain_types = ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']
            
            group_name = sample_name
            for chain in chain_types:
                # 鍖归厤妯″紡: xxx_CHAIN_xxx 鎴?xxx_CHAIN
                if f'_{chain}_' in sample_name:
                    group_name = sample_name.split(f'_{chain}_')[0]
                    break
                elif sample_name.endswith(f'_{chain}'):
                    group_name = sample_name.rsplit(f'_{chain}', 1)[0]
                    break
            
            # 娣诲姞鍒板垎缁?            if group_name not in sample_groups:
                sample_groups[group_name] = []
            sample_groups[group_name].append(sample_name)
        
        return sample_groups
    
    def interactive_select_samples(self) -> List[str]:
        """浜や簰寮忛€夋嫨鏍锋湰(鎸夋牱鏈粍)"""
        print_header("姝ラ 1: 閫夋嫨鏍锋湰")
        
        # 鎸夋牱鏈粍鍒嗙粍
        sample_groups = self.group_samples_by_prefix()
        group_names = sorted(sample_groups.keys())
        
        print("\n鍙敤鏍锋湰缁勫垪琛?")
        for i, group_name in enumerate(group_names, 1):
            samples_in_group = sample_groups[group_name]
            # 缁熻璇ョ粍鍖呭惈鐨勯摼绫诲瀷
            chains_in_group = set()
            for sample_name in samples_in_group:
                for chain in ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']:
                    if f'_{chain}_' in sample_name or sample_name.endswith(f'_{chain}'):
                        chains_in_group.add(chain)
            
            chain_info = f"[{', '.join(sorted(chains_in_group))}]" if chains_in_group else ""
            sample_count = f"({len(samples_in_group)} samples)"
            print(f"  {i:3d}. {group_name} {chain_info} {sample_count}")
        
        print("\nSelection options:")
        print("  - input 'all' to include all groups")
        print("  - input group indexes separated by commas, e.g. 1,2,3")
        print("  - input range such as 1-5")
        print("  - input 'exclude:1,2' to exclude groups")
        print("\nNote: selected groups include all chain files in each group")
        
        while True:
            choice = input("\n璇烽€夋嫨鏍锋湰缁?[all]: ").strip().lower() or 'all'
            
            selected_groups = []
            if choice == 'all':
                selected_groups = group_names
            elif choice.startswith('exclude:'):
                exclude_str = choice[8:]
                exclude_indices = self._parse_selection(exclude_str, len(group_names))
                selected_groups = [name for i, name in enumerate(group_names, 1) if i not in exclude_indices]
            else:
                indices = self._parse_selection(choice, len(group_names))
                selected_groups = [group_names[i-1] for i in indices if 1 <= i <= len(group_names)]
            
            # Expand selected groups to selected sample files.
            selected_samples = []
            for group_name in selected_groups:
                selected_samples.extend(sample_groups[group_name])
            
            if len(selected_samples) >= 2:
                break
            else:
                print_warning("At least 2 sample files are required, please reselect")
        
        self.selected_samples = selected_samples
        print_success(f"Selected {len(selected_groups)} groups, total {len(selected_samples)} sample files")
        
        # 鏄剧ず閫変腑鐨勬牱鏈粍璇︽儏
        print("\nSelected sample groups:")
        for group_name in selected_groups:
            samples_in_group = sample_groups[group_name]
            print(f"  - {group_name}: {len(samples_in_group)} files")
        
        return selected_samples
    
    def _parse_selection(self, selection: str, max_val: int) -> List[int]:
        """Parse a user selection string into indexes."""
        indices = []
        parts = selection.replace(' ', '').split(',')
        
        for part in parts:
            if '-' in part:
                try:
                    start, end = part.split('-')
                    indices.extend(range(int(start), int(end) + 1))
                except:
                    pass
            else:
                try:
                    indices.append(int(part))
                except:
                    pass
        
        return [i for i in indices if 1 <= i <= max_val]
    
    def interactive_rename_samples(self) -> Dict[str, str]:
        """浜や簰寮忛噸鍛藉悕鏍锋湰(鏀寔鏍锋湰缁勭骇鍒拰鍗曚釜鏂囦欢绾у埆)"""
        print_header("姝ラ 2: 鏍锋湰閲嶅懡鍚嶏紙鍙€夛級")
        
        print("\n褰撳墠鏍锋湰鍚嶇О:")
        for i, name in enumerate(self.selected_samples, 1):
            print(f"  {i:3d}. {name}")
        
        print("\nNeed to rename samples?")
        choice = input("Input 'y' to rename, or press Enter to skip [n]: ").strip().lower()
        
        if choice != 'y':
            # 浣跨敤鍘熷悕
            self.sample_display_names = {name: name for name in self.selected_samples}
            print_info("Keep original sample names")
            return self.sample_display_names
        
        # Select rename mode.
        print("\nRename mode:")
        print("  1. Group-level rename (recommended)")
        print("  2. File-level rename")
        
        mode_choice = input("\nSelect rename mode [1]: ").strip() or '1'
        
        if mode_choice == '1':
            # 鏍锋湰缁勭骇鍒噸鍛藉悕
            self._rename_by_sample_groups()
        else:
            # File-level rename.
            self._rename_individual_files()
        
        print_success("Sample rename completed")
        return self.sample_display_names
    
    def _rename_by_sample_groups(self):
        """Rename by sample groups."""
        # 鑾峰彇鏍锋湰鍒嗙粍
        sample_groups = self.group_samples_by_prefix()
        
        # 鍙鐞嗛€変腑鐨勬牱鏈?        selected_groups = {}
        for group_name, samples_in_group in sample_groups.items():
            # 妫€鏌ヨ缁勬槸鍚︽湁鏍锋湰琚€変腑
            selected_in_group = [s for s in samples_in_group if s in self.selected_samples]
            if selected_in_group:
                selected_groups[group_name] = selected_in_group
        
        print("\n涓烘瘡涓牱鏈粍杈撳叆鏂板悕绉帮紙鐩存帴鍥炶溅淇濇寔鍘熷悕锛?")
        print("鎻愮ず: 鏂板悕绉颁細鑷姩搴旂敤鍒拌缁勭殑鎵€鏈夐摼鏂囦欢")
        
        for group_name in sorted(selected_groups.keys()):
            samples_in_group = selected_groups[group_name]
            
            # 鏄剧ず璇ョ粍鍖呭惈鐨勯摼绫诲瀷
            chains_in_group = []
            for sample_name in samples_in_group:
                for chain in ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']:
                    if f'_{chain}_' in sample_name or sample_name.endswith(f'_{chain}'):
                        if chain not in chains_in_group:
                            chains_in_group.append(chain)
            
            chain_info = f"[{', '.join(sorted(chains_in_group))}]" if chains_in_group else ""
            new_group_name = input(f"  {group_name} {chain_info} ({len(samples_in_group)} 涓枃浠? -> ").strip()
            
            if new_group_name:
                # 搴旂敤鍒拌缁勭殑鎵€鏈夋牱鏈?                for sample_name in samples_in_group:
                    # 鎻愬彇閾剧被鍨嬪悗缂€
                    chain_suffix = ""
                    for chain in ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']:
                        if f'_{chain}_' in sample_name:
                            chain_suffix = sample_name.split(f'_{chain}_')[1]
                            chain_suffix = f"_{chain}_{chain_suffix}"
                            break
                        elif sample_name.endswith(f'_{chain}'):
                            chain_suffix = f"_{chain}"
                            break
                    
                    # 鏂板悕绉?= 鏂扮粍鍚?+ 閾惧悗缂€
                    self.sample_display_names[sample_name] = new_group_name + chain_suffix
            else:
                # 淇濇寔鍘熷悕
                for sample_name in samples_in_group:
                    self.sample_display_names[sample_name] = sample_name
        
        # 鏄剧ず閲嶅懡鍚嶇粨鏋?        print("\n閲嶅懡鍚嶇粨鏋滈瑙?")
        for group_name in sorted(selected_groups.keys()):
            samples_in_group = selected_groups[group_name]
            print(f"\n  鏍锋湰缁? {group_name}")
            for sample_name in samples_in_group:
                new_name = self.sample_display_names[sample_name]
                if new_name != sample_name:
                    print(f"    {sample_name} 鈫?{new_name}")
                else:
                    print(f"    {sample_name} (淇濇寔涓嶅彉)")
    
    def _rename_individual_files(self):
        """Rename each selected file interactively."""
        print("\nPlease input new name for each sample (press Enter to keep original):")
        for name in self.selected_samples:
            new_name = input(f"  {name} -> ").strip()
            self.sample_display_names[name] = new_name if new_name else name
    
    def interactive_reorder_samples(self) -> List[str]:
        """Interactively reorder samples (group-aware)."""
        print_header("姝ラ 3: 鏍锋湰鎺掑簭锛堝彲閫夛級")
        
        # 鑾峰彇鏍锋湰鍒嗙粍
        sample_groups = self.group_samples_by_prefix()
        
        # Keep only selected groups.
        selected_groups = {}
        group_order = []  # 淇濇寔缁勭殑鍘熷椤哄簭
        for sample_name in self.selected_samples:
            for group_name, samples_in_group in sample_groups.items():
                if sample_name in samples_in_group:
                    if group_name not in selected_groups:
                        selected_groups[group_name] = []
                        group_order.append(group_name)
                    if sample_name not in selected_groups[group_name]:
                        selected_groups[group_name].append(sample_name)
                    break
        
        print("\n褰撳墠鏍锋湰缁勯『搴?")
        for i, group_name in enumerate(group_order, 1):
            samples_in_group = selected_groups[group_name]
            display_names = [self.sample_display_names.get(s, s) for s in samples_in_group]
            # 鏄剧ず绗竴涓牱鏈殑鏄剧ず鍚?鍘绘帀閾惧悗缂€)
            first_display = display_names[0]
            for chain in ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']:
                if f'_{chain}' in first_display:
                    first_display = first_display.split(f'_{chain}')[0]
                    break
            print(f"  {i}. {first_display} ({len(samples_in_group)} 涓摼鏂囦欢)")
        
        print("\nNeed to reorder sample groups?")
        print("Hint: heatmaps will follow this order; files in the same group stay together.")
        choice = input("Input 'y' to reorder, or press Enter to skip [n]: ").strip().lower()
        
        if choice != 'y':
            print_info("淇濇寔褰撳墠鏍锋湰椤哄簭")
            return self.selected_samples
        
        print(f"\nSet new position for each group (1-{len(group_order)}).")
        print("Example: input 3 for group #1 to move it to position 3.")
        print("Press Enter to keep current position.")
        
        # 淇濆瓨鍘熷椤哄簭
        original_group_order = group_order.copy()
        
        while True:
            # 瀛樺偍姣忎釜鏍锋湰缁勭殑鏂颁綅缃? {缁勫悕: 鏂颁綅缃畗
            new_positions = {}
            
            print()
            for i, group_name in enumerate(original_group_order, 1):
                samples_in_group = selected_groups[group_name]
                display_names = [self.sample_display_names.get(s, s) for s in samples_in_group]
                first_display = display_names[0]
                for chain in ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']:
                    if f'_{chain}' in first_display:
                        first_display = first_display.split(f'_{chain}')[0]
                        break
                
                while True:
                    position_input = input(f"  {i}. {first_display} ({len(samples_in_group)} files) -> new position [{i}]: ").strip()
                    
                    if not position_input:
                        new_positions[group_name] = i
                        break
                    
                    try:
                        new_pos = int(position_input)
                        if 1 <= new_pos <= len(original_group_order):
                            new_positions[group_name] = new_pos
                            break
                        else:
                            print_warning(f"    Please input a number between 1 and {len(original_group_order)}")
                    except ValueError:
                        print_warning("    Please input a valid number")
            
            # Check duplicated positions.
            positions = list(new_positions.values())
            if len(set(positions)) != len(positions):
                print_warning("\nDuplicate positions detected, please set again")
                retry = input("Reset positions? [y]: ").strip().lower() or 'y'
                if retry == 'y':
                    continue
                else:
                    print_info("淇濇寔褰撳墠鏍锋湰椤哄簭")
                    return self.selected_samples
            
            # Build new group order by target positions.
            position_to_group = {pos: group for group, pos in new_positions.items()}
            new_group_order = [position_to_group[i] for i in sorted(position_to_group.keys())]
            
            # Expand to sample-file order (preserve in-group order).
            new_sample_order = []
            for group_name in new_group_order:
                new_sample_order.extend(selected_groups[group_name])
            
            # Show new order
            print("\nNew sample group order:")
            for i, group_name in enumerate(new_group_order, 1):
                samples_in_group = selected_groups[group_name]
                display_names = [self.sample_display_names.get(s, s) for s in samples_in_group]
                first_display = display_names[0]
                for chain in ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']:
                    if f'_{chain}' in first_display:
                        first_display = first_display.split(f'_{chain}')[0]
                        break
                
                original_pos = original_group_order.index(group_name) + 1
                if original_pos != i:
                    print(f"  {i}. {first_display} ({len(samples_in_group)} files) (original: {original_pos})")
                else:
                    print(f"  {i}. {first_display} ({len(samples_in_group)} files)")
            
            confirm = input("\nConfirm this order? [y]: ").strip().lower() or 'y'
            if confirm == 'y':
                self.selected_samples = new_sample_order
                print_success("Sample order updated")
                return self.selected_samples
            else:
                print_info("Please reset the order")
                continue
    
    def interactive_select_chains(self) -> List[str]:
        """浜や簰寮忛€夋嫨閾剧被鍨?"""
        if not self.detected_chains:
            return []
        
        print_header("Step 3: Select chains")
        
        chains = sorted(self.detected_chains)
        print("\nDetected chain types:")
        for i, chain in enumerate(chains, 1):
            print(f"  {i}. {chain}")
        
        print("\nSelection options:")
        print("  - input 'all' to include all chains")
        print("  - input chain indexes separated by commas")
        
        while True:
            choice = input("\n璇烽€夋嫨閾剧被鍨?[all]: ").strip().lower() or 'all'
            
            if choice == 'all':
                selected = chains
            else:
                indices = self._parse_selection(choice, len(chains))
                selected = [chains[i-1] for i in indices if 1 <= i <= len(chains)]
            
            if selected:
                break
            else:
                print_warning("璇疯嚦灏戦€夋嫨涓€涓摼绫诲瀷")
        
        self.chains = selected
        print_success(f"宸查€夋嫨閾剧被鍨? {', '.join(selected)}")
        
        return selected
    
    def interactive_field_mapping(self, sample_df: pd.DataFrame) -> Tuple[str, str]:
        """浜や簰寮忓瓧娈垫槧灏?"""
        print_header("姝ラ 4: 瀛楁鏄犲皠")
        
        columns = sample_df.columns.tolist()
        
        # Auto detect candidate columns.
        detected_cdr3, detected_copy = self.auto_detect_columns(sample_df)
        
        print("\n鏁版嵁鏂囦欢鍒楀悕:")
        for i, col in enumerate(columns, 1):
            markers = []
            if col == detected_cdr3:
                markers.append("recommended CDR3")
            if col == detected_copy:
                markers.append("recommended copy")
            marker_str = f" <- {', '.join(markers)}" if markers else ""
            print(f"  {i:3d}. {col}{marker_str}")
        
        # Show preview.
        print("\n鏁版嵁棰勮锛堝墠5琛岋級:")
        print(sample_df.head().to_string())
        
        # Select CDR3 column.
        print(f"\nSelect CDR3 column [recommended: {detected_cdr3}]:")
        cdr3_choice = input(f"杈撳叆鍒楃紪鍙锋垨鍒楀悕 [{detected_cdr3}]: ").strip()
        
        if not cdr3_choice:
            cdr3_col = detected_cdr3
        elif cdr3_choice.isdigit():
            idx = int(cdr3_choice) - 1
            cdr3_col = columns[idx] if 0 <= idx < len(columns) else detected_cdr3
        else:
            cdr3_col = cdr3_choice if cdr3_choice in columns else detected_cdr3
        
        # 閫夋嫨鎷疯礉鏁板垪
        print(f"\n璇烽€夋嫨鎷疯礉鏁?琛ㄨ揪閲忓垪 [鎺ㄨ崘: {detected_copy}]:")
        copy_choice = input(f"杈撳叆鍒楃紪鍙锋垨鍒楀悕 [{detected_copy}]: ").strip()
        
        if not copy_choice:
            copy_col = detected_copy
        elif copy_choice.isdigit():
            idx = int(copy_choice) - 1
            copy_col = columns[idx] if 0 <= idx < len(columns) else detected_copy
        else:
            copy_col = copy_choice if copy_choice in columns else detected_copy
        
        self.cdr3_col = cdr3_col
        self.copy_col = copy_col
        
        print_success(f"CDR3鍒? {cdr3_col}")
        print_success(f"鎷疯礉鏁板垪: {copy_col}")
        
        return cdr3_col, copy_col
    
    def interactive_settings(self):
        """浜や簰寮忚缃叾浠栧弬鏁?"""
        print_header("姝ラ 5: 杈撳嚭璁剧疆")
        
        # 鐑浘鏍囬
        print(f"\n褰撳墠鐑浘鏍囬: {self.title}")
        new_title = input("杈撳叆鏂版爣棰橈紙鐩存帴鍥炶溅淇濇寔锛? ").strip()
        if new_title:
            self.title = new_title
        
        # 鏄剧ず鏁板€?        show_val = input("\n鍦ㄧ儹鍥句笂鏄剧ず鏁板€? [Y/n]: ").strip().lower()
        self.show_values = show_val != 'n'
        
        # 瀵煎嚭CDR3鍏变韩鍒楄〃
        export = input("瀵煎嚭CDR3鍏变韩鍒楄〃? [y/N]: ").strip().lower()
        self.export_cdr3 = export == 'y'
        # Generate web report option.
        default_web_report = 'Y/n' if self.generate_web_report else 'y/N'
        web_report = input(f"鐢熸垚缃戦〉鐗堝垎浜姤鍛? [{default_web_report}]: ").strip().lower()
        if web_report:
            self.generate_web_report = web_report == 'y'

        if self.generate_web_report:
            default_scan = self.report_scan_path or str(self.input_dir)
            scan_path = input(
                f"鎶ュ憡鎵弿璺緞锛堥€掑綊鏌ユ壘 */output/shared_analysis锛塠{default_scan}]: "
            ).strip()
            self.report_scan_path = scan_path or default_scan
        
        print_success("璁剧疆瀹屾垚")
    
    def _extract_chain_from_filename(self, filename: str) -> Optional[str]:
        """Extract chain type from filename."""
        name = filename
        for ext in ['.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt']:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break
        
        # 鏂规硶1: 鍙屼笅鍒掔嚎鍒嗛殧绗?(濡? SS03P_DBY__IGH)
        if '__' in name:
            parts = name.split('__')
            potential_chain = parts[-1].upper()
            if potential_chain in self.CHAIN_TYPES:
                return potential_chain
        
        # 鏂规硶2: 妫€鏌ユ枃浠跺悕鏈熬鏄惁浠ラ摼绫诲瀷缁撳熬 (濡? DBY_IGH, DBY-PER_DBY_IGH)
        # 鎸夌収浠庨暱鍒扮煭鐨勯『搴忔鏌ワ紝閬垮厤璇尮閰?        name_upper = name.upper()
        for chain in self.CHAIN_TYPES:
            # 妫€鏌ユ槸鍚︿互 _CHAIN 鎴?-CHAIN 缁撳熬
            if name_upper.endswith(f'_{chain}') or name_upper.endswith(f'-{chain}'):
                return chain
        
        return None
    
    def _extract_sample_name_from_chain_file(self, filename: str) -> Optional[str]:
        """浠庨摼鍚庣紑鏂囦欢鍚嶆彁鍙栨牱鏈悕锛屾敮鎸佸绉嶅懡鍚嶆ā寮?"""
        name = filename
        for ext in ['.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt']:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break
        
        # 鏂规硶1: 鍙屼笅鍒掔嚎鍒嗛殧绗?(濡? SS03P_DBY__IGH -> SS03P_DBY)
        if '__' in name:
            parts = name.split('__')
            return '__'.join(parts[:-1])
        
        # 鏂规硶2: 妫€鏌ユ枃浠跺悕鏈熬鐨勯摼绫诲瀷骞剁Щ闄?(濡? DBY_IGH -> DBY, DBY-PER_DBY_IGH -> DBY-PER_DBY)
        name_upper = name.upper()
        for chain in self.CHAIN_TYPES:
            # 妫€鏌ユ槸鍚︿互 _CHAIN 缁撳熬
            if name_upper.endswith(f'_{chain}'):
                return name[:-len(chain)-1]  # 绉婚櫎 _CHAIN
            # 妫€鏌ユ槸鍚︿互 -CHAIN 缁撳熬
            if name_upper.endswith(f'-{chain}'):
                return name[:-len(chain)-1]  # 绉婚櫎 -CHAIN
        
        return None
    
    def load_data(self, file_path: Path) -> pd.DataFrame:
        """鍔犺浇鏁版嵁鏂囦欢"""
        is_gzipped = str(file_path).lower().endswith('.gz')
        
        # 妫€娴嬪垎闅旂
        if is_gzipped:
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
        
        sep = '\t' if '\t' in first_line else ','
        
        # 璇诲彇鏁版嵁
        if is_gzipped:
            df = pd.read_csv(file_path, sep=sep, compression='gzip', low_memory=False)
        else:
            df = pd.read_csv(file_path, sep=sep, low_memory=False)
        
        return df
    
    def auto_detect_columns(self, df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
        """Auto detect CDR3 and copy count columns."""
        columns = [col.lower().strip() for col in df.columns]
        
        cdr3_col = None
        copy_col = None
        
        # Detect CDR3 column.
        for col, col_lower in zip(df.columns, columns):
            for pattern in self.CDR3_PATTERNS:
                if pattern in col_lower:
                    cdr3_col = col
                    break
            if cdr3_col:
                break
        
        # Detect copy column.
        for col, col_lower in zip(df.columns, columns):
            for pattern in self.COPY_PATTERNS:
                if pattern in col_lower:
                    copy_col = col
                    break
            if copy_col:
                break
        
        return cdr3_col, copy_col
    
    def calculate_similarities(self, sample_data: Dict[str, pd.DataFrame]) -> Dict[str, np.ndarray]:
        """璁＄畻鎵€鏈夌浉浼煎害鎸囨爣锛堜笌flask_app AutoHeatmapService涓€鑷达級"""
        sample_names = list(sample_data.keys())
        n = len(sample_names)
        if n == 0:
            return {metric: np.array([]) for metric in self.METRICS}

        # 涓巜eb绔竴鑷达細鍏堟瀯寤簊et鍜屾寜cdr3鑱氬悎鍚庣殑涓板害瀛楀吀
        cdr3_sets: Dict[str, Set[str]] = {}
        abundance: Dict[str, Dict[str, float]] = {}
        for name, df in sample_data.items():
            cdr3_sets[name] = set(df['cdr3'].dropna().unique())
            abundance[name] = df.groupby('cdr3')['copy'].sum().to_dict()

        results: Dict[str, np.ndarray] = {}
        for metric in self.METRICS:
            matrix = np.ones((n, n))

            for i in range(n):
                for j in range(i + 1, n):
                    name_i = sample_names[i]
                    name_j = sample_names[j]

                    if metric == 'r2_inner':
                        sim = self._calculate_r2_inner(abundance[name_i], abundance[name_j])
                        matrix[i, j] = sim
                        matrix[j, i] = sim
                    elif metric == 'r2_outer':
                        sim = self._calculate_r2_outer(abundance[name_i], abundance[name_j])
                        matrix[i, j] = sim
                        matrix[j, i] = sim
                    elif metric == 'cdr3_sharing':
                        # 涓巜eb绔竴鑷达細涓婁笁瑙掑啓 B鈫扐锛屼笅涓夎鍐?A鈫払
                        sim_i_to_j, sim_j_to_i = self._calculate_cdr3_sharing_directional(
                            cdr3_sets[name_i], cdr3_sets[name_j]
                        )
                        matrix[i, j] = sim_j_to_i
                        matrix[j, i] = sim_i_to_j
                    elif metric == 'expression_sharing':
                        # 涓巜eb绔竴鑷达細涓婁笁瑙掑啓 B鈫扐锛屼笅涓夎鍐?A鈫払
                        sim_i_to_j, sim_j_to_i = self._calculate_expression_sharing(
                            abundance[name_i], abundance[name_j]
                        )
                        matrix[i, j] = sim_j_to_i
                        matrix[j, i] = sim_i_to_j
                    elif metric == 'morisita_horn':
                        sim = self._calculate_morisita_horn(abundance[name_i], abundance[name_j])
                        matrix[i, j] = sim
                        matrix[j, i] = sim
                    elif metric == 'sorensen':
                        sim = self._calculate_sorensen(cdr3_sets[name_i], cdr3_sets[name_j])
                        matrix[i, j] = sim
                        matrix[j, i] = sim
                    else:
                        sim = self._calculate_r2_inner(abundance[name_i], abundance[name_j])
                        matrix[i, j] = sim
                        matrix[j, i] = sim

            results[metric] = matrix

        return results

    def _calculate_r2_inner(self, abundance_a: Dict[str, float], abundance_b: Dict[str, float]) -> float:
        """R虏 inner锛堜笌web绔竴鑷达級"""
        if not abundance_a or not abundance_b:
            return 0.0

        shared_cdr3 = set(abundance_a.keys()) & set(abundance_b.keys())
        if len(shared_cdr3) < 2:
            return 0.0

        shared_list = sorted(shared_cdr3)
        values_a = np.array([abundance_a[cdr3] for cdr3 in shared_list])
        values_b = np.array([abundance_b[cdr3] for cdr3 in shared_list])

        std_a = np.std(values_a)
        std_b = np.std(values_b)
        if std_a > 0 and std_b > 0:
            corr = np.corrcoef(values_a, values_b)[0, 1]
            return corr ** 2 if not np.isnan(corr) else 0.0
        if std_a == 0 and std_b == 0:
            return 1.0
        return 0.0

    def _calculate_r2_outer(self, abundance_a: Dict[str, float], abundance_b: Dict[str, float]) -> float:
        """R虏 outer锛堜笌web绔竴鑷达級"""
        if not abundance_a or not abundance_b:
            return 0.0

        all_cdr3 = set(abundance_a.keys()) | set(abundance_b.keys())
        if len(all_cdr3) < 2:
            return 0.0

        all_list = sorted(all_cdr3)
        values_a = np.array([abundance_a.get(cdr3, 0) for cdr3 in all_list])
        values_b = np.array([abundance_b.get(cdr3, 0) for cdr3 in all_list])

        std_a = np.std(values_a)
        std_b = np.std(values_b)
        if std_a > 0 and std_b > 0:
            corr = np.corrcoef(values_a, values_b)[0, 1]
            return corr ** 2 if not np.isnan(corr) else 0.0
        if std_a == 0 and std_b == 0:
            return 1.0
        return 0.0

    def _calculate_cdr3_sharing_directional(self, set_a: Set[str], set_b: Set[str]) -> Tuple[float, float]:
        """CDR3 sharing directional锛堜笌web绔竴鑷达級"""
        if not set_a or not set_b:
            return 0.0, 0.0

        intersection = len(set_a & set_b)
        sim_a_to_b = intersection / len(set_a) if len(set_a) > 0 else 0.0
        sim_b_to_a = intersection / len(set_b) if len(set_b) > 0 else 0.0
        return sim_a_to_b, sim_b_to_a

    def _calculate_expression_sharing(
        self,
        abundance_a: Dict[str, float],
        abundance_b: Dict[str, float]
    ) -> Tuple[float, float]:
        """Expression sharing directional锛堜笌web绔竴鑷达紝涓嶄娇鐢╩in(copy_a, copy_b)锛?"""
        if not abundance_a or not abundance_b:
            return 0.0, 0.0

        set_a = set(abundance_a.keys())
        set_b = set(abundance_b.keys())
        shared_cdr3 = set_a & set_b

        total_reads_a = sum(abundance_a.values())
        total_reads_b = sum(abundance_b.values())

        shared_reads_a = sum(abundance_a[c] for c in shared_cdr3)
        shared_reads_b = sum(abundance_b[c] for c in shared_cdr3)

        a_to_b = shared_reads_a / total_reads_a if total_reads_a > 0 else 0.0
        b_to_a = shared_reads_b / total_reads_b if total_reads_b > 0 else 0.0
        return a_to_b, b_to_a

    def _calculate_sorensen(self, set_a: Set[str], set_b: Set[str]) -> float:
        """Sorensen-Dice锛堜笌web绔竴鑷达級"""
        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        size_sum = len(set_a) + len(set_b)
        return (2 * intersection) / size_sum if size_sum > 0 else 0.0

    def _calculate_morisita_horn(
        self,
        abundance_a: Dict[str, float],
        abundance_b: Dict[str, float]
    ) -> float:
        """Morisita-Horn锛堜笌web绔竴鑷达級"""
        if not abundance_a or not abundance_b:
            return 0.0

        all_cdr3 = set(abundance_a.keys()) | set(abundance_b.keys())
        all_list = sorted(all_cdr3)
        n_a = np.array([abundance_a.get(cdr3, 0) for cdr3 in all_list])
        n_b = np.array([abundance_b.get(cdr3, 0) for cdr3 in all_list])

        total_a = np.sum(n_a)
        total_b = np.sum(n_b)
        if total_a == 0 or total_b == 0:
            return 0.0

        d_a = np.sum((n_a / total_a) ** 2)
        d_b = np.sum((n_b / total_b) ** 2)

        numerator = 2 * np.sum(n_a * n_b)
        denominator = (d_a + d_b) * total_a * total_b
        return numerator / denominator if denominator > 0 else 0.0
    
    def generate_heatmap(self, matrix: np.ndarray, sample_names: List[str], metric: str, output_path: Path):
        """鐢熸垚鐑浘锛堜笌flask_app HeatmapGenerator榛樿琛屼负涓€鑷达級"""
        # 鎸囨爣鐗瑰畾棰滆壊鏂规锛堜笌flask_app涓€鑷达級
        METRIC_COLOR_SCHEMES = {
            'r2_inner': 'Greens',
            'r2_outer': 'Purples',
            'cdr3_sharing': 'Reds',
            'expression_sharing': 'Blues',
            'morisita_horn': 'Oranges',
            'sorensen': 'YlGnBu'
        }
        
        # 涓巜eb榛樿涓€鑷达細鍥哄畾鍥惧昂瀵?        fig, ax = plt.subplots(figsize=(10, 8))
        
        # 浣跨敤鎸囨爣鐗瑰畾棰滆壊鏂规
        cmap = METRIC_COLOR_SCHEMES.get(metric, 'viridis')
        
        # 涓巜eb榛樿涓€鑷达細涓嶉伄缃╁瑙掔嚎
        mask = None
        
        # 璁＄畻棰滆壊鑼冨洿
        matrix_copy = matrix.copy()
        vmin = np.nanmin(matrix_copy)
        vmax = np.nanmax(matrix_copy)
        
        # 澶勭悊杈圭晫鎯呭喌
        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
            vmin = 0.0
            vmax = 1.0
        
        # 鐢熸垚鐑浘
        sns.heatmap(
            matrix,
            xticklabels=sample_names,
            yticklabels=sample_names,
            cmap=cmap,
            mask=mask,
            annot=self.show_values,
            fmt=".2f",
            square=True,
            vmin=vmin,
            vmax=vmax,
            linewidths=0.5,
            linecolor='#e0e0e0',  # 娴呯伆鑹茬綉鏍肩嚎锛堜笌flask_app涓€鑷达級
            cbar_kws={'label': 'Similarity', 'shrink': 0.8},
            ax=ax,
            annot_kws={'fontsize': 10}
        )
        
        # 浣跨敤鑻辨枃鏍囩
        if self.title:
            ax.set_title(self.title, fontsize=14, fontweight='600', pad=15)
        ax.set_xlabel('Sample', fontsize=12)
        ax.set_ylabel('Sample', fontsize=12)
        
        # 璁剧疆鍒诲害鍙傛暟
        ax.tick_params(axis='x', rotation=45, labelsize=11)
        ax.tick_params(axis='y', rotation=0, labelsize=11)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"宸蹭繚瀛? {output_path}")
    
    def save_matrix(self, matrix: np.ndarray, sample_names: List[str], metric: str, output_path: Path):
        """淇濆瓨鐩镐技搴︾煩闃典负CSV锛堜繚瀛樺埌metric鏂囦欢澶癸級"""
        df = pd.DataFrame(matrix, index=sample_names, columns=sample_names)
        df.to_csv(output_path, encoding='utf-8-sig')  # 浣跨敤UTF-8 BOM缂栫爜锛孍xcel鍙嬪ソ
        logger.info(f"宸蹭繚瀛? {output_path}")

    def _build_matrix_table_data(self, matrix: np.ndarray, sample_names: List[str]) -> Dict[str, List[Any]]:
        """鏋勫缓涓巜eb绔竴鑷寸殑琛ㄦ牸鏁版嵁缁撴瀯"""
        rows: List[List[Any]] = []
        for idx, row_name in enumerate(sample_names):
            row_values = matrix[idx].tolist() if idx < len(matrix) else []
            formatted_values: List[Any] = []
            for value in row_values:
                if pd.isna(value):
                    formatted_values.append(None)
                else:
                    formatted_values.append(round(float(value), 4))
            rows.append([row_name] + formatted_values)

        return {
            'columns': ['Sample'] + list(sample_names),
            'rows': rows
        }

    def _format_table_from_csv(self, csv_path: Path) -> Dict[str, List[Any]]:
        """浠嶤SV鏋勫缓鎶ュ憡琛ㄦ牸鏁版嵁"""
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            return {'columns': [], 'rows': []}

        columns = [str(col) for col in df.columns.tolist()]
        rows: List[List[Any]] = []
        for row in df.values.tolist():
            normalized_row: List[Any] = []
            for value in row:
                if pd.isna(value):
                    normalized_row.append(None)
                elif isinstance(value, (float, np.floating)):
                    normalized_row.append(round(float(value), 4))
                else:
                    normalized_row.append(value)
            rows.append(normalized_row)
        return {'columns': columns, 'rows': rows}

    def _path_to_report_href(self, target_path: Path, report_dir: Path) -> str:
        """灏嗙洰鏍囪矾寰勮浆鎹负鎶ュ憡涓彲鐢ㄧ殑鐩稿璺緞"""
        try:
            return os.path.relpath(target_path, report_dir).replace('\\', '/')
        except Exception:
            return target_path.as_posix()

    def _detect_metric_key(self, file_stem: str) -> str:
        """浠庢枃浠跺悕涓娴嬫寚鏍囧悕"""
        stem_lower = file_stem.lower()
        for metric in self.METRICS:
            if metric in stem_lower:
                return metric
        return file_stem

    def _resolve_heatmap_image_path(
        self,
        metric_csv_path: Path,
        metric_root: Path,
        heatmap_root: Path,
        metric_key: str
    ) -> Optional[Path]:
        """涓烘煇涓寚鏍嘋SV瀵绘壘瀵瑰簲鐑浘PNG"""
        relative_csv = metric_csv_path.relative_to(metric_root)
        candidates = [
            heatmap_root / relative_csv.with_suffix('.png'),
            heatmap_root / relative_csv.parent / relative_csv.name.replace('_heatmap.csv', '_heatmap.png'),
            heatmap_root / relative_csv.parent / f'{metric_key}_heatmap.png',
            heatmap_root / relative_csv.parent / f'{metric_key}.png',
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        search_dir = heatmap_root / relative_csv.parent
        if search_dir.exists():
            matches = sorted(search_dir.glob(f'*{metric_key}*.png'))
            if matches:
                return matches[0]

        return None

    def _discover_shared_analysis_modules(self, scan_root: Path) -> List[Dict[str, Any]]:
        """
        閫掑綊鍙戠幇妯″潡鐩綍銆?        瑙勫垯锛氳瘑鍒?*/output/shared_analysis锛屾瘡涓洰褰曚綔涓轰竴涓ā鍧椼€?        """
        modules: List[Dict[str, Any]] = []
        seen_paths: Set[Path] = set()

        if scan_root.is_dir() and scan_root.name.lower() == 'shared_analysis':
            shared_dir = scan_root.resolve()
            module_name = shared_dir.parent.name or 'module'
            modules.append({'name': module_name, 'shared_dir': shared_dir})
            seen_paths.add(shared_dir)

        for shared_dir in scan_root.rglob('shared_analysis'):
            if not shared_dir.is_dir():
                continue
            if shared_dir.parent.name.lower() != 'output':
                continue

            resolved = shared_dir.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            module_name = shared_dir.parent.parent.name or f'module_{len(modules) + 1}'
            modules.append({'name': module_name, 'shared_dir': resolved})

        modules.sort(key=lambda item: item['name'].lower())
        return modules

    def _build_sections_from_shared_analysis_module(
        self,
        shared_dir: Path,
        report_dir: Path
    ) -> List[Dict[str, Any]]:
        """浠庝竴涓猻hared_analysis鐩綍鎻愬彇鎶ュ憡sections"""
        metric_root = shared_dir / 'metric'
        heatmap_root = shared_dir / 'heatmap'
        if not metric_root.exists():
            return []

        section_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for csv_path in sorted(metric_root.rglob('*.csv')):
            rel_parent = csv_path.parent.relative_to(metric_root).as_posix()
            section_key = rel_parent if rel_parent != '.' else 'overview'

            metric_key = self._detect_metric_key(csv_path.stem)
            metric_label = self.METRIC_NAMES.get(metric_key, csv_path.stem)
            table_data = self._format_table_from_csv(csv_path)

            image_path = None
            if heatmap_root.exists():
                image_path = self._resolve_heatmap_image_path(
                    metric_csv_path=csv_path,
                    metric_root=metric_root,
                    heatmap_root=heatmap_root,
                    metric_key=metric_key
                )

            section_map[section_key].append({
                'metric_name': metric_key,
                'metric_label': metric_label,
                'image_src': self._path_to_report_href(image_path, report_dir) if image_path else '',
                'csv_rel_path': self._path_to_report_href(csv_path, report_dir),
                'table_columns': table_data.get('columns', []),
                'table_rows': table_data.get('rows', []),
            })

        sections: List[Dict[str, Any]] = []
        for section_key in sorted(section_map.keys()):
            section_title = 'Overview' if section_key == 'overview' else section_key.replace('/', ' / ')
            section_id = re.sub(r'[^A-Za-z0-9_-]+', '_', section_key)
            sections.append({
                'id': section_id,
                'title': section_title,
                'entries': section_map[section_key]
            })
        return sections

    def _generate_multi_module_web_report(
        self,
        modules: List[Dict[str, Any]],
        output_path: Path,
        context: Dict[str, Any]
    ) -> Optional[Path]:
        """鐢熸垚鏀寔妯″潡鍒囨崲鐨勫崟椤礖TML鎶ュ憡"""
        if not modules:
            return None

        try:
            from flask_app.services.similarity_heatmap_report_service import SimilarityHeatmapReportService
            service = SimilarityHeatmapReportService(results_root=output_path.parent)

            module_option_html: List[str] = []
            module_panel_html: List[str] = []

            for idx, module in enumerate(modules):
                module_name = str(module.get('name') or f'Module_{idx + 1}')
                shared_dir = Path(module['shared_dir'])
                module_id = f"module_{idx + 1}"
                active_class = ' active' if idx == 0 else ''

                sections = self._build_sections_from_shared_analysis_module(
                    shared_dir=shared_dir,
                    report_dir=output_path.parent
                )
                if not sections:
                    continue

                module_option_html.append(
                    f'<option value="{html.escape(module_id)}">{html.escape(module_name)}</option>'
                )

                rendered_sections = []
                for section in sections:
                    section_dom_id = f"{module_id}_{section['id']}"
                    rendered_sections.append(
                        service._render_section_html(
                            section_id=section_dom_id,
                            section_title=section['title'],
                            entries=section.get('entries', [])
                        )
                    )

                module_panel_html.append(
                    (
                        f'<section id="{html.escape(module_id)}" class="module-panel{active_class}">'
                        f'<div class="module-meta"><strong>Module:</strong> {html.escape(module_name)} '
                        f'<span class="muted">({html.escape(str(shared_dir))})</span></div>'
                        + ''.join(rendered_sections)
                        + '</section>'
                    )
                )

            if not module_panel_html:
                return None

            summary_list = [
                f"<li><strong>Generated At:</strong> {html.escape(datetime.now().isoformat())}</li>",
                f"<li><strong>Module Count:</strong> {len(module_panel_html)}</li>",
            ]
            scan_base = context.get('scan_base')
            if scan_base:
                summary_list.append(f"<li><strong>Scan Base:</strong> {html.escape(str(scan_base))}</li>")

            report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Similarity Heatmap Multi-Module Report</title>
  <style>
    :root {{
      --bg: #f2f5f8;
      --panel: #ffffff;
      --ink: #1d2433;
      --muted: #60708a;
      --line: #d9e1ea;
      --accent: #1f6feb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f6f8fb, #eef3f8 45%, #e8eff7);
    }}
    .page {{ max-width: 1440px; margin: 0 auto; }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 22px;
      margin-bottom: 18px;
      box-shadow: 0 8px 30px rgba(27, 39, 74, 0.06);
      position: relative;
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: 26px; }}
    .summary {{ margin: 0; padding-left: 20px; color: var(--muted); }}
    .module-switch {{
      position: absolute;
      right: 22px;
      top: 22px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: #3d4f68;
      font-size: 13px;
    }}
    .module-switch select {{
      border: 1px solid #bfd1e6;
      border-radius: 8px;
      padding: 4px 8px;
      background: #fff;
      min-width: 260px;
    }}
    .module-panel {{ display: none; }}
    .module-panel.active {{ display: block; }}
    .module-meta {{
      margin-bottom: 10px;
      color: #364a63;
      font-size: 13px;
      background: #f9fbfe;
      border: 1px solid #dce7f3;
      border-radius: 10px;
      padding: 8px 10px;
    }}
    .muted {{ color: #647a95; }}
    .report-section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 8px 30px rgba(27, 39, 74, 0.04);
    }}
    .report-section h2 {{ margin: 0 0 14px; font-size: 20px; }}
    .metric-tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
    .metric-tab-btn {{
      border: 1px solid var(--line);
      background: #f8fbff;
      color: #3c4e66;
      border-radius: 999px;
      padding: 6px 12px;
      cursor: pointer;
      font-size: 13px;
      transition: all .12s ease;
    }}
    .metric-tab-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    .metric-panel {{
      display: none;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      background: #fcfdff;
    }}
    .metric-panel.active {{ display: block; }}
    .metric-meta {{ display: flex; justify-content: flex-end; margin-bottom: 8px; }}
    .download-link {{
      color: var(--accent);
      font-size: 13px;
      text-decoration: none;
      border: 1px solid #b9d4ff;
      padding: 4px 10px;
      border-radius: 999px;
      background: #f3f8ff;
    }}
    .image-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      padding: 8px;
      margin-bottom: 12px;
    }}
    .heatmap-image {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
    .table-card h4 {{ margin: 0 0 8px; font-size: 15px; color: #334257; }}
    .table-wrap {{
      max-height: 420px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
    }}
    .metric-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    .metric-table th,
    .metric-table td {{
      border: 1px solid #e2e8f0;
      padding: 6px 8px;
      text-align: center;
      white-space: nowrap;
    }}
    .metric-table th {{
      background: #f1f5fa;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    .empty-note {{ margin: 10px 0; color: #7d8da5; font-size: 13px; }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>Similarity Heatmap Multi-Module Report</h1>
      <div class="module-switch">
        <label for="moduleSelector"><strong>Module</strong></label>
        <select id="moduleSelector">
          {''.join(module_option_html)}
        </select>
      </div>
      <ul class="summary">
        {''.join(summary_list)}
      </ul>
    </section>
    {''.join(module_panel_html)}
  </main>
  <script>
    (function() {{
      const selector = document.getElementById('moduleSelector');
      const panels = Array.from(document.querySelectorAll('.module-panel'));
      function activateModule(moduleId) {{
        panels.forEach((panel) => panel.classList.toggle('active', panel.id === moduleId));
      }}
      selector.addEventListener('change', () => activateModule(selector.value));
      if (selector.options.length > 0) activateModule(selector.value);

      const sectionNodes = document.querySelectorAll('.report-section');
      sectionNodes.forEach((section) => {{
        const buttons = section.querySelectorAll('.metric-tab-btn');
        const panelsInner = section.querySelectorAll('.metric-panel');
        buttons.forEach((btn) => {{
          btn.addEventListener('click', () => {{
            const targetId = btn.getAttribute('data-target');
            buttons.forEach((x) => x.classList.remove('active'));
            panelsInner.forEach((x) => x.classList.remove('active'));
            btn.classList.add('active');
            const panel = section.querySelector('#' + CSS.escape(targetId));
            if (panel) panel.classList.add('active');
          }});
        }});
      }});
    }})();
  </script>
</body>
</html>"""

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report_html, encoding='utf-8')
            print_success(f"宸茬敓鎴愬妯″潡缃戦〉鐗堝垎浜姤鍛? {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error generating multi-module report: {e}", exc_info=True)
            print_warning(f"澶氭ā鍧楃綉椤电増鎶ュ憡鐢熸垚澶辫触: {e}")
            return None

    def _generate_web_share_report(
        self,
        sections: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Optional[Path]:
        """
        鐢熸垚缃戦〉鐗堝垎浜姤鍛婏紙HTML锛?        澶嶇敤flask_app涓殑SimilarityHeatmapReportService椤甸潰妯℃澘銆?        """
        if not sections:
            print_warning("鎶ュ憡鏁版嵁涓虹┖锛岃烦杩囩綉椤电増鍒嗕韩鎶ュ憡鐢熸垚")
            return None

        try:
            from flask_app.services.similarity_heatmap_report_service import SimilarityHeatmapReportService

            service = SimilarityHeatmapReportService(results_root=self.output_dir.parent)
            mode = 'chain' if any(str(s.get('id', '')).startswith('chain_') for s in sections) else 'traditional'
            report_metadata = {
                'generated_at': datetime.now().isoformat(),
                'mode': mode,
                'context': context
            }
            report_html = service._build_report_html(
                job_id=self.output_dir.name,
                sections=sections,
                metadata=report_metadata
            )

            report_path = self.output_dir / 'similarity_heatmap_report.html'
            report_path.write_text(report_html, encoding='utf-8')
            print_success(f"宸茬敓鎴愮綉椤电増鍒嗕韩鎶ュ憡: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Error generating web share report: {e}", exc_info=True)
            print_warning(f"缃戦〉鐗堝垎浜姤鍛婄敓鎴愬け璐? {e}")
            return None
    
    def export_cdr3_complete_analysis(self, sample_data: Dict[str, pd.DataFrame], output_dir: Path, top_n: int = 100):
        """瀵煎嚭瀹屾暣鐨凜DR3鍒嗘瀽鏁版嵁锛堝唴缃疄鐜帮紝鏃犻渶澶栭儴渚濊禆锛?"""
        print_info("瀵煎嚭CDR3瀹屾暣鍒嗘瀽鏁版嵁...")
        
        # Basic input check.
        if not sample_data or len(sample_data) < 2:
            print_warning("闇€瑕佽嚦灏?涓牱鏈墠鑳藉鍑篊DR3鍒嗘瀽")
            return
        
        try:
            # Validate sample data format.
            print_info(f"Sample count: {len(sample_data)}")
            for sample_name, df in sample_data.items():
                chain_info = ""
                if '_' in sample_name:
                    parts = sample_name.rsplit('_', 1)
                    if len(parts) == 2:
                        chain_info = f" [chain: {parts[1]}]"
                
                print_info(f"  - {sample_name}{chain_info}: {len(df)} rows")
                
                if 'cdr3' not in df.columns or 'copy' not in df.columns:
                    print_warning(f"    璀﹀憡: 缂哄皯蹇呴渶鍒楋紝瀹為檯鍒? {list(df.columns)}")
            
            # 浣跨敤鍐呯疆CDR3鍒嗘瀽鍔熻兘
            print_info("鐢熸垚CDR3鍒嗘瀽鏂囦欢...")
            self._export_cdr3_builtin(sample_data, output_dir, top_n=top_n)
            
        except Exception as e:
            logger.error(f"Error exporting CDR3 analysis: {e}", exc_info=True)
            print_error(f"CDR3鍒嗘瀽瀵煎嚭澶辫触: {e}")
            import traceback
            print_error(f"璇︾粏閿欒淇℃伅: {traceback.format_exc()}")

    def _build_cdr3_export_payload(self, sample_data: Dict[str, pd.DataFrame]):
        """
        灏嗗睍骞崇殑sample_data杞崲涓簑eb瀵煎嚭鏈嶅姟闇€瑕佺殑鏁版嵁缁撴瀯銆?        - 鏃犻摼妯″紡: {sample: df}
        - 閾炬ā寮? {chain: {sample: df}}
        """
        chain_payload: Dict[str, Dict[str, pd.DataFrame]] = defaultdict(dict)
        has_valid_chain = False

        for sample_name, df in sample_data.items():
            chain_type = "ALL"
            base_name = sample_name

            if "_" in sample_name:
                parts = sample_name.rsplit("_", 1)
                if len(parts) == 2 and parts[1].upper() in self.CHAIN_TYPES:
                    base_name = parts[0]
                    chain_type = parts[1].upper()
                    has_valid_chain = True

            # 閬垮厤閲嶅悕瑕嗙洊
            unique_name = base_name
            idx = 2
            while unique_name in chain_payload[chain_type]:
                unique_name = f"{base_name}_{idx}"
                idx += 1
            chain_payload[chain_type][unique_name] = df

        if has_valid_chain:
            return {chain: samples for chain, samples in chain_payload.items() if samples}

        if "ALL" in chain_payload and chain_payload["ALL"]:
            return chain_payload["ALL"]

        merged: Dict[str, pd.DataFrame] = {}
        for samples in chain_payload.values():
            for name, df in samples.items():
                unique_name = name
                idx = 2
                while unique_name in merged:
                    unique_name = f"{name}_{idx}"
                    idx += 1
                merged[unique_name] = df
        return merged
    
    def _export_cdr3_builtin(self, sample_data: Dict[str, pd.DataFrame], output_dir: Path, top_n: int = 100):
        """
        鍐呯疆CDR3鍒嗘瀽瀹炵幇锛堟棤闇€澶栭儴渚濊禆锛?        鎸夐摼绫诲瀷缁勭粐鏂囦欢锛屼笌flask_app淇濇寔涓€鑷?        """
        try:
            # Prefer web export service first; fallback to builtin export.
            try:
                from flask_app.services.cdr3_export_service import get_cdr3_export_service

                export_service = get_cdr3_export_service()
                export_payload = self._build_cdr3_export_payload(sample_data)

                exported_files = 0
                is_chain_based = isinstance(export_payload, dict) and bool(export_payload) and any(
                    isinstance(v, dict) for v in export_payload.values()
                )

                if is_chain_based:
                    for chain, chain_samples in export_payload.items():
                        if not chain_samples:
                            continue

                        shared_df = export_service.export_shared_cdr3_pairs(chain_samples, top_n=top_n)
                        if not shared_df.empty:
                            shared_excel = export_service.create_shared_cdr3_excel(shared_df)
                            with open(output_dir / f"{chain}_CDR3_Shared_List.xlsx", "wb") as f:
                                f.write(shared_excel)
                            exported_files += 1

                        top100_matrix = export_service.create_abundance_matrix_excel(
                            chain_samples, top_n=100, chain_name=chain
                        )
                        with open(output_dir / f"{chain}_Abundance_Union_Top100.xlsx", "wb") as f:
                            f.write(top100_matrix)
                        exported_files += 1

                        full_matrix = export_service.create_abundance_matrix_excel(
                            chain_samples, top_n=0, chain_name=chain
                        )
                        with open(output_dir / f"{chain}_Abundance_Union_Full.xlsx", "wb") as f:
                            f.write(full_matrix)
                        exported_files += 1

                        top100_analysis = export_service.create_top100_analysis_excel(
                            chain_samples, chain_name=chain
                        )
                        with open(output_dir / f"{chain}_Top100_Analysis.xlsx", "wb") as f:
                            f.write(top100_analysis)
                        exported_files += 1
                else:
                    shared_df = export_service.export_shared_cdr3_pairs(export_payload, top_n=top_n)
                    if not shared_df.empty:
                        shared_excel = export_service.create_shared_cdr3_excel(shared_df)
                        with open(output_dir / "CDR3_Shared_List.xlsx", "wb") as f:
                            f.write(shared_excel)
                        exported_files += 1

                    top100_matrix = export_service.create_abundance_matrix_excel(
                        export_payload, top_n=100, chain_name="All"
                    )
                    with open(output_dir / "Abundance_Union_Top100.xlsx", "wb") as f:
                        f.write(top100_matrix)
                    exported_files += 1

                    full_matrix = export_service.create_abundance_matrix_excel(
                        export_payload, top_n=0, chain_name="All"
                    )
                    with open(output_dir / "Abundance_Union_Full.xlsx", "wb") as f:
                        f.write(full_matrix)
                    exported_files += 1

                    top100_analysis = export_service.create_top100_analysis_excel(
                        export_payload, chain_name="All"
                    )
                    with open(output_dir / "Top100_Analysis.xlsx", "wb") as f:
                        f.write(top100_analysis)
                    exported_files += 1

                if exported_files == 0:
                    print_warning("鏈敓鎴愬彲瀵煎嚭鐨凜DR3鏂囦欢")
                else:
                    print_success(f"CDR3 export completed: {exported_files} files")
                return
            except Exception as web_export_error:
                print_warning(f"Web export service unavailable, fallback to builtin export: {web_export_error}")

            # 鎸夐摼绫诲瀷鍒嗙粍鏍锋湰
            from collections import defaultdict
            chain_groups = defaultdict(list)
            
            print_info(f"鍒嗘瀽鏍锋湰鍚嶆牸寮?..")
            for sample_name in sample_data.keys():
                print_info(f"  鏍锋湰: {sample_name}")
                if '_' in sample_name:
                    parts = sample_name.rsplit('_', 1)
                    if len(parts) == 2:
                        base_name, chain_type = parts
                        # 妫€鏌ユ槸鍚︽槸鏈夋晥鐨勯摼绫诲瀷
                        if chain_type.upper() in self.CHAIN_TYPES:
                            chain_groups[chain_type.upper()].append(sample_name)
                            print_info(f"    -> 閾剧被鍨? {chain_type.upper()}, 鍩虹鍚? {base_name}")
                        else:
                            # 涓嶆槸鏈夋晥閾剧被鍨?浣滀负鏅€氭牱鏈鐞?                            chain_groups['ALL'].append(sample_name)
                            print_info(f"    -> 鏃犻摼绫诲瀷('{chain_type}'涓嶆槸鏈夋晥閾?")
                    else:
                        chain_groups['ALL'].append(sample_name)
                        print_info(f"    -> 鏃犻摼绫诲瀷")
                else:
                    chain_groups['ALL'].append(sample_name)
                    print_info(f"    -> 鏃犻摼绫诲瀷(鏃犱笅鍒掔嚎)")
            
            # 鎵撳嵃鍒嗙粍缁撴灉
            print_info(f"閾惧垎缁勭粨鏋?")
            for chain, samples in chain_groups.items():
                print_info(f"  {chain}: {len(samples)} 涓牱鏈?- {samples[:3]}{'...' if len(samples) > 3 else ''}")
            
            # 1. 鐢熸垚CDR3鍏变韩鍒楄〃Excel
            print_info("鐢熸垚CDR3鍏变韩鍒楄〃...")
            self._generate_cdr3_shared_list(sample_data, chain_groups, output_dir)
            
            # 2. 鎸夐摼鐢熸垚涓板害鐭╅樀鍜孴op鍒嗘瀽
            all_chains = sorted(chain_groups.keys())
            print_info(f"鎸夐摼绫诲瀷缁勭粐鏂囦欢锛堝叡{len(all_chains)}涓摼锛?..")
            
            for chain_type in all_chains:
                chain_samples = chain_groups[chain_type]
                if len(chain_samples) < 2:
                    print_warning(f"  璺宠繃閾?{chain_type}: 鏍锋湰鏁颁笉瓒?({len(chain_samples)} < 2)")
                    continue
                
                # 鍒涘缓閾炬枃浠跺す
                chain_dir = output_dir / chain_type
                chain_dir.mkdir(parents=True, exist_ok=True)
                print_info(f"澶勭悊閾剧被鍨? {chain_type}")
                
                # 鎻愬彇璇ラ摼鐨勬牱鏈暟鎹?                chain_sample_data = {name: sample_data[name] for name in chain_samples}
                
                # 鐢熸垚涓板害鐭╅樀
                self._generate_abundance_matrices(chain_sample_data, chain_dir, chain_type, top_n)
                
                # 鐢熸垚Top鍒嗘瀽
                self._generate_top_analysis(chain_sample_data, chain_dir, chain_type, top_n)
            
            print_success("CDR3 analysis export completed")
            
        except Exception as e:
            logger.error(f"Error in builtin CDR3 export: {e}", exc_info=True)
            print_error(f"CDR3鍒嗘瀽澶辫触: {e}")
            raise
    
    def _generate_cdr3_shared_list(self, sample_data: Dict[str, pd.DataFrame], 
                                   chain_groups: Dict[str, List[str]], output_dir: Path):
        """鐢熸垚CDR3鍏变韩鍒楄〃Excel鏂囦欢"""
        def _make_unique_sheet_name(base_name: str, used_names: Set[str]) -> str:
            # Excel sheet names cannot contain: : \ / ? * [ ]
            sanitized = re.sub(r'[:\\/?*\[\]]', '_', base_name).strip() or "Sheet"
            candidate = sanitized[:31]
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate

            index = 2
            while True:
                suffix = f"_{index}"
                trimmed = sanitized[:max(1, 31 - len(suffix))]
                candidate = f"{trimmed}{suffix}"
                if candidate not in used_names:
                    used_names.add(candidate)
                    return candidate
                index += 1

        summary_columns = [
            'Chain',
            'Sample_A',
            'Sample_B',
            'Shared_CDR3',
            'Unique_A',
            'Unique_B',
            'Sharing_Rate_A',
            'Sharing_Rate_B',
            'Total_Abundance',
            'Avg_Abundance'
        ]

        with pd.ExcelWriter(output_dir / 'CDR3_Shared_List.xlsx', engine='openpyxl') as writer:
            # Summary sheet
            summary_data = []
            used_sheet_names = {'Summary'}
            
            for chain_type, samples in chain_groups.items():
                if len(samples) < 2:
                    continue
                
                for i, sample_a in enumerate(samples):
                    for sample_b in samples[i+1:]:
                        # 鑱氬悎寰楀埌涓板害瀛楀吀锛堥槻姝㈤噸澶岰DR3瀵艰嚧绱㈠紩闂锛?                        abundance_a = sample_data[sample_a].groupby('cdr3')['copy'].sum().to_dict()
                        abundance_b = sample_data[sample_b].groupby('cdr3')['copy'].sum().to_dict()
                        cdr3_a = set(abundance_a.keys())
                        cdr3_b = set(abundance_b.keys())
                        shared = cdr3_a & cdr3_b

                        pair_rows = []
                        for cdr3 in shared:
                            copy_a = abundance_a.get(cdr3, 0)
                            copy_b = abundance_b.get(cdr3, 0)
                            pair_rows.append({
                                'CDR3': cdr3,
                                f'{sample_a}_Copy': copy_a,
                                f'{sample_b}_Copy': copy_b,
                                'Min_Copy': min(copy_a, copy_b),
                                'Max_Copy': max(copy_a, copy_b),
                                'Total_Copy': copy_a + copy_b
                            })

                        pair_df = pd.DataFrame(pair_rows)
                        if not pair_df.empty:
                            pair_df = pair_df.sort_values(
                                ['Total_Copy', 'CDR3'],
                                ascending=[False, True]
                            )
                            sheet_name = _make_unique_sheet_name(
                                f"{sample_a}_vs_{sample_b}",
                                used_sheet_names
                            )
                            pair_df.to_excel(writer, sheet_name=sheet_name, index=False)
                         
                        summary_data.append({
                            'Chain': chain_type,
                            'Sample_A': sample_a,
                            'Sample_B': sample_b,
                            'Shared_CDR3': len(shared),
                            'Unique_A': len(cdr3_a),
                            'Unique_B': len(cdr3_b),
                            'Sharing_Rate_A': f"{len(shared)/len(cdr3_a)*100:.1f}%" if len(cdr3_a) > 0 else "0%",
                            'Sharing_Rate_B': f"{len(shared)/len(cdr3_b)*100:.1f}%" if len(cdr3_b) > 0 else "0%",
                            'Total_Abundance': pair_df['Total_Copy'].sum() if not pair_df.empty else 0,
                            'Avg_Abundance': pair_df['Total_Copy'].mean() if not pair_df.empty else 0
                        })
            
            summary_df = pd.DataFrame(summary_data, columns=summary_columns)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

            if summary_df.empty:
                print_warning("No exportable samples found (Summary sheet is empty)")
            else:
                print_success(f"Saved CDR3_Shared_List.xlsx (Summary + {len(summary_df)} sample sheets)")
    
    def _generate_abundance_matrices(self, sample_data: Dict[str, pd.DataFrame], 
                                     chain_dir: Path, chain_type: str, top_n: int):
        """鐢熸垚涓板害鐭╅樀锛圱op N鍜屽畬鏁寸増锛?"""
        # 鏀堕泦鎵€鏈塁DR3鍙婂叾涓板害
        all_cdr3_abundance = defaultdict(lambda: defaultdict(float))
        
        for sample_name, df in sample_data.items():
            grouped = df.groupby('cdr3')['copy'].sum()
            for cdr3, abundance in grouped.items():
                all_cdr3_abundance[cdr3][sample_name] = abundance
        
        # 璁＄畻鎬讳赴搴﹀苟鎺掑簭
        cdr3_total = {cdr3: sum(abundances.values()) 
                      for cdr3, abundances in all_cdr3_abundance.items()}
        sorted_cdr3 = sorted(cdr3_total.items(), key=lambda x: x[1], reverse=True)
        
        # Top N鐭╅樀
        top_cdr3s = [cdr3 for cdr3, _ in sorted_cdr3[:top_n]]
        top_matrix_data = []
        for cdr3 in top_cdr3s:
            row = {'CDR3': cdr3}
            row.update({sample: all_cdr3_abundance[cdr3].get(sample, 0) 
                       for sample in sample_data.keys()})
            top_matrix_data.append(row)
        
        if top_matrix_data:
            pd.DataFrame(top_matrix_data).to_excel(
                chain_dir / f'Abundance_Union_Top{top_n}.xlsx', index=False)
            print_success(f"  宸蹭繚瀛? {chain_type}/Abundance_Union_Top{top_n}.xlsx ({len(top_matrix_data)} CDR3s)")
        
        # 瀹屾暣鐭╅樀
        full_matrix_data = []
        for cdr3, _ in sorted_cdr3:
            row = {'CDR3': cdr3}
            row.update({sample: all_cdr3_abundance[cdr3].get(sample, 0) 
                       for sample in sample_data.keys()})
            full_matrix_data.append(row)
        
        if full_matrix_data:
            pd.DataFrame(full_matrix_data).to_excel(
                chain_dir / 'Abundance_Union_Full.xlsx', index=False)
            print_success(f"  宸蹭繚瀛? {chain_type}/Abundance_Union_Full.xlsx ({len(full_matrix_data)} CDR3s)")
    
    def _generate_top_analysis(self, sample_data: Dict[str, pd.DataFrame], 
                               chain_dir: Path, chain_type: str, top_n: int):
        """鐢熸垚Top N鍒嗘瀽鏂囦欢"""
        with pd.ExcelWriter(chain_dir / f'Top{top_n}_Analysis.xlsx', engine='openpyxl') as writer:
            # 鍚勬牱鏈琓op N
            for sample_name, df in sorted(sample_data.items()):
                top_df = df.nlargest(top_n, 'copy')[['cdr3', 'copy']].copy()
                base_name = sample_name.rsplit('_', 1)[0] if '_' in sample_name else sample_name
                sheet_name = f'{base_name}_Top{top_n}'[:31]
                top_df.to_excel(writer, sheet_name=sheet_name, index=False)
                print_success(f"    娣诲姞 {sheet_name} ({len(top_df)} CDR3s)")
            
            print_success(f"  宸蹭繚瀛? {chain_type}/Top{top_n}_Analysis.xlsx")
    
    def _generate_readme(self, output_dir: Path, all_chains: List[str], top_n: int):
        """鐢熸垚README鏂囦欢"""
        readme_content = f"""CDR3 Analysis Output
====================

Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Detected Chains: {', '.join(all_chains)}

Directory Structure:
CDR3_Shared/
  CDR3_Shared_List.xlsx
  <CHAIN>/Abundance_Union_Top{top_n}.xlsx
  <CHAIN>/Abundance_Union_Full.xlsx
  <CHAIN>/Top{top_n}_Analysis.xlsx
  README.txt
"""
        with open(output_dir / 'README.txt', 'w', encoding='utf-8') as f:
            f.write(readme_content)
        print_success("宸蹭繚瀛? README.txt")
    
    def _export_cdr3_as_files_old(self, export_service, sample_data: Dict[str, pd.DataFrame], output_dir: Path, top_n: int = 100):
        """
        鐩存帴瀵煎嚭CDR3鍒嗘瀽涓烘枃浠跺す缁撴瀯锛堟寜閾剧被鍨嬪垎绫伙級
        涓庣綉椤电増鐨刧enerate_complete_export_zip淇濇寔涓€鑷寸殑鏂囦欢缁勭粐缁撴瀯
        """
        try:
            # 1. 鐢熸垚CDR3鍏变韩鍒楄〃Excel鏂囦欢
            print_info("鐢熸垚CDR3鍏变韩鍒楄〃...")
            excel_bytes = export_service.generate_excel(sample_data, include_summary=True)
            excel_path = output_dir / 'CDR3_Shared_List.xlsx'
            with open(excel_path, 'wb') as f:
                f.write(excel_bytes)
            print_success(f"宸蹭繚瀛? {excel_path}")
            
            # 2. 鐢熸垚鍚勯摼涓板害鐭╅樀锛圱op100鍜屽畬鏁寸増锛?            print_info("鐢熸垚鍚勯摼涓板害鐭╅樀...")
            chain_matrices_top100 = export_service.generate_shared_abundance_matrix_by_chain(sample_data, top_n)
            chain_matrices_full = export_service.generate_shared_abundance_matrix_by_chain(sample_data, top_n=None)
            
            # 3. 鐢熸垚Top100鍒嗘瀽鏂囦欢锛堜氦闆嗙煩闃?+ 鍚勬牱鏈琓op100锛?            print_info("鐢熸垚Top100鍒嗘瀽...")
            individual_top100 = export_service.generate_individual_top100(sample_data, top_n)
            top100_intersection = export_service.generate_top100_intersection_matrix(sample_data, top_n)
            
            # 鑾峰彇鎵€鏈夐摼绫诲瀷
            all_chains = set()
            all_chains.update(chain_matrices_top100.keys())
            all_chains.update(chain_matrices_full.keys())
            all_chains.update(top100_intersection.keys())
            
            # 鎸夐摼绫诲瀷鍒嗙粍individual_top100
            chain_individual_map = {}
            for sample_name, top_df in individual_top100.items():
                if '_' in sample_name:
                    parts = sample_name.rsplit('_', 1)
                    if len(parts) == 2:
                        base_name, chain_type = parts
                        if chain_type not in chain_individual_map:
                            chain_individual_map[chain_type] = {}
                        chain_individual_map[chain_type][sample_name] = top_df
            
            # 涓烘瘡涓摼绫诲瀷鍒涘缓鐙珛鏂囦欢澶瑰苟淇濆瓨鏂囦欢
            print_info(f"鎸夐摼绫诲瀷缁勭粐鏂囦欢锛堝叡{len(all_chains)}涓摼锛?..")
            for chain_type in sorted(all_chains):
                # 鍒涘缓閾剧被鍨嬫枃浠跺す
                chain_dir = output_dir / chain_type
                chain_dir.mkdir(parents=True, exist_ok=True)
                print_info(f"澶勭悊閾剧被鍨? {chain_type}")
                
                # 淇濆瓨Top100涓板害鐭╅樀
                if chain_type in chain_matrices_top100:
                    abundance_df = chain_matrices_top100[chain_type]
                    excel_path = chain_dir / f"Abundance_Union_Top{top_n}.xlsx"
                    abundance_df.to_excel(excel_path, index=False)
                    print_success(f"  宸蹭繚瀛? {chain_type}/Abundance_Union_Top{top_n}.xlsx ({len(abundance_df)} CDR3s)")
                
                # 淇濆瓨瀹屾暣涓板害鐭╅樀
                if chain_type in chain_matrices_full:
                    abundance_df = chain_matrices_full[chain_type]
                    excel_path = chain_dir / "Abundance_Union_Full.xlsx"
                    abundance_df.to_excel(excel_path, index=False)
                    print_success(f"  宸蹭繚瀛? {chain_type}/Abundance_Union_Full.xlsx ({len(abundance_df)} CDR3s)")
                
                # 淇濆瓨Top100鍒嗘瀽鏂囦欢锛堜氦闆嗙煩闃?+ 鍚勬牱鏈琓op100锛?                if chain_type in top100_intersection or chain_type in chain_individual_map:
                    excel_path = chain_dir / f"Top{top_n}_Analysis.xlsx"
                    
                    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                        # 娣诲姞浜ら泦鐭╅樀
                        if chain_type in top100_intersection:
                            intersection_df = top100_intersection[chain_type]
                            intersection_df.to_excel(writer, sheet_name=f'{chain_type}_Intersection', index=False)
                            print_success(f"    娣诲姞 {chain_type}_Intersection ({len(intersection_df)} CDR3s)")
                        
                        # 娣诲姞鍚勬牱鏈琓op100
                        if chain_type in chain_individual_map:
                            for sample_name in sorted(chain_individual_map[chain_type].keys()):
                                top_df = chain_individual_map[chain_type][sample_name]
                                base_name = sample_name.rsplit('_', 1)[0] if '_' in sample_name else sample_name
                                sheet_name = f'{base_name}_Top{top_n}'
                                
                                if len(sheet_name) > 31:
                                    sheet_name = sheet_name[:31]
                                
                                top_df.to_excel(writer, sheet_name=sheet_name, index=False)
                                print_success(f"    娣诲姞 {sheet_name} ({len(top_df)} CDR3s)")
                    
                    print_success(f"  宸蹭繚瀛? {chain_type}/Top{top_n}_Analysis.xlsx")
            
            # 4. Generate README
            readme_content = f"""CDR3 Analysis Output
====================

Detected Chains: {', '.join(sorted(all_chains))}
Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Directory Structure:
CDR3_Shared/
  CDR3_Shared_List.xlsx
  <CHAIN>/Abundance_Union_Top{top_n}.xlsx
  <CHAIN>/Abundance_Union_Full.xlsx
  <CHAIN>/Top{top_n}_Analysis.xlsx
  README.txt
"""
            readme_path = output_dir / 'README.txt'
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            print_success(f"Saved {readme_path}")
            
            # 5. Completion logs
            print_success("CDR3 analysis export completed")
            print_info(f"杈撳嚭鐩綍: {output_dir}")
            print_info("\n鐢熸垚鐨勬枃浠剁粨鏋?")
            print(f"  {output_dir.name}/")
            print(f"    鈹溾攢鈹€ CDR3_Shared_List.xlsx")
            
            for chain in sorted(all_chains):
                print(f"    鈹溾攢鈹€ {chain}/")
                print(f"    鈹?  鈹溾攢鈹€ Abundance_Union_Top{top_n}.xlsx")
                print(f"    鈹?  鈹溾攢鈹€ Abundance_Union_Full.xlsx")
                print(f"    鈹?  鈹斺攢鈹€ Top{top_n}_Analysis.xlsx")
            
            print(f"    鈹斺攢鈹€ README.txt")
            
        except Exception as e:
            logger.error(f"Error exporting CDR3 files: {e}", exc_info=True)
            print_error(f"CDR3鏂囦欢瀵煎嚭澶辫触: {e}")
            raise
    
    def _export_cdr3_fallback(self, sample_data: Dict[str, pd.DataFrame], output_dir: Path):
        """澶囩敤鐨凜DR3瀵煎嚭鏂规硶锛堢敓鎴愮畝鍗曠殑CSV鏂囦欢锛?"""
        print_info("浣跨敤澶囩敤鏂规硶瀵煎嚭CDR3鍏变韩鍒楄〃...")
        
        try:
            sample_names = list(sample_data.keys())
            n_samples = len(sample_names)
            
            # 鏋勫缓姣忎釜鏍锋湰鐨勪赴搴﹀瓧鍏?            abundance_dicts = {}
            for sample_name, df in sample_data.items():
                grouped = df.groupby('cdr3')['copy'].sum()
                abundance_dicts[sample_name] = grouped.to_dict()
            
            # 鑾峰彇鎵€鏈塁DR3鐨勫苟闆?            all_cdr3s = set()
            for abundance_dict in abundance_dicts.values():
                all_cdr3s.update(abundance_dict.keys())
            
            # 鏋勫缓璇︾粏鐨凜DR3鍏变韩鍒楄〃
            cdr3_list = []
            for cdr3 in all_cdr3s:
                row = {'CDR3': cdr3}
                
                # 娣诲姞姣忎釜鏍锋湰鐨勬嫹璐濇暟
                total_copy = 0
                sample_count = 0
                present_samples = []
                
                for sample_name in sample_names:
                    copy_count = abundance_dicts[sample_name].get(cdr3, 0)
                    row[f'{sample_name}_Copy'] = copy_count if copy_count > 0 else ''
                    
                    if copy_count > 0:
                        total_copy += copy_count
                        sample_count += 1
                        present_samples.append(sample_name)
                
                row['Total_Copy'] = total_copy
                row['Sample_Count'] = sample_count
                row['Present_In'] = ','.join(present_samples)
                row['Sharing_Rate'] = f"{sample_count}/{n_samples}"
                
                cdr3_list.append(row)
            
            # 鍒涘缓DataFrame骞舵帓搴?            df_result = pd.DataFrame(cdr3_list)
            
            # 鎸夋牱鏈暟閲忛檷搴忋€佹€绘嫹璐濇暟闄嶅簭鎺掑簭
            df_result = df_result.sort_values(['Sample_Count', 'Total_Copy'], ascending=[False, False])
            
            # 閲嶆柊鎺掑垪鍒楅『搴?            copy_cols = [col for col in df_result.columns if col.endswith('_Copy') and col != 'Total_Copy']
            ordered_cols = ['CDR3', 'Sample_Count', 'Sharing_Rate', 'Total_Copy', 'Present_In'] + copy_cols
            df_result = df_result[ordered_cols]
            
            # 淇濆瓨CSV鏂囦欢
            output_path = output_dir / 'CDR3_Sharing_List.csv'
            df_result.to_csv(output_path, index=False, encoding='utf-8-sig')
            
            print_success(f"宸插鍑篊DR3鍏变韩鍒楄〃: {output_path}")
            
            # 缁熻淇℃伅
            total_cdr3 = len(df_result)
            unique_to_one = (df_result['Sample_Count'] == 1).sum()
            shared_by_2 = (df_result['Sample_Count'] == 2).sum()
            shared_by_3plus = (df_result['Sample_Count'] >= 3).sum()
            
            print_info(f"鎬籆DR3鏁? {total_cdr3}")
            print_info(f"浠?涓牱鏈嫭鏈? {unique_to_one} ({unique_to_one/total_cdr3*100:.1f}%)")
            print_info(f"2涓牱鏈叡浜? {shared_by_2} ({shared_by_2/total_cdr3*100:.1f}%)")
            print_info(f"3涓互涓婃牱鏈叡浜? {shared_by_3plus} ({shared_by_3plus/total_cdr3*100:.1f}%)")
            
        except Exception as e:
            print_error(f"澶囩敤瀵煎嚭鏂规硶涔熷け璐? {e}")
            logger.error(f"Fallback export failed: {e}", exc_info=True)
    
    def run(self):
        """杩愯鐑浘鐢熸垚娴佺▼"""
        print_header("Immune Repertoire Similarity Heatmap Tool")
        print(f"鏃堕棿: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. 鎵弿鏍锋湰
        samples = self.scan_samples()
        if not samples:
            print_error("No sample files found")
            return False
        
        # 2. 浜や簰妯″紡锛氶€夋嫨鏍锋湰
        if self.interactive:
            self.interactive_select_samples()
            self.interactive_rename_samples()
            self.interactive_reorder_samples()
            
            # If chain types are detected, allow selecting chains.
            if self.detected_chains:
                self.interactive_select_chains()
        else:
            # Batch mode: use all samples.
            self.selected_samples = list(samples.keys())
            self.sample_display_names = {name: name for name in self.selected_samples}
        
        # 3. 鍔犺浇绗竴涓牱鏈互妫€娴嬪垪
        first_sample = self.selected_samples[0]
        first_file = self.scanned_samples[first_sample][0]
        first_df = self.load_data(first_file)
        
        # 4. Interactive mode: field mapping + settings
        if self.interactive:
            self.interactive_field_mapping(first_df)
            self.interactive_settings()
        else:
            # Auto detect fields.
            if not self.cdr3_col or not self.copy_col:
                self.cdr3_col, self.copy_col = self.auto_detect_columns(first_df)
        
        if not self.cdr3_col or not self.copy_col:
            print_error("Failed to detect CDR3/copy columns")
            return False
        
        # 5. Load all selected samples (grouped by chain)
        print_header("Loading sample data")
        
        # 鎸夐摼鍒嗙粍鐨勬暟鎹粨鏋? {chain: {sample_name: df}}
        chain_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        # 鐢ㄤ簬CDR3瀵煎嚭鐨勬暟鎹紙灞曞钩鏍煎紡锛? {sample_name_chain: df}
        sample_data_with_chain: Dict[str, pd.DataFrame] = {}
        
        if self.chains:
            # 閾炬ā寮忥細鎸夐摼鍒嗙粍鍔犺浇鏁版嵁
            for chain in self.chains:
                chain_data[chain] = {}
            
            for sample_name in self.selected_samples:
                file_paths = self.scanned_samples[sample_name]
                display_name = self.sample_display_names.get(sample_name, sample_name)
                
                for fp in file_paths:
                    file_chain = self._extract_chain_from_filename(fp.name)
                    if file_chain not in self.chains:
                        continue
                    
                    print_info(f"鍔犺浇: {display_name} [{file_chain}] <- {fp.name}")
                    
                    try:
                        df = self.load_data(fp)
                        
                        if self.cdr3_col not in df.columns:
                            print_warning(f"  CDR3鍒?'{self.cdr3_col}' 涓嶅瓨鍦紝璺宠繃")
                            continue
                        if self.copy_col not in df.columns:
                            print_warning(f"  鎷疯礉鏁板垪 '{self.copy_col}' 涓嶅瓨鍦紝璺宠繃")
                            continue
                        
                        # Normalize data columns.
                        normalized_df = pd.DataFrame({
                            'cdr3': df[self.cdr3_col],
                            'copy': pd.to_numeric(df[self.copy_col], errors='coerce').fillna(0)
                        })
                        
                        # 娓呯悊鏁版嵁
                        normalized_df = normalized_df.dropna(subset=['cdr3', 'copy'])
                        normalized_df = normalized_df.groupby('cdr3', as_index=False)['copy'].sum()
                        
                        # 鎸夐摼鍒嗙粍瀛樺偍锛堢敤浜庣儹鍥撅級
                        chain_data[file_chain][display_name] = normalized_df
                        
                        # 灞曞钩鏍煎紡瀛樺偍锛堢敤浜嶤DR3瀵煎嚭锛?                        sample_data_with_chain[f"{display_name}_{file_chain}"] = normalized_df
                        print_success(f"  鍔犺浇 {len(normalized_df)} 鏉＄嫭鐗笴DR3搴忓垪")
                        
                    except Exception as e:
                        print_error(f"  鍔犺浇澶辫触: {e}")
                        continue
            
            # 绉婚櫎鏍锋湰鏁颁笉瓒?鐨勯摼
            chain_data = {chain: samples for chain, samples in chain_data.items() if len(samples) >= 2}
            
            if not chain_data:
                print_error("鎵€鏈夐摼鐨勬牱鏈暟閲忛兘涓嶈冻2涓紝鏃犳硶鐢熸垚鐑浘")
                return False
            
            print_success(f"Loaded data for {len(chain_data)} chains")
            for chain, samples in chain_data.items():
                print_info(f"  {chain}: {len(samples)} samples")
        
        else:
            # No-chain mode: use one file per sample.
            sample_data = {}
            for sample_name in self.selected_samples:
                file_paths = self.scanned_samples[sample_name]
                file_path = file_paths[0]
                display_name = self.sample_display_names.get(sample_name, sample_name)
                print_info(f"鍔犺浇: {display_name} <- {file_path.name}")
                
                try:
                    df = self.load_data(file_path)
                    
                    if self.cdr3_col not in df.columns:
                        print_warning(f"  CDR3鍒?'{self.cdr3_col}' 涓嶅瓨鍦紝璺宠繃")
                        continue
                    if self.copy_col not in df.columns:
                        print_warning(f"  鎷疯礉鏁板垪 '{self.copy_col}' 涓嶅瓨鍦紝璺宠繃")
                        continue
                    
                    # Normalize data columns.
                    normalized_df = pd.DataFrame({
                        'cdr3': df[self.cdr3_col],
                        'copy': pd.to_numeric(df[self.copy_col], errors='coerce').fillna(0)
                    })
                    
                    # 娓呯悊鏁版嵁
                    normalized_df = normalized_df.dropna(subset=['cdr3', 'copy'])
                    normalized_df = normalized_df.groupby('cdr3', as_index=False)['copy'].sum()
                    
                    sample_data[display_name] = normalized_df
                    
                    # 鐢ㄤ簬CDR3瀵煎嚭
                    chain = self._extract_chain_from_filename(file_path.name)
                    if chain:
                        cdr3_export_name = f"{display_name}_{chain}"
                    else:
                        cdr3_export_name = display_name if '_' in display_name else f"{display_name}_UNKNOWN"
                    sample_data_with_chain[cdr3_export_name] = normalized_df
                    print_success(f"  鍔犺浇 {len(normalized_df)} 鏉＄嫭鐗笴DR3搴忓垪")
                    
                except Exception as e:
                    print_error(f"  鍔犺浇澶辫触: {e}")
                    continue
            
            if len(sample_data) < 2:
                print_error("At least 2 samples are required to generate heatmaps")
                return False
            
            # Wrap into single-chain structure.
            chain_data = {'ALL': sample_data}
            print_success(f"Loaded {len(sample_data)} samples")
        
        # 6. 鎸夐摼鐢熸垚鐑浘锛堟寜閾惧垱寤哄瓙鏂囦欢澶癸級
        print_header("璁＄畻鐩镐技搴︾煩闃靛苟鐢熸垚鐑浘")
        
        all_sample_names = []  # 鐢ㄤ簬鍏冩暟鎹?        report_sections: List[Dict[str, Any]] = []  # 缃戦〉鎶ュ憡鏁版嵁
        
        for chain, sample_data in chain_data.items():
            sample_names = list(sample_data.keys())
            all_sample_names.extend([f"{name}_{chain}" if chain != 'ALL' else name for name in sample_names])
            
            print_info(f"\n澶勭悊閾? {chain} ({len(sample_names)} 涓牱鏈?")
            
            # 璁＄畻鐩镐技搴︾煩闃?            similarities = self.calculate_similarities(sample_data)
            section_entries: List[Dict[str, Any]] = []
            
            # 涓烘瘡涓摼鍒涘缓瀛愭枃浠跺す锛堜笌 flask_app 淇濇寔涓€鑷达級
            if chain != 'ALL':
                chain_heatmap_dir = self.heatmap_dir / chain
                chain_metric_dir = self.metric_dir / chain
                chain_heatmap_dir.mkdir(parents=True, exist_ok=True)
                chain_metric_dir.mkdir(parents=True, exist_ok=True)
            else:
                chain_heatmap_dir = self.heatmap_dir
                chain_metric_dir = self.metric_dir
            
            # 涓烘瘡涓寚鏍囩敓鎴愮儹鍥?            for metric in self.METRICS:
                # 鏂囦欢鍚嶆牸寮? metric_heatmap.png 鍜?metric_heatmap.csv
                heatmap_filename = f"{metric}_heatmap.png"
                matrix_filename = f"{metric}_heatmap.csv"
                
                # 淇濆瓨鐑浘PNG
                heatmap_path = chain_heatmap_dir / heatmap_filename
                # 璁剧疆鏍囬鏍煎紡: chain_metric (濡?IGH_r2_inner)
                original_title = self.title
                if chain != 'ALL':
                    self.title = f"{chain}_{metric}"
                else:
                    self.title = metric
                self.generate_heatmap(similarities[metric], sample_names, metric, heatmap_path)
                self.title = original_title
                
                # 淇濆瓨鐭╅樀CSV
                matrix_path = chain_metric_dir / matrix_filename
                self.save_matrix(similarities[metric], sample_names, metric, matrix_path)
                table_data = self._build_matrix_table_data(similarities[metric], sample_names)

                section_entries.append({
                    'metric_name': metric,
                    'metric_label': self.METRIC_NAMES.get(metric, metric),
                    'image_src': heatmap_path.relative_to(self.output_dir).as_posix(),
                    'csv_rel_path': matrix_path.relative_to(self.output_dir).as_posix(),
                    'table_columns': table_data['columns'],
                    'table_rows': table_data['rows'],
                })

            if section_entries:
                if chain != 'ALL':
                    section_id = f"chain_{re.sub(r'[^A-Za-z0-9_-]+', '_', chain)}"
                    section_title = f"Chain: {chain}"
                else:
                    section_id = 'original'
                    section_title = 'Original Sample Heatmaps'
                report_sections.append({
                    'id': section_id,
                    'title': section_title,
                    'entries': section_entries
                })
        
        # 8. 瀵煎嚭CDR3瀹屾暣鍒嗘瀽锛堥粯璁ゆ墽琛岋級
        print_header("瀵煎嚭CDR3鍒嗘瀽")
        if len(sample_data_with_chain) >= 2:
            cdr3_shared_dir = self.output_dir / 'CDR3_Shared'
            cdr3_shared_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.export_cdr3_complete_analysis(sample_data_with_chain, cdr3_shared_dir, top_n=100)
            except Exception as e:
                print_error(f"CDR3鍒嗘瀽瀵煎嚭澶辫触: {e}")
                import traceback
                print_error(traceback.format_exc())
        else:
            print_warning(f"鏍锋湰鏁颁笉瓒筹紙{len(sample_data_with_chain)}锛夛紝璺宠繃CDR3鍒嗘瀽")
        
        # 9. 鐢熸垚缃戦〉鐗堝垎浜姤鍛婏紙鍙€夛紝榛樿鍏抽棴锛?        report_path = None
        if self.generate_web_report:
            print_header("鐢熸垚缃戦〉鍒嗕韩鎶ュ憡")
            report_scan_base = Path(self.report_scan_path).expanduser() if self.report_scan_path else self.input_dir
            if not report_scan_base.exists():
                print_warning(f"鎶ュ憡鎵弿璺緞涓嶅瓨鍦紝鍥為€€褰撳墠浠诲姟缁撴灉: {report_scan_base}")
                report_scan_base = self.output_dir

            report_context = {
                'source': 'standalone_heatmap_cli',
                'base_path': str(self.input_dir),
                'scan_base': str(report_scan_base),
                'selected_samples': self.selected_samples,
                'selected_chains': self.chains if self.chains else None,
                'generated_at': datetime.now().isoformat()
            }

            modules = self._discover_shared_analysis_modules(report_scan_base)
            if modules:
                print_info(f"Detected {len(modules)} modules (*/output/shared_analysis)")
                report_path = self._generate_multi_module_web_report(
                    modules=modules,
                    output_path=self.output_dir / 'similarity_heatmap_report.html',
                    context=report_context
                )
            else:
                print_warning("鏈彂鐜板彲鑱氬悎妯″潡锛屼娇鐢ㄥ綋鍓嶄换鍔＄粨鏋滅敓鎴愬崟妯″潡鎶ュ憡")
                report_path = self._generate_web_share_report(report_sections, report_context)
        else:
            print_info("宸茶烦杩囩綉椤电増鍒嗕韩鎶ュ憡鐢熸垚锛堥粯璁ゅ叧闂紝鍙€氳繃 --web-report 寮€鍚級")
        
        # 10. Save metadata
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'input_dir': str(self.input_dir),
            'output_dir': str(self.output_dir),
            'samples': all_sample_names,
            'n_samples': len(all_sample_names),
            'metrics': self.METRICS,
            'cdr3_column': self.cdr3_col,
            'copy_column': self.copy_col,
            'title': self.title,
            'chains': list(chain_data.keys()) if self.chains else None,
            'web_report_enabled': self.generate_web_report,
            'web_report': str(report_path.relative_to(self.output_dir)) if report_path else None
        }
        
        metadata_path = self.output_dir / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # 11. 瀹屾垚
        print_header("Heatmap generation completed")
        print_success(f"杈撳嚭鐩綍: {self.output_dir}")
        print("\n鐢熸垚鐨勬枃浠剁粨鏋?")
        print(f"  {self.output_dir.name}/")
        print(f"    鈹溾攢鈹€ heatmap/")
        if self.chains:
            for chain in sorted(chain_data.keys()):
                if chain != 'ALL':
                    print(f"    鈹?  鈹溾攢鈹€ {chain}/")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ expression_sharing_heatmap.png")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ morisita_horn_heatmap.png")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ cdr3_sharing_heatmap.png")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ r2_inner_heatmap.png")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ r2_outer_heatmap.png")
                    print(f"    鈹?  鈹?  鈹斺攢鈹€ sorensen_heatmap.png")
        else:
            print(f"    鈹?  鈹溾攢鈹€ *_heatmap.png (6涓寚鏍?")
        print(f"    鈹溾攢鈹€ metric/")
        if self.chains:
            for chain in sorted(chain_data.keys()):
                if chain != 'ALL':
                    print(f"    鈹?  鈹溾攢鈹€ {chain}/")
                    print(f"    鈹?  鈹?  鈹斺攢鈹€ *_heatmap.csv (6涓寚鏍?")
        else:
            print(f"    鈹?  鈹溾攢鈹€ *_heatmap.csv (6涓寚鏍?")
        print(f"    鈹溾攢鈹€ CDR3_Shared/")
        print(f"    鈹?  鈹溾攢鈹€ CDR3_Shared_List.xlsx")
        if self.chains:
            for chain in sorted(chain_data.keys()):
                if chain != 'ALL':
                    print(f"    鈹?  鈹溾攢鈹€ {chain}/")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ Abundance_Union_Top100.xlsx")
                    print(f"    鈹?  鈹?  鈹溾攢鈹€ Abundance_Union_Full.xlsx")
                    print(f"    鈹?  鈹?  鈹斺攢鈹€ Top100_Analysis.xlsx")
        if report_path:
            print(f"    鈹溾攢鈹€ similarity_heatmap_report.html")
        print(f"    鈹斺攢鈹€ metadata.json")
        
        return True


def run_report_only_mode(args) -> bool:
    """
    Report-only mode:
    - scan modules under */output/shared_analysis
    - render one aggregated HTML report
    - do not run heatmap calculations
    """
    try:
        from aggregate_shared_analysis_report import (
            discover_modules,
            build_module_sections,
            build_cdr3_table_entries,
            render_report_html,
        )
    except Exception as e:
        print_error(f"无法加载报告聚合模块: {e}")
        return False

    scan_root = Path(args.report_scan_path).expanduser().resolve() if args.report_scan_path else Path(args.input).expanduser().resolve()
    if not scan_root.exists() or not scan_root.is_dir():
        print_error(f"报告扫描根路径不存在: {scan_root}")
        return False

    if args.report_output:
        output_html = Path(args.report_output).expanduser().resolve()
    elif args.output and str(args.output).lower().endswith('.html'):
        output_html = Path(args.output).expanduser().resolve()
    elif args.output:
        output_html = (Path(args.output).expanduser().resolve() / 'pipeline_comparison_report.html')
    else:
        output_html = scan_root / 'pipeline_comparison_report.html'

    modules = discover_modules(scan_root)
    if not modules:
        print_error(f"未找到任何 output/shared_analysis 模块: {scan_root}")
        return False

    report_dir = output_html.parent.resolve()
    for module in modules:
        shared_dir = Path(module['shared_dir'])
        module['sections'] = build_module_sections(
            shared_dir=shared_dir,
            report_dir=report_dir,
            max_rows=args.report_max_rows,
            max_cols=args.report_max_cols,
        )
        module['cdr3_table_entries'] = build_cdr3_table_entries(
            shared_dir=shared_dir,
            report_dir=report_dir,
            max_rows=args.report_max_rows,
            max_cols=args.report_max_cols,
        )

    modules = [m for m in modules if m.get('sections') or m.get('cdr3_table_entries')]
    if not modules:
        print_error(f"发现模块但没有可渲染内容: {scan_root}")
        return False

    report_html = render_report_html(
        title=args.report_title,
        scan_root=scan_root,
        modules=modules,
        report_dir=report_dir,
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(report_html, encoding='utf-8')

    print_success(f"报告生成成功: {output_html}")
    print_info(f"聚合模块数: {len(modules)}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='鍏嶇柅缁勫簱鐩镐技搴︾儹鍥剧敓鎴愬伐鍏?- 鎸夐摼鍒嗙粍鐢熸垚鐑浘锛岃嚜鍔ㄦ墽琛孋DR3鍒嗘瀽',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
绀轰緥:
  # 浜や簰妯″紡锛堟帹鑽愶紝鍏佽閫夋嫨鏍锋湰鍜岄厤缃級
  python standalone_heatmap_cli.py -i /path/to/samples --interactive
  
  # 鎵归噺妯″紡锛堣嚜鍔ㄥ鐞嗘墍鏈夋牱鏈級
  python standalone_heatmap_cli.py -i /path/to/samples
  
  # 鎸囧畾杈撳嚭鐩綍鍜屽垪鍚?  python standalone_heatmap_cli.py -i ./data -o ./output --cdr3-col "CDR3(pep)" --copy-col "copy"
  
  # 鍙垎鏋愮壒瀹氶摼绫诲瀷
  python standalone_heatmap_cli.py -i ./data --chains IGH,IGK,IGL
  
  # 鐢熸垚缃戦〉鐗堝垎浜姤鍛婏紙榛樿鍏抽棴锛?  python standalone_heatmap_cli.py -i ./data --web-report
  
  # 鎸囧畾鎶ュ憡鎵弿鏍硅矾寰勶紙閫掑綊鑱氬悎 */output/shared_analysis锛?  python standalone_heatmap_cli.py -i ./data --web-report --report-scan-path /workspace/data_shared/To_ZQY/20260305_TRB_fixed12_split
        """
    )
    
    parser.add_argument('--input', '-i', required=True, help='Input directory path')
    parser.add_argument('--output', '-o', default=None, help='Output directory path')
    parser.add_argument('--interactive', action='store_true', help='Enable interactive mode')
    parser.add_argument('--cdr3-col', help='CDR3 column name (auto-detect by default)')
    parser.add_argument('--copy-col', help='Copy/expression column name (auto-detect by default)')
    parser.add_argument('--mode', choices=['chain', 'traditional', 'auto'], default='auto', 
                        help='Analysis mode: chain/traditional/auto')
    parser.add_argument('--chains', help='Chain types to analyze, comma-separated (e.g. IGH,IGK,IGL)')
    parser.add_argument('--title', default='Similarity Heatmap', help='Heatmap title')
    parser.add_argument('--no-values', action='store_true', help='Hide values on heatmap')
    parser.add_argument('--web-report', action='store_true', help='Generate web report')
    parser.add_argument('--report-scan-path', help='Report scan base path for */output/shared_analysis')
    parser.add_argument('--report-only', action='store_true', help='仅生成聚合网页报告（不执行热图计算）')
    parser.add_argument('--report-output', help='report-only模式下的HTML输出路径')
    parser.add_argument('--report-title', default='Pipeline Comparison Report', help='report-only模式下报告标题')
    parser.add_argument('--report-max-rows', type=int, default=0, help='report-only模式下每个表格最大预览行数（0表示不限制）')
    parser.add_argument('--report-max-cols', type=int, default=0, help='report-only模式下每个表格最大预览列数（0表示不限制）')
    
    args = parser.parse_args()
    
    # 楠岃瘉杈撳叆鐩綍
    if not os.path.isdir(args.input):
        print_error(f"杈撳叆鐩綍涓嶅瓨鍦? {args.input}")
        sys.exit(1)

    if args.report_only:
        success = run_report_only_mode(args)
        sys.exit(0 if success else 1)
    
    # Parse chain list.
    chains = [c.strip().upper() for c in args.chains.split(',')] if args.chains else []
    
    # Create generator instance.
    generator = StandaloneHeatmapGenerator(
        input_dir=args.input,
        output_dir=args.output,
        interactive=args.interactive,
        cdr3_col=args.cdr3_col,
        copy_col=args.copy_col,
        mode=args.mode,
        chains=chains,
        title=args.title,
        show_values=not args.no_values,
        web_report=args.web_report,
        report_scan_path=args.report_scan_path
    )
    
    success = generator.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()


