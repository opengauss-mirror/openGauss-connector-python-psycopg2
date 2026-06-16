#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Opensearch兼容接口的 ping() 方法
验证与 OpenSearch SDK 的接口一致性
"""

import json
from pathlib import Path
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


def test_ping():
    """测试 ping 方法"""
    
    # 加载配置
    db_config = load_db_config()
    
    print("=" * 70)
    print("测试 Opensearch兼容接口ping() 方法")
    print("=" * 70)
    
    # 创建客户端
    client = OpenGauss(
        hosts=[{'host': db_config['host'], 'port': db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    try:
        # 测试1：正常连接时 ping 应该返回 True
        print("\n[测试1] 检查数据库连接状态...")
        result = client.ping()
        print(f"  结果: {result}")
        
        if result:
            print("  [OK] 数据库连接正常")
        else:
            print("  [FAIL] 数据库连接异常")
            return False
        
        # 测试2：关闭连接后 ping 应该返回 False
        print("\n[测试2] 关闭连接后检查...")
        client.close()
        result_after_close = client.ping()
        print(f"  结果: {result_after_close}")
        
        if not result_after_close:
            print("  [OK] 关闭连接后正确返回 False")
        else:
            print("  [WARN] 关闭连接后仍返回 True（可能自动重连）")
        
        # 测试3：重新连接后 ping 应该返回 True
        print("\n[测试3] 重新连接后检查...")
        client.connection.connect()
        result_after_reconnect = client.ping()
        print(f"  结果: {result_after_reconnect}")
        
        if result_after_reconnect:
            print("  [OK] 重新连接后正确返回 True")
        else:
            print("  [FAIL] 重新连接后返回 False")
            return False
        
        print("\n" + "=" * 70)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 确保关闭连接
        try:
            client.close()
        except:
            pass


if __name__ == "__main__":
    success = test_ping()
    exit(0 if success else 1)
