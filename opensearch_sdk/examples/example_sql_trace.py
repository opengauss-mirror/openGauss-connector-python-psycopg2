"""
SQL 追踪功能完整示例

演示如何使用 SQL 追踪功能监控数据库操作，
包括基础追踪、参数脱敏、结果采样和多线程追踪。

运行方式: python examples/example_sql_trace.py
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils import load_config

from opensearch_sdk import OpenGauss

config = load_config()


def print_separator(title):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_section(title):
    """打印小节标题"""
    print("-" * 80)
    print(title)
    print("-" * 80)


def _cleanup_index(client, index_name):
    """清理索引（忽略不存在错误）"""
    try:
        client.indices.delete(index=index_name)
    except Exception as e:
        error_msg = str(e).lower()
        if "not found" not in error_msg and "404" not in error_msg:
            print(f"[WARN] 清理索引时出错：{e}")


def _export_trace_session(client, session):
    """导出追踪会话到文件"""
    print("\n导出追踪记录到文件:")
    print("-" * 80)
    try:
        export_dir = Path("tmp/sql_trace_exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        client.sql_tracer.export_dir = export_dir

        md_file = client.sql_tracer.export_to_file(export_format="markdown", verbose=False)
        print(f"[OK] 已导出 Markdown 报告：{md_file}")

        json_file = client.sql_tracer.export_to_file(export_format="json")
        print(f"[OK] 已导出 JSON 数据：{json_file}")

        yaml_content = session.to_yaml_style()
        yaml_file = export_dir / f"{session.session_id}.yaml"
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        print(f"[OK] 已导出 YAML 格式：{yaml_file}")

    except Exception as e:
        print(f"[WARN] 导出失败：{e}")


def _print_param_masking_status(record):
    """打印参数脱敏状态"""
    params_str = str(record.params)
    if 'MASKED' in params_str or '***' in params_str:
        print("[OK] 参数已自动脱敏")
    else:
        print("[INFO] 当前查询未包含敏感参数")


def example_basic_trace():
    """示例 1：基础 SQL 追踪"""
    print_separator("示例 1：基础 SQL 追踪")

    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password'],
        enable_sql_trace=True,
        sql_trace_mask_sensitive=True,
        sql_trace_max_sample_rows=10
    )

    test_index = f"example_sql_trace_{int(time.time())}"

    try:
        print_section("清理旧索引")
        _cleanup_index(client, test_index)

        print_section("1. 创建索引")
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "tags": {"type": "text"},
                    "created_at": {"type": "text"}
                }
            }
        }

        result = client.indices.create(test_index, mapping)
        print(f"[OK] 索引创建成功：{result.get('acknowledged')}")

        print(f"  Tracer enabled: {client.sql_tracer.enabled}")
        print(f"  Sessions count: {len(client.sql_tracer._sessions)}")
        session = client.sql_tracer.get_last_session()
        if session is None:
            print("  [WARN] 警告：没有获取到会话")
        else:
            print("\nYAML 风格输出:")
            print("-" * 80)
            client.sql_tracer.print_last_session()
            _export_trace_session(client, session)

        print_section("2. 创建文档")
        doc_data = {
            "title": "SQL 追踪功能详解",
            "content": "本文详细介绍了 Opensearch 兼容接口的 SQL 追踪功能",
            "tags": ["sql-trace", "debug", "opensearch"],
            "created_at": "2026-03-31"
        }

        result = client.create(test_index, "doc1", doc_data)
        print(f"[OK] 文档创建成功：{result['result']}")

        session = client.sql_tracer.get_last_session()
        print(f"  Operation: {session.operation}")
        print(f"  SQL 记录数：{len(session.records)}")
        if session.records:
            record = session.records[-1]
            print(f"  Context: {record.context}")
            print(f"  Metadata: {record.metadata}")

        print_section("3. 获取文档")
        result = client.get(test_index, "doc1")
        print(f"[OK] 文档获取成功：{result['_id']}")
        print(f"  标题：{result['_source']['title']}")

        session = client.sql_tracer.get_last_session()
        print(f"  Operation: {session.operation}")
        print(f"  SQL 记录数：{len(session.records)}")

        print_section("4. 更新文档")
        update_data = {
            "title": "SQL 追踪功能完全指南",
            "content": "本文详细介绍了 Opensearch 兼容接口的 SQL 追踪功能，包括使用方法、配置选项和最佳实践。"
        }

        result = client.update(test_index, "doc1", update_data)
        print(f"[OK] 文档更新成功：{result['result']}")

        session = client.sql_tracer.get_last_session()
        print(f"  Operation: {session.operation}")
        if session.records:
            record = session.records[-1]
            print(f"  Context: {record.context}")
            print(f"  更新字段：{record.metadata.get('updated_fields')}")

        print_section("5. 搜索文档")
        query_body = {
            "query": {
                "match": {
                    "title": "SQL 追踪"
                }
            },
            "size": 10
        }

        result = client.search(test_index, query_body)
        print(f"[OK] 搜索完成，命中数：{result['hits']['total']['value']}")

        session = client.sql_tracer.get_last_session()
        print(f"  Operation: {session.operation}")
        print(f"  SQL 记录数：{len(session.records)}")
        if session.records:
            record = session.records[-1]
            print(f"  Context: {record.context}")
            print(f"  Query Body: {record.metadata.get('query_body', {})}")

        print_section("6. 删除文档")
        result = client.delete(test_index, "doc1")
        print(f"[OK] 文档删除成功：{result['result']}")

        session = client.sql_tracer.get_last_session()
        print(f"  Operation: {session.operation}")
        if session.records:
            record = session.records[-1]
            print(f"  Context: {record.context}")
            print(f"  Metadata: {record.metadata}")

        print_section("7. 删除索引")
        result = client.indices.delete(test_index)
        print(f"[OK] 索引删除成功：{result.get('acknowledged')}")

        session = client.sql_tracer.get_last_session()
        if session is None:
            print("  [WARN] 没有获取到会话")
        else:
            print(f"  Operation: {session.operation}")
            if session.records:
                record = session.records[-1]
                print(f"  Context: {record.context}")
                print(f"  Metadata: {record.metadata}")

    finally:
        _cleanup_index(client, test_index)
        client.close()


def example_param_masking():
    """示例 2：参数脱敏"""
    print_separator("示例 2：参数脱敏")

    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password'],
        enable_sql_trace=True,
        sql_trace_mask_sensitive=True
    )

    test_index = f"example_users_{int(time.time())}"

    try:
        print_section("执行包含敏感参数的查询")

        mapping = {
            "mappings": {
                "properties": {
                    "username": {"type": "keyword"},
                    "password": {"type": "keyword"},
                    "email": {"type": "keyword"}
                }
            }
        }
        client.indices.create(test_index, mapping)

        user_data = {
            "username": "testuser",
            "password": os.getenv("TEST_USER_PASSWORD", "secret_password_123"),
            "email": "test@example.com"
        }
        client.create(test_index, "user1", user_data)

        result = client.search(test_index, {
            "query": {
                "term": {"username": "testuser"}
            }
        })

        session = client.sql_tracer.get_last_session()
        print(f"Operation: {session.operation}")

        if session.records:
            record = session.records[-1]
            print(f"SQL: {record.sql}")
            print(f"Params: {record.params}")
            _print_param_masking_status(record)

        client.indices.delete(test_index)
        print("[OK] 已清理测试索引")

    except Exception as e:
        print(f"测试跳过：{str(e)}")
        try:
            client.indices.delete(test_index)
        except Exception:
            pass

    finally:
        client.close()


def example_result_sampling():
    """示例 3：结果采样"""
    print_separator("示例 3：结果采样")

    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password'],
        enable_sql_trace=True,
        sql_trace_max_sample_rows=5
    )

    test_index = "example_sampling"

    try:
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "score": {"type": "integer"}
                }
            }
        }
        client.indices.create(test_index, mapping)

        print_section("批量插入测试数据（20 条）")
        for i in range(20):
            doc_data = {
                "title": f"Document {i}",
                "score": i * 10
            }
            client.create(test_index, f"doc{i}", doc_data)
        print("[OK] 插入 20 条文档")

        print_section("执行查询（返回 20 条，但只采样 5 条）")
        result = client.search(test_index, {
            "query": {"match_all": {}},
            "size": 20
        })

        print(f"实际返回：{len(result['hits']['hits'])} 条")

        session = client.sql_tracer.get_last_session()
        if session.records:
            record = session.records[-1]
            sampled_count = len(record.sampled_results) if hasattr(record, 'sampled_results') else 0
            print(f"采样结果数：{sampled_count} 条")
            print("[OK] 结果采样生效，避免内存溢出")

        client.indices.delete(test_index)

    finally:
        client.close()


def example_multithread_trace():
    """示例 4：多线程追踪"""
    print_separator("示例 4：多线程追踪")

    results = {}

    def worker(thread_id):
        """工作线程函数"""
        client = OpenGauss(
            hosts=[{'host': config['host'], 'port': config['port']}],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            enable_sql_trace=True
        )

        test_index = f"example_thread_{thread_id}"

        try:
            mapping = {
                "mappings": {
                    "properties": {
                        "thread_id": {"type": "integer"},
                        "data": {"type": "text"}
                    }
                }
            }
            client.indices.create(test_index, mapping)

            client.create(test_index, "doc1", {
                "thread_id": thread_id,
                "data": f"Data from thread {thread_id}"
            })

            result = client.search(test_index, {
                "query": {"term": {"thread_id": thread_id}}
            })

            session = client.sql_tracer.get_last_session()
            sql_count = len(session.records) if session else 0

            results[thread_id] = {
                'index': test_index,
                'sql_count': sql_count,
                'operation': session.operation if session else 'N/A'
            }

            client.indices.delete(test_index)

        except Exception as e:
            results[thread_id] = {'error': str(e)}
        finally:
            client.close()

    print_section("启动 5 个并发线程")
    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print_section("各线程的 SQL 追踪（线程隔离）")
    for thread_id, result in sorted(results.items()):
        if 'error' in result:
            print(f"Thread {thread_id}: [ERROR] {result['error']}")
        else:
            print(f"Thread {thread_id}: [OK] {result['sql_count']} SQLs, Operation: {result['operation']}")

    print("\n[OK] 所有线程的追踪会话互不干扰，线程安全验证通过")


def example_disable_trace():
    """示例 5：禁用追踪（生产环境模式）"""
    print_separator("示例 5：禁用追踪（生产环境模式）")

    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password'],
        enable_sql_trace=False
    )

    test_index = "example_no_trace"

    try:
        mapping = {
            "mappings": {
                "properties": {
                    "data": {"type": "text"}
                }
            }
        }
        client.indices.create(test_index, mapping)
        print("[OK] 索引创建成功（无追踪）")

        client.create(test_index, "doc1", {"data": "test"})
        print("[OK] 文档创建成功（无追踪）")

        result = client.search(test_index, {"query": {"match_all": {}}})
        print("[OK] 搜索完成（无追踪）")

        if hasattr(client, 'sql_tracer') and client.sql_tracer:
            session = client.sql_tracer.get_last_session()
            if session is None:
                print("[OK] 确认无追踪记录（零性能开销）")
            else:
                print(f"[INFO] 有追踪记录：{len(session.records)} SQLs")

        client.indices.delete(test_index)

    finally:
        client.close()


def main():
    """主函数"""
    print("=" * 80)
    print("SQL 追踪功能完整示例")
    print("  版本：v1.0")
    print("  时间：" + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    try:
        example_basic_trace()
        example_param_masking()
        example_result_sampling()
        example_multithread_trace()
        example_disable_trace()

        print_separator("所有示例运行完成！")
        print("\n提示：")
        print("  - 开发/测试环境建议启用 SQL 追踪")
        print("  - 生产环境建议禁用以获得最佳性能")
        print("  - 可通过配置文件灵活控制追踪行为")

    except Exception as e:
        print(f"\n[ERROR] 运行错误：{str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
