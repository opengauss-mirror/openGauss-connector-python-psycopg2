#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Opensearch兼容接口测试配置常量

Python 命令会自动检测，优先使用 python3，如果不存在则使用 python。
也可以通过环境变量 PYTHON_CMD 手动指定。
"""

import os
import shutil


# ==================== Python 解释器配置 ====================

def _detect_python_cmd():
    """
    智能检测 Python 命令
    
    优先级：
    1. 环境变量 PYTHON_CMD（如果设置）
    2. 根据操作系统选择：
       - Windows: python
       - Linux/macOS: python3（如果存在），否则 python
    
    Returns:
        str: Python 命令名称
    """
    import sys
    
    # 1. 检查环境变量
    env_cmd = os.environ.get('PYTHON_CMD')
    if env_cmd:
        return env_cmd
    
    # 2. 根据操作系统选择
    if sys.platform == 'win32':
        # Windows 使用 python
        return 'python'
    else:
        # Linux/macOS 优先尝试 python3
        if shutil.which('python3'):
            return 'python3'
        return 'python'


PYTHON_CMD = _detect_python_cmd()


# ==================== 项目路径配置 ====================

# 项目根目录（相对于此文件的位置）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 测试目录
TESTS_DIR = os.path.join(PROJECT_ROOT, 'opensearch_sdk', 'tests')

# 报告目录
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

# 临时文件目录
TMP_DIR = os.path.join(PROJECT_ROOT, 'tmp')


# ==================== 数据库配置 ====================

# 数据库配置文件路径
DB_CONFIG_FILE = os.path.join(PROJECT_ROOT, 'db_config.json')
TESTS_DB_CONFIG_FILE = os.path.join(TESTS_DIR, 'db_config.json')


# ==================== 测试配置 ====================

# 测试超时时间（秒）
TEST_TIMEOUT = 300

# 测试模块列表
TEST_MODULES = [
    'connection',      # 数据库连接测试
    'utils',           # 工具函数测试
    'index_ops',       # 索引操作测试
    'document_ops',    # 文档 CRUD 测试
    'search_ops',      # 搜索操作测试
    'bool_query',      # Bool 查询测试
    'vector_search',   # 向量搜索测试
    'bm25_search',     # BM25 搜索测试
    'match_phrase',    # 短语匹配测试
    'sql_trace',       # SQL 追踪测试
    'features',        # 功能特性测试
]

# 根目录下的测试文件
ROOT_TEST_FILES = [
    'test_basic_client.py',
]


# ==================== 其他配置 ====================

# 日志级别
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# 是否启用详细输出
VERBOSE = os.environ.get('VERBOSE', 'false').lower() == 'true'
