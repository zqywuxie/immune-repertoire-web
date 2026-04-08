#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细测试样本名提取功能
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auto_heatmap_service import AutoHeatmapService


def test_extract_sample_name_from_chain_file():
    """详细测试 _extract_sample_name_from_chain_file 方法"""
    service = AutoHeatmapService()

    # 测试文件名
    test_cases = [
        {
            "input": "SD_01_CD8_0127__TRA.csv.gz",
            "expected": "SD_01_CD8_0127",
            "description": "正常链后缀文件（双下划线）",
        },
        {
            "input": "Patient_A__IGH.csv.gz",
            "expected": "Patient_A",
            "description": "正常链后缀文件（双下划线）",
        },
        {
            "input": "Sample_001_TRA.csv",
            "expected": "Sample_001",
            "description": "单下划线分隔",
        },
        {
            "input": "artificial_peps",
            "expected": None,
            "description": "没有链后缀的文件名",
        },
        {
            "input": "SD_01_CD8_0127.csv",
            "expected": None,
            "description": "没有链后缀的文件名",
        },
    ]

    print("测试 _extract_sample_name_from_chain_file 方法：")
    print("=" * 80)

    for i, case in enumerate(test_cases, 1):
        result = service._extract_sample_name_from_chain_file(case["input"])
        status = "✓ 通过" if result == case["expected"] else "✗ 失败"
        print(f"测试 {i}: {case['description']}")
        print(f"  输入: {case['input']}")
        print(f"  期望: {case['expected']}")
        print(f"  实际: {result}")
        print(f"  状态: {status}")
        print()


def test_extract_chain_from_filename():
    """测试 _extract_chain_from_filename 方法"""
    service = AutoHeatmapService()

    test_cases = [
        {
            "input": "SD_01_CD8_0127__TRA.csv.gz",
            "expected": "TRA",
            "description": "TRA链文件",
        },
        {
            "input": "Patient_A__IGH.csv.gz",
            "expected": "IGH",
            "description": "IGH链文件",
        },
        {
            "input": "Sample_001_TRB.csv",
            "expected": "TRB",
            "description": "TRB链文件（单下划线）",
        },
        {"input": "artificial_peps", "expected": None, "description": "没有链后缀"},
    ]

    print("测试 _extract_chain_from_filename 方法：")
    print("=" * 80)

    for i, case in enumerate(test_cases, 1):
        result = service._extract_chain_from_filename(case["input"])
        status = "✓ 通过" if result == case["expected"] else "✗ 失败"
        print(f"测试 {i}: {case['description']}")
        print(f"  输入: {case['input']}")
        print(f"  期望: {case['expected']}")
        print(f"  实际: {result}")
        print(f"  状态: {status}")
        print()


def test_is_data_file():
    """测试 _is_data_file 方法"""
    service = AutoHeatmapService()

    test_cases = [
        {
            "input": "SD_01_CD8_0127__TRA.csv.gz",
            "expected": True,
            "description": "CSV.GZ文件",
        },
        {"input": "Patient_A__IGH.csv", "expected": True, "description": "CSV文件"},
        {"input": "data.txt", "expected": True, "description": "TXT文件"},
        {"input": "report.pdf", "expected": False, "description": "PDF文件"},
        {
            "input": "artificial_peps",
            "expected": False,
            "description": "没有扩展名的文件",
        },
    ]

    print("测试 _is_data_file 方法：")
    print("=" * 80)

    for i, case in enumerate(test_cases, 1):
        result = service._is_data_file(case["input"])
        status = "✓ 通过" if result == case["expected"] else "✗ 失败"
        print(f"测试 {i}: {case['description']}")
        print(f"  输入: {case['input']}")
        print(f"  期望: {case['expected']}")
        print(f"  实际: {result}")
        print(f"  状态: {status}")
        print()


if __name__ == "__main__":
    test_extract_sample_name_from_chain_file()
    print("\n")
    test_extract_chain_from_filename()
    print("\n")
    test_is_data_file()
