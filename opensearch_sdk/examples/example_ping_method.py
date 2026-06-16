#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Opensearch兼容接口ping() 方法使用示例

演示如何使用 ping() 方法进行健康检查，与 OpenSearch SDK 保持接口一致
"""

from utils import load_config

from opensearch_sdk import OpenGauss

config = load_config()


def example_basic_ping():
    """基本用法：检查数据库连接状态"""

    print("=" * 70)
    print("示例1：基本 ping 用法")
    print("=" * 70)
    # 创建客户端
    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password']
    )

    try:
        # 使用 ping 检查连接
        if client.ping():
            print("[OK] 数据库连接正常，可以执行操作")
        else:
            print("[ERROR] 数据库连接异常，请检查配置")
            return False

    finally:
        client.close()

    return True


def _reconnect_if_needed(client):
    """检查连接并尝试重连"""
    is_connected = client.ping()
    status = "[OK]" if is_connected else "[FAIL]"

    if is_connected:
        return True

    print(f"  {status} 连接状态: 异常")
    print("  [WARN] 检测到连接断开，尝试重连...")
    try:
        client.connection.connect()
        return True
    except Exception as e:
        print(f"  [ERROR] 重连失败: {e}")
        return False


def example_health_check_loop():
    """循环健康检查：监控数据库连接状态"""

    print("\n" + "=" * 70)
    print("示例2：循环健康检查")
    print("=" * 70)
    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password']
    )

    try:
        for i in range(3):
            status = "[OK]" if client.ping() else "[FAIL]"
            print(f"  第 {i+1} 次检查: {status} 连接状态: {'正常' if client.ping() else '异常'}")
            _reconnect_if_needed(client)
    finally:
        client.close()


def example_with_error_handling():
    """带错误处理的 ping 用法"""

    print("\n" + "=" * 70)
    print("示例3：带错误处理的健康检查")
    print("=" * 70)

    max_retries = 3

    for retry_count in range(max_retries):
        try:
            client = OpenGauss(
                hosts=[{'host': config['host'], 'port': config['port']}],
                database=config['database'],
                user=config['user'],
                password=config['password']
            )

            if client.ping():
                print(f"[OK] 第 {retry_count + 1} 次尝试：连接成功")
                client.close()
                return True

            print(f"[WARN] 第 {retry_count + 1} 次尝试：连接失败")
            client.close()

        except Exception as e:
            print(f"[ERROR] 第 {retry_count + 1} 次尝试：异常 - {e}")

        if retry_count < max_retries - 1:
            print("  等待 2 秒后重试...")
            import time
            time.sleep(2)

    print(f"[FAIL] 达到最大重试次数 ({max_retries})，连接失败")
    return False


def example_opensearch_compatibility():
    """OpenSearch 兼容性示例"""

    print("\n" + "=" * 70)
    print("示例4：OpenSearch 兼容用法")
    print("=" * 70)

    print("""
# OpenSearch SDK 的用法:
from opensearchpy import OpenSearch

client = OpenSearch(...)
if client.ping():
    print("Opensearch正在运行中")
else:
    print("Opensearch未连接")

# Opensearch兼容接口的用法（完全一致）:
from opensearch_sdk import OpenGauss

client = OpenGauss(...)
if client.ping():
    print("Opensearch正在运行中")
else:
    print("Opensearch未连接")
    """)

    print("[INFO] Opensearch兼容接口的 ping() 方法与 OpenSearch SDK 完全兼容")
    print("[INFO] 可以轻松从 OpenSearch 迁移到 Opensearch")


if __name__ == "__main__":
    print("Opensearch兼容接口ping() 方法使用示例\n")
    print("注意：以下示例需要有效的数据库连接才能正常运行\n")

    # 示例1：基本用法
    try:
        example_basic_ping()
    except Exception as e:
        print(f"[SKIP] 示例1跳过（数据库不可达）: {e}\n")

    # 示例2：循环健康检查
    try:
        example_health_check_loop()
    except Exception as e:
        print(f"[SKIP] 示例2跳过（数据库不可达）: {e}\n")

    # 示例3：带错误处理
    try:
        example_with_error_handling()
    except Exception as e:
        print(f"[SKIP] 示例3跳过（数据库不可达）: {e}\n")

    # 示例4：兼容性说明（不需要数据库连接）
    example_opensearch_compatibility()

    print("\n" + "=" * 70)
    print("示例演示完成")
    print("=" * 70)
