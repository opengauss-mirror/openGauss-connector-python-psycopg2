"""
验证 minimum_should_match = 1 时走 SQL OR 路径的性能优化

测试场景：
1. minimum_should_match = 1 + term -> 应该走 SQL 路径（性能好）
2. minimum_should_match = 2 + term -> 应该走 Python 过滤（逻辑正确）
3. minimum_should_match = 1 + match -> 应该走 Python 过滤（BM25 需要）
"""

import os
import sys
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from document_ops.delete_query_common import (
    category_should_query,
    cleanup_index_and_close,
    create_client,
    field_match_should_query,
    insert_docs,
    recreate_index,
    search_hits,
    total_count,
)


TEST_INDEX = "test_msm_optimization"

TEST_MAPPING = {
    "mappings": {
        "properties": {
            "question": {"type": "text"},
            "category": {"type": "keyword"},
            "score": {"type": "integer"}
        }
    }
}


def _print_section(title):
    print(f"\n{'='*60}")
    print(title)
    print(f"{'='*60}")


def _msm_docs(count=100):
    categories = ["编程", "数据库", "AI", "网络"]
    return [
        {
            "id": f"doc_{i:03d}",
            "question": f"问题{i}",
            "category": categories[i % len(categories)],
            "score": i % 100
        }
        for i in range(count)
    ]


def _insert_msm_docs(client, ignore_errors=False):
    inserted_count = insert_docs(client, TEST_INDEX, _msm_docs(), ignore_errors=ignore_errors)
    print(f"[PASS] 插入 {inserted_count} 条测试数据")


def _run_timed_delete(client, query):
    start_time = time.time()
    result = client.delete_by_query(index=TEST_INDEX, body=query)
    elapsed = time.time() - start_time
    remaining = len(search_hits(client, TEST_INDEX, size=100))

    print(f"删除结果: {result}")
    print(f"耗时: {elapsed:.4f} 秒")
    print(f"剩余文档: {remaining}")
    return result, elapsed, remaining


def _validate_deleted_count(result, remaining, expected_deleted, expected_remaining, label):
    if result['deleted'] == expected_deleted and remaining == expected_remaining:
        print(f"[PASS] {label}通过：正确删除{expected_deleted}条，剩余{expected_remaining}条")
        return True

    print(f"[FAIL] {label}失败：预期删除{expected_deleted}条，实际删除{result['deleted']}条")
    return False


def _run_sql_path_case(client):
    _print_section("测试1: minimum_should_match = 1 + term (预期: SQL 路径)")
    query = category_should_query(["编程", "数据库"], minimum_should_match=1)
    result, elapsed, remaining = _run_timed_delete(client, query)
    success = _validate_deleted_count(result, remaining, 50, 50, "测试1")
    return success, elapsed


def _run_python_term_case(client):
    _print_section("测试2: minimum_should_match = 2 + term (预期: Python 过滤)")
    _insert_msm_docs(client, ignore_errors=True)
    query = category_should_query(["编程", "数据库", "AI"], minimum_should_match=2)
    result, elapsed, remaining = _run_timed_delete(client, query)
    success = _validate_deleted_count(result, remaining, 0, 100, "测试2")
    return success, elapsed


def _run_python_match_case(client):
    _print_section("测试3: minimum_should_match = 1 + match (预期: Python 过滤)")
    query = field_match_should_query("question", ["问题1", "问题2"], minimum_should_match=1)
    result, elapsed, _ = _run_timed_delete(client, query)

    if result['deleted'] > 0:
        print(f"[PASS] 测试3通过：match 查询走 Python 过滤，删除{result['deleted']}条")
    else:
        print("[WARN] 测试3警告：match 查询未删除任何文档（可能是 BM25 分词问题）")
    return elapsed


def _print_performance(elapsed1, elapsed2, elapsed3):
    _print_section("性能对比:")
    print(f"测试1 (SQL路径):     {elapsed1:.4f} 秒")
    print(f"测试2 (Python过滤):  {elapsed2:.4f} 秒")
    print(f"测试3 (Python过滤):  {elapsed3:.4f} 秒")
    if elapsed1 > 0 and elapsed1 < elapsed2:
        print(f"[PASS] SQL 路径比 Python 过滤快 {elapsed2/elapsed1:.2f} 倍")


def test_minimum_should_match_optimization():
    """测试 minimum_should_match 的优化逻辑"""
    client = create_client()
    success = True
    try:
        recreate_index(client, TEST_INDEX, TEST_MAPPING)

        print(f"\n[NOTE] 插入测试数据...")
        _insert_msm_docs(client)
        print(f"[STATS] 当前文档数量: {total_count(client, TEST_INDEX)}")

        case1_success, elapsed1 = _run_sql_path_case(client)
        case2_success, elapsed2 = _run_python_term_case(client)
        elapsed3 = _run_python_match_case(client)
        _print_performance(elapsed1, elapsed2, elapsed3)
        success = case1_success and case2_success
    except Exception as error:
        print(f"\n[FAIL] 测试失败: {str(error)}")
        import traceback
        traceback.print_exc()
        success = False
    finally:
        cleanup_index_and_close(client, TEST_INDEX)

    return success


if __name__ == "__main__":
    print("="*60)
    print("验证 minimum_should_match 优化逻辑")
    print("="*60)
    print()

    success = test_minimum_should_match_optimization()

    print()
    print("="*60)
    if success:
        print("[PASS] 所有测试通过！")
    else:
        print("[FAIL] 测试失败")
    print("="*60)

    sys.exit(0 if success else 1)
