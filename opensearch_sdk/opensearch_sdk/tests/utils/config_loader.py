#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试工具包 - 配置加载模块

提供统一的配置文件查找和加载功能
"""

import os
import json


def find_db_config(start_dir=None):
    """
    从指定目录开始向上查找 db_config.json 文件
    
    查找策略：
    1. 从 start_dir 开始
    2. 逐层向上查找
    3. 最多查找 10 层，直到找到配置文件或到达文件系统根目录
    4. 优先使用项目根目录的 db_config.json
    
    Args:
        start_dir: 起始查找目录，默认为调用者所在目录
        
    Returns:
        dict: 数据库配置字典
        
    Raises:
        FileNotFoundError: 如果未找到配置文件
    """
    if start_dir is None:
        # 获取调用者的目录
        import inspect
        frame = inspect.currentframe().f_back.f_back
        caller_file = frame.f_globals.get('__file__')
        if caller_file:
            start_dir = os.path.dirname(os.path.abspath(caller_file))
        else:
            start_dir = os.path.dirname(os.path.abspath(__file__))
    
    current_dir = start_dir
    max_levels = 10
    
    for _ in range(max_levels):
        config_path = os.path.join(current_dir, 'db_config.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 向上一级目录
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            # 已到达文件系统根目录
            break
        current_dir = parent_dir
    
    raise FileNotFoundError(
        f"未找到 db_config.json 文件\n"
        f"查找起始点：{start_dir}\n"
        f"请确保 db_config.json 存在于项目根目录或测试目录中"
    )


def load_db_config():
    """
    加载数据库配置的便捷函数
    
    自动查找并加载 db_config.json，支持以下查找顺序：
    1. 当前文件所在目录
    2. 上级目录（逐层查找）
    3. tests 目录
    
    Returns:
        dict: 数据库配置，包含 host, port, database, user, password 等字段
        
    Example:
        >>> from utils.config_loader import load_db_config
        >>> config = load_db_config()
        >>> print(config['host'])
    """
    return find_db_config()


if __name__ == '__main__':
    # 测试配置加载
    try:
        config = load_db_config()
        print("[OK] 成功加载数据库配置")
        print(f"   Host: {config.get('host', 'N/A')}:{config.get('port', 'N/A')}")
        print(f"   Database: {config.get('database', 'N/A')}")
        print(f"   User: {config.get('user', 'N/A')}")
    except FileNotFoundError as e:
        print(f"[FAIL] 配置加载失败:\n{e}")
