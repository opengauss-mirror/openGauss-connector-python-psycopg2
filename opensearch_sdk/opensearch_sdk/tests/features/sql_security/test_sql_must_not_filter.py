#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
其他功能测试 - SQL Must Not 过滤

功能说明：
- 测试使用 WHERE 子句实现 must_not（完全替换 Python 层过滤）
- 验证在 search() 方法中通过修改 SQL 构建逻辑
- 将 must_not 条件直接转换为 WHERE NOT LIKE
- 避免 Python 层过滤，提高性能
- 更符合 SQL 优化原则

注意：本测试需要临时修改 search_ops.py，仅用于验证概念

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.other_features.test_sql_must_not_filter -v
    python opensearch_sdk/tests/other_features/test_sql_must_not_filter.py
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearch_sdk import OpenGauss
