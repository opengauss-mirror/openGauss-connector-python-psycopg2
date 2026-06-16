"""
验证 delete_by_query 对 term 条件的支持

测试场景：
1. bool.should + term + minimum_should_match = 1
2. 验证数据是否真正被删除
"""

import json
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from document_ops.delete_query_common import (
    category_should_query,
    cleanup_index_and_close,
    create_client,
    insert_docs,
    recreate_index,
    search_hits,
    total_count,
)


TEST_INDEX = "test_delete_term_validation"

TEST_MAPPING = {
    "mappings": {
        "properties": {
            "question": {"type": "text"},
            "answer": {"type": "text"},
            "category": {"type": "keyword"}
        }
    }
}

TEST_DOCS = [
    {"id": "doc1", "question": "什么是Python", "answer": "Python是一种编程语言", "category": "编程"},
    {"id": "doc2", "question": "什么是Java", "answer": "Java是一种编程语言", "category": "编程"},
    {"id": "doc3", "question": "什么是数据库", "answer": "数据库是数据存储系统", "category": "数据库"},
    {"id": "doc4", "question": "如何使用MySQL", "answer": "MySQL是关系型数据库", "category": "数据库"},
    {"id": "doc5", "question": "什么是人工智能", "answer": "AI是模拟人类智能的技术", "category": "AI"},
]


def _print_query(query):
    print(f"\n[SEARCH] 执行删除查询:")
    print(json.dumps(query, indent=2, ensure_ascii=False))


def _insert_test_docs(client, ignore_errors=False):
    inserted_count = insert_docs(client, TEST_INDEX, TEST_DOCS, ignore_errors=ignore_errors)
    print(f"[PASS] 插入 {inserted_count} 条测试数据")


def _validate_remaining_ai_doc(remaining_docs):
    expected_remaining = 1
    actual_remaining = len(remaining_docs)
    if actual_remaining != expected_remaining:
        print(f"\n[FAIL] 验证失败！预期剩余 {expected_remaining} 条，实际剩余 {actual_remaining} 条")
        return False

    remaining_category = remaining_docs[0]['_source'].get('category')
    if remaining_category != "AI":
        print(f"[FAIL] 剩余文档分类错误: {remaining_category} (预期: AI)")
        return False

    print(f"\n[PASS] 验证通过！预期剩余 {expected_remaining} 条，实际剩余 {actual_remaining} 条")
    print(f"[PASS] 剩余文档分类正确: {remaining_category}")
    return True


def _run_multi_term_delete(client):
    delete_query = category_should_query(["编程", "数据库"], minimum_should_match=1)
    _print_query(delete_query)

    result = client.delete_by_query(index=TEST_INDEX, body=delete_query)
    print(f"\n[RESULT] 删除结果: {result}")

    remaining_docs = search_hits(client, TEST_INDEX, size=10)
    print(f"[STATS] 剩余文档数量: {len(remaining_docs)}")
    print(f"\n[INFO] 剩余文档列表:")
    for hit in remaining_docs:
        doc = hit['_source']
        print(f"  - ID: {hit['_id']}, category: {doc.get('category')}")

    return _validate_remaining_ai_doc(remaining_docs)


def _run_single_term_delete(client):
    print(f"\n{'='*60}")
    print("测试2: 单个 term 条件删除")
    print(f"{'='*60}")

    _insert_test_docs(client, ignore_errors=True)
    single_term_query = category_should_query(["AI"], minimum_should_match=1)

    print("执行删除查询: category = 'AI'")
    result = client.delete_by_query(index=TEST_INDEX, body=single_term_query)
    print(f"删除结果: {result}")

    final_count = len(search_hits(client, TEST_INDEX, size=10))
    print(f"最终文档数量: {final_count}")
    if result['deleted'] > 0:
        print(f"[PASS] 单个 term 条件删除成功，删除了 {result['deleted']} 条文档")
        return True

    print("[FAIL] 单个 term 条件删除失败，deleted = 0")
    return False


def test_delete_by_query_with_term():
    """测试 delete_by_query 处理 term 条件"""
    client = create_client()
    success = True
    try:
        recreate_index(client, TEST_INDEX, TEST_MAPPING)
        _insert_test_docs(client)
        print(f"[STATS] 当前文档数量: {total_count(client, TEST_INDEX)}")

        success = _run_multi_term_delete(client) and success
        success = _run_single_term_delete(client) and success
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
    print("验证 delete_by_query 对 term 条件的支持")
    print("="*60)
    print()

    success = test_delete_by_query_with_term()

    print()
    print("="*60)
    if success:
        print("[PASS] 所有测试通过！")
    else:
        print("[FAIL] 测试失败")
    print("="*60)

    sys.exit(0 if success else 1)
