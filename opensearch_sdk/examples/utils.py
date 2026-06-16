"""
Example 共享工具模块

提供统一的数据库配置加载功能，避免各 example 重复实现。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    加载数据库配置。

    默认从 ``opensearch_sdk/db_config.json`` 读取（相对于本文件向上 1 级），
    也支持传入自定义路径。

    Returns:
        Dict 包含 ``host``, ``port``, ``database``, ``dbname``,
        ``user``, ``password`` 等键。其中 ``database`` 和 ``dbname``
        均为同一值，方便不同 Client 按需取用。
    """
    if config_path is None:
        config_path = str(Path(__file__).resolve().parent.parent / 'db_config.json')

    p = Path(config_path)
    if not p.exists():
        print(f"[ERROR] 数据库配置文件不存在：{p}")
        print("请确认 opensearch_sdk/db_config.json 存在且配置正确。")
        print("参考格式：")
        print(json.dumps({
            "host": "127.0.0.1",
            "port": 5432,
            "database": "your_db",
            "user": "your_user",
            "password": "your_password"
        }, indent=4, ensure_ascii=False))
        sys.exit(1)

    with open(p, 'r', encoding='utf-8') as f:
        config: Dict[str, Any] = json.load(f)

    # 确保 database 和 dbname 两个键都存在（值相同）
    if 'database' in config and 'dbname' not in config:
        config['dbname'] = config['database']
    elif 'dbname' in config and 'database' not in config:
        config['database'] = config['dbname']

    return config
